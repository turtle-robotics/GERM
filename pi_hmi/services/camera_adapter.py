"""One explicit synthetic owner. No physical-camera import or access."""
from dataclasses import dataclass
from datetime import datetime,timezone
import threading
import math
from services.image_validation import inspect_jpeg
from services.sqlite_repository import utc


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    captured_at_utc: str
    sequence: int
    source: str='synthetic'


class CameraUnavailable(RuntimeError):pass
class CameraStale(CameraUnavailable):pass


class CameraOwner:
    def __init__(self,adapter=None,*,utc_now=lambda:datetime.now(timezone.utc),maximum_age_s=5):
        if type(maximum_age_s) not in (int,float) or not math.isfinite(maximum_age_s) or maximum_age_s<=0:raise ValueError('Finite camera age policy required')
        if adapter is not None:
            if getattr(adapter,'synthetic',False) is not True:raise ValueError('Physical camera integration is not authorized')
            if getattr(adapter,'_germ_owner',None) is not None:raise ValueError('Camera adapter already has an owner')
            adapter._germ_owner=self
        self.adapter,self.utc_now,self.maximum_age_s=adapter,utc_now,maximum_age_s
        self.lock=threading.RLock();self.last=None;self.state='unavailable';self.error=None

    def read(self):
        with self.lock:
            try:
                if self.adapter is None:raise CameraUnavailable('No camera adapter configured')
                frame=self.adapter.read()
                if not isinstance(frame,Frame) or frame.source!='synthetic' or type(frame.sequence) is not int or frame.sequence<0:raise ValueError('Invalid synthetic frame envelope')
                age=(self.utc_now()-datetime.fromisoformat(utc(frame.captured_at_utc))).total_seconds()
                if age<0:raise ValueError('Future camera timestamp')
                inspect_jpeg(frame.jpeg)
                self.last=frame
                if age>=self.maximum_age_s:raise CameraStale('Camera frame is stale')
                self.last=frame;self.state='ready';self.error=None
                return frame
            except Exception as exc:
                self.state='stale' if isinstance(exc,CameraStale) else ('unavailable' if isinstance(exc,CameraUnavailable) else 'error')
                self.error=type(exc).__name__
                raise

    def get_frame(self):
        try:return self.read().jpeg
        except Exception:return None

    def snapshot(self,refresh=True):
        if refresh:self.get_frame()
        with self.lock:
            age=None if self.last is None else (self.utc_now()-datetime.fromisoformat(self.last.captured_at_utc)).total_seconds()
            state=self.state
            if age is not None and age<0:state='error';age=None
            if age is not None and age>=self.maximum_age_s and state=='ready':state='stale'
            return dict(state=state,source='synthetic' if self.adapter else 'not_configured',
                        timestamp_utc=self.last.captured_at_utc if self.last else None,age_seconds=age,error=self.error,
                        physically_verified=False)
