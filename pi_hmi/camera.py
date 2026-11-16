"""Compatibility facade; physical Picamera2 startup remains unauthorized."""
from services.camera_adapter import CameraOwner


class Camera(CameraOwner):
    def __init__(self,adapter=None,**kwargs):
        if adapter is None:raise RuntimeError('Physical camera activation is not authorized; inject a synthetic adapter')
        super().__init__(adapter,**kwargs)

    def stop(self):
        with self.lock:self.adapter=None;self.last=None;self.state='unavailable'
