"""Offline lifecycle/permissions and local seven-screen runtime, temporary hosts only."""
from contextlib import ExitStack
from pathlib import Path
import json
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.host_lifecycle import HostLifecycle,DEPENDENCIES
from services.artifact_jobs import ExportBusy
from services.media_repository import MediaRepository
from services.command_service import CommandGateway
from services.state_service import StateManager
from sim.offline_adapters import OfflineAdapter
from sim.media_fakes import SyntheticCamera

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.host=HostLifecycle(self.root,create=True);self.addCleanup(self.host.stop)

    def start(self,**kwargs):return self.host.start(background=False,**kwargs)

    def test_startup_dependency_order_restricted_defaults_and_shutdown(self):
        status=self.start();self.assertEqual(status['state'],'running');self.assertEqual(status['readiness'],'degraded')
        self.assertEqual(status['startup_order'],list(DEPENDENCIES))
        self.assertTrue(status['restart_required']);self.assertFalse(status['schedules_armed']);self.assertFalse(status['production_controls_enabled'])
        self.assertEqual(status['camera']['state'],'unavailable');self.assertNotIn(status['model_state'],('ready','completed'))
        self.assertTrue(self.host.step());self.assertEqual(set(self.host.gateway.adapter.commands)-{'STATUS','STOP'},set())
        self.assertTrue(self.host.stop());self.assertIsNone(self.host.repo);self.assertEqual(self.host.status,'stopped')

    def test_no_outgoing_internet_connections_for_start_tick_or_snapshot(self):
        with patch('socket.create_connection',side_effect=AssertionError('Internet access attempted')),patch('urllib.request.urlopen',side_effect=AssertionError('HTTP attempted')),patch.object(socket.socket,'connect',side_effect=AssertionError('Network attempted')):
            self.assertEqual(self.start()['state'],'running');self.assertTrue(self.host.step());self.host.snapshot();self.assertTrue(self.host.stop())

    def test_repeated_restarts_preserve_history_and_never_permissions(self):
        self.start();self.host.repo._write("INSERT INTO experiments(name,plant_profile,status,start_time_utc) VALUES('retained','basil','paused','2026-11-15T00:00:00Z')")
        old=self.host.gateway;old.confirmations['old-token']={'synthetic':'expired on recovery'}
        for _ in range(4):
            status=self.host.recover();self.assertTrue(status['restart_required']);self.assertFalse(status['schedules_armed']);self.assertIsNot(self.host.gateway,old)
            self.assertEqual(len(self.host.repo.get_experiments()),1);self.assertEqual(set(self.host.gateway.adapter.commands)-{'STOP','STATUS'},set())
        self.assertEqual(old.confirmations,{})
        result=self.host.gateway.execute(self.host.gateway.intent('start'),old.operator_authority)
        self.assertFalse(result['allowed']);self.assertEqual(result['http_status'],403)

    def test_duplicate_instance_and_duplicate_start_do_not_duplicate_workers(self):
        self.host.start();worker=self.host.worker
        with self.assertRaises(ExportBusy):self.host.start()
        other=HostLifecycle(self.root)
        with self.assertRaises(ExportBusy):other.start()
        self.assertIs(self.host.worker,worker);self.assertTrue(worker.is_alive())

    def test_detected_worker_exit_latches_recovery_inhibit(self):
        self.host.start();self.host.stop_event.set();self.host.worker.join(3)
        result=self.host.snapshot();self.assertEqual(result['state'],'degraded');self.assertTrue(self.host.gateway.state.restart_required)
        self.assertFalse(self.host.gateway.state.startup_complete);self.assertFalse(self.host.step())
        self.assertEqual(self.host.recover()['state'],'running');self.assertTrue(self.host.gateway.state.restart_required)

    def test_stale_worker_heartbeat_fails_closed(self):
        self.start();self.host.background=True;self.host.worker=threading.current_thread();self.host.heartbeat=time.monotonic()-20
        self.assertEqual(self.host.snapshot()['state'],'degraded');self.host.worker=None
        self.assertIn('host_service_unavailable',self.host.gateway.state.service_inhibits)

    def test_blocked_worker_prevents_release_and_duplicate_recovery(self):
        entered=threading.Event();release=threading.Event()
        def blocked():entered.set();release.wait(5);return False
        with patch.object(self.host,'step',side_effect=blocked):
            self.host.start();self.assertTrue(entered.wait(2));self.assertFalse(self.host.stop(timeout=.01))
            self.assertEqual(self.host.status,'shutdown_waiting_worker')
            with self.assertRaises(ExportBusy):HostLifecycle(self.root).start()
            release.set();self.host.worker.join(3)
        self.assertTrue(self.host.stop())

    def test_database_failure_never_auto_heals_or_grants_permission(self):
        self.start()
        with patch.object(self.host.repo,'_rows',side_effect=sqlite3.OperationalError('simulated DB failure')):
            self.assertFalse(self.host.step());self.assertEqual(self.host.snapshot()['state'],'degraded')
        self.assertFalse(self.host.step());self.assertFalse(self.host.gateway.state.startup_complete)
        self.assertEqual(self.host.recover()['state'],'running');self.assertTrue(self.host.gateway.state.restart_required)

    def test_logging_failure_isolated_and_requires_explicit_recovery(self):
        self.start()
        with patch.object(self.host.grow.persistence,'tick',return_value=False):self.assertFalse(self.host.step())
        self.assertEqual(self.host.status,'degraded');self.assertEqual(self.host.gateway.adapter.commands[-1],'STOP')
        self.assertFalse(self.host.gateway.state.startup_complete)
        self.host.recover()
        with patch.object(self.host.gateway,'poll_status',return_value=False):self.assertFalse(self.host.step())
        self.assertEqual(self.host.components['gateway']['state'],'unavailable')

    def test_missing_database_is_never_recreated_after_initialized_workspace(self):
        self.start();database=self.host.repo.path;self.host.stop();database.unlink()  # owned temporary failure fixture
        self.assertEqual(self.host.recover()['state'],'degraded');self.assertFalse(database.exists())
        MediaRepository(database,workspace_root=self.root,create=True)
        self.assertEqual(self.host.recover()['state'],'running')

    def test_unmarked_existing_database_is_not_adopted_or_overwritten(self):
        path=self.root/'host.sqlite';path.write_bytes(b'keep existing bytes')
        self.assertEqual(self.start()['state'],'degraded');self.assertEqual(path.read_bytes(),b'keep existing bytes')

    def test_non_synthetic_adapter_or_camera_rejected_without_dispatch(self):
        adapter=OfflineAdapter();adapter.synthetic_host_only=False
        self.host.gateway_factory=lambda:CommandGateway(StateManager(),adapter,safe_commands=('STOP',))
        self.assertEqual(self.start()['state'],'degraded');self.assertFalse(adapter.commands)
        self.host.stop();self.host.gateway_factory=lambda:CommandGateway(StateManager(),OfflineAdapter(),safe_commands=('STOP',))
        self.host.camera_factory=lambda:object()
        self.assertEqual(self.start()['state'],'degraded');self.assertIsNone(self.host.media)

    def test_optional_synthetic_camera_no_model_honestly_degraded(self):
        self.host.camera_factory=SyntheticCamera;status=self.start();self.assertEqual(status['readiness'],'degraded')
        self.assertNotIn(status['model_state'],('ready','completed'));self.assertFalse(status['production_controls_enabled'])
        self.assertEqual(self.host.media.captures.camera.adapter.reads,0)

    def test_camera_schedule_restart_hold_preserves_claims_and_generation(self):
        self.host.camera_factory=SyntheticCamera;self.start();self.host.grow.create_cycle('basil','Synthetic cycle',self.host.gateway.operator_authority)
        anchor=self.host.gateway.state.utc_now().isoformat();self.host.media.captures.configure_schedule(True,3600,anchor);self.host.step()
        before=self.host.repo.recent_capture_requests();self.assertEqual(len(before),1);generation=self.host.repo.capture_schedule()['generation']
        self.host.recover();self.host.step()
        self.assertEqual(self.host.repo.capture_schedule()['generation'],generation);self.assertEqual(len(self.host.repo.recent_capture_requests()),1)
        self.assertEqual(self.host.media.captures.camera.adapter.reads,0);self.assertEqual(self.host.media.captures.scheduling_snapshot()['state'],'host_inhibited')
        self.assertFalse(self.host.grow.armed)

    def test_running_export_blocks_shutdown_and_new_workspace_owner(self):
        self.start();entered=threading.Event();release=threading.Event();original=self.host.repo.backup
        def blocked(path):entered.set();release.wait(5);return original(path)
        history=self.host.history
        with patch.object(self.host.repo,'backup',side_effect=blocked):
            history.start(str(uuid.uuid4()),{'resources':['experiments']});self.assertTrue(entered.wait(2))
            self.assertFalse(self.host.stop());self.assertEqual(self.host.status,'shutdown_waiting_jobs')
            with self.assertRaises(ExportBusy):HostLifecycle(self.root).start()
            release.set();history.wait()
        self.assertTrue(self.host.stop())

    def test_inflight_mutation_lease_blocks_shutdown_until_teardown(self):
        self.start();self.assertTrue(self.host.begin_data_request());self.assertFalse(self.host.stop())
        self.assertEqual(self.host.status,'shutdown_waiting_requests');self.assertFalse(self.host.begin_data_request())
        self.host.end_data_request();self.assertTrue(self.host.stop())

    def test_restart_recovers_interrupted_artifact_receipts_without_execution(self):
        self.start();request_id=str(uuid.uuid4())
        self.host.repo._write("INSERT INTO storage_jobs VALUES(?,?,'running',1,?,?,NULL,NULL)",(request_id,'{"kind":"backup"}','2026-11-15T00:00:00Z','2026-11-15T00:00:00Z'))
        self.host.recover();job=self.host.storage.job(request_id)
        self.assertEqual(job['status'],'interrupted');self.assertFalse(self.host.storage.active);self.assertIsNone(job['download_url'])

    def test_required_synthetic_sensor_provider_rejects_untrusted_callback(self):
        with self.assertRaises(ValueError):HostLifecycle(self.root,sensor_provider=lambda gateway:None)

    def test_current_synthetic_samples_expire_instead_of_becoming_real_values(self):
        from m1_fixtures import fixture,feed
        def factory():
            clock,state,adapter,gateway=fixture(started=False);adapter.synthetic_host_only=True;gateway.fixture_clock=clock;return gateway
        class Provider:
            synthetic=True
            def __call__(self,gateway):gateway.fixture_clock.advance(.2);feed(gateway)
        self.host.gateway_factory=factory;self.host.sensor_provider=Provider();self.start();self.host.step()
        reading=self.host.gateway.state.snapshot()['sensors']['air_temperature'];self.assertEqual(reading['fault_reason'],'recovering')
        self.host.step();reading=self.host.gateway.state.snapshot()['sensors']['air_temperature'];self.assertEqual(reading['value'],24)
        self.host.sensor_provider=None;self.host.gateway.fixture_clock.advance(10);self.host.step()
        reading=self.host.gateway.state.snapshot()['sensors']['air_temperature'];self.assertEqual(reading['quality_flag'],'stale')
        self.assertIsNone(reading['value']);self.assertTrue(self.host.gateway.state.restart_required)

    def test_corrupt_existing_database_is_not_repaired_or_replaced(self):
        self.start();path=self.host.repo.path;self.host.stop()
        with path.open('r+b') as stream:stream.write(b'corrupt-snapshot')
        self.assertEqual(self.host.recover()['state'],'degraded');self.assertTrue(path.read_bytes().startswith(b'corrupt-snapshot'))

    def test_gateway_and_model_owners_cannot_be_reused_across_restart(self):
        shared=CommandGateway(StateManager(),OfflineAdapter(),safe_commands=('STOP',))
        self.host.gateway_factory=lambda:shared;self.assertEqual(self.start()['state'],'running')
        self.assertEqual(self.host.recover()['state'],'degraded');self.assertTrue(self.host.gateway.state.restart_required)
        self.host.stop();self.host.gateway_factory=lambda:CommandGateway(StateManager(),OfflineAdapter(),safe_commands=('STOP',))
        self.host.ml_factory=lambda captures:object()
        self.assertEqual(self.start()['state'],'degraded')


