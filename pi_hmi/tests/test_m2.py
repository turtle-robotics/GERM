"""SQLite migrations/repository/restart recovery on temporary host files only."""
from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.sqlite_repository import SQLiteRepository, MIGRATIONS, VERSION
from services.restart_service import attach_restart_store
from m1_fixtures import fixture,confirmed,feed

STAMP='2026-11-15T00:00:00+00:00'


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.repo=SQLiteRepository(self.root/'germ.sqlite',workspace_root=self.root,create=True)

    def test_empty_migration_repeat_pragmas_indexes_and_explicit_seed(self):
        with self.repo.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],VERSION)
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0],0)
            indexes={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertTrue({'inference_image_model','maintenance_component_time','readings_sensor_time'}<=indexes)
        self.repo.load_seed_fixture()
        reopened=SQLiteRepository(self.repo.path,workspace_root=self.root)
        self.assertEqual(len(reopened.get_experiments()),1)
        self.assertTrue(reopened.integrity_check())

    def test_v1_upgrade_preserves_rows_and_verified_preupgrade_backup(self):
        old=self.root/'legacy.sqlite'
        with closing(sqlite3.connect(old)) as db:
            db.executescript((MIGRATIONS/'001_baseline.sql').read_text())
            db.executescript((MIGRATIONS.parent/'tests/fixtures/seed.sql').read_text())
        repo=SQLiteRepository(old,workspace_root=self.root)
        self.assertEqual(len(repo.backups),1)
        with closing(sqlite3.connect(repo.backups[0])) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM sensor_readings').fetchone()[0],4)
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(len(repo.get_sensor_history('air_temperature')),3)
        self.assertEqual(repo.get_experiments()[0]['notes'],None)

    def test_interrupted_upgrade_rolls_back_and_unknown_schema_is_not_repaired(self):
        import services.sqlite_repository as module
        old=self.root/'interrupted.sqlite'
        with closing(sqlite3.connect(old)) as db:db.executescript((MIGRATIONS/'001_baseline.sql').read_text())
        original=module._apply
        calls=[]
        def fail(db,script):
            original(db,script)
            calls.append(script)
            # expected-schema construction only applies v1; actual v2 must roll back.
            if 'CREATE TABLE restart_state' in script:raise OSError('Injected migration interruption')
        with patch.object(module,'_apply',side_effect=fail),self.assertRaises(OSError):SQLiteRepository(old,workspace_root=self.root)
        with closing(sqlite3.connect(old)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertNotIn('notes',[r[1] for r in db.execute('PRAGMA table_info(experiments)')])
        upgraded=SQLiteRepository(old,workspace_root=self.root)
        with upgraded.connection() as db:db.execute('CREATE TABLE unexpected(x)')
        with self.assertRaises(ValueError):SQLiteRepository(old,workspace_root=self.root)

    def test_future_checksum_and_corruption_are_rejected(self):
        with self.repo.connection() as db:db.execute("UPDATE migration_history SET sha256='changed' WHERE version=1")
        with self.assertRaises(ValueError):SQLiteRepository(self.repo.path,workspace_root=self.root)
        with self.repo.connection() as db:db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):SQLiteRepository(self.repo.path,workspace_root=self.root)
        bad=self.root/'corrupt.sqlite';bad.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):SQLiteRepository(bad,workspace_root=self.root)

    def test_repository_reads_bounds_ack_and_parameterization(self):
        self.repo.load_seed_fixture()
        self.assertEqual(self.repo.get_latest_sensor_values()['humidity']['value'],None)
        self.assertEqual(self.repo.get_sensor_history("air_temperature' OR 1=1 --"),[])
        self.assertEqual(len(self.repo.get_sensor_history('air_temperature','2026-10-01T00:00:00+00:00',None,1)),3)
        self.assertEqual(self.repo.get_experiment_data(1)['reading_count'],4)
        self.assertIsNone(self.repo.get_experiment_data(999))
        self.assertTrue(self.repo.acknowledge_alert(1))
        self.assertIsNone(self.repo.get_active_alerts()[0]['clear_time_utc'])
        self.assertFalse(self.repo.acknowledge_alert(999))
        with self.assertRaises(ValueError):self.repo.get_alert_history(1001)
        for i in range(1002):
            self.repo.log_sensor_reading(dict(sensor_id='humidity',timestamp_utc=STAMP,value=None,quality_flag='missing'))
        self.assertEqual(len(self.repo.get_sensor_history('humidity')),1000)

    def test_validation_foreign_keys_and_image_metadata(self):
        self.repo.load_seed_fixture()
        for reading in [dict(value=float('nan'),quality_flag='good'),dict(value=2,quality_flag='invalid'),dict(value=1,quality_flag='good',timestamp_utc='2026-01-01')]:
            data=dict(sensor_id='humidity',timestamp_utc=STAMP);data.update(reading)
            with self.assertRaises(ValueError):self.repo.log_sensor_reading(data)
        with self.assertRaises(sqlite3.IntegrityError):self.repo.log_sensor_reading(dict(sensor_id='unknown',timestamp_utc=STAMP,value=None,quality_flag='missing'))
        image=dict(file_path='2026/11/15/test.jpg',timestamp_utc=STAMP,sha256='a'*64,size_bytes=100,width_px=640,height_px=480,capture_reason='manual')
        for path in ('../x','/tmp/x','C:/x','a\\b'):
            with self.assertRaises(ValueError):self.repo.record_image(dict(image,file_path=path))
        self.assertEqual(self.repo.record_image(image),1)
        self.assertEqual(self.repo.get_recent_images()[0]['sha256'],'a'*64)
        with self.assertRaises(ValueError):self.repo.record_actuator_event(dict(actuator='pump',timestamp_utc=STAMP,requested_state='on',source='test',firmware_confirmed=True))

    def test_backup_restore_reopen_and_never_overwrite(self):
        self.repo.load_seed_fixture()
        self.repo.save_restart_state(dict(profile='basil',maintenance=True,estop_latched=False),0)
        backup=self.repo.backup(self.root/'backup.sqlite')
        with self.assertRaises(FileExistsError):self.repo.backup(backup)
        recovered=SQLiteRepository.restore(backup,self.root/'restored.sqlite',workspace_root=self.root)
        self.assertEqual(recovered.load_restart_state()['profile'],'basil')
        self.assertEqual(len(recovered.get_active_alerts()),1)
        self.assertTrue(recovered.integrity_check())
        with self.assertRaises(FileExistsError):SQLiteRepository.restore(backup,recovered.path,workspace_root=self.root)
        with self.assertRaises(ValueError):self.repo.backup(self.root.parent/'outside.sqlite')

    def test_lock_failure_is_visible_and_cannot_report_success(self):
        self.repo.load_seed_fixture()
        with self.repo.connection() as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):self.repo.acknowledge_alert(1)
            writer.execute('ROLLBACK')
        self.assertEqual(self.repo.status,'error')
        self.assertIsNone(self.repo.get_active_alerts()[0]['ack_time_utc'])

    def test_restart_generation_cas_rejects_stale_writer(self):
        state=dict(profile='basil',maintenance=True,estop_latched=True)
        self.assertEqual(self.repo.save_restart_state(state,0),1)
        with self.assertRaises(ValueError):self.repo.save_restart_state(dict(state,maintenance=False),0)
        self.assertTrue(self.repo.load_restart_state()['maintenance'])

    def test_recovery_restores_intent_but_never_permission_or_old_health(self):
        self.repo.save_restart_state(dict(profile='basil',maintenance=True,estop_latched=True),0)
        clock,state,adapter,gateway=fixture(started=False)
        coordinator=attach_restart_store(gateway,self.repo)
        self.assertTrue(state.snapshot()['persistence']['restart_recovery_verified'])
        self.assertTrue(state.maintenance);self.assertTrue(state.estop_latched)
        self.assertFalse(state.snapshot()['controller_connected'])
        self.assertFalse(state.startup_complete)
        for _ in range(2):
            clock.advance(0.1);feed(gateway)
        state.complete_startup()
        adapter.commands.clear()
        self.assertFalse(gateway.command('PUMP_ON',source='automatic',authority=gateway.automatic_authority)['allowed'])
        self.assertEqual(adapter.commands,[])
        self.assertTrue(confirmed(gateway,'exit_maintenance')['allowed'])
        self.assertTrue(confirmed(gateway,'start')['allowed'])
        self.assertFalse(state.restart_required)
        self.assertFalse(self.repo.load_restart_state()['maintenance'])
        self.assertTrue(self.repo.load_restart_state()['restart_required'])

    def test_checkpoint_repeats_when_profile_changes_during_commit(self):
        _,state,_,gateway=fixture()
        store=attach_restart_store(gateway,self.repo)
        first=True
        original=self.repo.save_restart_state
        def interleaved(fields,generation):
            nonlocal first
            saved=original(fields,generation)
            if first:
                first=False;state.set_profile('spearmint')
            return saved
        with patch.object(self.repo,'save_restart_state',side_effect=interleaved):self.assertTrue(store.checkpoint())
        self.assertEqual(self.repo.load_restart_state()['profile'],'spearmint')
        self.assertEqual(self.repo.load_restart_state()['generation'],2)
        self.assertTrue(state.restart_required)

    def test_recovery_read_failure_is_visible_and_cannot_enable_start(self):
        _,state,adapter,gateway=fixture()
        with patch.object(self.repo,'load_restart_state',side_effect=OSError('corrupt read')):
            attach_restart_store(gateway,self.repo)
        self.assertTrue(state.maintenance)
        self.assertIsNone(state.profile)
        self.assertEqual(state.snapshot()['persistence']['state'],'error')
        adapter.commands.clear()
        self.assertFalse(confirmed(gateway,'start')['allowed'])
        self.assertEqual(adapter.commands,[])

    def test_failed_restart_store_inhibits_and_safe_stop_ignores_slow_checkpoint(self):
        _,state,adapter,gateway=fixture()
        store=attach_restart_store(gateway,self.repo)
        with patch.object(self.repo,'save_restart_state',side_effect=OSError('disk full')):
            self.assertFalse(store.checkpoint())
            adapter.commands.clear()
            self.assertFalse(gateway.command('PUMP_ON',source='automatic',authority=gateway.automatic_authority)['allowed'])
            self.assertEqual(adapter.commands,[])
        self.assertTrue(store.checkpoint())
        self.assertTrue(state.restart_required)
        entered,release=threading.Event(),threading.Event()
        original=self.repo.save_restart_state
        def slow(*args):entered.set();release.wait(2);return original(*args)
        state.set_profile('spearmint')
        with patch.object(self.repo,'save_restart_state',side_effect=slow):
            thread=threading.Thread(target=store.checkpoint);thread.start()
            self.assertTrue(entered.wait(1))
            try:self.assertTrue(gateway.command('PUMP_OFF',source='touchscreen',authority=gateway.operator_authority)['firmware_confirmed'])
            finally:release.set();thread.join(2)
        self.assertFalse(thread.is_alive())


if __name__=='__main__':unittest.main(verbosity=2)
