"""Task 131: real disposable SQLite/files/ZIP; no hardware or real models."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m5_fixtures import media_fixture,capture,scores
from services.history_repository import HistoryRepository,SOURCES
from services.history_export import HistoryService,ExportBusy,spreadsheet,sha
from services.sqlite_repository import VERSION,MIGRATIONS

STAMP='2026-11-15T00:00:00+00:00'


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.clock,self.state,self.actuator,self.gateway,self.repo,_,self.camera,self.media,*_=media_fixture(self.root)
        self.service=HistoryService(self.repo,self.root/'images',self.root/'exports',software_version='m6-test')
        self.addCleanup(self.service.close)
        self.repo._write("INSERT OR IGNORE INTO sensors(sensor_id,unit,location,expected_period_s) VALUES('history_sensor','°C','host fixture',1)")
        self.exp=self.state.experiment_id

    def rows(self,n=4):
        with self.repo.connection() as db:
            db.execute('BEGIN')
            db.executemany("INSERT INTO sensor_readings(sensor_id,experiment_id,timestamp_utc,value,quality_flag) VALUES('history_sensor',?,?,?,'good')",((self.exp,STAMP,float(i)) for i in range(n)))
            db.execute('COMMIT')

    def export(self,definition=None,request_id=None):
        request_id=request_id or str(uuid.uuid4())
        self.service.start(request_id,definition or {});self.service.wait()
        return self.service.job(request_id)

    def archive(self,job):
        data,result=self.service.download(job['request_id']);self.assertEqual(sha(data),result['sha256'])
        package=zipfile.ZipFile(io.BytesIO(data));self.addCleanup(package.close)
        manifest=json.loads(package.read('manifest.json'))
        for name,meta in manifest['members'].items():self.assertEqual(sha(package.read(name)),meta['sha256'])
        return package,manifest

    def test_all_resources_empty_or_legacy_and_no_adapter_side_effects(self):
        before=list(self.actuator.commands);reads=self.camera.reads
        for resource in SOURCES:
            page=self.service.history.page(resource)
            self.assertLessEqual(len(page['rows']),100);self.assertIsInstance(page['columns'],list)
        self.assertEqual(self.actuator.commands,before);self.assertEqual(self.camera.reads,reads)
        page=self.service.history.page('experiments');self.assertEqual(page['rows'][0]['experiment_id'],self.exp)
        self.assertEqual(self.service.history.page('sensors')['rows'],[])
        with self.service.history.connection() as db,self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE experiments SET name='denied'")
        with self.assertRaises(ValueError):self.service.definition({'resources':[{}]})

    def test_v6_migration_preserves_history_and_verified_preupgrade_backup(self):
        import services.sqlite_repository as module
        folder=self.root/'v6-migrations';folder.mkdir()
        for source in sorted(MIGRATIONS.glob('*.sql'))[:6]:shutil.copyfile(source,folder/source.name)
        path=self.root/'v6.sqlite'
        with patch.object(module,'MIGRATIONS',folder),patch.object(module,'VERSION',6):
            legacy=module.SQLiteRepository(path,workspace_root=self.root,create=True);legacy.load_seed_fixture()
        upgraded=module.SQLiteRepository(path,workspace_root=self.root)
        self.assertEqual(len(upgraded.backups),1);self.assertTrue(upgraded.integrity_check())
        with closing(sqlite3.connect(upgraded.backups[0])) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM sensor_readings').fetchone()[0],4)
        with upgraded.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sensor_readings').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM export_jobs').fetchone()[0],0)

    def test_pagination_equal_times_high_water_and_filter_bound_cursors(self):
        self.rows(5);first=self.service.history.page('sensors',{'sensor':'history_sensor'},limit=2)
        self.rows(2)
        second=self.service.history.page('sensors',{'sensor':'history_sensor'},limit=2,cursor=first['next_cursor'])
        third=self.service.history.page('sensors',{'sensor':'history_sensor'},limit=2,cursor=second['next_cursor'])
        values=[r['value'] for page in (first,second,third) for r in page['rows']]
        self.assertEqual(values,[0,1,2,3,4]);self.assertIsNone(third['next_cursor'])
        for query,limit,cursor in (({},2,first['next_cursor']),({'sensor':'history_sensor'},3,first['next_cursor']),({'sensor':'history_sensor'},2,first['next_cursor']+'x')):
            with self.assertRaises(ValueError):self.service.history.page('sensors',query,limit=limit,cursor=cursor)

    def test_microsecond_order_legacy_invalid_time_and_half_open_utc(self):
        for stamp,value in [('2026-11-15T00:00:00.000001Z',1),(STAMP,0),('2026-11-15T00:00:00.1+00:00',2),('unknown',3)]:
            self.repo._write("INSERT INTO sensor_readings(sensor_id,timestamp_utc,value,quality_flag) VALUES('history_sensor',?,?,'good')",(stamp,value))
        result=self.service.history.page('sensors')['rows']
        self.assertEqual([r['value'] for r in result],[3,0,1,2]);self.assertEqual(result[0]['timestamp_quality'],'unknown_or_invalid')
        result=self.service.history.page('sensors',{'start_utc':STAMP,'end_utc':'2026-11-15T00:00:00.1Z'})['rows']
        self.assertEqual([r['value'] for r in result],[0,1])

    def test_literal_search_filters_unknown_experiment_and_validation(self):
        self.rows();self.assertEqual(len(self.service.history.page('sensors',{'experiment':self.exp,'type':'good','search':'history_sensor'})['rows']),4)
        self.assertEqual(self.service.history.page('sensors',{'search':"%' OR 1=1 --"})['rows'],[])
        self.assertEqual(self.service.history.page('sensors',{'experiment':9999})['rows'],[])
        for query in ({'bad':'x'},{'experiment':True},{'start_utc':'2026-01-01'},{'start_utc':STAMP,'end_utc':STAMP},{'search':'x'*121}):
            with self.assertRaises(ValueError):self.service.history.page('sensors',query)
        for limit in (0,501,True):
            with self.assertRaises(ValueError):self.service.history.page('sensors',limit=limit)
        with self.assertRaises(ValueError):self.service.history.page('events',{'sensor':'x'})

    def test_100000_rows_index_plan_bounded_pagination_and_concurrent_writes(self):
        self.rows(100000)
        with self.repo.connection() as db:
            plan=' '.join(str(tuple(r)) for r in db.execute('EXPLAIN QUERY PLAN SELECT reading_id FROM sensor_readings WHERE sensor_id=? AND timestamp_utc>=? ORDER BY timestamp_utc LIMIT 100',('history_sensor',STAMP)))
            self.assertIn('readings_sensor_time',plan)
        first=self.service.history.page('sensors',{'sensor':'history_sensor'},limit=500)
        self.assertEqual(len(first['rows']),500);self.assertTrue(first['next_cursor'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            write=pool.submit(self.rows,10)
            page=pool.submit(self.service.history.page,'sensors',{'sensor':'history_sensor'},limit=500,cursor=first['next_cursor']).result()
            write.result()
        self.assertEqual(page['rows'][0]['value'],500);self.assertEqual(page['high_water_rowid'],first['high_water_rowid'])

    def test_csv_utf8_formula_injection_and_raw_provenance(self):
        malicious='\ufeff  ＝HYPERLINK("x")\nβ, "quoted"'
        self.repo._write('UPDATE experiments SET name=? WHERE experiment_id=?',(malicious,self.exp))
        self.rows(1);self.repo._write('UPDATE sensor_readings SET value=-2.5')
        job=self.export();self.assertEqual(job['status'],'complete',job)
        package,manifest=self.archive(job)
        text=package.read('tables/experiments.v1.csv').decode('utf-8');row=next(csv.DictReader(io.StringIO(text)))
        self.assertEqual(row['name'],"'"+malicious)
        raw=json.loads(package.read('provenance/experiments.jsonl').decode('utf-8').splitlines()[0]);self.assertEqual(raw['name'],malicious)
        row=next(csv.DictReader(io.StringIO(package.read('tables/sensors.v1.csv').decode('utf-8'))))
        self.assertEqual(row['value'],'-2.5');self.assertEqual(row['unit'],'°C');self.assertEqual(row['quality_flag'],'good')
        self.assertEqual(manifest['sqlite_schema_version'],VERSION);self.assertEqual(manifest['tables']['sensors']['rows'],1)

    def test_formula_prefix_variants_and_typed_negative(self):
        for text in ('=1','+1','-1','@SUM(A1)',' \t=1','\r1','\n1','\ufeff=1','\u200b@x','\uff1d1'):
            self.assertEqual(spreadsheet(text),"'"+text)
        self.assertEqual(spreadsheet(-2.5),-2.5);self.assertEqual(spreadsheet('basil'),'basil')

    def test_verified_jpeg_manifest_and_legacy_unknown_source(self):
        image=capture(self.media,self.clock)
        self.repo._write('UPDATE images SET source=NULL WHERE image_id=?',(image['image_id'],))
        page=self.service.history.page('images')['rows'][0];self.assertEqual(page['source_quality'],'legacy_unknown')
        job=self.export({'resources':['images']});package,manifest=self.archive(job)
        entry=manifest['images'][0];self.assertEqual(entry['state'],'verified')
        self.assertEqual(sha(package.read(entry['member'])),image['sha256'])
        self.assertEqual(self.camera.reads,1)

    def test_missing_corrupt_images_partial_status_and_strict_failure(self):
        first=capture(self.media,self.clock);second=capture(self.media,self.clock)
        # Test fixtures only: deletion/corruption simulates external file damage.
        (self.root/'images'/first['file_path']).unlink()
        (self.root/'images'/second['file_path']).write_bytes(b'broken')
        job=self.export({'resources':['images']});self.assertEqual(job['status'],'complete_with_errors',job)
        package,manifest=self.archive(job);self.assertEqual(len(manifest['errors']),2)
        self.assertFalse(any(name.endswith('.jpg') for name in package.namelist()))
        strict=self.export({'resources':['images'],'strict_images':True});self.assertEqual(strict['status'],'failed')
        with self.assertRaises(ValueError):self.service.download(strict['request_id'])
        self.assertEqual(len(self.repo.get_recent_images()),2)

    def test_snapshot_consistency_with_writer_after_backup_and_ack_update(self):
        self.rows(3);original=self.repo.backup
        def snapshot_then_write(destination):
            result=original(destination);self.rows(2)
            self.repo._write("UPDATE sensor_readings SET quality_flag='suspect'")
            return result
        with patch.object(self.repo,'backup',side_effect=snapshot_then_write):job=self.export({'resources':['sensors']})
        package,manifest=self.archive(job);rows=list(csv.DictReader(io.StringIO(package.read('tables/sensors.v1.csv').decode())))
        self.assertEqual(len(rows),3);self.assertTrue(all(r['quality_flag']=='good' for r in rows))
        self.assertEqual(len(self.service.history.page('sensors')['rows']),5)
        self.assertEqual(self.actuator.commands,[])

    def test_same_request_concurrency_idempotency_and_content_conflict(self):
        self.rows();request_id=str(uuid.uuid4());definition={'resources':['sensors']}
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.service.start(request_id,definition),range(4)))
        self.service.wait();job=self.service.job(request_id)
        self.assertEqual(job['status'],'complete',job);self.assertTrue(all(r['request_id']==request_id for r in results));self.assertEqual(job['attempt'],1)
        self.assertEqual(len(list((self.root/'exports'/request_id).iterdir())),1)
        with self.assertRaises(ValueError):self.service.start(request_id,{'resources':['events']})

    def test_db_failure_never_claims_persistence_and_restart_marks_interrupted(self):
        request_id=str(uuid.uuid4());original=self.repo._write
        def fail_completion(sql,args=()):
            if 'result_json=?' in sql or "status='failed'" in sql:raise sqlite3.OperationalError('Injected disk failure')
            return original(sql,args)
        with patch.object(self.repo,'_write',side_effect=fail_completion):self.service.start(request_id,{'resources':['sensors']});self.service.wait()
        self.assertEqual(self.service.job(request_id)['status'],'running')
        with self.assertRaises(ValueError):self.service.download(request_id)
        self.service.close()
        restarted=HistoryService(self.repo,self.root/'images',self.root/'exports',software_version='m6-test');self.addCleanup(restarted.close)
        self.assertEqual(restarted.job(request_id)['status'],'interrupted')
        restarted.start(request_id,{'resources':['sensors']},retry=True);restarted.wait()
        self.assertEqual(restarted.job(request_id)['attempt'],2);self.assertEqual(restarted.job(request_id)['status'],'complete')
        self.assertEqual(len(list((self.root/'exports'/request_id).iterdir())),2)

    def test_backup_failure_disk_full_partial_stage_and_quotas_preserve_files(self):
        for error in (sqlite3.OperationalError('backup error'),OSError('disk full')):
            with patch.object(self.repo,'backup',side_effect=error):job=self.export({'resources':['sensors']})
            self.assertEqual(job['status'],'failed');self.assertIsNone(job['result'])
        self.rows(5);self.service.max_rows=2
        job=self.export({'resources':['sensors']});self.assertEqual(job['status'],'failed')
        self.assertTrue(list((self.root/'exports'/job['request_id']).rglob('*.part')))
        self.service.max_rows=200000;self.service.max_bytes=100
        job=self.export();self.assertEqual(job['status'],'failed')
        self.service.max_jobs=1
        with self.assertRaises(ExportBusy):self.service.start(str(uuid.uuid4()),{})
        self.assertEqual(len(self.service.history.page('sensors')['rows']),5)

    def test_initial_job_write_failure_and_read_failure_propagate(self):
        with patch.object(self.repo,'_write',side_effect=sqlite3.OperationalError('read only')):
            with self.assertRaises(sqlite3.OperationalError):self.service.start(str(uuid.uuid4()),{})
        with patch.object(self.service.history,'connection',side_effect=sqlite3.OperationalError('read failed')):
            with self.assertRaises(sqlite3.OperationalError):self.service.history.page('sensors')

    def test_modified_archive_and_unsafe_path_download_denied(self):
        job=self.export();path=self.root/'exports'/job['result']['file']
        with path.open('r+b') as stream:stream.write(b'corrupt')
        with self.assertRaises(ValueError):self.service.download(job['request_id'])
        with self.assertRaises(ValueError):self.service._safe_artifact('../outside.zip')
        image=capture(self.media,self.clock);image['file_path']='../outside.jpg'
        with self.assertRaises(ValueError):self.service._image(image)

    def test_changing_image_bytes_are_not_silently_archived(self):
        capture(self.media,self.clock)
        with patch.object(self.service,'_image',side_effect=ValueError('Image changed during export')):job=self.export({'resources':['images']})
        self.assertEqual(job['status'],'complete_with_errors');_,manifest=self.archive(job)
        self.assertIn('changed',manifest['errors'][0]['error'])

    def test_export_deadline_and_total_quota_fail_without_deletion(self):
        self.service.max_seconds=-1;job=self.export();self.assertEqual(job['status'],'failed')
        files=list((self.root/'exports').rglob('*'));self.service.max_total_bytes=0
        with self.assertRaises(ExportBusy):self.service.start(str(uuid.uuid4()),{})
        self.assertTrue(all(p.exists() for p in files))

    def test_single_owner_and_busy_different_request_do_not_create_claim(self):
        with self.assertRaises(ExportBusy):HistoryService(self.repo,self.root/'images',self.root/'other-exports',software_version='other')
        entered=threading.Event();release=threading.Event();original=self.repo.backup
        def delayed(destination):entered.set();release.wait(5);return original(destination)
        request_id=str(uuid.uuid4());other=str(uuid.uuid4())
        with patch.object(self.repo,'backup',side_effect=delayed):
            self.service.start(request_id,{'resources':['events']});self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(ExportBusy):self.service.start(other,{})
                with self.assertRaises(LookupError):self.service.job(other)
                self.assertEqual(self.actuator.commands,[])
                # Gateway reads proceed while a snapshot worker is blocked.
                self.assertIsInstance(self.gateway.state.snapshot(),dict)
            finally:release.set();self.service.wait()
        self.assertEqual(self.service.job(request_id)['status'],'complete')

    def test_inference_policy_manifest_and_actuator_ack_provenance(self):
        image=capture(self.media,self.clock)
        self.media.ml.analyze_image(image['image_id'],request_id=str(uuid.uuid4()))
        self.repo._write("INSERT OR IGNORE INTO actuators(actuator_id,description) VALUES('history_fan','fixture')")
        self.repo.record_actuator_event(dict(actuator='history_fan',experiment_id=self.exp,timestamp_utc=STAMP,requested_state='on',reported_state='on',source='synthetic',firmware_confirmed=True,physically_verified=False))
        self.repo._write('INSERT INTO maintenance_events(experiment_id,timestamp_utc,action,component,details_json) VALUES(?,?,?,?,?)',(self.exp,STAMP,'check','history_fan','{}'))
        inference=self.service.history.page('inference')['rows'][0]
        self.assertTrue(inference['manifest_json']);self.assertTrue(inference['policy_sha256'])
        actuator=self.service.history.page('actuators')['rows'][0]
        self.assertEqual(actuator['firmware_confirmed'],1);self.assertEqual(actuator['physically_verified'],0)
        job=self.export({'resources':['inference','actuators','maintenance']});_,manifest=self.archive(job)
        self.assertEqual(manifest['tables']['maintenance']['rows'],1)

    def test_archive_verifier_rejects_extra_members_and_truncated_zip(self):
        job=self.export();_,manifest=self.archive(job)
        path=self.root/'exports'/job['result']['file']
        with zipfile.ZipFile(path,'a') as package:package.writestr('../escape',b'bad')
        with self.assertRaises(ValueError):self.service._verify_archive(path,manifest)
        with path.open('r+b') as stream:stream.write(b'PK');stream.truncate()
        with self.assertRaises(zipfile.BadZipFile):self.service._verify_archive(path,manifest)

    def test_symlink_image_and_download_are_denied(self):
        image=capture(self.media,self.clock);path=self.root/'images'/image['file_path']
        target=self.root/'outside.jpg';target.write_bytes(path.read_bytes());path.unlink()
        try:path.symlink_to(target)
        except OSError:
            if os.name!='nt':raise
            self.skipTest('Host lacks symlink privilege; POSIX CI requires this test')
        with self.assertRaises(ValueError):self.service._image(image)
        job=self.export({'resources':['images']});self.assertEqual(job['status'],'complete_with_errors')

    def test_partial_archive_write_disk_full_is_not_downloadable(self):
        original=zipfile.ZipFile.writestr
        def partial(package,name,data,*args,**kwargs):
            original(package,name,data[:8],*args,**kwargs)
            raise OSError('Injected disk-full during archive write')
        with patch.object(zipfile.ZipFile,'writestr',new=partial):job=self.export({'resources':['events']})
        self.assertEqual(job['status'],'failed');self.assertIsNone(job['result'])
        with self.assertRaises(ValueError):self.service.download(job['request_id'])
        self.assertTrue(list((self.root/'exports'/job['request_id']).rglob('archive.part')))

    def test_large_export_streams_100000_rows_and_exact_counts(self):
        self.rows(100000);self.service.max_seconds=120
        job=self.export({'resources':['sensors']});self.assertEqual(job['status'],'complete',job)
        package,manifest=self.archive(job);self.assertEqual(manifest['tables']['sensors']['rows'],100000)
        with package.open('tables/sensors.v1.csv') as source:self.assertEqual(sum(1 for _ in csv.reader(io.TextIOWrapper(source,encoding='utf-8'))),100001)


class HistoryHttpTests(unittest.TestCase):
    # Reuse the real fixture without duplicating the parent tests.
    setUp=HistoryTests.setUp
    def test_http_bounds_restricted_exports_verified_download_and_seven_routes(self):
        import app
        from services.control_runtime import install_simulation_gateway
        install_simulation_gateway(self.gateway)
        old=dict(app.app.config)
        self.addCleanup(lambda:app.app.config.update(old))
        app.app.config.update(TESTING=True,GERM_HISTORY_SERVICE=self.service,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
        client=app.app.test_client();headers={'X-GERM-Token':app.control_token}
        for route in ('/','/plant','/trends','/controls','/alerts','/maintenance','/settings'):self.assertEqual(client.get(route).status_code,200)
        self.assertIn(b'history-form',client.get('/trends').data)
        image=capture(self.media,self.clock)
        response=client.get('/api/history/images/'+str(image['image_id'])+'/file')
        self.assertEqual(response.status_code,200);self.assertEqual(sha(response.data),image['sha256'])
        path=self.root/'images'/image['file_path'];path.unlink()
        self.assertEqual(client.get('/api/history/images/'+str(image['image_id'])+'/file').status_code,503)
        for query in ('?limit=501','?limit=2&limit=3','?start_utc=bad','?cursor=bad'):self.assertEqual(client.get('/api/history/sensors'+query).status_code,400)
        self.assertEqual(client.get('/api/history/unknown').status_code,400)
        request_id=str(uuid.uuid4());data={'request_id':request_id,'definition':{'resources':['sensors']}}
        self.assertEqual(client.post('/api/exports',json=data).status_code,403)
        self.assertEqual(client.post('/api/exports',json=data,headers=headers).status_code,202);self.service.wait()
        response=client.get('/api/exports/'+request_id+'/download');self.assertEqual(response.status_code,200)
        self.assertEqual(sha(response.data),response.headers['X-GERM-SHA256'])
        self.assertEqual(client.get('/api/exports/'+str(uuid.uuid4())).status_code,404)
        app.app.config['GERM_SIMULATION']=False
        self.assertEqual(client.post('/api/exports',json=data,headers=headers).status_code,403)
        app.app.config['GERM_HISTORY_SERVICE']=None
        self.assertEqual(client.get('/api/history/sensors').status_code,503)


if __name__=='__main__':unittest.main(verbosity=2)
