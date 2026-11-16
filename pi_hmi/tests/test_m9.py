"""Acceptance/hardening on disposable host data, never production or physical I/O."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import errno,json,os,sqlite3,subprocess,sys,tempfile,threading,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_acceptance_matrix import build,ROOT
from services.host_lifecycle import HostLifecycle
from services.history_export import ExportBusy
from services.command_service import dispatch_authorized
from services.sqlite_repository import canonical
from m5_fixtures import media_fixture,capture
from m1_fixtures import feed
from m4_fixtures import workflow

class AcceptanceTests(unittest.TestCase):
    def test_every_official_objective_and_requirement_retains_wording_status_and_gates(self):
        expected=build();stored=json.loads((ROOT/'docs/phase0/M9_ACCEPTANCE_MATRIX.json').read_text(encoding='utf-8'))
        self.assertEqual(expected,stored);self.assertEqual(len(stored['requirements']),40);self.assertEqual(len(stored['objectives']),6)
        for row in stored['requirements']:
            self.assertFalse(row['requirements_approved']);self.assertFalse(row['physical_accepted']);self.assertFalse(row['production_accepted'])
            for path in row['implementation']+row['automated_evidence']:self.assertTrue((ROOT/path).is_file(),path)
            self.assertTrue(row['remaining_gate']);self.assertTrue(row['manual_evidence']['source_url'])

    def test_reviewed_gateway_sources_and_http_surface_match_audit(self):
        from m9_security_audit import inventory
        expected=json.loads((ROOT/'docs/phase0/M9_HTTP_GATEWAY_AUDIT.json').read_text(encoding='utf-8'))
        self.assertEqual(inventory(),expected)
        self.assertTrue(any(s['call']=='self.adapter.send' and s['path'].endswith('command_service.py') for s in expected['low_level_call_sites']))

class LifecycleHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.host=HostLifecycle(self.root,create=True);self.addCleanup(self.host.stop)
        self.assertEqual(self.host.start(background=False)['state'],'running')

    def test_event_arriving_during_drain_stays_queued_without_false_worker_crash(self):
        original=self.host.repo.log_event;added=False
        def write(event):
            nonlocal added
            result=original(event)
            if not added:added=True;self.host.gateway.state.emit('concurrent_fixture',{'scope':'synthetic'})
            return result
        self.host.gateway.state.emit('before_drain_fixture',{})
        with patch.object(self.host.repo,'log_event',side_effect=write),patch.object(self.host.media.captures,'flush_outbox'):
            self.assertTrue(self.host.step())
        self.assertEqual(self.host.status,'running');self.assertEqual(self.host.components['logging']['state'],'queued')
        self.assertEqual(self.host.gateway.state.snapshot()['logging']['state'],'pending');self.assertTrue(self.host.gateway.state.restart_required)
        self.assertTrue(self.host.step());self.assertEqual(self.host.components['logging']['state'],'ready')

    def test_unknown_false_or_error_drain_still_fails_closed(self):
        for outcome in ('unknown','error'):
            with self.subTest(outcome=outcome):
                if self.host.status!='running':self.host.recover()
                if outcome=='unknown':
                    with patch.object(self.host.grow.persistence,'tick',return_value=False):self.assertFalse(self.host.step())
                else:
                    self.host.gateway.state.emit('failure_fixture',{})
                    with patch.object(self.host.repo,'log_event',side_effect=OSError(errno.ENOSPC,'Injected full disk')):self.assertFalse(self.host.step())
                self.assertEqual(self.host.status,'degraded');self.assertTrue(self.host.gateway.state.restart_required)
                self.assertFalse(self.host.gateway.state.startup_complete)

    def test_disk_full_restart_checkpoint_does_not_erase_history_or_grant_permission(self):
        self.host.grow.create_cycle('basil','Retain me',self.host.gateway.operator_authority)
        self.host.gateway.state.maintenance=True
        with patch.object(self.host.repo,'save_restart_state',side_effect=OSError(errno.ENOSPC,'Injected full disk')):self.assertFalse(self.host.step())
        self.assertTrue(self.host.gateway.state.restart_required);self.assertIsNotNone(self.host.repo.active_cycle())
        self.assertEqual(self.host.recover()['state'],'running');self.assertFalse(self.host.grow.armed)

    def test_real_sqlite_corruption_requires_isolated_repair_not_recreation(self):
        self.host.stop();database=self.root/'host.sqlite'
        database.write_bytes(b'INTENTIONAL CORRUPTION OF DISPOSABLE SYNTHETIC DATABASE')
        before=database.read_bytes();self.assertEqual(self.host.start(background=False)['state'],'degraded')
        self.assertEqual(database.read_bytes(),before);self.assertTrue(self.host.gateway.state.restart_required)

    def test_artifact_quota_exhaustion_preserves_existing_files(self):
        saved=self.host.history.root/'retained-fixture';saved.write_bytes(b'KEEP')
        self.host.history.max_total_bytes=1
        with self.assertRaises(ExportBusy):self.host.history.start(str(uuid.uuid4()),{})
        self.assertEqual(saved.read_bytes(),b'KEEP');self.assertFalse(self.host.grow.armed)

    def test_status_reads_are_read_only_without_writer_setup_during_wal_write(self):
        connect=sqlite3.connect
        class Probe(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                if sql=='PRAGMA synchronous=FULL':raise sqlite3.OperationalError('Injected writer-setup lock')
                return super().execute(sql,*args,**kwargs)
        # Reproduce a setup-only lock independently of SQL query execution.
        with patch('services.sqlite_repository.sqlite3.connect',side_effect=lambda *a,**kw:connect(*a,**kw,factory=Probe)):
            self.assertTrue(self.host.repo._rows('SELECT version FROM migration_history'))
            self.assertEqual(self.host.repo.status,'ready')
            with self.host.repo.connection(read_only=True) as reader:
                with self.assertRaises(sqlite3.OperationalError):reader.execute("UPDATE grow_profiles SET name='denied'")
        self.host.recover()
        with self.host.repo.connection() as writer:
            writer.execute('BEGIN IMMEDIATE')
            with ThreadPoolExecutor() as pool:
                self.assertTrue(pool.submit(self.host.repo._rows,'SELECT version FROM migration_history').result(timeout=2))
            writer.execute('ROLLBACK')

    def test_killed_process_releases_lease_recovers_receipt_and_preserves_stage(self):
        self.host.stop()
        with tempfile.TemporaryDirectory() as directory:
            process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('m9_crash_host.py')),directory],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,PYTHONUTF8='1'))
            try:
                # communicate cannot be used while deliberately live; a bounded reader prevents hanging CI.
                result={};ready=threading.Event()
                def read():
                    try:result['line']=process.stdout.readline()
                    finally:ready.set()
                reader=threading.Thread(target=read,daemon=True);reader.start();self.assertTrue(ready.wait(20),'Synthetic crash fixture did not start')
                self.assertTrue(result['line'],process.poll());receipt=json.loads(result['line'])
            finally:process.kill();process.communicate(timeout=10)
            recovered=HostLifecycle(directory)
            try:
                status=recovered.start(background=False);self.assertEqual(status['state'],'running');self.assertTrue(status['restart_required'])
                self.assertEqual(recovered.history.job(receipt['request_id'])['status'],'interrupted')
                self.assertTrue((Path(directory)/'exports/interrupted-fixture.part').is_file());self.assertIsNotNone(recovered.repo.active_cycle())
                self.assertFalse(recovered.grow.armed);self.assertEqual(set(recovered.gateway.adapter.commands)-{'STOP','STATUS'},set())
            finally:recovered.stop()

class FaultAndBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.clock,self.state,self.adapter,self.gateway,self.repo,self.grow,self.camera,self.media,self.inference,*_=media_fixture(self.root)
        self.grow.configure([dict(target='lighting',enabled=True,start_utc='00:00',end_utc='23:59',rgb=[1,2,3])],self.gateway.operator_authority)
        self.adapter.commands.clear()

    def test_sensor_loss_and_rollback_schedule_never_bypass_gateway(self):
        self.assertTrue(workflow(self.grow,'start')['accepted']);self.adapter.commands.clear()
        self.clock.advance(.1);self.gateway.observe_sensor('door',None,self.clock.utc().isoformat(),source='SYNTHETIC LOSS')
        self.grow.scheduler_tick();self.assertNotIn('PUMP_5S',self.adapter.commands);self.assertTrue(self.state.restart_required)
        self.media.captures.configure_schedule(True,3600,self.clock.utc().isoformat());self.media.captures.scheduler_tick()
        self.clock.advance(-100);before=self.camera.reads
        for _ in range(5):self.assertIsNone(self.media.captures.scheduler_tick())
        self.assertEqual(self.camera.reads,before);self.assertTrue(self.media.captures.scheduling_snapshot()['clock_fault'])

    def test_camera_loss_and_failed_inference_never_claim_committed_results(self):
        self.camera.available=False
        with self.assertRaises(Exception):capture(self.media,self.clock)
        self.camera.available=True;image=capture(self.media,self.clock)
        with patch.object(self.inference,'infer',side_effect=RuntimeError('Injected model loss')):result=self.media.ml.analyze_image(image['image_id'])
        self.assertFalse(result['committed']);self.assertEqual(result['state'],'error');self.assertEqual(self.adapter.commands,[])

    def test_all_synthetic_actuation_dispatches_require_gateway_context(self):
        original=self.adapter.send;transitions=[]
        def audited(command):
            if command!='STATUS':self.assertTrue(dispatch_authorized('command'));transitions.append(command)
            return original(command)
        self.adapter.send=audited
        self.assertTrue(workflow(self.grow,'start')['accepted']);self.grow.scheduler_tick()
        self.assertTrue(workflow(self.grow,'pause')['accepted'])
        self.gateway.command('MODE:rainbow',authority=object());self.gateway.command('PUMP_ON',authority=object())
        with self.assertRaises(ValueError):self.gateway.intent('firmware_update',{'mode':'custom'})
        denied=self.gateway.execute(self.gateway.intent('firmware_update',{'mode':'normal'}),self.gateway.operator_authority)
        self.assertFalse(denied['allowed']);self.assertEqual(self.adapter.update_steps,[]);self.assertTrue(transitions)

    def test_pause_uses_existing_revision_optional_contract_while_start_stays_confirmed(self):
        self.assertTrue(workflow(self.grow,'start')['accepted'])
        prepared=self.gateway.prepare(self.gateway.intent('pause'),self.gateway.operator_authority)
        self.gateway.state.revision+=1
        stale=self.grow.workflow('pause',dict(expected_state_revision=prepared['state_revision']),self.gateway.operator_authority)
        self.assertEqual(stale['http_status'],409);self.assertTrue(self.grow.armed)
        result=self.grow.workflow('pause',{},self.gateway.operator_authority)
        self.assertTrue(result['accepted']);self.assertFalse(self.grow.armed)
        prepared=self.gateway.prepare(self.gateway.intent('start'),self.gateway.operator_authority)
        self.gateway.state.revision+=1
        stale=self.grow.workflow('start',dict(confirmation_id=prepared['confirmation_id'],expected_state_revision=prepared['state_revision']),self.gateway.operator_authority)
        self.assertFalse(stale['accepted']);self.assertFalse(self.grow.armed)

class HttpAuditTests(unittest.TestCase):
    def test_every_post_route_denied_without_approved_boundary_and_gets_do_not_enable_it(self):
        from m1_http_harness import app
        import services.control_runtime as runtime
        old_gateway=runtime._gateway;old=dict(app.app.config)
        with tempfile.TemporaryDirectory() as directory:
            host=HostLifecycle(directory,create=True);host.bind(app.app);host.start(background=False)
            try:
                client=app.app.test_client();app.app.config['GERM_CONTROL_AUTHORIZER']=None
                for rule in app.app.url_map.iter_rules():
                    if 'POST' in rule.methods:
                        path=str(rule).replace('<request_id>',str(uuid.uuid4()))
                        with self.subTest(route=path):
                            response=client.post(path,json={'authority':'automatic','simulation':True,'enable_hardware':True},headers={'X-GERM-Token':app.control_token,'Origin':'https://untrusted.invalid'})
                            self.assertEqual(response.status_code,403)
                response=client.get('/');self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
                # Read routes currently have no authentication: explicitly audited gap, not approved access.
                self.assertEqual(client.get('/api/history/experiments').status_code,200)
                self.assertEqual(client.get('/api/history/events?limit=1001').status_code,400)
                self.assertEqual(client.get('/api/history/events?limit=1&limit=2').status_code,400)
                self.assertIn(client.get('/api/exports/../../secret/download').status_code,(400,404))
                app.app.config['GERM_SIMULATION']=False;app.app.config['GERM_CONTROL_AUTHORIZER']=lambda request:True
                self.assertEqual(client.post('/api/services/recover',json={},headers={'X-GERM-Token':app.control_token}).status_code,403)
                self.assertFalse(host.grow.armed);self.assertTrue(host.gateway.state.restart_required)
            finally:host.stop();app.app.config.update(old);runtime._gateway=old_gateway

if __name__=='__main__':unittest.main(verbosity=2)
