"""M5 correction: durable clock fault, explicit recovery and stable claims."""
from contextlib import closing
from datetime import datetime,timedelta
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m5_fixtures import media_fixture
from services.capture_service import CaptureService
from services.media_repository import MediaRepository
from services.sqlite_repository import MIGRATIONS
from services.control_runtime import install_simulation_gateway


class CaptureClockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.clock,self.state,_,self.gateway,self.repo,_,self.camera,self.media,*_=media_fixture(self.root)
        self.service=self.media.captures
        self.anchor=self.clock.utc()
        self.service.configure_schedule(True,3600,self.anchor.isoformat())

    def advance_to(self,stamp):self.clock.advance((stamp-self.clock.utc()).total_seconds())
    def claims(self):return self.repo._rows("SELECT * FROM capture_requests WHERE capture_reason='scheduled' ORDER BY request_id")

    def latch_fault(self):
        self.service.scheduler_tick()
        self.clock.advance(30);self.service.scheduler_tick()
        self.clock.advance(-20)
        self.assertIsNone(self.service.scheduler_tick())
        self.assertTrue(self.repo.capture_schedule()['clock_fault'])

    def restart(self):
        repo=MediaRepository(self.repo.path,workspace_root=self.root)
        service=CaptureService(self.state,repo,self.service.camera,self.service.root)
        service.recover()  # Ordinary process recovery must never acknowledge clock faults.
        return service

    def test_repeated_rollback_ticks_never_read_camera_or_create_new_claims(self):
        self.latch_fault();claims=self.claims();reads=self.camera.reads
        for shift in (0,-1,0,2,5):self.clock.advance(shift);self.service.scheduler_tick()
        self.assertEqual(self.camera.reads,reads);self.assertEqual(self.claims(),claims)
        status=self.service.scheduling_snapshot()
        self.assertEqual(status['state'],'clock_fault');self.assertTrue(status['inhibited'])
        self.assertTrue(status['operator_recovery_required'])

    def test_time_recovery_alone_never_clears_persisted_fault(self):
        self.latch_fault();reads=self.camera.reads;count=len(self.claims())
        for stamp in (self.anchor+timedelta(seconds=30),self.anchor+timedelta(hours=1),self.anchor+timedelta(hours=4)):
            self.advance_to(stamp);self.service.scheduler_tick()
            self.assertEqual(self.service.scheduling_snapshot()['state'],'clock_fault')
        self.assertEqual(self.camera.reads,reads);self.assertEqual(len(self.claims()),count)

    def test_explicit_recovery_requires_high_water_and_waits_for_strict_future_slot(self):
        self.latch_fault();original=self.repo.capture_schedule();reads=self.camera.reads
        with self.assertRaisesRegex(ValueError,'high-water'):self.service.recover_schedule_clock()
        self.advance_to(self.anchor+timedelta(seconds=30))
        recovered=self.service.recover_schedule_clock()
        self.assertEqual(recovered['generation'],original['generation']);self.assertEqual(recovered['anchor_utc'],original['anchor_utc'])
        self.assertEqual(recovered['resume_not_before_utc'],(self.anchor+timedelta(hours=1)).isoformat())
        self.assertEqual(self.service.scheduling_snapshot()['state'],'waiting_for_boundary')
        self.service.scheduler_tick();self.assertEqual(self.camera.reads,reads)
        self.advance_to(self.anchor+timedelta(hours=1))
        result=self.service.scheduler_tick();self.assertTrue(result['indexed'])
        expected=str(uuid.uuid5(uuid.NAMESPACE_URL,'capture:1:'+str(self.state.experiment_id)+':'+self.clock.utc().isoformat()))
        self.assertEqual(result['request_id'],expected)
        self.service.scheduler_tick();self.assertEqual(self.camera.reads,reads+1)

    def test_restart_preserves_latch_and_recovery_boundary_and_claim_identity(self):
        self.latch_fault();original_claims=self.claims();reads=self.camera.reads
        service=self.restart();self.advance_to(self.anchor+timedelta(seconds=30))
        service.scheduler_tick();self.assertEqual(service.scheduling_snapshot()['state'],'clock_fault')
        self.assertEqual(self.camera.reads,reads);self.assertEqual(self.claims(),original_claims)
        service.recover_schedule_clock();service=self.restart()
        self.assertEqual(service.scheduling_snapshot()['state'],'waiting_for_boundary')
        service.scheduler_tick();self.assertEqual(self.camera.reads,reads)
        self.advance_to(self.anchor+timedelta(hours=1));first=service.scheduler_tick()
        service=self.restart();second=service.scheduler_tick()
        self.assertEqual(first['request_id'],second['request_id']);self.assertEqual(self.camera.reads,reads+1)

    def test_restart_detects_rollback_against_persisted_tick_without_previous_fault(self):
        self.service.scheduler_tick();self.clock.advance(90);self.service.scheduler_tick()
        self.clock.advance(-60);reads=self.camera.reads
        service=self.restart();service.scheduler_tick()
        self.assertEqual(service.scheduling_snapshot()['state'],'clock_fault')
        self.assertEqual(self.camera.reads,reads)

    def test_missed_slots_and_interrupted_claims_remain_terminal_after_recovery(self):
        self.service.scheduler_tick()
        self.advance_to(self.anchor+timedelta(hours=1,seconds=10));missed=self.service.scheduler_tick()
        self.assertEqual(missed['status'],'missed')
        due=self.anchor+timedelta(hours=2)
        self.advance_to(due)
        with patch.object(self.camera,'read',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.service.scheduler_tick()
        claimed=next(r for r in self.claims() if r['scheduled_at_utc']==due.isoformat())
        self.assertEqual(claimed['status'],'claimed')
        service=self.restart()
        self.assertEqual(self.repo.capture_request(claimed['request_id'])['status'],'interrupted')
        self.clock.advance(-1);service.scheduler_tick();self.advance_to(due)
        service.recover_schedule_clock();reads=self.camera.reads
        for _ in range(3):service.scheduler_tick()
        self.assertEqual(self.camera.reads,reads)
        self.assertEqual(self.repo.capture_request(missed['request_id'])['status'],'missed')
        self.assertEqual(self.repo.capture_request(claimed['request_id'])['status'],'interrupted')
        self.advance_to(self.anchor+timedelta(hours=3));self.assertTrue(service.scheduler_tick()['indexed'])

    def test_late_recovery_skips_expired_slot_without_catchup_burst(self):
        self.latch_fault();self.advance_to(self.anchor+timedelta(seconds=30));self.service.recover_schedule_clock()
        reads=self.camera.reads
        self.advance_to(self.anchor+timedelta(hours=6,seconds=10))
        result=self.service.scheduler_tick();self.assertEqual(result['status'],'missed')
        for _ in range(3):self.service.scheduler_tick()
        self.assertEqual(self.camera.reads,reads);self.assertEqual(len(self.claims()),2)
        self.advance_to(self.anchor+timedelta(hours=7));self.assertTrue(self.service.scheduler_tick()['indexed'])

    def test_reconfiguration_and_journal_recovery_cannot_bypass_clock_latch(self):
        self.latch_fault();old=self.repo.capture_schedule()
        with self.assertRaises(ValueError):self.service.configure_schedule(True,60,self.anchor.isoformat())
        self.service.recover();self.assertTrue(self.repo.capture_schedule()['clock_fault'])
        self.service.configure_schedule(False,3600,self.anchor.isoformat())
        with self.assertRaises(ValueError):self.service.configure_schedule(True,3600,self.anchor.isoformat())
        current=self.repo.capture_schedule()
        self.assertEqual(current['generation'],old['generation']);self.assertEqual(current['anchor_utc'],old['anchor_utc'])
        self.assertTrue(current['clock_fault']);self.assertFalse(current['enabled'])

    def test_repeated_ack_and_reconfiguration_cannot_duplicate_recovered_slot(self):
        self.latch_fault();self.advance_to(self.anchor+timedelta(seconds=30))
        boundary=self.service.recover_schedule_clock()['resume_not_before_utc']
        self.clock.advance(10)
        self.assertEqual(self.service.recover_schedule_clock()['resume_not_before_utc'],boundary)
        self.service.configure_schedule(True,60,self.anchor.isoformat())
        current=self.repo.capture_schedule()
        self.assertEqual(current['resume_not_before_utc'],boundary)
        reads=self.camera.reads;self.service.scheduler_tick();self.assertEqual(self.camera.reads,reads)
        self.advance_to(datetime.fromisoformat(boundary));self.service.scheduler_tick()
        self.service.configure_schedule(True,60,self.anchor.isoformat())
        for _ in range(3):self.service.scheduler_tick()
        self.assertEqual(self.camera.reads,reads+1)

    def test_clock_guard_persistence_failure_fails_closed(self):
        with patch.object(self.repo,'observe_capture_clock',side_effect=sqlite3.OperationalError('full database')):
            self.assertIsNone(self.service.scheduler_tick())
        self.assertEqual(self.camera.reads,0);self.assertEqual(self.claims(),[])
        self.assertEqual(self.service.scheduling_snapshot()['state'],'unavailable')

    def test_advancing_utc_observations_do_not_create_false_rollback(self):
        def advancing():self.clock.advance(.001);return self.clock.utc()
        with patch.object(self.state,'utc_now',side_effect=advancing):
            result=self.service.scheduler_tick()
        self.assertTrue(result['indexed'])
        self.assertEqual(self.camera.reads,1);self.assertFalse(self.repo.capture_schedule()['clock_fault'])

    def test_rollback_during_frame_read_cannot_index_a_wrong_slot(self):
        original=self.camera.read
        def rollback():self.clock.advance(-1);return original()
        with patch.object(self.camera,'read',side_effect=rollback):self.service.scheduler_tick()
        self.assertEqual(self.repo.get_recent_images(),[])
        self.assertEqual(self.service.scheduling_snapshot()['state'],'clock_fault')
        self.assertTrue(all(r['status']=='failed' for r in self.claims()))

    def test_schema_v5_upgrade_seeds_high_water_from_all_persisted_claims(self):
        import services.sqlite_repository as module
        folder=self.root/'v5';folder.mkdir()
        for name in sorted(MIGRATIONS.glob('*.sql'))[:5]:shutil.copyfile(name,folder/name.name)
        path=self.root/'legacy.sqlite'
        with patch.object(module,'MIGRATIONS',folder),patch.object(module,'VERSION',5):
            legacy=MediaRepository(path,workspace_root=self.root,create=True)
            legacy._write("INSERT INTO experiments VALUES(1,'fixture','basil','active',?,NULL,NULL)",(self.anchor.isoformat(),))
            legacy._write('INSERT INTO capture_schedule VALUES(1,3,1,3600,?)',(self.anchor.isoformat(),))
            high=(self.anchor+timedelta(hours=2,seconds=30)).isoformat()
            legacy._write("INSERT INTO capture_requests(request_id,experiment_id,capture_reason,scheduled_at_utc,created_at_utc,status) VALUES(?,1,'scheduled',?,?,'missed')",(str(uuid.uuid4()),(self.anchor+timedelta(hours=2)).isoformat(),high))
        upgraded=MediaRepository(path,workspace_root=self.root)
        self.assertEqual(upgraded.capture_schedule()['last_observed_utc'],high)
        self.assertEqual(len(upgraded.backups),1)
        service=CaptureService(self.state,upgraded,self.service.camera,self.root/'legacy-images')
        service.scheduler_tick();self.assertTrue(upgraded.capture_schedule()['clock_fault']);self.assertEqual(self.camera.reads,0)


class ClockHttpTests(unittest.TestCase):
    def test_api_reports_persistent_fault_and_explicit_recovery_without_capture(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            clock,state,_,gateway,repo,_,camera,media,*_=media_fixture(Path(directory))
            install_simulation_gateway(gateway)
            app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
            client=app.app.test_client();headers={'X-GERM-Token':app.control_token}
            anchor=clock.utc();media.captures.configure_schedule(True,3600,anchor.isoformat())
            media.tick();clock.advance(30);media.tick();clock.advance(-20);media.tick()
            self.assertEqual(client.get('/api/media').json['scheduling']['state'],'clock_fault')
            response=client.post('/api/media/recover',json={'recover_clock':True},headers=headers)
            self.assertEqual(response.status_code,423)
            self.assertEqual(client.post('/api/media/recover',json={},headers=headers).status_code,200)
            self.assertTrue(repo.capture_schedule()['clock_fault'])
            clock.advance(20);reads=camera.reads
            response=client.post('/api/media/recover',json={'recover_clock':True},headers=headers)
            self.assertEqual(response.status_code,200);self.assertFalse(response.json['captures_started'])
            self.assertEqual(camera.reads,reads)
            self.assertEqual(client.get('/api/media').json['scheduling']['state'],'waiting_for_boundary')
            self.assertEqual(client.post('/api/media/recover',json={'recover_clock':1},headers=headers).status_code,400)


if __name__=='__main__':unittest.main(verbosity=2)
