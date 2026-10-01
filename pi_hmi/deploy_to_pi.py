"""Run from the staging directory on the Pi after checks pass."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
TARGET = Path('/home/germ/hmi_flask')
FILES = ['app.py', 'arduino_serial.py', 'dashboard.py', 'firmware_service.py',
         'static/hmi.js', 'templates/index.html', 'templates/firmware.html',
         'arduino_program/arduino_program.ino']
BACKUP = Path('/home/germ/hmi-backups') / datetime.now(timezone.utc).strftime('controls-%Y%m%dT%H%M%SZ')


def run(args):
    subprocess.run(args, check=True)


if __name__ == '__main__':
    for relative in FILES:
        if not (SOURCE / relative).is_file():
            raise RuntimeError('Missing staged file: ' + relative)
    BACKUP.mkdir(parents=True, exist_ok=False)
    existed = []
    for relative in FILES:
        original = TARGET / relative
        if original.exists():
            saved = BACKUP / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, saved)
            existed.append(relative)
    (BACKUP / 'manifest.json').write_text(json.dumps({'files': FILES, 'existed': existed}, indent=2))
    print('BACKUP=' + str(BACKUP), flush=True)
    run(['sudo', '-n', 'systemctl', 'stop', 'hmi.service'])
    try:
        for relative in FILES:
            destination = TARGET / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, destination)
        run(['/usr/local/bin/arduino-cli', 'upload', '--fqbn', 'arduino:avr:uno',
             '--port', '/dev/ttyUSB0', '--input-dir', str(SOURCE.parent / 'build'),
             str(TARGET / 'arduino_program')])
    except Exception:
        for relative in FILES:
            destination = TARGET / relative
            if relative in existed:
                shutil.copy2(BACKUP / relative, destination)
            elif destination.exists():
                destination.unlink()
        raise
    finally:
        run(['sudo', '-n', 'systemctl', 'start', 'hmi.service'])
