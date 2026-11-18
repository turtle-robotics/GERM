"""Live HTTP verification; commands only turn outputs off."""
import json
import time
import urllib.request

BASE = 'http://127.0.0.1:5000'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as response:
        return response.read()


if __name__ == '__main__':
    for attempt in range(10):
        try:
            state = json.loads(get('/api/state'))
            if state['arduino']['state'] == 'connected':
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('HMI did not establish a GERM protocol connection')
    for path, payload in [('/api/fan', {'state': 'off'}), ('/api/pump', {'state': 'off'}),
                          ('/api/led', dict(r=0, g=0, b=0, w=0))]:
        request = urllib.request.Request(BASE + path, json.dumps(payload).encode(),
                                         {'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        if not data.get('firmware_confirmed'):
            raise RuntimeError('Command not confirmed: ' + path)
        print(path + ': firmware acknowledged OFF')
    for path in ['/controls', '/settings', '/firmware']:
        get(path)
        print(path + ': HTTP OK')
    state = json.loads(get('/api/state'))
    print(json.dumps({'arduino': state['arduino']['state'], 'actuators': state['actuators'],
                      'camera': state['camera'], 'sensors': state['sensors']}, indent=2))
