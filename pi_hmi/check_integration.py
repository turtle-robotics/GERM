"""Run from the staged directory. Hardware and background workers are stubbed."""
import io
import json
import re
import sys
import types
import unittest
from unittest.mock import patch

import arduino_serial as bridge


def module(name, **attributes):
    item = types.ModuleType(name)
    item.__dict__.update(attributes)
    sys.modules[name] = item
    return item


class FakeSerial:
    is_open = True
    port = '/dev/fake'

    def __init__(self, acknowledge=True):
        self.pending = []
        self.acknowledge = acknowledge

    def write(self, data):
        self.command = data.decode().strip()
        seq = int(self.command.split(':', 2)[1])
        # Old acknowledgement must never satisfy the next command.
        state = dict(protocol=2, id=seq - 1, fan=False, pump=False, rgb=[0, 0, 0])
        self.pending.append(json.dumps(state).encode() + b'\n')
        if self.acknowledge:
            state['id'] = seq
            self.pending.append(json.dumps(state).encode() + b'\n')

    def read_until(self, *args):
        return self.pending.pop(0) if self.pending else b''

    def close(self):
        self.is_open = False


class SerialTests(unittest.TestCase):
    def tearDown(self):
        bridge._reconnect()

    def test_matched_acknowledgement(self):
        bridge._ser = FakeSerial()
        self.assertTrue(bridge.send('FAN_OFF'))
        self.assertTrue(bridge.is_connected())
        self.assertTrue(bridge._ser.command.endswith(':FAN_OFF'))

    def test_stale_acknowledgement_is_not_success(self):
        bridge._ser = FakeSerial(acknowledge=False)
        with patch.object(bridge.time, 'monotonic', side_effect=[0, 0, 0, 0, 4]):
            self.assertFalse(bridge.send('FAN_OFF'))

    def test_firmware_pause_closes_connection(self):
        port = FakeSerial()
        bridge._ser = port
        with bridge.firmware_port() as name:
            self.assertEqual(name, '/dev/fake')
            self.assertFalse(port.is_open)
            self.assertIsNone(bridge._ser)


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module('camera', Camera=lambda: None)
        module('dht11_reader', read_dht=lambda: None, latest_dht={'temperature': None, 'humidity': None})
        module('sensor_reader', read_serial=lambda: None)
        module('services')
        readings = {key: {'state': 'unavailable'} for key in ('air_temperature', 'humidity', 'water_temperature', 'arduino_a0')}
        module('services.sensor_service', current_readings=lambda: readings)
        repository = types.SimpleNamespace(status='not_configured', record_actuator_event=lambda event: True,
                                           get_active_alerts=lambda: [])
        module('services.database_service', repository=repository)
        module('services.camera_service', IMAGE_ROOT='/tmp', latest_local_manual_capture=lambda: None,
               save_manual_capture=lambda frame: {})
        module('services.ml_service', ml_service=types.SimpleNamespace(status='not_configured', get_latest_result=lambda: None, get_model_info=lambda: None))
        with patch('threading.Thread.start'):
            import app
        cls.app_module = app
        cls.client = app.app.test_client()

    def test_routes_preserved(self):
        for route in ['/', '/controls', '/settings', '/firmware', '/api/state', '/sensor']:
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_invalid_values_never_send(self):
        with patch.object(self.app_module, 'send_command') as send:
            for route, data in [('/api/led', {'r': 1.5}), ('/api/led', {'w': 20}),
                                ('/api/fan/speed', {'speed': 128}), ('/api/fan', []),
                                ('/api/pump', {'state': 'bad'})]:
                self.assertEqual(self.client.post(route, json=data).status_code, 400)
            send.assert_not_called()

    def test_fan_command_is_acknowledged(self):
        with patch.object(self.app_module, 'send_command', return_value=True) as send:
            response = self.client.post('/api/fan', json={'state': 'off'})
        send.assert_called_once_with('FAN_OFF')
        self.assertTrue(response.json['firmware_confirmed'])
        self.assertFalse(response.json['verified'])  # No physical feedback sensor.

    def test_upload_token_and_build_failure(self):
        self.assertEqual(self.client.post('/api/firmware').status_code, 403)
        html = self.client.get('/firmware').text
        token = json.loads(re.search(r'const token = (.*);', html).group(1))
        with patch('firmware_service.subprocess.run', return_value=types.SimpleNamespace(returncode=1, stdout='', stderr='compile error')) as run, patch('firmware_service.firmware_port') as port:
            response = self.client.post('/api/firmware', headers={'X-GERM-Token': token})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(run.call_count, 1)
        port.assert_not_called()

    def test_host_scripts_rejected(self):
        token = json.loads(re.search(r'const token = (.*);', self.client.get('/firmware').text).group(1))
        response = self.client.post('/api/firmware', data={'firmware': (io.BytesIO(b'x'), 'test.py')}, headers={'X-GERM-Token': token})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
