"""Arduino updates inside the existing HMI; USB is owned by one bridge."""
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
from flask import Blueprint, jsonify, render_template, request
from arduino_serial import firmware_port, send, last_error

ROOT = Path(__file__).resolve().parent


def create_firmware_blueprint():
    ui = Blueprint('firmware', __name__)
    token = secrets.token_urlsafe(32)
    update_lock = threading.Lock()

    @ui.app_context_processor
    def firmware_context():
        return {'firmware_token': token}

    @ui.get('/firmware')
    def screen():
        return render_template('firmware.html', token=token)

    @ui.post('/api/firmware')
    def upload():
        request.max_content_length = 1024 * 1024
        if not secrets.compare_digest(request.headers.get('X-GERM-Token', ''), token):
            return jsonify(error='Reload the firmware page first'), 403
        file = request.files.get('firmware')
        if file is not None:
            if not file.filename or not file.filename.lower().endswith('.ino'):
                return jsonify(error='Upload one Arduino .ino sketch'), 400
            source = file.read()
        else:
            mode = request.form.get('mode', 'normal')
            if mode not in ('normal', 'rainbow'):
                return jsonify(error='Choose normal or rainbow lighting'), 400
            source = (ROOT / 'arduino_program' / 'arduino_program.ino').read_bytes()
            source = ('#define GERM_DEFAULT_RAINBOW %d\n' % (mode == 'rainbow')).encode() + source
        if not source.strip():
            return jsonify(error='Sketch is empty'), 400
        if not update_lock.acquire(blocking=False):
            return jsonify(error='Another firmware update is running'), 409
        cli = os.environ.get('GERM_ARDUINO_CLI', '/usr/local/bin/arduino-cli')
        fqbn = 'arduino:avr:uno'

        def run(args):
            # hmi.service intentionally has only the venv in PATH. Toolchain
            # helpers need normal system paths; leave the service itself intact.
            env = os.environ.copy()
            env['PATH'] = os.pathsep.join([env.get('PATH', ''), '/usr/local/bin', '/usr/bin', '/bin'])
            result = subprocess.run([cli, *args], capture_output=True, text=True,
                                    timeout=180, shell=False, env=env)
            log = (result.stdout + result.stderr)[-8000:]
            if result.returncode:
                raise RuntimeError(log or 'Arduino CLI failed')
            return log

        try:
            with tempfile.TemporaryDirectory(prefix='germ-firmware-') as temporary:
                sketch = Path(temporary) / 'GERM'
                sketch.mkdir()
                (sketch / 'GERM.ino').write_bytes(source)
                build = Path(temporary) / 'build'
                run(['compile', '--fqbn', fqbn, '--output-dir', str(build), str(sketch)])
                with firmware_port() as port:
                    log = run(['upload', '--fqbn', fqbn, '--port', port,
                               '--input-dir', str(build), str(sketch)])
                    confirmed = send('STATUS')
                    if confirmed and file is None:
                        confirmed = send('MODE:' + mode)
                    warning = None if confirmed else 'Uploaded, but HMI protocol check failed: ' + last_error()
                return jsonify(uploaded=True, compatible=confirmed, warning=warning, log=log)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return jsonify(error=str(exc)), 503
        finally:
            update_lock.release()

    return ui
