"""In-process route/helper boundary tests using explicit synthetic fixtures."""
import io
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from m1_http_harness import client_fixture, confirmation
from m1_fixtures import feed, confirmed
from services.command_service import CommandGateway, dispatch_authorized
from services.control_runtime import UnavailableAdapter, install_simulation_gateway
import arduino_serial as bridge
import fan_sender
import led_sender


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app_module, self.client, self.headers, self.clock, self.state, self.adapter, self.gateway = client_fixture()

    def post(self, path, data):
        return self.client.post(path, json=data, headers=self.headers)

    def confirmed_command(self, path, data, command):
        context = confirmation(self.client, self.headers, 'command', {'command': command})
        return self.post(path, dict(data, confirmation_id=context.get('confirmation_id'), expected_state_revision=context.get('state_revision')))

    def test_all_mutations_denied_without_approved_boundary_or_token(self):
        paths = [r.rule for r in self.app_module.app.url_map.iter_rules() if 'POST' in r.methods]
        for authorizer, simulation, headers in [(None, True, self.headers), (lambda request:True, False, self.headers),
                                               (lambda request:True, True, {})]:
            self.app_module.app.config.update(GERM_CONTROL_AUTHORIZER=authorizer, GERM_SIMULATION=simulation)
            for path in paths:
                self.assertEqual(self.client.post(path.replace('<int:alert_id>', '1'),json={},headers=headers).status_code,403,path)
        self.assertEqual(self.adapter.commands, [])

    def test_physical_adapter_remains_denied_even_with_page_token_and_env(self):
        locked = CommandGateway(self.state, UnavailableAdapter())
        with self.assertRaises(ValueError):
            install_simulation_gateway(locked)
        with patch('services.control_runtime._gateway', locked), patch.dict(os.environ, {'GERM_CONTROL_ENABLED':'1', 'GERM_SIMULATION':'1', 'GERM_SERIAL_PORT':'COM1'}), patch('serial.Serial') as serial_open:
            self.assertEqual(self.post('/api/pump', {'state':'on'}).status_code,403)
            self.assertFalse(bridge._exchange('PUMP_ON'))
            serial_open.assert_not_called()
        self.assertEqual(self.adapter.commands, [])

    def test_every_control_route_is_inhibited_even_when_old_send_is_patched(self):
        self.clock.advance(0.1)
        feed(self.gateway, {'door': False})
        self.adapter.commands.clear()
        with patch.object(self.app_module, 'send_command',return_value=True) as bypass:
            for path,data in [('/api/led',{'r':255}),('/api/fan',{'state':'on'}),
                              ('/api/fan/speed',{'speed':128}),('/api/pump',{'state':'on'})]:
                response = self.post(path,data)
                self.assertEqual(response.status_code,423)
                self.assertFalse(response.json['accepted'])
            bypass.assert_not_called()
        self.assertEqual(self.adapter.commands, [])

    def test_direct_post_missing_confirmation_and_source_spoof_cannot_write(self):
        for source in ('safety','automatic','service','touchscreen'):
            response = self.post('/api/pump',{'state':'on','source':source,'authorized':True})
            self.assertEqual(response.status_code,409)
        self.assertEqual(self.adapter.commands, [])

    def test_confirm_cancel_change_accept_and_physical_distinction(self):
        context = confirmation(self.client,self.headers,'command',{'command':'PUMP_ON'})
        self.assertEqual(self.adapter.commands, [])  # cancel/prepare never dispatch
        self.state.set_warning('state changed')
        response = self.post('/api/pump',dict(state='on',confirmation_id=context['confirmation_id'],expected_state_revision=context['state_revision']))
        self.assertEqual(response.status_code,409)
        response = self.confirmed_command('/api/pump',{'state':'on'},'PUMP_ON')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['accepted'])
        self.assertTrue(response.json['firmware_confirmed'])
        self.assertFalse(response.json['physically_verified'])
        self.assertEqual(self.adapter.commands, ['PUMP_ON'])

    def test_maintenance_persists_across_pages_and_requires_exit_then_start(self):
        context = confirmation(self.client,self.headers,'enter_maintenance')
        response = self.post('/api/workflow',dict(action='enter_maintenance',confirmation_id=context['confirmation_id'],expected_state_revision=context['state_revision']))
        self.assertTrue(response.json['accepted'])
        for path in ('/','/plant','/trends','/controls','/alerts','/maintenance','/settings'):
            html = self.client.get(path).text
            self.assertIn('id="maintenance-banner"',html)
            self.assertIn('MAINTENANCE - OUTPUTS INHIBITED',html)
            state = self.client.get('/api/state').json
            self.assertEqual(state['system_state'],'MAINTENANCE')
            self.assertEqual(state['maintenance_banner'],'MAINTENANCE - OUTPUTS INHIBITED')
        self.assertEqual(self.post('/api/workflow',{'action':'exit_maintenance'}).status_code,409)
        self.assertTrue(confirmed(self.gateway,'exit_maintenance')['allowed'])
        self.assertEqual(self.client.get('/api/state').json['system_state'],'SAFE STOP')
        self.assertEqual(self.post('/api/pump',{'state':'on'}).status_code,423)

    def test_helpers_modes_heartbeat_and_raw_transport_share_boundary(self):
        self.clock.advance(0.1)
        feed(self.gateway, {'leak':True})
        self.adapter.commands.clear()
        self.assertFalse(fan_sender.send_fan('on'))
        self.assertFalse(led_sender.send_led(255,0,0,0))
        self.assertFalse(bridge.send('MODE:rainbow'))
        self.assertFalse(self.app_module.send_command('PUMP_ON'))
        self.assertFalse(bridge._exchange('PUMP_ON'))
        self.assertEqual(self.adapter.commands, [])
        with patch.object(self.adapter,'send', wraps=self.adapter.send):
            self.assertIsNone(bridge.read_line())  # STOP precedes STATUS; no A0 invented
        self.assertEqual(self.adapter.commands, ['STOP','STATUS'])
        self.assertFalse(dispatch_authorized())

    def test_custom_and_builtin_firmware_cannot_flash_or_auto_change_mode(self):
        for name in ('custom.ino','script.py'):
            self.assertEqual(self.client.post('/api/firmware',data={'firmware':(io.BytesIO(b'x'),name)},headers=self.headers).status_code,403)
        for mode in ('normal','rainbow'):
            self.assertEqual(self.client.post('/api/firmware',data={'mode':mode},headers=self.headers).status_code,423)
        self.assertEqual(self.adapter.commands, [])
        self.assertEqual(self.adapter.update_steps, [])

    def test_serial_rejects_truthy_command_id_and_physical_object(self):
        from types import SimpleNamespace
        raw = json.dumps(dict(protocol=2,id=True,fan=False,pump=False,rgb=[0,0,0])).encode()+b'\n'
        self.assertIsNone(bridge._read_packet(SimpleNamespace(read_until=lambda *args:raw)))
        with patch.object(bridge,'_ser', SimpleNamespace(is_open=True,simulated=False)), self.assertRaises(Exception):
            bridge.get_serial()

    def test_matching_ack_after_deadline_is_not_success(self):
        from check_integration import FakeSerial
        from services.command_service import dispatch_authorized
        port = FakeSerial()
        packet = dict(protocol=2,id=1,fan=False,pump=False,rgb=[0,0,0])
        with patch.object(bridge,'_sequence',0), patch.object(bridge,'get_serial',return_value=port), \
             patch('services.command_service.dispatch_authorized',return_value=True), \
             patch.object(bridge,'_read_packet',return_value=packet), \
             patch.object(bridge.time,'monotonic',side_effect=[0,0,4]):
            self.assertFalse(bridge._exchange('STOP'))
            self.assertIn('did not acknowledge',bridge.last_error())

    def test_firmware_usb_context_cannot_release_without_acknowledged_stop(self):
        from check_integration import FakeSerial
        from services.command_service import AdapterResult
        self.gateway.firmware_reviewed=True
        confirmed(self.gateway,'enter_maintenance')
        for fail in (True,False):
            self.clock.advance(0.1)
            feed(self.gateway)
            port=FakeSerial()
            bridge._ser=port
            def updater(mode):
                self.assertTrue(dispatch_authorized('firmware_update'))
                if fail:
                    with patch.object(bridge,'_exchange',return_value=False):
                        with bridge.firmware_port(): self.fail('Must not release USB')
                else:
                    with bridge.firmware_port() as name:
                        self.assertEqual(name,'/dev/fake')
                        self.assertFalse(port.is_open)
                        self.assertIsNone(bridge._ser)
                    return self.adapter.send('STATUS')
            with patch.object(self.adapter,'firmware_update',side_effect=updater):
                result=confirmed(self.gateway,'firmware_update',{'mode':'normal'})
            self.assertEqual(result['firmware_confirmed'],not fail)
            if fail:self.assertTrue(port.is_open)
            bridge._reconnect()

    def test_deployment_and_live_utilities_stop_before_any_side_effect(self):
        root = Path(__file__).resolve().parents[1]
        with patch('subprocess.run') as process, patch('urllib.request.urlopen') as network:
            for script in ('deploy_to_pi.py','verify_live.py'):
                with self.assertRaises(RuntimeError):
                    runpy.run_path(str(root/script),run_name='__main__')
            process.assert_not_called()
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
