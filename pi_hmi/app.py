"""Local HMI; all control is host-only and passes the shared gateway."""
import secrets
import time
import threading
import uuid
from datetime import datetime, timezone
from flask import Flask, Response, g, jsonify, render_template, request
from dht11_reader import read_dht, latest_dht
from sensor_reader import read_serial
from arduino_serial import send
from services.control_runtime import get_gateway
from services.sensor_service import current_readings
from services.database_service import repository
from services.history_http import history_routes

app = Flask(__name__)
app.config.update(GERM_CONTROL_AUTHORIZER=None, GERM_SIMULATION=False, MAX_CONTENT_LENGTH=1024 * 1024)
control_token = secrets.token_urlsafe(32)
cam = None
app.register_blueprint(history_routes)


@app.errorhandler(413)
def request_too_large(error):
    return jsonify(error='Request exceeds the 1 MiB host control limit'), 413


@app.context_processor
def control_context():
    return {'firmware_token': control_token, 'control_token': control_token,
            'simulation': app.config['GERM_SIMULATION']}


@app.before_request
def restrict_mutations():
    if request.method != 'POST':
        return None
    authorize = app.config.get('GERM_CONTROL_AUTHORIZER')
    try:
        approved = (app.config.get('GERM_SIMULATION') is True and
                    get_gateway().adapter.simulated is True and callable(authorize) and authorize(request) is True)
    except Exception:
        approved = False
    if not approved:
        return jsonify(status='restricted', error='Production authentication/network boundary is not approved'), 403
    if not secrets.compare_digest(request.headers.get('X-GERM-Token', ''), control_token):
        return jsonify(status='restricted', error='Reload the local HMI before requesting a command'), 403
    g.control_authority = get_gateway().operator_authority


def send_command(command, **context):
    return send(command, **context)


def command_context(data):
    return {key: data[key] for key in ('expected_state_revision', 'confirmation_id', 'request_id') if key in data}


def respond(result):
    status = result['http_status']
    result = dict(result)
    if not result.get('allowed', True):
        result['error'] = '; '.join(result['reason_codes'])
    return jsonify(result), status


def record_control_request(actuator, state, feedback=None):
    try:
        packet = feedback or {}
        return repository.record_actuator_event({
            'actuator': actuator, 'requested_state': state,
            'reported_state': packet.get({'lighting': 'rgb', 'fan': 'fan', 'pump': 'pump'}[actuator]),
            'source': 'touchscreen', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'firmware_confirmed': True, 'physically_verified': False})
    except Exception:
        app.logger.exception('Accepted control request could not be logged')
        return False


def control_response(command, actuator, requested, data):
    try:
        gateway = get_gateway()
        intent = gateway.intent('command', {'command': command}, **command_context(data))
        result = gateway.execute(intent, getattr(g, 'control_authority', None))
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    if gateway.event_pipeline is not None:
        result['logged'] = False  # queued != durable; use event ID and logging status
        result['logging_status'] = gateway.state.snapshot()['logging']['state']
    elif result['firmware_confirmed']:
        result['logged'] = record_control_request(actuator, requested, result['reported_state'])
    return respond(result)


@app.get('/sensor')
def sensor():
    return jsonify(dht11={'temperature': latest_dht['temperature'], 'humidity': latest_dht['humidity']},
                   readings=current_readings())


@app.get('/')
def index():
    return render_template('index.html', page='home', control_tab='lighting')


@app.get('/led')
@app.get('/fan')
@app.get('/pump')
def legacy_controls():
    return render_template('index.html', page='controls',
                           control_tab={'/led': 'lighting', '/fan': 'fan', '/pump': 'pump'}[request.path])


def gen_frames():
    owner=get_gateway().media_service.captures.camera if get_gateway().media_service else cam
    while owner is not None:
        frame = owner.get_frame()
        if frame:
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        else:break
        time.sleep(0.03)


@app.get('/video_feed')
def video_feed():
    owner=get_gateway().media_service.captures.camera if get_gateway().media_service else cam
    if owner is None or owner.get_frame() is None:
        return Response('Camera unavailable\n', status=503, mimetype='text/plain')
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.get('/camera.jpg')
def camera_snapshot():
    owner=get_gateway().media_service.captures.camera if get_gateway().media_service else cam
    frame = owner.get_frame() if owner is not None else None
    if frame is None:
        return Response('Camera unavailable\n', status=503, mimetype='text/plain')
    response = Response(frame, mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'no-store'
    if get_gateway().media_service:
        response.headers['X-GERM-Source']='synthetic'
        response.headers['X-GERM-Frame-UTC']=owner.snapshot(refresh=False)['timestamp_utc']
    return response


@app.post('/api/led')
def led_control():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Expected a JSON object'), 400
    channels = [data.get(key, 0) for key in ('r', 'g', 'b', 'w')]
    if any(type(v) is not int or not 0 <= v <= 255 for v in channels):
        return jsonify(error='RGBW values must be integers 0–255'), 400
    if channels[3]:
        return jsonify(error='White channel is unavailable in this software candidate'), 400
    return control_response('LED:' + ','.join(map(str, channels)), 'lighting', channels, data)


@app.post('/api/fan')
def fan_control():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('state') not in ('on', 'off'):
        return jsonify(error='State must be on or off'), 400
    return control_response('FAN_ON' if data['state'] == 'on' else 'FAN_OFF', 'fan', data['state'], data)


@app.post('/api/fan/speed')
def fan_speed():
    data = request.get_json(silent=True)
    speed = data.get('speed') if isinstance(data, dict) else None
    if type(speed) is not int or not 0 <= speed <= 255:
        return jsonify(error='Speed must be an integer 0–255'), 400
    return control_response(f'FAN_SPEED:{speed}', 'fan', {'speed': speed}, data)


@app.post('/api/pump')
def pump_control():
    data = request.get_json(silent=True)
    commands = {'on': 'PUMP_ON', 'off': 'PUMP_OFF', '5s': 'PUMP_5S'}
    if not isinstance(data, dict) or data.get('state') not in commands:
        return jsonify(error='State must be on, off, or 5s'), 400
    return control_response(commands[data['state']], 'pump', data['state'], data)


@app.post('/api/confirmations')
def confirmation():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('payload', {}), dict):
        return jsonify(error='Expected action and object payload'), 400
    try:
        gateway = get_gateway()
        intent = gateway.intent(data.get('action'), data.get('payload', {}), **command_context(data))
        return respond(gateway.prepare(intent, getattr(g, 'control_authority', None)))
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


