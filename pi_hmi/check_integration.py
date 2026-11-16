"""Existing integration checks reconciled to the authorized M1 host boundary."""
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tests'))
import arduino_serial as bridge
from m1_http_harness import client_fixture, confirmation
from services.control_runtime import SimulatedSerialAdapter


class FakeSerial:
    simulated = True
    is_open = True
    port = '/dev/fake'

    def __init__(self, acknowledge=True):
        self.pending = []
        self.acknowledge = acknowledge

    def write(self, data):
        self.command = data.decode().strip()
        seq = int(self.command.split(':', 2)[1])
        state = dict(protocol=2, id=seq-1, fan=False, pump=False, rgb=[0, 0, 0])
        self.pending.append(json.dumps(state).encode() + b'\n')
        if self.acknowledge:
            state['id'] = seq
            self.pending.append(json.dumps(state).encode() + b'\n')

    def read_until(self, *args):
        return self.pending.pop(0) if self.pending else b''

    def close(self):
        self.is_open = False


class SerialTests(unittest.TestCase):
    def setUp(self):
        *_, self.gateway = client_fixture()
        self.gateway.adapter = SimulatedSerialAdapter()

    def tearDown(self):
        bridge._reconnect()

    def test_matched_acknowledgement(self):
        bridge._ser = FakeSerial()
        self.assertTrue(bridge.send('FAN_OFF', authority=self.gateway.service_authority))
        self.assertTrue(bridge.is_connected())
        self.assertTrue(bridge._ser.command.endswith(':FAN_OFF'))

    def test_stale_acknowledgement_is_not_success(self):
        bridge._ser = FakeSerial(acknowledge=False)
        with patch.object(bridge.time, 'monotonic', side_effect=[0, 0, 0, 0, 4]):
            self.assertFalse(bridge.send('FAN_OFF', authority=self.gateway.service_authority))

    def test_firmware_pause_requires_gateway_session(self):
        bridge._ser = FakeSerial()
        with self.assertRaises(RuntimeError):
            with bridge.firmware_port():
                self.fail('Unscoped firmware port must be denied')
        self.assertTrue(bridge._ser.is_open)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.app_module, self.client, self.headers, self.clock, self.state, self.adapter, self.gateway = client_fixture()

    def test_routes_preserved(self):
        for route in ['/', '/controls', '/settings', '/firmware', '/api/state', '/sensor']:
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_invalid_values_never_send(self):
        for route, data in [('/api/led', {'r': 1.5}), ('/api/led', {'w':20}),
                            ('/api/fan/speed', {'speed':256}), ('/api/fan', []), ('/api/pump', {'state':'bad'})]:
            self.assertEqual(self.client.post(route, json=data, headers=self.headers).status_code,400)
        self.assertEqual(self.adapter.commands, [])

    def test_fan_command_is_acknowledged(self):
        response = self.client.post('/api/fan', json={'state':'off'}, headers=self.headers)
        self.assertEqual(self.adapter.commands, ['FAN_OFF'])
        self.assertTrue(response.json['firmware_confirmed'])
        self.assertFalse(response.json['verified'])

    def test_fan_pwm_speed_is_acknowledged(self):
        context = confirmation(self.client, self.headers, 'command', {'command':'FAN_SPEED:128'})
        data = {'speed':128, 'confirmation_id':context['confirmation_id'], 'expected_state_revision':context['state_revision']}
        response = self.client.post('/api/fan/speed', json=data, headers=self.headers)
        self.assertEqual(self.adapter.commands, ['FAN_SPEED:128'])
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['firmware_confirmed'])
        self.assertFalse(response.json['verified'])

    def test_dashboard_reports_fan_pwm_speed(self):
        packet = dict(protocol=2, id=1, fan=True, fan_speed=128, pump=False, rgb=[0,0,0])
        self.state.controller_feedback(packet)
        response = self.client.get('/api/state')
        self.assertEqual(response.json['actuators']['fan']['speed'],128)

    def test_upload_token_and_review_gate(self):
        self.assertEqual(self.client.post('/api/firmware').status_code,403)
        response = self.client.post('/api/firmware', headers=self.headers)
        self.assertEqual(response.status_code,423)
        self.assertFalse(response.json['accepted'])
        self.assertEqual(self.adapter.update_steps, [])

    def test_host_scripts_and_custom_sketches_rejected(self):
        for name in ('test.py','custom.ino'):
            response = self.client.post('/api/firmware',data={'firmware':(io.BytesIO(b'x'),name)},headers=self.headers)
            self.assertEqual(response.status_code,403)
        self.assertEqual(self.adapter.commands, [])

    def test_lighting_selector_and_unknown_mode(self):
        html = self.client.get('/controls').text
        self.assertIn('id="lighting-mode"',html)
        self.assertIn('value="rainbow"',html)
        response = self.client.post('/api/firmware',data={'mode':'../invalid'},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.adapter.commands, [])

    def test_upload_modes_do_not_bypass_gateway(self):
        for mode in ('normal','rainbow'):
            response = self.client.post('/api/firmware',data={'mode':mode},headers=self.headers)
            self.assertEqual(response.status_code,423)
        self.assertEqual(self.adapter.commands, [])
        self.assertEqual(self.adapter.update_steps, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
