from picamera2 import Picamera2
import threading
import time
import cv2


class Camera:
    # ── FIXED: was **init** ──
    def __init__(self):
        self.picam2 = Picamera2()

        config = self.picam2.create_video_configuration(
            main={
                "size": (640, 480),
                "format": "XRGB8888"
            }
        )
        self.picam2.configure(config)

        self.picam2.set_controls({
            "AwbEnable": True,
            "AeEnable": True
        })

        self.picam2.start()
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            frame = self.picam2.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            success, jpeg = cv2.imencode('.jpg', frame)
            if success:
                with self.lock:
                    self.frame = jpeg.tobytes()
            time.sleep(0.03)

    def get_frame(self):
        with self.lock:
            return self.frame

    def stop(self):
        self.running = False
        self.thread.join()
        self.picam2.stop()