@app.post('/api/workflow')
def workflow():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('action') not in ('start', 'pause', 'enter_maintenance', 'exit_maintenance', 'safe_manual_test', 'complete_cycle'):
        return jsonify(error='Unsupported workflow action'), 400
    try:
        gateway = get_gateway()
        if gateway.grow_service is not None:
            return respond(gateway.grow_service.workflow(data['action'],dict(payload=data.get('payload',{}),**command_context(data)),getattr(g,'control_authority',None)))
        intent = gateway.intent(data['action'], data.get('payload', {}), **command_context(data))
        return respond(gateway.execute(intent, getattr(g, 'control_authority', None)))
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    except PermissionError:
        return jsonify(error='Operator authorization required'),403
    except Exception:
        return jsonify(error='Grow workflow persistence failed; restart inhibited'),503


@app.get('/api/grow')
def grow_snapshot():
    service=get_gateway().grow_service
    if service is None:return jsonify(state='not_configured',error='Grow repository is not configured'),503
    try:return jsonify(service.snapshot())
    except Exception:return jsonify(state='error',error='Grow database unavailable; restart inhibited'),503


@app.get('/api/media')
def media_snapshot():
    media=get_gateway().media_service
    if media is None:return jsonify(state='not_configured',camera={'state':'unavailable'},ml={'state':'not_configured'}),503
    try:return jsonify(media.snapshot())
    except Exception:return jsonify(state='error',error='Media database unavailable'),503


@app.post('/api/camera/schedule')
@app.post('/api/media/recover')
@app.post('/api/ml/analyze')
def media_operation():
    media=get_gateway().media_service
    if media is None:return jsonify(state='not_configured',error='Media runtime not configured'),503
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify(error='Expected JSON object'),400
    try:
        if request.path.endswith('/schedule'):
            if set(data)!={'enabled','interval_s','anchor_utc'}:raise ValueError('Expected enabled, interval_s and anchor_utc')
            return jsonify(media.captures.configure_schedule(**data))
        if request.path.endswith('/recover'):
            if data:
                if set(data)!={'recover_clock'} or data['recover_clock'] is not True:raise ValueError('Expected empty object or recover_clock true')
                try:clock=media.captures.recover_schedule_clock()
                except ValueError as exc:return jsonify(state='inhibited',error=str(exc)),423
                return jsonify(clock=clock,captures_started=False)
            return jsonify(media.captures.recover())
        if set(data)-{'image_id','request_id'} or 'image_id' not in data:raise ValueError('Expected image_id and optional request_id')
        result=media.ml.analyze_image(data['image_id'],request_id=data.get('request_id'))
        return jsonify(result),200 if result.get('committed') else 503
    except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400
    except Exception:return jsonify(state='error',error='Media/inference operation unavailable; persistence not acknowledged'),503


@app.post('/api/grow/cycles')
@app.post('/api/grow/schedules')
@app.post('/api/grow/recover')
def grow_mutation():
    service=get_gateway().grow_service
    if service is None:return jsonify(state='not_configured',error='Grow repository is not configured'),503
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify(error='Expected JSON object'),400
    try:
        authority=getattr(g,'control_authority',None)
        if request.path.endswith('/cycles'):
            if set(data)!={'profile_id','name'}:raise ValueError('Expected profile_id and name')
            result=service.create_cycle(data['profile_id'],data['name'],authority)
        elif request.path.endswith('/schedules'):
            if set(data)!={'schedules'}:raise ValueError('Expected schedules')
            result=service.configure(data['schedules'],authority)
        else:
            service._authorize(authority)
            if not service.recover():return jsonify(error='Recovery failed; restart remains inhibited'),503
            result=service.snapshot()
        return jsonify(result),200
    except PermissionError:return jsonify(error='Operator authorization required'),403
    except (TypeError,ValueError) as exc:return jsonify(error=str(exc)),400
    except Exception:return jsonify(error='Grow database write failed; restart inhibited'),503


from dashboard import create_dashboard
app.register_blueprint(create_dashboard(lambda: cam, lambda: get_gateway().state.requested_states))
from firmware_service import create_firmware_blueprint
app.register_blueprint(create_firmware_blueprint(control_token))


def start_simulation_workers(camera, dht_device):
    if not app.config['GERM_SIMULATION'] or not get_gateway().adapter.simulated:
        raise RuntimeError('Explicit simulated runtime required')
    global cam
    cam = camera
    import dht11_reader
    dht11_reader.dhtDevice = dht_device
    threading.Thread(target=read_dht, daemon=True).start()
    threading.Thread(target=read_serial, daemon=True).start()


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
