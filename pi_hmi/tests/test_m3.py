"""Durable event commits, retry/recovery and command/storage isolation."""
import copy
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.sqlite_repository import SQLiteRepository,MIGRATIONS
from services.event_repository import EventValidationError,EventConflictError
from services.event_service import HostPersistenceRuntime,EventPipeline
from m1_fixtures import fixture,feed,confirmed


def envelope(kind='test',payload=None):
    return dict(schema_version=1,event_id=str(uuid.uuid4()),timestamp_utc='2026-11-15T00:00:00+00:00',
                event_type=kind,source='test',software_version='m3-test',experiment_id=None,payload=payload or {})


class DurableEventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.repo=SQLiteRepository(self.root/'events.sqlite',workspace_root=self.root,create=True)
        self.clock,self.state,self.adapter,self.gateway=fixture(started=False)
        self.runtime=HostPersistenceRuntime(self.gateway,self.repo)
        for _ in range(2):self.clock.advance(0.1);feed(self.gateway)
        self.state.complete_startup()
        self.assertTrue(self.runtime.tick())
        self.assertTrue(confirmed(self.gateway,'start')['accepted'])
        self.assertTrue(self.runtime.tick())
        self.adapter.commands.clear()

    def rows(self,table):return self.repo._rows('SELECT * FROM '+table)

    def test_event_retry_same_id_is_idempotent_and_reopen_keeps_exact_envelope(self):
        event=envelope(payload={'nullable':None,'value':1})
        self.assertTrue(self.repo.log_event(event));self.assertTrue(self.repo.log_event(copy.deepcopy(event)))
        reopened=SQLiteRepository(self.repo.path,workspace_root=self.root)
        self.assertTrue(reopened.log_event(event))
        rows=reopened._rows('SELECT * FROM system_events WHERE event_id=?',(event['event_id'],))
        self.assertEqual(len(rows),1)
        self.assertEqual(json.loads(rows[0]['envelope_json'])['payload'],event['payload'])
        changed=copy.deepcopy(event);changed['payload']['value']=2
        with self.assertRaises(EventConflictError):self.repo.log_event(changed)

    def test_invalid_envelopes_cannot_be_acknowledged(self):
        variants=[dict(schema_version=True),dict(event_id='not-uuid'),dict(timestamp_utc='2026-01-01'),
                  dict(timestamp_utc='2026-01-01T01:00:00+01:00'),dict(payload={'nan':float('nan')}),dict(extra='not silently dropped')]
        for change in variants:
            event=envelope();event.update(change)
            with self.assertRaises(EventValidationError):self.repo.log_event(event)

    def test_actuator_accept_ack_failure_and_reject_are_distinct(self):
        result=confirmed(self.gateway,'command',{'command':'PUMP_ON'})
        self.assertFalse(result['logged']);self.assertFalse(result['physically_verified'])
        self.assertIn('event_id',result)
        self.assertEqual(self.state.snapshot()['logging']['state'],'pending')
        self.assertTrue(self.runtime.tick())
        accepted=[r for r in self.rows('actuator_events') if r['request_id']==result['request_id']]
        self.assertEqual(len(accepted),1)
        self.assertEqual(accepted[0]['firmware_confirmed'],1)
        self.assertEqual(accepted[0]['physically_verified'],0)
        self.assertIsNotNone(accepted[0]['acknowledged_at_utc'])
        before=len(self.rows('actuator_events'))
        self.gateway.command('PUMP_ON',source='automatic',authority=object())
        self.assertTrue(self.runtime.tick())
        self.assertEqual(len(self.rows('actuator_events')),before)
        self.adapter.fail=True
        failed=self.gateway.command('PUMP_OFF',source='touchscreen',authority=self.gateway.operator_authority)
        self.assertTrue(failed['accepted']);self.assertFalse(failed['firmware_confirmed'])
        self.assertTrue(self.runtime.tick())
        row=[r for r in self.rows('actuator_events') if r['request_id']==failed['request_id']][0]
        self.assertEqual(row['firmware_confirmed'],0);self.assertIsNone(row['reported_state'])

    def test_projection_failure_rolls_back_envelope_and_retry_commits_once(self):
        import services.event_repository as module
        event=envelope('sensor_sample',dict(sensor_id='humidity',reading=dict(value=50,quality_flag='good')))
        original=module._project
        def fail(db,event):original(db,event);raise OSError('Injected disk full before COMMIT')
        with patch.object(module,'_project',side_effect=fail),self.assertRaises(OSError):self.repo.log_event(event)
        self.assertEqual(self.repo._rows('SELECT * FROM system_events WHERE event_id=?',(event['event_id'],)),[])
        self.assertEqual(self.repo._rows('SELECT * FROM sensor_readings WHERE system_event_id=?',(event['event_id'],)),[])
        self.assertTrue(self.repo.log_event(event));self.assertTrue(self.repo.log_event(event))
        self.assertEqual(len(self.repo._rows('SELECT * FROM sensor_readings WHERE system_event_id=?',(event['event_id'],))),1)

    def test_sensor_fault_records_invalid_null_and_safe_state_outcomes(self):
        self.clock.advance(0.1)
        self.gateway.observe_sensor('humidity',float('nan'),self.clock.utc().isoformat(),source='fault injection')
        self.assertIn('STOP',self.adapter.commands)
        self.assertTrue(self.runtime.tick())
        faults=[r for r in self.rows('sensor_readings') if r['sensor_id']=='humidity' and r['quality_flag']=='invalid']
        self.assertTrue(faults);self.assertIsNone(faults[-1]['value'])
        events=[json.loads(r['payload_json']) for r in self.rows('system_events') if r['event_type']=='sensor_quality']
        self.assertTrue(any(p.get('raw_value')=='nan' for p in events))
        self.assertFalse(self.gateway.command('PUMP_ON',source='automatic',authority=self.gateway.automatic_authority)['allowed'])

    def test_maintenance_and_recovery_events_survive_reopen_without_restart(self):
        entered=confirmed(self.gateway,'enter_maintenance')
        self.assertTrue(entered['accepted']);self.assertTrue(self.runtime.tick())
        self.assertEqual(self.rows('maintenance_events')[-1]['action'],'enter_maintenance')
        _,state,adapter,gateway=fixture(started=False)
        runtime=HostPersistenceRuntime(gateway,SQLiteRepository(self.repo.path,workspace_root=self.root))
        self.assertTrue(state.maintenance);self.assertTrue(state.restart_required)
        self.assertFalse(state.snapshot()['controller_connected'])
        adapter.commands.clear()
        self.assertFalse(gateway.command('PUMP_ON',source='automatic',authority=gateway.automatic_authority)['allowed'])
        self.assertEqual(adapter.commands,[])
        self.assertTrue(runtime.tick())
        self.assertTrue(any(r['event_type']=='restart_recovery' for r in self.rows('system_events')))

    def test_failed_logger_retains_event_ids_then_retries_without_granting_permission(self):
        confirmed(self.gateway,'pause')
        pending={e['event_id'] for e in self.state.events}
        with patch.object(self.repo,'log_event',side_effect=OSError('disk full')):
            self.assertFalse(self.runtime.tick())
            self.assertEqual(self.state.snapshot()['logging']['state'],'error')
            self.assertTrue(pending<={e['event_id'] for e in self.state.events})
            self.adapter.commands.clear()
            self.assertFalse(self.gateway.command('PUMP_ON',source='automatic',authority=self.gateway.automatic_authority)['allowed'])
            self.assertEqual(self.adapter.commands,[])
        self.assertTrue(self.runtime.tick())
        self.assertTrue(self.state.restart_required)
        self.assertTrue(pending<={r['event_id'] for r in self.rows('system_events')})

    def test_slow_logger_and_concurrent_drains_do_not_block_safe_stop(self):
        self.state.emit('test',{})
        entered,release=threading.Event(),threading.Event()
        original=self.repo.log_event
        def slow(event):entered.set();release.wait(2);return original(event)
        with patch.object(self.repo,'log_event',side_effect=slow):
            thread=threading.Thread(target=self.runtime.events.drain);thread.start()
            self.assertTrue(entered.wait(1))
            try:
                self.assertFalse(self.runtime.events.drain())
                result=self.gateway.command('PUMP_OFF',source='touchscreen',authority=self.gateway.operator_authority)
                self.assertTrue(result['firmware_confirmed'])
            finally:release.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertTrue(self.runtime.tick())

    def test_poison_event_is_visible_and_does_not_prevent_valid_commits(self):
        invalid=self.state.emit('test',{'nonfinite':float('nan')})
        valid=self.state.emit('test',{'valid':True})
        self.assertFalse(self.runtime.events.drain())
        self.assertEqual(self.state.snapshot()['logging']['poison_events'],1)
        self.assertIn(invalid['event_id'],{e['event_id'] for e in self.state.events})
        self.assertIn(valid['event_id'],{e['event_id'] for e in self.rows('system_events')})

    def test_queue_loss_and_unacknowledged_commit_never_show_durable(self):
        self.state.events.clear()
        from collections import deque
        self.state.events=deque(maxlen=2)
        for _ in range(3):self.state.emit('test',{})
        self.assertEqual(self.state.dropped_events,1)
        self.assertFalse(self.runtime.events.drain())
        self.assertEqual(self.state.snapshot()['logging']['state'],'error')
        self.state.emit('test',{})
        with patch.object(self.repo,'log_event',return_value=False):self.assertFalse(self.runtime.events.drain())
        self.assertTrue(self.state.events)

    def test_locked_database_has_no_false_receipt_and_preserves_retry(self):
        event=self.state.emit('test',{})
        with self.repo.connection() as writer:
            writer.execute('BEGIN IMMEDIATE')
            try:self.assertFalse(self.runtime.events.drain())
            finally:writer.execute('ROLLBACK')
        self.assertIn(event['event_id'],{e['event_id'] for e in self.state.events})
        self.assertTrue(self.runtime.tick())

    def test_process_loss_before_commit_is_not_claimed_as_durable(self):
        event=self.state.emit('uncommitted_before_crash',{})
        self.assertEqual(self.state.snapshot()['logging']['state'],'pending')
        reopened=SQLiteRepository(self.repo.path,workspace_root=self.root)
        self.assertEqual(reopened._rows('SELECT * FROM system_events WHERE event_id=?',(event['event_id'],)),[])

    def test_explicit_sensor_snapshot_and_dictionary_conflict(self):
        self.runtime.record_sensor_snapshot();self.assertTrue(self.runtime.tick())
        samples=[r for r in self.rows('system_events') if r['event_type']=='sensor_sample']
        self.assertEqual(len(samples),6)
        self.repo._write("UPDATE sensors SET unit='wrong' WHERE sensor_id='humidity'")
        _,state,_,gateway=fixture()
        with self.assertRaises(ValueError):HostPersistenceRuntime(gateway,self.repo)
        self.assertTrue(state.restart_required)
        self.assertEqual(state.persistence_status,'error')

    def test_concurrent_stop_revokes_start_waiting_for_latch_checkpoint(self):
        self.clock.advance(0.1)
        self.gateway.observe_sensor('estop',True,self.clock.utc().isoformat(),source='test')
        for _ in range(2):self.clock.advance(0.1);feed(self.gateway)
        self.assertTrue(self.runtime.tick())
        entered,release=threading.Event(),threading.Event();results=[]
        original=self.repo.save_restart_state
        def slow(*args):entered.set();release.wait(2);return original(*args)
        with patch.object(self.repo,'save_restart_state',side_effect=slow):
            thread=threading.Thread(target=lambda:results.append(confirmed(self.gateway,'start')))
            thread.start();self.assertTrue(entered.wait(1))
            try:
                self.assertTrue(self.gateway.command('PUMP_OFF',source='touchscreen',authority=self.gateway.operator_authority)['accepted'])
            finally:release.set();thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(self.state.restart_required)
        self.assertNotEqual(self.state.snapshot()['system_state'],'NORMAL')
        self.assertTrue(self.runtime.tick())
        self.assertTrue(self.state.restart_required)

    def test_concurrent_same_event_retry_has_one_durable_row(self):
        event=envelope();barrier=threading.Barrier(5);errors=[]
        def writer():
            barrier.wait()
            try:self.repo.log_event(event)
            except sqlite3.OperationalError:pass  # A busy failure must retry the same ID.
            except Exception as exc:errors.append(exc)
        threads=[threading.Thread(target=writer) for _ in range(4)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(2);self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[]);self.assertTrue(self.repo.log_event(event))
        self.assertEqual(len(self.repo._rows('SELECT * FROM system_events WHERE event_id=?',(event['event_id'],))),1)

    def test_http_reports_pending_without_legacy_duplicate_write(self):
        from m1_http_harness import client_fixture,confirmation
        application,client,headers,clock,state,adapter,gateway=client_fixture()
        runtime=HostPersistenceRuntime(gateway,self.repo)
        for _ in range(2):clock.advance(0.1);feed(gateway)
        state.complete_startup();runtime.tick();confirmed(gateway,'start');runtime.tick()
        context=confirmation(client,headers,'command',{'command':'PUMP_ON'})
        with patch.object(application,'record_control_request') as legacy:
            response=client.post('/api/pump',json=dict(state='on',confirmation_id=context['confirmation_id'],expected_state_revision=context['state_revision']),headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json['logged'])
            self.assertEqual(response.json['logging_status'],'pending')
            legacy.assert_not_called()
        self.assertTrue(runtime.tick())
        event_id=response.json['event_id']
        self.assertEqual(len(self.repo._rows('SELECT * FROM actuator_events WHERE system_event_id=?',(event_id,))),1)

    def test_existing_v2_migrates_with_backup_and_preserves_events(self):
        import services.sqlite_repository as module
        migration_dir=self.root/'v2';migration_dir.mkdir()
        for name in ('001_baseline.sql','002_repository_recovery.sql'):shutil.copyfile(MIGRATIONS/name,migration_dir/name)
        with patch.object(module,'MIGRATIONS',migration_dir),patch.object(module,'VERSION',2):
            old=SQLiteRepository(self.root/'old.sqlite',workspace_root=self.root,create=True)
            old.save_restart_state(dict(profile='basil',maintenance=True,estop_latched=False),0)
        upgraded=SQLiteRepository(old.path,workspace_root=self.root)
        self.assertEqual(len(upgraded.backups),1)
        self.assertTrue(upgraded.load_restart_state()['maintenance'])
        self.assertTrue(upgraded.log_event(envelope()))


if __name__=='__main__':unittest.main(verbosity=2)
