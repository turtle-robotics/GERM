"""Explicit offline synthetic host lifecycle. No daemon install, cloud or hardware."""
from datetime import datetime,timezone
import json
from pathlib import Path
import threading
import time
from services.artifact_jobs import ExportBusy
from services.file_lease import FileLease
from services.media_repository import MediaRepository
from services.grow_service import GrowService
from services.camera_adapter import CameraOwner
from services.media_runtime import MediaRuntime
from services.local_ml_service import LocalMLService
from services.ml_service import MLUnavailable
from services.history_export import HistoryService
from services.storage_service import StorageService
from services.control_runtime import install_simulation_gateway
from sim.offline_adapters import offline_gateway

DEPENDENCIES={'gateway':[],'database':['gateway'],'restart_grow':['database'],'logging':['restart_grow'],'sensors':['gateway'],
 'camera_ml':['logging'],'history_export':['database'],'backup':['history_export'],'worker':['restart_grow','logging','sensors','camera_ml','backup']}

class HostLifecycle:
    def __init__(self,root,*,create=False,gateway_factory=offline_gateway,camera_factory=None,ml_factory=None,sensor_provider=None,interval=.5):
        self.root=Path(root)
        if self.root.is_symlink():raise ValueError('Host workspace symlink denied')
        self.root=self.root.resolve(strict=True)
        if not .1<=interval<=5:raise ValueError('Host worker interval must be 0.1–5 seconds')
        if sensor_provider is not None and getattr(sensor_provider,'synthetic',False) is not True:raise ValueError('Explicit synthetic sensor provider required')
        self.create,self.gateway_factory,self.camera_factory,self.ml_factory,self.sensor_provider=create,gateway_factory,camera_factory,ml_factory,sensor_provider
        self.interval=interval;self.lock=threading.RLock();self.worker=None;self.stop_event=threading.Event();self.ready=threading.Event()
        self.lease=None;self.gateway=offline_gateway();self.repo=None;self.grow=None;self.media=None;self.history=None;self.storage=None;self.app=None
        self.status='stopped';self.error=None;self.components={};self.order=[];self.heartbeat=None;self.epoch=0;self.camera_generation=0;self.background=True
        self.data_requests=0

    def begin_data_request(self):
        with self.lock:
            if self.status!='running':return False
            self.data_requests+=1;return True

    def end_data_request(self):
        with self.lock:self.data_requests=max(0,self.data_requests-1)

    def _component(self,name,state,error=None):
        self.components[name]=dict(state=state,error=error,dependencies=DEPENDENCIES.get(name,[]),observed_at_utc=datetime.now(timezone.utc).isoformat())
        if name not in self.order:self.order.append(name)

    def _revoke(self,reason):
        if self.gateway:
            with self.gateway.state.lock:
                self.gateway.state.restart_required=True;self.gateway.state.startup_complete=False
                self.gateway.state.service_inhibits.add(reason);self.gateway.confirmations.clear()
                if self.grow:self.grow.armed=False;self.grow._grant=None
            return self.gateway.command('STOP',source='safety',authority=self.gateway.safety_authority)

    def _fault(self,name,exc):
        self.status='degraded';self.error=type(exc).__name__+': '+str(exc)[:180]
        self._component(name,'unavailable',self.error);self._revoke('host_service_unavailable')

    def bind(self,app):
        self.app=app
        if self.gateway:install_simulation_gateway(self.gateway)
        app.config.update(GERM_HOST_LIFECYCLE=self,GERM_HISTORY_SERVICE=self.history,GERM_STORAGE_SERVICE=self.storage,GERM_SIMULATION=True)

    def start(self,*,background=True):
        with self.lock:
            if self.lease is not None:raise ExportBusy('Host workspace already started; stop/recover explicitly')
            try:self.lease=FileLease(self.root/'.host-owner.lock')
            except OSError:raise ExportBusy('Another host owns this workspace') from None
            self.status='recovering';self.error=None;self.components={};self.order=[];self.epoch+=1;self.background=background
            self.stop_event.clear();self.ready.clear();self.heartbeat=None
            try:
                candidate=self.gateway_factory()
                if getattr(candidate.adapter,'synthetic_host_only',False) is not True or candidate.adapter.simulated is not True:raise ValueError('Only explicitly synthetic host adapters may run')
                if getattr(candidate,'_host_lifecycle_claimed',False):raise ValueError('Fresh unowned gateway required for each startup')
                candidate._host_lifecycle_claimed=True
                self.gateway=candidate
                self._revoke('host_recovering');self._component('gateway','restricted')
                if self.app:self.bind(self.app)
                marker=self.root/'HOST_SIMULATION.json';database=self.root/'host.sqlite'
                fresh=not marker.exists() and self.create and not database.exists()
                if fresh:
                    with marker.open('x',encoding='utf-8') as stream:json.dump({'format':'germ-host-simulation-v1'},stream)
                if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text())!={'format':'germ-host-simulation-v1'}:raise ValueError('Explicit marked host workspace required; no existing DB adoption')
                self.repo=MediaRepository(database,workspace_root=self.root,create=fresh);self._component('database','ready')
                self.grow=GrowService(self.gateway,self.repo)
                if not self.grow.persistence.restart.checkpoint() or not self.grow.recover():raise OSError('Conservative restart recovery failed')
                self._component('restart_grow','paused_restart_required')
                if not self.grow.persistence.tick():raise OSError('Initial event persistence not durable')
                self._component('logging','ready')
                self._component('sensors','recovering' if self.sensor_provider else 'unavailable')
                adapter=self.camera_factory() if self.camera_factory else None
                owner=CameraOwner(adapter,utc_now=self.gateway.state.utc_now)
                self.media=MediaRuntime(self.gateway,self.repo,owner,self.root/'images',self.ml_factory)
                if not isinstance(self.media.ml,(MLUnavailable,LocalMLService)) or (isinstance(self.media.ml,LocalMLService) and self.media.ml.captures is not self.media.captures):raise ValueError('Current local synthetic ML ownership required')
                interrupted=self.repo.recover_ml_jobs()
                if interrupted:self.media.captures.emit('ml_recovery',{'interrupted_jobs':interrupted,'rerun':False})
                self._component('camera_ml','synthetic_optional' if adapter else 'unavailable','No physical camera or model is configured')
                schedule=self.repo.capture_schedule();self.camera_generation=schedule['generation'] if schedule else 0
                self.media.captures.lifecycle_inhibit=self._camera_inhibit
                self.history=HistoryService(self.repo,self.root/'images',self.root/'exports',software_version='m8-host-simulation')
                self._component('history_export','ready')
                self.storage=StorageService(self.history,self.root/'storage',software_version='m8-host-simulation');self._component('backup','ready')
                if self.app:self.bind(self.app)
                self.status='running'
                if background:
                    self.worker=threading.Thread(target=self._loop,daemon=True,name='germ-offline-services');self.worker.start()
                    if not self.ready.wait(2) or not self.worker.is_alive():raise RuntimeError('Host worker did not start')
                else:self.worker=None;self._component('worker','manual_test_only')
                with self.gateway.state.lock:
                    self.gateway.state.service_inhibits.discard('host_recovering')
                    if not self.gateway.state.validator.policies:self.gateway.state.service_inhibits.add('host_sensor_policy_unreviewed')
                if self.status=='running':self.gateway.state.complete_startup()
                return self.snapshot()
            except Exception as exc:
                self._fault(next((n for n in DEPENDENCIES if n not in self.components),'database'),exc)
                if self.app:self.bind(self.app)
                return self.snapshot()

    def _camera_inhibit(self):
        if self.status!='running':return 'host_service_unavailable'
        try:schedule=self.repo.capture_schedule()
        except Exception:return 'host_database_unavailable'
        return 'host_restart_requires_explicit_capture_schedule_configuration' if schedule and schedule['generation']<=self.camera_generation else None

    def step(self):
        if self.status!='running':return False
        stage='database'
        try:
            self.repo._rows('SELECT version FROM migration_history ORDER BY version DESC LIMIT 1')
            if self.repo.status!='ready':raise OSError('Repository remains in error; explicit recovery required')
            stage='logging'
            if not self.grow.persistence.tick():raise OSError('Logging/restart persistence unavailable')
            stage='sensors'
            if self.sensor_provider:self.sensor_provider(self.gateway)
            readings=self.gateway.state.validator.snapshot()
            self._component('sensors','current_synthetic' if readings and all(r['state']=='fresh' for r in readings.values()) else 'unavailable_or_recovering')
            stage='gateway'
            if not self.gateway.poll_status():raise OSError('Synthetic gateway status unavailable')
            stage='restart_grow'
            if self.grow.armed and not self.gateway.state.restart_required:self.grow.scheduler_tick()
            stage='camera_ml'
            self.media.captures.scheduler_tick();self.media.captures.flush_outbox(self.gateway.event_pipeline)
            self.heartbeat=time.monotonic();self._component('worker','running' if self.background else 'manual_test_only')
            return True
        except Exception as exc:
            self._fault(stage,exc);self._component('worker','unavailable',self.error);return False

    def _loop(self):
        self.ready.set()
        try:
            while not self.stop_event.is_set():
                if not self.step():break
                self.stop_event.wait(self.interval)
        except Exception as exc:self._fault('worker',exc)

    def snapshot(self):
        if self.status=='running' and self.repo and self.repo.status!='ready':self._fault('database',OSError('Repository reports an unresolved error'))
        if self.status=='running' and self.background:
            if self.worker is None or not self.worker.is_alive():self._fault('worker',RuntimeError('Owned worker stopped; explicit recovery required'))
            elif self.heartbeat and time.monotonic()-self.heartbeat>max(3,4*self.interval):self._fault('worker',TimeoutError('Owned worker heartbeat is stale'))
        inputs=self.gateway.state.snapshot() if self.gateway else None
        camera=self.media.captures.camera.snapshot(refresh=False) if self.media else {'state':'unavailable'}
        model=getattr(self.media.ml,'status','unavailable') if self.media else 'unavailable'
        readings=inputs.get('sensors',{}) if inputs else {}
        sensors_current=bool(readings) and all(r['state']=='fresh' for r in readings.values())
        degraded=camera['state']!='ready' or model not in ('ready','completed') or not sensors_current
        return dict(state=self.status,readiness='degraded' if degraded or self.status!='running' else 'host_ready',error=self.error,epoch=self.epoch,components=dict(self.components),startup_order=list(self.order),
                    camera=camera,model_state=model,sensor_state='current_synthetic_inputs' if sensors_current else 'unavailable_or_recovering',
                    worker_alive=bool(self.worker and self.worker.is_alive()),last_heartbeat_monotonic=self.heartbeat,
                    scope='synthetic host only',internet_dependency=False,production_controls_enabled=False,
                    restart_required=True if not self.gateway else self.gateway.state.restart_required,
                    schedules_armed=bool(self.grow and self.grow.armed),capture_restart_hold=bool(self.media and self._camera_inhibit()),
                    recovery_instruction='Restore missing dependencies, then explicitly Recover host services. Recheck current sensors; schedules require a separate confirmed action. No permissions are restored.')

    def stop(self,timeout=2):
        with self.lock:
            self.status='stopping';self._revoke('host_shutdown');self.stop_event.set()
            if self.worker and self.worker is not threading.current_thread():self.worker.join(timeout)
            if self.worker and self.worker.is_alive():self.status='shutdown_waiting_worker';return False
            self._component('worker','stopped')
            if self.data_requests:self.status='shutdown_waiting_requests';return False
            if self.media:
                inference=getattr(self.media.ml,'worker',None)
                acquired=self.media.captures.lock.acquire(blocking=False)
                if not acquired or (inference and inference.is_alive()):
                    if acquired:self.media.captures.lock.release()
                    self.status='shutdown_waiting_media';return False
                self.media.captures.lock.release()
            if any(service and (service.active or (service.thread and service.thread.is_alive())) for service in (self.storage,self.history)):
                self.status='shutdown_waiting_jobs';return False
            try:
                if self.grow:self.grow.persistence.tick()
            except Exception:pass  # Existing M3 status retains failed/queued evidence; never assert a flush.
            for service in (self.storage,self.history):
                if service:service.close()
            if self.gateway:self.gateway.grow_service=None;self.gateway.media_service=None
            self.storage=self.history=self.media=self.grow=self.repo=None
            if self.lease:self.lease.close();self.lease=None
            self.status='stopped';self._component('worker','stopped')
            if self.app:self.bind(self.app)
            return True

    def recover(self):
        if not self.stop():raise ExportBusy('Owned workers/jobs still active; no duplicate recovery is allowed')
        return self.start(background=self.background)