class LifecycleHttpTests(unittest.TestCase):
    def test_seven_screens_local_assets_headers_status_recovery_and_production_denial(self):
        import app
        from services.control_runtime import get_gateway,install_simulation_gateway
        old=dict(app.app.config);old_gateway=get_gateway()
        with tempfile.TemporaryDirectory() as directory:
            host=HostLifecycle(directory,create=True);host.bind(app.app);host.start(background=False)
            try:
                client=app.app.test_client();headers={'X-GERM-Token':app.control_token}
                for route in ('/','/plant','/trends','/controls','/alerts','/maintenance','/settings'):
                    response=client.get(route);self.assertEqual(response.status_code,200);self.assertIn(b'Skip navigation',response.data)
                    self.assertIn("connect-src 'self'",response.headers['Content-Security-Policy'])
                for asset in ('hmi.css','hmi.js','offline.css','offline.js','history.js','storage.js'):
                    response=client.get('/static/'+asset)
                    try:self.assertEqual(response.status_code,200)
                    finally:response.close()
                self.assertEqual(client.get('/api/services').json['state'],'running');self.assertEqual(client.get('/api/services').headers['Cache-Control'],'no-store')
                app.app.config['GERM_CONTROL_AUTHORIZER']=None
                self.assertEqual(client.post('/api/services/recover',json={},headers=headers).status_code,403)
                app.app.config['GERM_CONTROL_AUTHORIZER']=lambda request:True
                response=client.post('/api/services/recover',json={},headers=headers);self.assertEqual(response.status_code,200)
                self.assertTrue(response.json['restart_required']);self.assertFalse(response.json['schedules_armed'])
                self.assertEqual(client.post('/api/services/recover',json={'enable_hardware':True},headers=headers).status_code,400)
                app.app.config['GERM_SIMULATION']=False
                self.assertEqual(client.post('/api/services/recover',json={},headers=headers).status_code,403)
                with self.assertRaises(RuntimeError):app.start_simulation_workers(object(),object())
            finally:
                host.stop();app.app.config.update(old)
                import services.control_runtime as control_runtime
                control_runtime._gateway=old_gateway  # Restore the original test-process default, including its unavailable adapter.

if __name__=='__main__':unittest.main(verbosity=2)
