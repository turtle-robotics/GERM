"""Explicit M5 host installation; default application has no media runtime."""
from services.capture_service import CaptureService
from services.ml_service import MLUnavailable


class MediaRuntime:
    def __init__(self,gateway,repository,camera,image_root,ml_factory=None):
        if not gateway.adapter.simulated:raise ValueError('Host simulation gateway required')
        if gateway.event_pipeline is None:raise ValueError('M3 event pipeline required before media installation')
        self.gateway,self.repo=gateway,repository
        self.captures=CaptureService(gateway.state,repository,camera,image_root)
        self.captures.recover()
        try:self.ml=ml_factory(self.captures) if ml_factory else MLUnavailable()
        except Exception as exc:
            self.ml=MLUnavailable(type(exc).__name__)
            self.captures.emit('model_unavailable',{'error':type(exc).__name__})
        gateway.media_service=self

    def snapshot(self):
        result=self.captures.snapshot()
        result['ml']=self.ml.snapshot() if hasattr(self.ml,'snapshot') else dict(state=self.ml.status,latest_result=None,model=None)
        result['database_state']=self.repo.status
        result['server_time_utc']=self.gateway.state.utc_now().isoformat()
        result['event_logging']=self.gateway.state.snapshot()['logging']
        return result

    def tick(self):
        try:
            result=self.captures.scheduler_tick()
            self.captures.flush_outbox(self.gateway.event_pipeline)
            return result
        except Exception as exc:
            self.captures.last_error=type(exc).__name__
            self.captures.emit('media_persistence_failed',{'error':type(exc).__name__,'event_committed':False})
            return None
