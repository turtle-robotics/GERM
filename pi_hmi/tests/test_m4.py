"""M4 lifecycle, persistent schedules, fault and HTTP integration; host only."""
import copy
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m4_fixtures import grow_fixture,workflow,fresh,PUMP,LIGHT
from m1_fixtures import fixture,feed
from services.grow_repository import GrowRepository
from services.grow_service import GrowService,schedule_definitions
from services.control_runtime import install_simulation_gateway


class GrowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.clock,self.state,self.adapter,self.gateway,self.repo,self.grow=grow_fixture(self.root)

    def test_preloaded_profiles_and_persisted_cycle_config_are_not_agronomic_defaults(self):
        self.assertEqual({p['profile_id'] for p in self.repo.profiles()},{'basil','spearmint'})
        self.assertTrue(all(p['definition']['timings'] is None for p in self.repo.profiles()))
        row=self.repo.active_cycle()
        self.assertEqual(row['profile_id'],'basil');self.assertEqual(row['status'],'paused')
        self.assertEqual(len(self.repo.schedules(row['cycle_id'])),2)
        self.assertTrue(self.state.restart_required);self.assertFalse(self.grow.armed)

    def test_authorities_cannot_be_supplied_as_strings_or_bypass_gateway(self):
        with self.assertRaises(PermissionError):self.grow.configure([], 'touchscreen')
        with self.assertRaises(PermissionError):self.grow.workflow('start',{},object())
        self.assertFalse(self.gateway.command('PUMP_5S',source='automatic',authority=self.gateway.automatic_authority)['allowed'])
        workflow(self.grow,'start');self.adapter.commands.clear()
        self.assertFalse(self.gateway.command('PUMP_5S',source='automatic',authority=self.gateway.automatic_authority)['allowed'])
        self.assertEqual(self.adapter.commands,[])

    def test_start_requires_backend_confirmation_and_configured_schedules(self):
        result=self.grow.workflow('start',{},self.gateway.operator_authority)
        self.assertFalse(result['accepted']);self.assertFalse(self.grow.armed)
        self.grow.configure([],self.gateway.operator_authority)
        self.assertIn('grow_schedules_unconfigured',workflow(self.grow,'start')['reason_codes'])
        self.assertFalse(self.grow.armed)

    def test_conflicting_invalid_schedules_are_rejected_without_writes_or_commands(self):
        before=self.repo.schedules(self.grow.cycle['cycle_id'])
        variants=[[PUMP,PUMP],[dict(PUMP,interval_s=True)],[dict(PUMP,interval_s=5)],[dict(LIGHT,end_utc='00:00')],
                  [dict(LIGHT,start_utc='25:01')],[dict(LIGHT,rgb=[0,0,0])],[dict(LIGHT,rgb=[True,0,0])],[dict(target='fan',enabled=True)],
                  [dict(PUMP,command='PUMP_ON')]]
        for definitions in variants:
            with self.assertRaises(ValueError):self.grow.configure(definitions,self.gateway.operator_authority)
        self.assertEqual(self.repo.schedules(self.grow.cycle['cycle_id']),before)
        self.assertEqual(self.adapter.commands,[])

    def test_due_commands_run_once_and_events_remain_queued_until_committed(self):
        self.assertTrue(workflow(self.grow,'start')['accepted'])
        results=self.grow.scheduler_tick()
        self.assertEqual(self.adapter.commands,['LED:10,20,30,0','PUMP_5S'])
        self.assertTrue(all(r['firmware_confirmed'] and not r['physically_verified'] for r in results))
        self.assertEqual(self.grow.scheduler_tick(),[])
        self.assertEqual(len(self.adapter.commands),2)
        self.assertEqual(self.grow.snapshot()['last_command_event'],'queued')
        self.assertTrue(self.grow.persistence.tick())
        self.assertEqual(self.grow.snapshot()['last_command_event'],'committed')
        runs=self.repo.recent_runs(self.grow.cycle['cycle_id'])
        self.assertEqual(len(runs),2)
        self.assertTrue(all(r['status']=='acknowledged' and r['definition_snapshot_json'] for r in runs))

    def test_restart_pauses_and_restores_profile_schedules_but_no_health_or_arm(self):
        workflow(self.grow,'start');self.grow.tick()
        clock,state,adapter,gateway=fixture(started=False)
        restarted=GrowService(gateway,GrowRepository(self.repo.path,workspace_root=self.root))
        self.assertEqual(restarted.cycle['profile_id'],'basil')
        self.assertEqual(restarted.cycle['status'],'paused')
        self.assertEqual(len(restarted.schedules),2)
        self.assertFalse(restarted.armed);self.assertTrue(state.restart_required)
        self.assertFalse(state.startup_complete)
        adapter.commands.clear();self.assertEqual(restarted.scheduler_tick(),[])
        self.assertFalse(workflow(restarted,'start')['allowed'])
        self.assertNotIn('PUMP_5S',adapter.commands)
        fresh(clock,gateway)
        self.assertTrue(workflow(restarted,'start')['allowed'])

    def test_missing_stale_and_unsafe_inputs_disarm_without_energizing(self):
        for kind in ('missing','stale','leak','door','estop','controller'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                clock,state,adapter,gateway,repo,grow=grow_fixture(directory)
                workflow(grow,'start')
                if kind=='missing':gateway.observe_sensor('humidity',None,clock.utc().isoformat(),source='synthetic missing')
                elif kind=='stale':clock.advance(4)
                elif kind=='controller':state.controller_feedback(None)
                else:
                    clock.advance(0.1);feed(gateway,{kind:False if kind=='door' else True})
                adapter.commands.clear();grow.scheduler_tick()
                self.assertFalse(grow.armed);self.assertTrue(state.restart_required)
                self.assertTrue(all(c=='STOP' for c in adapter.commands))

    def test_maintenance_exit_and_estop_reset_never_restart_schedules(self):
        workflow(self.grow,'start');self.grow.scheduler_tick()
        self.assertTrue(workflow(self.grow,'enter_maintenance')['accepted'])
        self.adapter.commands.clear();self.grow.scheduler_tick();self.assertEqual(self.adapter.commands,[])
        self.assertTrue(workflow(self.grow,'exit_maintenance')['accepted'])
        self.assertTrue(self.state.restart_required);self.assertFalse(self.grow.armed)
        workflow(self.grow,'start')
        self.clock.advance(0.1);feed(self.gateway,{'estop':True});self.grow.scheduler_tick()
        fresh(self.clock,self.gateway);self.adapter.commands.clear();self.grow.scheduler_tick()
        self.assertEqual(self.adapter.commands,[]);self.assertTrue(self.state.estop_latched)
        self.assertTrue(self.grow.persistence.tick())
        self.assertTrue(workflow(self.grow,'start')['accepted'])

    def test_failed_cycle_write_cannot_arm_or_claim_success(self):
        with patch.object(self.repo,'transition_cycle',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):workflow(self.grow,'start')
        self.assertFalse(self.grow.armed);self.assertTrue(self.state.restart_required)
        self.assertIn('grow_storage_unavailable',self.state.snapshot()['inhibits'])
        self.assertFalse(workflow(self.grow,'start')['allowed'])
        self.assertTrue(self.grow.recover());self.assertTrue(self.state.restart_required)

    def test_failed_claim_and_failed_outcome_do_not_retry_or_allow_running(self):
        workflow(self.grow,'start')
        with patch.object(self.repo,'claim_run',side_effect=OSError('write locked')):self.grow.scheduler_tick()
        self.assertTrue(all(c=='STOP' for c in self.adapter.commands));self.assertFalse(self.grow.armed)
        self.grow.recover();workflow(self.grow,'start');self.adapter.commands.clear()
        with patch.object(self.repo,'finish_run',side_effect=OSError('full after send')):self.grow.scheduler_tick()
        runs=self.repo.recent_runs(self.grow.cycle['cycle_id'])
        self.assertTrue(any(r['status']=='claimed' for r in runs))
        before=list(self.adapter.commands);self.grow.scheduler_tick()
        self.assertEqual(before,self.adapter.commands);self.assertFalse(self.grow.armed)

    def test_concurrent_ticks_claim_each_occurrence_once(self):
        workflow(self.grow,'start');barrier=threading.Barrier(9)
        threads=[threading.Thread(target=lambda:(barrier.wait(),self.grow.scheduler_tick())) for _ in range(8)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
        self.assertEqual(self.adapter.commands.count('PUMP_5S'),1)
        self.assertEqual(self.adapter.commands.count('LED:10,20,30,0'),1)

    def test_pause_during_slow_start_write_prevents_arm_and_dispatch(self):
        entered,release=threading.Event(),threading.Event();results=[]
        original=self.repo.transition_cycle
        def slow(*args):
            if args[2]=='running':entered.set();release.wait(3)
            return original(*args)
        with patch.object(self.repo,'transition_cycle',side_effect=slow):
            start=threading.Thread(target=lambda:results.append(workflow(self.grow,'start')));start.start()
            self.assertTrue(entered.wait(1))
            stop=threading.Thread(target=lambda:workflow(self.grow,'pause'));stop.start()
            try:
                # Pure gateway still processes the stop while the cycle writer waits.
                self.assertTrue(self.gateway.command('PUMP_OFF',source='touchscreen',authority=self.gateway.operator_authority)['accepted'])
            finally:release.set();start.join(3);stop.join(3)
        self.assertFalse(start.is_alive());self.assertFalse(stop.is_alive())
        self.assertFalse(self.grow.armed);self.assertTrue(self.state.restart_required)
        self.assertEqual(self.repo.active_cycle()['status'],'paused')

    def test_cross_midnight_light_window_and_late_pulses_have_no_catchup_burst(self):
        self.grow.configure([dict(LIGHT,start_utc='23:00',end_utc='01:00'),PUMP],self.gateway.operator_authority)
        workflow(self.grow,'start')
        self.grow.scheduler_tick();self.assertIn('LED:10,20,30,0',self.adapter.commands)
        self.clock.advance(65);fresh(self.clock,self.gateway)
        # The gap causes a restart inhibit; a fresh explicit start still cannot replay a late pulse.
        self.assertTrue(workflow(self.grow,'start')['accepted'])
        self.adapter.commands.clear();self.grow.scheduler_tick()
        self.assertNotIn('PUMP_5S',self.adapter.commands)
        self.assertTrue(any(r['status']=='missed' for r in self.repo.recent_runs(self.grow.cycle['cycle_id'])))

    def test_clock_rollback_inhibits_and_cycle_day_is_utc_calendar(self):
        workflow(self.grow,'start');self.grow.scheduler_tick()
        self.clock.advance(-0.1);self.adapter.commands.clear();self.grow.scheduler_tick()
        self.assertIn('schedule_clock_fault',self.state.snapshot()['inhibits'])
        self.assertTrue(all(c=='STOP' for c in self.adapter.commands));self.assertFalse(self.grow.armed)
        self.clock.advance(86401)
        self.assertEqual(self.grow.snapshot()['grow_day'],2)

    def test_configuration_commit_revokes_confirmation_prepared_during_write(self):
        entered,release=threading.Event(),threading.Event();original=self.repo.replace_schedules
        def slow(*args):entered.set();release.wait(3);return original(*args)
        with patch.object(self.repo,'replace_schedules',side_effect=slow):
            thread=threading.Thread(target=lambda:self.grow.configure([dict(PUMP,interval_s=120)],self.gateway.operator_authority));thread.start()
            self.assertTrue(entered.wait(1))
            prepared=self.gateway.prepare(self.gateway.intent('start'),self.gateway.operator_authority)
            self.assertTrue(prepared['allowed']);self.assertIn('60 s',prepared['description'])
            release.set();thread.join(3)
        self.adapter.commands.clear()
        result=self.grow.workflow('start',dict(confirmation_id=prepared['confirmation_id'],expected_state_revision=prepared['state_revision']),self.gateway.operator_authority)
        self.assertFalse(result['accepted']);self.assertEqual(result['http_status'],409)
        self.assertEqual(self.adapter.commands,[])

    def test_configuration_write_failure_and_transport_failure_inhibit(self):
        with patch.object(self.repo,'replace_schedules',side_effect=OSError('read-only database')):
            with self.assertRaises(OSError):self.grow.configure([PUMP],self.gateway.operator_authority)
        self.assertFalse(self.grow.armed);self.assertTrue(self.state.restart_required)
        self.assertEqual(self.grow.snapshot()['state'],'error')
        self.grow.recover();workflow(self.grow,'start')
        self.adapter.fail=True;self.adapter.commands.clear();self.grow.scheduler_tick()
        self.assertFalse(self.grow.armed)
        count=len(self.adapter.commands);self.grow.scheduler_tick();self.assertEqual(len(self.adapter.commands),count)

    def test_repeated_start_rejection_preserves_existing_schedule_arm(self):
        self.assertTrue(workflow(self.grow,'start')['accepted'])
        self.adapter.commands.clear()
        result=self.grow.workflow('start',{},self.gateway.operator_authority)
        self.assertFalse(result['accepted']);self.assertTrue(self.grow.armed)
        self.assertEqual(self.adapter.commands,[])

    def test_failed_creation_has_no_cycle_or_fabricated_success(self):
        with tempfile.TemporaryDirectory() as directory:
            clock,state,adapter,gateway,repo,grow=grow_fixture(directory,configure=False)
            with patch.object(repo,'create_cycle',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):grow.create_cycle('basil','Failed cycle',gateway.operator_authority)
            self.assertIsNone(repo.active_cycle());self.assertIsNone(grow.cycle)
            self.assertTrue(state.restart_required);self.assertFalse(grow.armed)

    def test_complete_preserves_history_and_allows_spearmint_selection(self):
        workflow(self.grow,'start');self.grow.tick()
        cycle_id=self.grow.cycle['cycle_id']
        self.assertTrue(workflow(self.grow,'complete_cycle')['accepted'])
        self.assertIsNone(self.repo.active_cycle())
        self.assertTrue(self.repo.recent_runs(cycle_id))
        self.grow.create_cycle('spearmint','Next synthetic cycle',self.gateway.operator_authority)
        self.assertEqual(self.grow.cycle['profile_id'],'spearmint')
        self.assertFalse(self.grow.armed)


class GrowHttpTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app=app;self.client=app.app.test_client()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock,self.state,self.adapter,self.gateway,self.repo,self.grow=grow_fixture(Path(self.temp.name))
        install_simulation_gateway(self.gateway)
        self.app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
        self.headers={'X-GERM-Token':self.app.control_token}

    def post(self,url,payload):return self.client.post(url,json=payload,headers=self.headers)

    def test_dashboard_uses_sql_and_missing_electronics_remains_missing(self):
        data=self.client.get('/api/state').json
        self.assertEqual(data['database']['state'],'ready');self.assertEqual(data['grow']['cycle']['profile_id'],'basil')
        self.assertIsNone(data['sensors']['electronics_temperature']['value'])
        self.assertEqual(data['data_scope'],'simulation')
        self.assertEqual(self.client.get('/api/experiments').json['items'][0]['plant_profile'],'basil')

    def test_default_post_boundary_and_failed_workflow_database_are_honest(self):
        self.app.app.config['GERM_SIMULATION']=False
        for path in ('/api/grow/cycles','/api/grow/schedules','/api/grow/recover'):
            self.assertEqual(self.post(path,{}).status_code,403)
        self.app.app.config['GERM_SIMULATION']=True
        prepared=self.post('/api/confirmations',{'action':'start'}).json
        with patch.object(self.repo,'transition_cycle',side_effect=OSError('disk full')):
            response=self.post('/api/workflow',dict(action='start',confirmation_id=prepared['confirmation_id'],expected_state_revision=prepared['state_revision']))
        self.assertEqual(response.status_code,503)
        self.assertTrue(self.state.restart_required);self.assertFalse(self.grow.armed)

    def test_highest_alarm_and_profile_settings_preserve_severity_and_maintenance(self):
        self.repo._write("INSERT INTO alerts(severity,source_type,message,timestamp_utc) VALUES('critical','test','Older critical','2026-11-01T00:00:00+00:00')")
        self.repo._write("INSERT INTO alerts(severity,source_type,message,timestamp_utc) VALUES('warning','test','New warning','2026-11-02T00:00:00+00:00')")
        self.assertEqual(self.client.get('/api/state').json['alerts']['highest']['message'],'Older critical')
        workflow(self.grow,'enter_maintenance');self.grow.persistence.tick()
        data=self.client.get('/api/state').json
        self.assertEqual(data['maintenance_banner'],'MAINTENANCE - OUTPUTS INHIBITED')
        self.assertIsNotNone(data['grow']['last_maintenance'])


if __name__=='__main__':unittest.main(verbosity=2)
