"""M5 camera/capture/ML journal recovery, fault injection and HTTP tests."""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m5_fixtures import media_fixture,capture,scores
from services.camera_adapter import CameraOwner,CameraUnavailable,CameraStale,Frame
from services.capture_service import CaptureService
from services.local_ml_service import LocalMLService
from services.model_contract import ModelManifest,ClassificationPolicy
from services.media_repository import MediaRepository
from services.control_runtime import install_simulation_gateway
from sim.media_fakes import synthetic_jpeg,SyntheticInference


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.clock,self.state,self.actuator,self.gateway,self.repo,self.grow,self.camera,self.media,self.inference,self.manifest,self.artifact)=media_fixture(self.root)

    def test_default_and_physical_camera_never_activate(self):
        from camera import Camera
        with patch.dict('sys.modules',{'picamera2':None}),self.assertRaises(RuntimeError):Camera()
        class Physical:
            synthetic=False
            def read(self):raise AssertionError('Physical camera must not be accessed')
        with self.assertRaises(ValueError):CameraOwner(Physical())
        self.assertIsNone(CameraOwner().get_frame())
        self.assertEqual(CameraOwner().snapshot()['state'],'unavailable')

    def test_single_owner_serializes_parallel_reads_and_rejects_second_owner(self):
        with self.assertRaises(ValueError):CameraOwner(self.camera)
        active=[];original=self.camera.read;lock=threading.Lock();count=0
        def read():
            nonlocal count
            with lock:count+=1;active.append(count)
            time.sleep(.005)
            result=original()
            with lock:count-=1
            return result
        with patch.object(self.camera,'read',side_effect=read):
            threads=[threading.Thread(target=self.media.captures.camera.get_frame) for _ in range(8)]
            for t in threads:t.start()
            for t in threads:t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(max(active),1)

    def test_capture_exact_bytes_dimensions_utc_hash_and_experiment_plant(self):
        plant=self.repo.plants_for_experiment(self.state.experiment_id)[0]['plant_id']
        image=capture(self.media,self.clock,plant_id=plant)
        data=self.media.captures.image_bytes(image['image_id'])
        self.assertEqual((image['width_px'],image['height_px']),(320,180))
        self.assertEqual(image['size_bytes'],len(data));self.assertEqual(image['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(image['timestamp_utc'],self.clock.utc().isoformat())
        self.assertEqual(image['experiment_id'],self.state.experiment_id);self.assertEqual(image['plant_id'],plant)
        self.assertEqual(image['source'],'synthetic')
        self.assertEqual(synthetic_jpeg(),synthetic_jpeg())
        self.assertEqual(self.actuator.commands,[])

    def test_duplicate_capture_request_does_not_acquire_or_index_twice(self):
        request=str(uuid.uuid4())
        first=self.media.captures.capture(request)
        reads=self.camera.reads
        second=self.media.captures.capture(request)
        self.assertEqual(first['image']['image_id'],second['image']['image_id']);self.assertEqual(self.camera.reads,reads)
        self.assertEqual(len(self.repo.get_recent_images()),1)
        with self.assertRaises(ValueError):self.media.captures.capture(request,plant_id=1)

    def test_concurrent_duplicate_capture_is_one_frame_one_image(self):
        request=str(uuid.uuid4());barrier=threading.Barrier(7);results=[]
        def worker():barrier.wait();results.append(self.media.captures.capture(request))
        threads=[threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
        self.assertEqual(len({r['image']['image_id'] for r in results}),1);self.assertEqual(self.camera.reads,1)

    def test_unavailable_stale_future_corrupt_frames_do_not_become_images(self):
        for mode in ('unavailable','stale','future','corrupt'):
            self.camera.available=True;self.camera.timestamp=None;self.camera.jpeg=synthetic_jpeg()
            if mode=='unavailable':self.camera.available=False
            if mode=='stale':self.camera.timestamp=(self.clock.utc()-timedelta(seconds=5)).isoformat()
            if mode=='future':self.camera.timestamp=(self.clock.utc()+timedelta(seconds=1)).isoformat()
            if mode=='corrupt':self.camera.jpeg=b'not JPEG'
            with self.subTest(mode=mode),self.assertRaises(Exception):self.media.captures.capture(str(uuid.uuid4()))
        self.assertEqual(self.repo.get_recent_images(),[])

    def test_partial_disk_write_is_preserved_and_never_finalized(self):
        request=str(uuid.uuid4())
        def partial(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data[:30]);raise OSError('ENOSPC')
        with patch.object(self.media.captures,'_write_stage',side_effect=partial),self.assertRaises(OSError):self.media.captures.capture(request)
        report=self.media.captures.recover()
        self.assertIn(request,report['needs_review'])
        self.assertTrue((self.media.captures.root/'.staging'/f'{request}.part').exists())
        self.assertEqual(self.repo.get_recent_images(),[])

    def test_interrupted_after_stage_recovers_without_acquiring_frame(self):
        request=str(uuid.uuid4())
        with patch.object(self.media.captures,'_finalize',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.media.captures.capture(request)
        reads=self.camera.reads
        report=self.media.captures.recover()
        self.assertIn(request,report['indexed']);self.assertEqual(self.camera.reads,reads)
        self.assertEqual(len(self.repo.get_recent_images()),1)

    def test_interrupted_after_final_link_and_database_rollback_are_recoverable(self):
        request=str(uuid.uuid4())
        with patch.object(self.repo,'_link_capture',side_effect=sqlite3.OperationalError('Injected rollback')),self.assertRaises(sqlite3.OperationalError):self.media.captures.capture(request)
        self.assertEqual(self.repo.get_recent_images(),[])
        self.assertEqual(self.repo.pending_media_events(),[])
        reopened=MediaRepository(self.repo.path,workspace_root=self.root)
        recovered=CaptureService(self.state,reopened,self.media.captures.camera,self.media.captures.root)
        report=recovered.recover();self.assertIn(request,report['indexed'])
        self.assertTrue(reopened.integrity_check())

    def test_claim_without_frame_is_interrupted_not_reacquired(self):
        request=str(uuid.uuid4());self.repo.claim_capture(request,self.state.experiment_id,None,'manual',self.clock.utc().isoformat())
        self.assertIn(request,self.media.captures.recover()['interrupted'])
        result=self.media.captures.capture(request)
        self.assertFalse(result['indexed']);self.assertEqual(self.camera.reads,0)

    def test_orphan_files_are_reported_preserved_and_not_indexed(self):
        root=self.media.captures.root
        (root/'orphan.jpg').write_bytes(synthetic_jpeg())
        (root/'orphan.part').write_bytes(b'partial')
        report=self.media.captures.recover()
        self.assertEqual(set(report['orphaned_files']),{'orphan.jpg','orphan.part'})
        self.assertTrue((root/'orphan.jpg').exists());self.assertEqual(self.repo.get_recent_images(),[])

    def test_final_name_collision_and_invalid_plant_do_not_overwrite(self):
        request=str(uuid.uuid4());_,final=self.media.captures.names(request,self.clock.utc().isoformat())
        path=self.media.captures.path(final);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'Historical file')
        with self.assertRaises(ValueError):self.media.captures.capture(request)
        self.assertEqual(path.read_bytes(),b'Historical file')
        with self.assertRaises(ValueError):self.media.captures.capture(str(uuid.uuid4()),plant_id=999)
        with self.assertRaises(ValueError):self.media.captures.path('../escape')

    def test_corrupt_indexed_file_is_not_served_or_inferred(self):
        image=capture(self.media,self.clock)
        self.media.captures.path(image['file_path']).write_bytes(b'corrupted after indexing')
        with self.assertRaises(ValueError):self.media.captures.image_bytes(image['image_id'])
        result=self.media.ml.analyze_image(image['image_id'])
        self.assertFalse(result['committed']);self.assertEqual(self.inference.calls,0)

    def test_hourly_schedule_deduplicates_and_skips_downtime_bursts(self):
        anchor=self.clock.utc().isoformat()
        self.media.captures.configure_schedule(True,3600,anchor)
        first=self.media.captures.scheduler_tick();self.assertTrue(first['indexed'])
        self.media.captures.scheduler_tick();self.assertEqual(self.camera.reads,1)
        self.clock.advance(3600*5+30)
        missed=self.media.captures.scheduler_tick();self.assertEqual(missed['status'],'missed')
        self.assertEqual(self.camera.reads,1)
        self.clock.advance(3570)
        self.assertTrue(self.media.captures.scheduler_tick()['indexed']);self.assertEqual(self.camera.reads,2)
        self.assertEqual(len(self.repo.get_recent_images()),2)

    def test_capture_outbox_survives_queue_loss_and_commit_retry(self):
        image=capture(self.media,self.clock);request=image['capture_request_id']
        self.assertEqual(self.repo.media_receipt(request)['status'],'pending')
        self.state.events.clear()  # simulate process queue loss; durable outbox remains
        with patch.object(self.repo,'log_event',side_effect=OSError('locked')):self.media.tick()
        self.assertEqual(self.repo.media_receipt(request)['status'],'pending')
        self.media.tick();self.assertEqual(self.repo.media_receipt(request)['status'],'committed')
        self.assertEqual(len(self.repo._rows("SELECT * FROM system_events WHERE event_type='capture_indexed'")),1)

    def test_clock_rollback_does_not_show_historical_image_as_zero_age_fresh(self):
        image=capture(self.media,self.clock)
        self.media.ml.analyze_image(image['image_id'])
        self.clock.advance(-1)
        snapshot=self.media.snapshot()
        self.assertIsNone(snapshot['recent'][0]['age_seconds'])
        self.assertTrue(snapshot['ml']['latest_result']['clock_fault'])
        self.assertTrue(snapshot['ml']['latest_result']['stale'])

    def test_manifest_hash_input_policy_and_unapproved_adapter_validation(self):
        roundtrip=ModelManifest.from_dict(self.manifest.as_dict());self.assertEqual(roundtrip.digest,self.manifest.digest)
        with self.assertRaises(ValueError):LocalMLService(self.media.captures,object(),self.manifest,self.artifact)
        self.repo._write("UPDATE model_manifests SET manifest_json='{}' WHERE manifest_sha256=?",(self.manifest.digest,))
        with self.assertRaisesRegex(ValueError,'Stored model manifest'):LocalMLService(self.media.captures,SyntheticInference(),self.manifest,self.artifact)
        self.artifact.write_bytes(b'changed artifact')
        with self.assertRaises(ValueError):LocalMLService(self.media.captures,SyntheticInference(),self.manifest,self.artifact)
        self.assertEqual(self.inference.calls,0)
        with self.assertRaises(ValueError):ClassificationPolicy('unapproved real plant diagnosis',(),('disease',))

    def test_database_claim_failure_is_traced_without_acquiring_frame(self):
        with patch.object(self.repo,'claim_capture',side_effect=sqlite3.OperationalError('database full')):
            with self.assertRaises(sqlite3.OperationalError):self.media.captures.capture(str(uuid.uuid4()))
        self.assertEqual(self.camera.reads,0);self.assertEqual(self.repo.get_recent_images(),[])
        self.assertTrue(any(e['event_type']=='capture_failed' for e in self.state.events))

    def test_scheduled_restart_reuses_claim_and_never_reacquires_same_slot(self):
        self.media.captures.configure_schedule(True,3600,self.clock.utc().isoformat())
        first=self.media.captures.scheduler_tick()
        restarted=CaptureService(self.state,MediaRepository(self.repo.path,workspace_root=self.root),self.media.captures.camera,self.media.captures.root)
        restarted.recover();second=restarted.scheduler_tick()
        self.assertEqual(first['image']['image_id'],second['image']['image_id']);self.assertEqual(self.camera.reads,1)

    def test_inference_is_versioned_linked_and_duplicate_is_idempotent(self):
        image=capture(self.media,self.clock)
        first=self.media.ml.analyze_image(image['image_id']);second=self.media.ml.analyze_image(image['image_id'])
        self.assertTrue(first['committed']);self.assertEqual(first['result']['inference_id'],second['result']['inference_id'])
        self.assertEqual(first['result']['manifest_sha256'],self.manifest.digest)
        self.assertEqual(first['result']['scope'],'synthetic-contract-only');self.assertEqual(self.inference.calls,1)
        self.assertEqual(self.actuator.commands,[])

    def test_low_confidence_and_unreviewed_classifications_are_uncertain(self):
        self.inference.outputs=[scores('fixture_abnormal',.699)]
        first=self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['result']
        self.assertEqual(first['predicted_class'],'uncertain');self.assertEqual(first['alert_eligible'],0)
        unreviewed=LocalMLService(self.media.captures,SyntheticInference([scores('fixture_abnormal',.99)]),self.manifest,self.artifact)
        self.assertTrue(unreviewed.get_latest_result()['historical_policy'])
        second=unreviewed.analyze_image(capture(self.media,self.clock)['image_id'])['result']
        self.assertEqual(second['predicted_class'],'uncertain');self.assertEqual(second['abnormal_streak'],0)

    def test_two_consecutive_reviewed_abnormal_results_and_reset(self):
        self.inference.outputs=[scores('fixture_abnormal',.7),scores('fixture_abnormal',.9),scores('fixture_normal',.9),scores('fixture_abnormal',.9)]
        results=[self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['result'] for _ in range(4)]
        self.assertEqual([r['abnormal_streak'] for r in results],[1,2,0,1])
        self.assertEqual([r['alert_eligible'] for r in results],[0,1,0,0])
        self.assertEqual(self.repo.get_active_alerts(),[])  # fixture signal is not a plant diagnosis/alarm

    def test_failed_and_non_monotonic_results_cannot_extend_abnormal_streak(self):
        self.inference.outputs=[scores('fixture_abnormal'),scores('fixture_abnormal')]
        old=capture(self.media,self.clock);new=capture(self.media,self.clock)
        first=self.media.ml.analyze_image(new['image_id'])['result']
        second=self.media.ml.analyze_image(old['image_id'])['result']
        self.assertEqual(first['abnormal_streak'],1);self.assertEqual(second['abnormal_streak'],0)
        self.assertEqual(second['predicted_class'],'uncertain')

    def test_failed_inference_breaks_reviewed_abnormal_streak(self):
        self.inference.outputs=[scores('fixture_abnormal'),scores('fixture_abnormal')]
        first=self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['result']
        with patch.object(self.inference,'infer',side_effect=OSError('model unavailable')):
            self.assertFalse(self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['committed'])
        third=self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['result']
        self.assertEqual(first['abnormal_streak'],1);self.assertEqual(third['abnormal_streak'],1)

    def test_versioned_models_can_analyze_same_image_without_combining_streaks(self):
        image=capture(self.media,self.clock)
        self.media.ml.analyze_image(image['image_id'])
        manifest=ModelManifest(self.manifest.model_id,'fixture-2',self.manifest.artifact_sha256,self.manifest.labels,32,24)
        other=LocalMLService(self.media.captures,SyntheticInference([scores('fixture_abnormal')]),manifest,self.artifact,policy=self.media.ml.policy)
        result=other.analyze_image(image['image_id'])['result']
        self.assertEqual(result['abnormal_streak'],1);self.assertEqual(result['model_version'],'fixture-2')
        self.assertEqual(len(self.repo._rows('SELECT * FROM ml_inferences')),2)

    def test_concurrent_inference_is_single_flight(self):
        image=capture(self.media,self.clock);entered,release=threading.Event(),threading.Event();results=[]
        original=self.inference.infer
        def slow(inputs):entered.set();release.wait(2);return original(inputs)
        with patch.object(self.inference,'infer',side_effect=slow):
            thread=threading.Thread(target=lambda:results.append(self.media.ml.analyze_image(image['image_id'])));thread.start()
            self.assertTrue(entered.wait(1))
            second=self.media.ml.analyze_image(image['image_id']);self.assertEqual(second['state'],'busy')
            release.set();thread.join(3);self.assertFalse(thread.is_alive())
        self.assertTrue(results[0]['committed']);self.assertEqual(self.inference.calls,1)

    def test_restart_marks_running_inference_interrupted_without_rerun(self):
        from services.sqlite_repository import canonical
        image=capture(self.media,self.clock)
        policy_json=canonical(self.media.ml.policy.as_dict());policy_hash=hashlib.sha256(policy_json.encode()).hexdigest()
        request=str(uuid.uuid4())
        self.repo.claim_ml_job(request,image['image_id'],self.manifest.digest,policy_json,policy_hash,self.clock.utc().isoformat())
        adapter=SyntheticInference()
        restarted=LocalMLService(self.media.captures,adapter,self.manifest,self.artifact,policy=self.media.ml.policy)
        result=restarted.analyze_image(image['image_id'])
        self.assertEqual(result['state'],'interrupted');self.assertFalse(result['committed']);self.assertEqual(adapter.calls,0)

    def test_invalid_scores_and_failed_adapter_report_error_without_inference(self):
        for output in (dict(label='fixture_normal',scores={'fixture_normal':float('nan'),'fixture_abnormal':0}),dict(label='unknown',scores={'fixture_normal':.9,'fixture_abnormal':.1})):
            self.inference.outputs=[output]
            result=self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])
            self.assertEqual(result['state'],'error');self.assertFalse(result['committed'])
        with patch.object(self.inference,'infer',side_effect=OSError('failed model')):
            self.assertFalse(self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])['committed'])
        self.assertEqual(self.repo._rows('SELECT * FROM ml_inferences'),[])

    def test_slow_inference_times_out_late_result_cannot_commit_or_spawn_more_workers(self):
        adapter=SyntheticInference();release=threading.Event();entered=threading.Event()
        def slow(inputs):entered.set();release.wait(2);return scores('fixture_abnormal')
        model=LocalMLService(self.media.captures,adapter,self.manifest,self.artifact,policy=self.media.ml.policy,timeout_s=.03)
        image=capture(self.media,self.clock)
        with patch.object(adapter,'infer',side_effect=slow):
            result=model.analyze_image(image['image_id']);self.assertTrue(entered.is_set())
            self.assertEqual(result['state'],'timed_out')
            self.assertEqual(model.analyze_image(capture(self.media,self.clock)['image_id'])['state'],'busy')
            self.assertFalse(self.gateway.command('PUMP_ON',source='automatic',authority=self.gateway.automatic_authority)['allowed'])
            self.assertTrue(self.gateway.command('PUMP_OFF',source='touchscreen',authority=self.gateway.operator_authority)['accepted'])
            release.set();model.worker.join(2)
        self.assertEqual(self.repo._rows('SELECT * FROM ml_inferences'),[])

    def test_inference_rollback_recovery_and_durable_outbox(self):
        image=capture(self.media,self.clock)
        with patch.object(self.repo,'_complete_ml_job',side_effect=sqlite3.OperationalError('rollback')):
            result=self.media.ml.analyze_image(image['image_id'])
        self.assertFalse(result['committed']);self.assertEqual(self.repo._rows('SELECT * FROM ml_inferences'),[])
        next_result=self.media.ml.analyze_image(capture(self.media,self.clock)['image_id'])
        self.assertTrue(next_result['committed'])
        receipt=self.repo.media_receipt(next_result['request_id']);self.assertEqual(receipt['status'],'pending')
        self.media.tick();self.assertEqual(self.repo.media_receipt(next_result['request_id'])['status'],'committed')
        reopened=MediaRepository(self.repo.path,workspace_root=self.root)
        self.assertEqual(reopened.latest_inference()['inference_id'],next_result['result']['inference_id'])


class MediaHttpTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app=app;self.client=app.app.test_client()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        values=media_fixture(Path(self.temp.name));self.clock,self.state,_,self.gateway,self.repo,_,self.camera,self.media,*_=values
        install_simulation_gateway(self.gateway)
        app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
        self.headers={'X-GERM-Token':app.control_token}

    def test_media_capture_infer_view_and_metadata_flow(self):
        self.assertEqual(self.client.get('/camera.jpg').headers['X-GERM-Source'],'synthetic')
        request=str(uuid.uuid4())
        response=self.client.post('/api/camera/capture',json={'request_id':request},headers=self.headers)
        self.assertEqual(response.status_code,201);image=response.json['image']
        self.assertEqual(self.client.get(image['url']).status_code,200)
        inferred=self.client.post('/api/ml/analyze',json={'image_id':image['image_id']},headers=self.headers)
        self.assertEqual(inferred.status_code,200);self.assertTrue(inferred.json['committed'])
        state=self.client.get('/api/state').json
        self.assertEqual(state['camera']['source'],'synthetic');self.assertEqual(state['ml']['latest_result']['scope'],'synthetic-contract-only')

    def test_stale_camera_and_corrupt_saved_image_never_serve_placeholders(self):
        self.camera.timestamp=(self.clock.utc()-timedelta(seconds=6)).isoformat()
        self.assertEqual(self.client.get('/camera.jpg').status_code,503)
        self.assertEqual(self.client.get('/api/media').json['camera']['state'],'stale')
        self.camera.timestamp=None;image=capture(self.media,self.clock)
        self.media.captures.path(image['file_path']).write_bytes(b'bad')
        self.assertEqual(self.client.get('/captures/'+image['file_path']).status_code,404)
        self.assertEqual(self.client.get('/captures/.staging/unknown.part').status_code,404)

    def test_all_production_media_posts_and_model_paths_are_denied(self):
        self.app.app.config['GERM_SIMULATION']=False
        for path in ('/api/camera/capture','/api/camera/schedule','/api/media/recover','/api/ml/analyze'):
            self.assertEqual(self.client.post(path,json={},headers=self.headers).status_code,403)
        self.app.app.config['GERM_SIMULATION']=True
        response=self.client.post('/api/ml/analyze',json={'image_id':1,'model_path':'unapproved'},headers=self.headers)
        self.assertEqual(response.status_code,400)


if __name__=='__main__':unittest.main(verbosity=2)
