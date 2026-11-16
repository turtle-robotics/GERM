"""Task 124 temporary host DB/files. No hardware, deployment or history cleanup."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m5_fixtures import media_fixture,capture
from services.history_export import HistoryService,ExportBusy,sha
from services.storage_service import StorageService,safe_member
from services.sqlite_repository import SQLiteRepository,MIGRATIONS,VERSION,canonical


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.clock,self.state,self.actuator,self.gateway,self.repo,_,self.camera,self.media,*_=media_fixture(self.root)
        self.history=HistoryService(self.repo,self.root/'images',self.root/'exports',software_version='m7-fixture')
        self.addCleanup(self.history.close)
        self.storage=StorageService(self.history,self.root/'storage',software_version='m7-fixture')
        self.addCleanup(self.storage.close)

    def job(self,kind='backup',backup_id=None,request_id=None):
        definition=dict(kind=kind)
        if backup_id:definition['backup_id']=backup_id
        request_id=request_id or str(uuid.uuid4());self.storage.start(request_id,definition);self.storage.wait()
        return self.storage.job(request_id)

    def frame(self):return capture(self.media,self.clock)

    def package(self,job):return self.storage._safe_artifact(job['result']['file'])

    def rewrite(self,job,mutate):
        path=self.package(job)
        with zipfile.ZipFile(path) as source:members={name:source.read(name) for name in source.namelist()}
        mutate(members)
        target=path.with_name('injected-'+uuid.uuid4().hex+'.zip')
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_STORED) as package:
            for name,data in members.items():package.writestr(name,data)
        return target

    def verify(self,path):
        directory=self.root/'storage'/'verification'/uuid.uuid4().hex;directory.mkdir(parents=True)
        return self.storage.verify_package(path,directory)

    def test_observed_inventory_estimate_capacity_and_no_camera_reads(self):
        image=self.frame();reads=self.camera.reads
        (self.root/'exports'/'kept.txt').write_bytes(b'keep')
        observed=self.storage.inventory()
        # Accepted M5 publication retains a staging hard link on POSIX; logical
        # file sizes count both names rather than inventing physical allocation.
        expected_files=2 if os.name=='posix' else 1
        self.assertEqual(observed['state'],'observed');self.assertEqual(observed['categories']['images']['files'],expected_files)
        self.assertEqual(observed['categories']['images']['logical_bytes'],image['size_bytes']*expected_files)
        self.assertEqual(observed['categories']['exports']['logical_bytes'],4)
        self.assertIn('estimate',observed['backup_estimate']['measurement']);self.assertEqual(observed['backup_estimate']['image_count'],1)
        self.assertIsInstance(observed['volume']['free_bytes'],int);self.assertFalse(observed['retention']['automatic_deletion'])
        usage=shutil._ntuple_diskusage(100,90,10)
        with patch('services.storage_service.shutil.disk_usage',return_value=usage):self.assertTrue(self.storage.inventory()['capacity_warning'])
        self.assertEqual(self.camera.reads,reads);self.assertEqual(self.actuator.commands,[])

    def test_complete_backup_manifest_database_and_jpeg_integrity(self):
        image=self.frame();job=self.job();self.assertEqual(job['status'],'complete',job)
        data,result=self.storage.download(job['request_id']);self.assertEqual(sha(data),result['sha256'])
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            manifest=json.loads(package.read('manifest.json'))
            self.assertEqual(manifest['schema_version'],VERSION);self.assertEqual(manifest['software_version'],'m7-fixture')
            self.assertEqual(manifest['request_id'],job['request_id']);self.assertEqual(manifest['attempt'],1)
            self.assertEqual(sha(package.read('images/'+image['file_path'])),image['sha256'])
            for name,meta in manifest['members'].items():self.assertEqual(sha(package.read(name)),meta['sha256'])
        self.assertTrue(result['report']['database_verified']);self.assertEqual(result['report']['images_verified'],1)

    def test_isolated_restore_preserves_live_database_images_and_permissions(self):
        image=self.frame();backup=self.job();live=self.repo.path;image_path=self.root/'images'/image['file_path']
        before=image_path.read_bytes();state=self.gateway.state.snapshot()
        job=self.job('restore',backup['request_id']);self.assertEqual(job['status'],'complete',job)
        result=job['result'];destination=self.root/'storage'/result['destination']
        self.assertNotEqual(destination/'database.sqlite',live);self.assertFalse(result['runtime_attached']);self.assertFalse(result['permissions_restored']);self.assertFalse(result['restore_activation_allowed'])
        self.assertEqual((destination/'images'/image['file_path']).read_bytes(),before)
        self.assertEqual(image_path.read_bytes(),before);self.assertEqual(self.repo.get_recent_images()[0]['sha256'],image['sha256'])
        self.assertTrue(SQLiteRepository.validate_snapshot(destination/'database.sqlite'))
        self.assertTrue((destination/'RECOVERY_REPORT.json').exists());self.assertEqual(self.actuator.commands,[])
        self.assertEqual(self.gateway.state.snapshot(),state)

    def test_live_writes_after_snapshot_never_enter_backup_or_restore(self):
        first=self.frame();original=self.repo.backup
        def snapshot_then_capture(destination):result=original(destination);self.frame();return result
        with patch.object(self.repo,'backup',side_effect=snapshot_then_capture):backup=self.job()
        self.assertEqual(backup['status'],'complete',backup)
        self.assertEqual(backup['result']['report']['images_verified'],1);self.assertEqual(len(self.repo.get_recent_images()),2)
        restored=self.job('restore',backup['request_id']);destination=self.root/'storage'/restored['result']['destination']
        with closing(sqlite3.connect(destination/'database.sqlite')) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM images').fetchone()[0],1)
        self.assertTrue((destination/'images'/first['file_path']).exists())

    def test_missing_image_backup_is_explicitly_incomplete_and_not_downloadable(self):
        image=self.frame();(self.root/'images'/image['file_path']).unlink()  # owned temporary fault fixture only
        job=self.job();self.assertEqual(job['status'],'incomplete',job);self.assertFalse(job['result']['verified'])
        self.assertTrue(job['result']['report']['image_errors']);self.assertIsNone(job['download_url'])
        with self.assertRaises(ValueError):self.storage.download(job['request_id'])
        restore=self.job('restore',job['request_id']);self.assertEqual(restore['status'],'incomplete')
        self.assertFalse(list((self.root/'storage'/'restores').rglob('offline-restore')))

    def test_corrupt_image_and_changed_image_cannot_make_usable_backup(self):
        image=self.frame();path=self.root/'images'/image['file_path'];path.write_bytes(b'broken')
        job=self.job();self.assertEqual(job['status'],'incomplete')
        with patch.object(self.history,'_image',side_effect=ValueError('changed during read')):job=self.job()
        self.assertEqual(job['status'],'incomplete');self.assertTrue(path.exists())

    def test_corrupted_archive_hash_verify_and_restore_refuse(self):
        backup=self.job();path=self.package(backup)
        with path.open('r+b') as stream:stream.write(b'bad')
        verified=self.job('verify',backup['request_id']);self.assertEqual(verified['status'],'incomplete')
        self.assertIn('SHA-256',verified['result']['errors'][0])
        with self.assertRaises(ValueError):self.storage.download(backup['request_id'])
        restored=self.job('restore',backup['request_id']);self.assertEqual(restored['status'],'incomplete')

    def test_unexpected_missing_and_inconsistent_members_are_rejected(self):
        self.frame();backup=self.job()
        def remove(members):members.pop(next(name for name in members if name.startswith('images/')))
        self.assertFalse(self.verify(self.rewrite(backup,remove))['valid'])
        def extra(members):members['extra.txt']=b'extra'
        self.assertFalse(self.verify(self.rewrite(backup,extra))['valid'])
        def inconsistent(members):
            manifest=json.loads(members['manifest.json']);manifest['images'][0]['image_id']=999;members['manifest.json']=canonical(manifest).encode()
        self.assertIn('inconsistency',self.verify(self.rewrite(backup,inconsistent))['errors'][0])

    def test_archive_traversal_absolute_reserved_case_and_zip_symlinks_denied(self):
        for name in ('../escape','/absolute','C:/windows','images/../escape','images\\file','images/NUL.jpg','images/a.','images//a'):
            with self.assertRaises(ValueError):safe_member(name)
        backup=self.job()
        for name in ('../escape','/absolute','DATABASE.SQLITE'):
            def inject(members):members[name]=b'bad'
            self.assertFalse(self.verify(self.rewrite(backup,inject))['valid'])
        path=self.root/'storage'/'link.zip'
        with zipfile.ZipFile(path,'x') as package:
            info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;package.writestr(info,'../outside')
        self.assertFalse(self.verify(path)['valid'])

    def test_schema_mismatch_schema_drift_fk_corruption_and_missing_db(self):
        self.frame();backup=self.job()
        def bad_schema(members):
            manifest=json.loads(members['manifest.json']);manifest['schema_version']=VERSION+1;members['manifest.json']=canonical(manifest).encode()
        self.assertIn('schema',self.verify(self.rewrite(backup,bad_schema))['errors'][0])
        for sql in ('PRAGMA user_version=999','CREATE TABLE unexpected(x)','PRAGMA foreign_keys=OFF;UPDATE images SET plant_id=999'):
            def modify(members):
                path=self.root/('bad-'+uuid.uuid4().hex+'.sqlite');path.write_bytes(members['database.sqlite'])
                with closing(sqlite3.connect(path)) as db:db.executescript(sql);db.commit()
                members['database.sqlite']=path.read_bytes();manifest=json.loads(members['manifest.json']);manifest['members']['database.sqlite']=dict(sha256=sha(members['database.sqlite']),size_bytes=len(members['database.sqlite']));members['manifest.json']=canonical(manifest).encode()
            self.assertFalse(self.verify(self.rewrite(backup,modify))['valid'])
        self.assertFalse(self.verify(self.rewrite(backup,lambda members:members.pop('database.sqlite')))['valid'])

    def test_idempotent_concurrent_requests_and_single_owner(self):
        request_id=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.storage.start(request_id,{'kind':'backup'}),range(4)))
        self.storage.wait();self.assertEqual(self.storage.job(request_id)['attempt'],1)
        self.assertTrue(all(r['request_id']==request_id for r in results))
        with self.assertRaises(ValueError):self.storage.start(request_id,{'kind':'verify','backup_id':request_id})
        with self.assertRaises(ExportBusy):StorageService(self.history,self.root/'second-storage',software_version='other')

    def test_export_and_backup_are_independent_and_gateway_is_not_locked(self):
        entered=threading.Event();release=threading.Event();original=self.repo.backup
        def block(destination):entered.set();release.wait(5);return original(destination)
        with patch.object(self.repo,'backup',side_effect=block):
            self.storage.start(str(uuid.uuid4()),{'kind':'backup'});self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(ExportBusy):self.storage.start(str(uuid.uuid4()),{'kind':'backup'})
                self.assertIsInstance(self.gateway.state.snapshot(),dict);self.assertEqual(self.actuator.commands,[])
            finally:release.set();self.storage.wait()
        request_id=str(uuid.uuid4());self.history.start(request_id,{'resources':['experiments']});self.history.wait()
        self.assertEqual(self.history.job(request_id)['status'],'complete')

    def test_disk_full_quota_deadline_and_partial_backup_never_delete(self):
        image=self.frame();kept=self.root/'exports'/'keep.txt';kept.write_bytes(b'keep')
        with patch('services.storage_service.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):job=self.job()
        self.assertEqual(job['status'],'failed');self.assertIn('space',job['error'])
        with patch.object(self.repo,'backup',side_effect=OSError('disk full')):job=self.job()
        self.assertEqual(job['status'],'failed')
        self.storage.max_bytes=100;self.assertEqual(self.job()['status'],'failed');self.storage.max_bytes=256*1024*1024
        self.storage.max_seconds=-1;self.assertEqual(self.job()['status'],'failed');self.storage.max_seconds=60
        self.assertTrue((self.root/'images'/image['file_path']).exists());self.assertEqual(kept.read_bytes(),b'keep')
        self.storage.max_total_bytes=0
        with self.assertRaises(ExportBusy):self.storage.start(str(uuid.uuid4()),{'kind':'backup'})

    def test_partial_archive_write_and_restore_failure_are_retained(self):
        self.frame();original=zipfile.ZipFile.writestr
        def partial(target,name,data,*args,**kwargs):original(target,name,data[:8],*args,**kwargs);raise OSError('partial write disk full')
        with patch.object(zipfile.ZipFile,'writestr',new=partial):failed=self.job()
        self.assertEqual(failed['status'],'failed');self.assertTrue(list((self.root/'storage').rglob('package.part')))
        backup=self.job();original_copy=self.storage._copy_member
        def fail_restore(package,name,path,check):
            original_copy(package,name,path,check)
            if 'offline-restore' in path.parts:raise OSError('Power loss after a restore file write')
        with patch.object(self.storage,'_copy_member',side_effect=fail_restore):failed=self.job('restore',backup['request_id'])
        self.assertEqual(failed['status'],'failed');self.assertFalse(list((self.root/'storage'/'restores').rglob('RECOVERY_REPORT.json')))
        old=list((self.root/'storage').rglob('*'));self.storage.start(failed['request_id'],failed['definition'],retry=True);self.storage.wait()
        self.assertEqual(self.storage.job(failed['request_id'])['status'],'complete');self.assertTrue(all(p.exists() for p in old))

    def test_power_loss_after_publication_before_receipt_is_interrupted_on_restart(self):
        original=self.repo._write
        def lose_receipt(sql,args=()):
            if 'storage_jobs' in sql and ('result_json=?' in sql or "status='failed'" in sql):raise sqlite3.OperationalError('simulated power loss')
            return original(sql,args)
        with patch.object(self.repo,'_write',side_effect=lose_receipt):job=self.job()
        self.assertEqual(job['status'],'running');self.assertIsNone(job['download_url']);self.assertTrue(list((self.root/'storage').rglob('package.zip')))
        self.storage.close();self.storage=StorageService(self.history,self.root/'storage',software_version='m7-fixture');self.addCleanup(self.storage.close)
        job=self.storage.job(job['request_id']);self.assertEqual(job['status'],'interrupted')
        self.storage.start(job['request_id'],job['definition'],retry=True);self.storage.wait()
        self.assertEqual(self.storage.job(job['request_id'])['attempt'],2);self.assertEqual(self.storage.job(job['request_id'])['status'],'complete')

    def test_preexisting_restore_files_never_overwritten(self):
        backup=self.job();request_id=str(uuid.uuid4());directory=self.root/'storage'/'restores'/request_id/'attempt-1';directory.mkdir(parents=True)
        marker=directory/'keep.txt';marker.write_bytes(b'existing')
        job=self.job('restore',backup['request_id'],request_id);self.assertEqual(job['status'],'failed');self.assertEqual(marker.read_bytes(),b'existing')
        for bad in ({'kind':'restore','backup_id':backup['request_id'],'destination':str(self.repo.path)},{'kind':'delete'},{'kind':'backup','delete':True}):
            with self.assertRaises(ValueError):self.storage.definition(bad)

    def test_insufficient_restore_space_fails_before_offline_copy(self):
        self.frame();backup=self.job()
        with patch('services.storage_service.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):restore=self.job('restore',backup['request_id'])
        self.assertEqual(restore['status'],'failed');self.assertIn('space',restore['error'])
        self.assertFalse(list((self.root/'storage'/'restores').rglob('offline-restore')))

    def test_restore_power_loss_after_copy_before_receipt_does_not_adopt_files(self):
        self.frame();backup=self.job();original=self.repo._write
        def lose(sql,args=()):
            if 'storage_jobs' in sql and ('result_json=?' in sql or "status='failed'" in sql):raise sqlite3.OperationalError('Power loss before restore receipt')
            return original(sql,args)
        with patch.object(self.repo,'_write',side_effect=lose):restore=self.job('restore',backup['request_id'])
        self.assertEqual(restore['status'],'running');self.assertTrue(list((self.root/'storage'/'restores').rglob('RECOVERY_REPORT.json')))
        self.storage.close();self.storage=StorageService(self.history,self.root/'storage',software_version='m7-fixture');self.addCleanup(self.storage.close)
        self.assertEqual(self.storage.job(restore['request_id'])['status'],'interrupted')
        self.storage.start(restore['request_id'],restore['definition'],retry=True);self.storage.wait()
        self.assertEqual(self.storage.job(restore['request_id'])['status'],'complete');self.assertEqual(self.actuator.commands,[])

    def test_symlink_source_and_restore_root_are_rejected(self):
        image=self.frame();path=self.root/'images'/image['file_path'];outside=self.root/'outside.jpg';outside.write_bytes(path.read_bytes());path.unlink()
        try:path.symlink_to(outside)
        except OSError:
            if os.name!='nt':raise
            self.skipTest('Windows symlink privilege unavailable; POSIX CI must pass')
        self.assertEqual(self.job()['status'],'incomplete');self.assertEqual(self.storage.inventory()['categories']['images']['complete'],False)
        alias=self.root/'alias';alias.symlink_to(self.root/'storage',target_is_directory=True)
        with self.assertRaises(ValueError):StorageService(self.history,alias,software_version='other')

    def test_inventory_reports_failed_database_reads_without_fabricated_estimate(self):
        with patch.object(self.repo,'connection',side_effect=sqlite3.OperationalError('database failure')):inventory=self.storage.inventory()
        self.assertEqual(inventory['state'],'degraded');self.assertEqual(inventory['backup_estimate']['state'],'unavailable')
        self.assertIsInstance(inventory['volume']['free_bytes'],int)

    def test_v7_upgrade_backup_preserves_records_and_validates_current_schema(self):
        import services.sqlite_repository as module
        folder=self.root/'v7';folder.mkdir()
        for source in sorted(MIGRATIONS.glob('*.sql'))[:7]:shutil.copyfile(source,folder/source.name)
        path=self.root/'v7.sqlite'
        with patch.object(module,'MIGRATIONS',folder),patch.object(module,'VERSION',7):legacy=SQLiteRepository(path,workspace_root=self.root,create=True)
        legacy.load_seed_fixture();upgraded=SQLiteRepository(path,workspace_root=self.root)
        self.assertEqual(len(upgraded.backups),1)
        with closing(sqlite3.connect(upgraded.backups[0])) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)
        snapshot=upgraded.backup(self.root/'upgrade-check.sqlite');self.assertTrue(SQLiteRepository.validate_snapshot(snapshot))
        self.assertEqual(len(upgraded.get_sensor_history('air_temperature')),3)


class StorageHttpTests(unittest.TestCase):
    setUp=StorageTests.setUp
    def test_host_boundary_inventory_jobs_verify_restore_and_download(self):
        import app
        from services.control_runtime import install_simulation_gateway
        install_simulation_gateway(self.gateway);old=dict(app.app.config);self.addCleanup(lambda:app.app.config.update(old))
        app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True,GERM_STORAGE_SERVICE=self.storage)
        client=app.app.test_client();headers={'X-GERM-Token':app.control_token}
        self.assertEqual(client.get('/api/storage').status_code,200);self.assertIn(b'storage-backup',client.get('/settings').data)
        data={'request_id':str(uuid.uuid4()),'definition':{'kind':'backup'}}
        self.assertEqual(client.post('/api/storage/jobs',json=data).status_code,403)
        self.assertEqual(client.post('/api/storage/jobs',json=data,headers=headers).status_code,202);self.storage.wait()
        response=client.get('/api/storage/jobs/'+data['request_id']+'/download');self.assertEqual(response.status_code,200);self.assertEqual(sha(response.data),response.headers['X-GERM-SHA256'])
        self.assertEqual(client.get('/api/storage/jobs/'+data['request_id']).json['status'],'complete')
        self.assertEqual(client.post('/api/storage/jobs/'+data['request_id']+'/retry',json={'retry':1},headers=headers).status_code,400)
        app.app.config['GERM_SIMULATION']=False;self.assertEqual(client.post('/api/storage/jobs',json=data,headers=headers).status_code,403)
        app.app.config['GERM_STORAGE_SERVICE']=None;self.assertEqual(client.get('/api/storage').status_code,503)


if __name__=='__main__':unittest.main(verbosity=2)
