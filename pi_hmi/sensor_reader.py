from arduino_serial import read_line, is_connected
import time

latest_data = {"A0": None, "A0_at": None}


def read_serial():
    """
    Continuously reads lines from the Arduino via the shared
    serial connection in arduino_serial.py.
    Run this in a daemon thread.
    """
    global latest_data
    while True:
        try:
            line = read_line()
            if line and "A0:" in line:
                value = float(line.split(":")[1])
                latest_data["A0"] = value
                latest_data["A0_at"] = time.time()
        except Exception as e:
            print(f"[SENSOR] Read error: {e}")
        time.sleep(0.5 if is_connected() else 2)
