from flask import Flask, render_template, request, jsonify, Response
import time
import threading
from camera import Camera
from dht11_reader import read_dht, latest_dht
from sensor_reader import read_serial
from arduino_serial import send, is_connected, reported_state, last_error
from services.sensor_service import current_readings
from services.database_service import repository
from datetime import datetime, timezone

app = Flask(__name__)

# ═══════════════════════════════════════════════════
#  SERIAL CONNECTION
# ═══════════════════════════════════════════════════
requested_states = {"lighting": None, "fan": None, "pump": None}

def send_command(cmd):
    # The sensor reader and control routes share the same Arduino connection.
    return send(cmd)


def record_control_request(actuator, state):
    try:
        return repository.record_actuator_event({
            "actuator": actuator,
            "requested_state": state,
            "reported_state": (reported_state() or {}).get({'lighting': 'rgb', 'fan': 'fan', 'pump': 'pump'}[actuator]),
            "source": "touchscreen",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        app.logger.exception("Accepted control request could not be logged")
        return False

# ═══════════════════════════════════════════════════
#  CAMERA
# ═══════════════════════════════════════════════════
try:
    cam = Camera()
except Exception as e:
    cam = None
    print("[CAMERA] Failed: {}".format(e))

def gen_frames():
    while True:
        frame = cam.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.03)
        else:
            time.sleep(0.03)

# ═══════════════════════════════════════════════════
#  BACKGROUND THREADS
# ═══════════════════════════════════════════════════
threading.Thread(target=read_dht, daemon=True).start()
threading.Thread(target=read_serial, daemon=True).start()

# ═══════════════════════════════════════════════════
#  SENSOR
# ═══════════════════════════════════════════════════
@app.route('/sensor')
def sensor():
    readings = current_readings()
    return jsonify({
        "dht11": {
            "temperature": latest_dht["temperature"],
            "humidity": latest_dht["humidity"]
        },
        "readings": readings
    })

# ═══════════════════════════════════════════════════
#  PAGES
# ═══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html', page='home', control_tab='lighting')

@app.route('/led')
def led_page():
    return render_template('index.html', page='controls', control_tab='lighting')

@app.route('/fan')
def fan_page():
    return render_template('index.html', page='controls', control_tab='fan')

@app.route('/pump')
def pump_page():
    return render_template('index.html', page='controls', control_tab='pump')

@app.route('/video_feed')
def video_feed():
    if cam is None:
        return Response("Camera unavailable\n", status=503, mimetype="text/plain")
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera.jpg')
def camera_snapshot():
    frame = cam.get_frame() if cam is not None else None
    if frame is None:
        return Response("Camera unavailable\n", status=503, mimetype="text/plain")
    response = Response(frame, mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'no-store'
    return response

# ═══════════════════════════════════════════════════
#  LED API
# ═══════════════════════════════════════════════════
@app.route('/api/led', methods=['POST'])
def led_control():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error='Expected a JSON object'), 400
    try:
        channels = [data.get(key, 0) for key in ('r', 'g', 'b', 'w')]
        if any(type(value) is not int for value in channels):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "RGBW values must be integers"}), 400
    if any(value < 0 or value > 255 for value in channels):
        return jsonify({"error": "RGBW values must be 0–255"}), 400
    if channels[3]:
        return jsonify(error='No separate white LED is wired. Use RGB channels.'), 400
    if not send_command('LED:' + ','.join(map(str, channels))):
        return jsonify({"status": "unavailable", "error": last_error()}), 503
    requested_states['lighting'] = channels
    logged = record_control_request('lighting', channels)
    return jsonify({"status": "confirmed", "firmware_confirmed": True, "verified": False, "reported_state": reported_state(), "logged": logged})

# ═══════════════════════════════════════════════════
#  FAN API
# ═══════════════════════════════════════════════════
@app.route('/api/fan', methods=['POST'])
def fan_control():
    data = request.get_json(silent=True)
    state = data.get('state') if isinstance(data, dict) else None
    if state not in ('on', 'off'):
        return jsonify({"error": "State must be on or off"}), 400
    if not send_command('FAN_ON' if state == 'on' else 'FAN_OFF'):
        return jsonify({"status": "unavailable", "error": last_error()}), 503
    requested_states['fan'] = state
    logged = record_control_request('fan', state)
    return jsonify({"status": "confirmed", "state": state, "firmware_confirmed": True, "verified": False, "reported_state": reported_state(), "logged": logged})

@app.route('/api/fan/speed', methods=['POST'])
def fan_speed():
    try:
        data = request.get_json(silent=True)
        speed = data.get('speed') if isinstance(data, dict) else None
        if type(speed) is not int:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "Speed must be an integer"}), 400
    if not 0 <= speed <= 255:
        return jsonify({"error": "Speed must be 0–255"}), 400
    if speed not in (0, 255):
        return jsonify(error='Uno D2 supports fan on/off only; speed control requires rewiring to a PWM pin.'), 400
    if not send_command(f'FAN_SPEED:{speed}'):
        return jsonify({"status": "unavailable", "error": last_error()}), 503
    requested_states['fan'] = {"speed": speed}
    logged = record_control_request('fan', {"speed": speed})
    return jsonify({"status": "confirmed", "speed": speed, "firmware_confirmed": True, "verified": False, "reported_state": reported_state(), "logged": logged})

# ═══════════════════════════════════════════════════
#  PUMP API
# ═══════════════════════════════════════════════════
@app.route('/api/pump', methods=['POST'])
def pump_control():
    data = request.get_json(silent=True)
    state = data.get('state') if isinstance(data, dict) else None
    commands = {'on': 'PUMP_ON', 'off': 'PUMP_OFF', '5s': 'PUMP_5S'}
    if state not in commands:
        return jsonify({"error": "State must be on, off, or 5s"}), 400
    if not send_command(commands[state]):
        return jsonify({"status": "unavailable", "error": last_error()}), 503
    requested_states['pump'] = state
    logged = record_control_request('pump', state)
    return jsonify({"status": "confirmed", "state": state, "firmware_confirmed": True, "verified": False, "reported_state": reported_state(), "logged": logged})

from dashboard import create_dashboard

app.register_blueprint(create_dashboard(cam, requested_states))
from firmware_service import create_firmware_blueprint
app.register_blueprint(create_firmware_blueprint())

# ═══════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
