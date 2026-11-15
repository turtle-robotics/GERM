"""Run the GERM HMI on a normal PC with a simulated Pi and Arduino.

Usage (from pi_hmi/):  python sim/run_sim.py   ->  http://localhost:5000

Nothing in the real app is modified. Before importing app.py this launcher
installs fake modules into sys.modules:
  * board / adafruit_dht -> DHT11 returning drifting temperature/humidity
  * picamera2            -> camera producing a moving test pattern with a clock
  * serial               -> an in-process Uno that mirrors arduino_program.ino
                            (same CMD:<id>:<cmd> protocol, JSON acks, 10 s
                            contact timeout, 30 s / 5 s pump limits, errors)
"""
import json
import os
import random
import sys
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# -- Fake Arduino Uno + serial port ------------------------------------
class FakeUno:
    def __init__(self):
        self.lock = threading.RLock()
        self.fan = self.pump = False
        self.rgb = [0, 0, 0]
        self.rainbow = False
        self.last_contact = time.monotonic()
        self.pump_started = 0.0
        self.pump_duration = 30.0
        self.out = bytearray()

    def _tick(self):
        now = time.monotonic()
        if now - self.last_contact >= 10:  # firmware contact timeout
            self.fan = self.pump = self.rainbow = False
            self.rgb = [0, 0, 0]
        if self.pump and now - self.pump_started >= self.pump_duration:
            self.pump = False
        if self.rainbow:  # one hue degree per 20 ms, like the sketch
            h = int((now * 50) % 360)
            rise = int((h % 60) * 255 / 60)
            fall = 255 - rise
            self.rgb = list([
                (255, rise, 0), (fall, 255, 0), (0, 255, rise),
                (0, fall, 255), (rise, 0, 255), (255, 0, fall)][h // 60])

    def _reply(self, cid, error=None):
        pkt = {"protocol": 2, "id": cid, "fan": self.fan, "pump": self.pump,
               "rgb": list(self.rgb), "a0": None, "fan_pwm": False,
               "white_channel": False,
               "lighting_mode": "rainbow" if self.rainbow else "normal"}
        if error:
            pkt["error"] = error
        self.out.extend((json.dumps(pkt, separators=(",", ":")) + "\n").encode())

    @staticmethod
    def _num(s, maxv):
        if not s or len(s) > 5 or not s.isdigit() or int(s) > maxv:
            return None
        return int(s)

    def handle(self, line):
        cid = 0
        cmd = line
        if cmd.startswith("CMD:"):
            sep = cmd.find(":", 4)
            n = self._num(cmd[4:sep], 60000) if sep != -1 else None
            if not n:
                return self._reply(0, "Invalid command ID")
            cid, cmd = n, cmd[sep + 1:]
        err = None
        if cmd == "STATUS":
            pass
        elif cmd == "STOP":
            self.fan = self.pump = self.rainbow = False
            self.rgb = [0, 0, 0]
        elif cmd == "FAN_ON":
            self.fan = True
        elif cmd == "FAN_OFF":
            self.fan = False
        elif cmd.startswith("FAN_SPEED:"):
            s = self._num(cmd[10:], 255)
            if s not in (0, 255):
                err = "D2 supports fan on/off only"
            else:
                self.fan = s == 255
        elif cmd == "PUMP_OFF":
            self.pump = False
        elif cmd in ("PUMP_ON", "PUMP_5S"):
            d = 5.0 if cmd == "PUMP_5S" else 30.0
            if not self.pump:
                self.pump_started, self.pump_duration = time.monotonic(), d
            elif d < self.pump_duration:
                self.pump_duration = d
            self.pump = True
        elif cmd == "MODE:rainbow":
            self.rainbow = True
        elif cmd in ("MODE:normal", "LED_OFF"):
            self.rainbow = False
            self.rgb = [0, 0, 0]
        elif cmd == "LED_ON":
            self.rainbow = False
            self.rgb = [255, 255, 255]
        elif cmd.startswith("LED:"):
            parts = cmd[4:].split(",")
            vals = [self._num(p, 255) for p in parts]
            if len(parts) != 4 or None in vals:
                err = "Invalid RGB values"
            elif vals[3] != 0:
                err = "No separate white channel; use RGB"
            else:
                self.rainbow = False
                self.rgb = vals[:3]
        else:
            err = "Unknown command"
        if not err:
            self.last_contact = time.monotonic()
        self._tick()
        if cmd != "STATUS":  # heartbeats would flood the console
            print("[SIM-UNO] %r -> fan=%s pump=%s rgb=%s%s" % (
                line, self.fan, self.pump, self.rgb,
                " ERROR=" + err if err else ""))
        self._reply(cid, err)


UNO = FakeUno()


class SerialException(OSError):
    pass


class FakeSerial:
    def __init__(self, port, baud=9600, timeout=None, write_timeout=None):
        self.port, self.is_open = port, True
        self._in = bytearray()

    def write(self, data):
        with UNO.lock:
            self._in.extend(data)
            while b"\n" in self._in:
                raw, _, rest = bytes(self._in).partition(b"\n")
                self._in = bytearray(rest)
                UNO.handle(raw.decode("ascii", "replace").strip("\r"))
        return len(data)

    def read_until(self, expected=b"\n", size=None):
        with UNO.lock:
            UNO._tick()
            i = UNO.out.find(expected)
            if i == -1:
                time.sleep(0.01)
                return b""
            chunk = bytes(UNO.out[:i + 1])
            del UNO.out[:i + 1]
            return chunk

    def close(self):
        self.is_open = False


def install_fakes():
    # serial: an in-process Uno, so no virtual COM ports are needed
    serial = types.ModuleType("serial")
    serial.Serial, serial.SerialException = FakeSerial, SerialException
    tools = types.ModuleType("serial.tools")
    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: []
    serial.tools, tools.list_ports = tools, lp
    sys.modules.update({"serial": serial, "serial.tools": tools,
                        "serial.tools.list_ports": lp})
    os.environ.setdefault("GERM_SERIAL_PORT", "SIM-UNO")

    # DHT11
    board = types.ModuleType("board")
    board.D4 = "D4"

    class DHT11:
        def __init__(self, pin):
            self._t, self._h = 24.0, 55.0

        @property
        def temperature(self):
            self._t = min(35, max(15, self._t + random.uniform(-0.4, 0.4)))
            return round(self._t)

        @property
        def humidity(self):
            self._h = min(90, max(30, self._h + random.uniform(-1, 1)))
            return round(self._h)

    dht = types.ModuleType("adafruit_dht")
    dht.DHT11 = DHT11
    sys.modules.update({"board": board, "adafruit_dht": dht})

    # Camera
    import cv2
    import numpy as np

    class Picamera2:
        def create_video_configuration(self, **kw): return kw
        def configure(self, cfg): pass
        def set_controls(self, c): pass
        def start(self): pass
        def stop(self): pass

        def capture_array(self):
            t = time.time()
            img = np.zeros((480, 640, 4), np.uint8)
            img[:, :, 1] = 90
            cv2.circle(img, (int((t * 80) % 640), 240), 60, (60, 200, 80, 255), -1)
            cv2.putText(img, "SIMULATED CAMERA", (140, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255, 255), 2)
            cv2.putText(img, time.strftime("%H:%M:%S"), (250, 440),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255, 255), 2)
            return img

    pc2 = types.ModuleType("picamera2")
    pc2.Picamera2 = Picamera2
    sys.modules["picamera2"] = pc2


if __name__ == "__main__":
    install_fakes()
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import app as hmi
    print("Simulated GERM HMI at http://localhost:5000")
    hmi.app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
