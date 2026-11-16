"""M0 contracts and candidate-controller simulation; never opens hardware."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pi_hmi'))

import arduino_serial as bridge
import sim.run_sim as simulator
from sim.run_sim import FakeUno

class SimulatorContractTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.uno = FakeUno(clock=lambda: self.now)

    def command(self, text, cid=1):
        with contextlib.redirect_stdout(io.StringIO()):
            self.uno.handle(f'CMD:{cid}:{text}')
        packet = json.loads(self.uno.out)
        self.uno.out.clear()
        self.assertEqual(packet['id'], cid)
        self.assertEqual(packet['protocol'], 2)
        self.assertIsNone(packet['a0'])
        return packet

    def test_pwm_requests_and_reported_state_match_candidate(self):
        for speed in (0, 1, 128, 254, 255):
            packet = self.command(f'FAN_SPEED:{speed}')
            self.assertNotIn('error', packet)
            self.assertTrue(packet['fan_pwm'])
            self.assertEqual(packet['fan_speed'], speed)
            self.assertEqual(packet['fan'], speed > 0)
        self.assertEqual(self.command('FAN_OFF')['fan_speed'], 0)
        self.assertEqual(self.command('FAN_ON')['fan_speed'], 255)

    def test_invalid_pwm_does_not_change_output_or_extend_watchdog(self):
        self.command('FAN_SPEED:128')
        self.now = 9
        for value in ('256', '-1', '1.5', '', '１２', '000000'):
            packet = self.command('FAN_SPEED:' + value)
            self.assertEqual(packet['error'], 'Invalid fan speed')
            self.assertEqual(packet['fan_speed'], 128)
        self.now = 10
        self.uno._tick()
        self.assertEqual(self.uno.fan_speed, 0)

    def test_watchdog_and_stop_clear_all_reported_outputs(self):
        self.command('MODE:rainbow')
        self.command('FAN_SPEED:128')
        self.command('PUMP_ON')
        self.now = 10
        self.uno._tick()
        self.assertFalse(self.uno.pump or self.uno.fan or self.uno.rainbow)
        self.assertEqual(self.uno.rgb, [0, 0, 0])
        self.assertEqual(self.uno.fan_speed, 0)
        self.command('FAN_SPEED:128')
        self.assertEqual(self.command('STOP')['fan_speed'], 0)

    def test_status_does_not_extend_pump_limit_or_on_reset_timer(self):
        self.command('PUMP_ON')
        for second in (5, 10, 15, 20, 25):
            self.now = second
            self.assertTrue(self.command('STATUS')['pump'])
            self.command('PUMP_ON')
        self.now = 30
        self.assertFalse(self.command('STATUS')['pump'])

    def test_shorter_pulse_shortens_existing_run(self):
        self.command('PUMP_ON')
        self.now = 4
        self.command('PUMP_5S')
        self.now = 5
        self.assertFalse(self.command('STATUS')['pump'])

    def test_led_white_rejection_preserves_rgb_and_mode(self):
        self.command('MODE:rainbow')
        self.assertIn('error', self.command('LED:1,2,3,4'))
        self.assertTrue(self.uno.rainbow)
        packet = self.command('LED:1,2,3,0')
        self.assertEqual(packet['rgb'], [1, 2, 3])
        self.assertEqual(packet['lighting_mode'], 'normal')
        self.assertFalse(packet['white_channel'])

    def test_real_bridge_accepts_simulator_ack_without_opening_serial(self):
        try:
            with patch.object(simulator, 'UNO', self.uno), patch.object(bridge, 'get_serial') as opened:
                bridge._ser = simulator.FakeSerial('/dev/synthetic-only')
                opened.return_value = bridge._ser
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertTrue(bridge.send('FAN_SPEED:128'))
                packet = bridge.reported_state()
                self.assertEqual(packet['fan_speed'], 128)
                self.assertTrue(packet['fan'])
        finally:
            bridge._reconnect()

    def test_bundled_showcase_only_changes_startup_default(self):
        canonical = (ROOT / 'pi_hmi/arduino_program/arduino_program.ino').read_text(encoding='utf-8')
        showcase = (ROOT / 'Showcase LED Display.ino').read_text(encoding='utf-8')
        self.assertEqual('\n'.join(showcase.splitlines()[2:]), '\n'.join(canonical.splitlines()))


class ChecklistContractTests(unittest.TestCase):
    def test_all_screen_fields_and_actual_endpoint_references_are_grounded(self):
        docs = ROOT / 'docs' / 'phase0'
        checklist = json.loads((docs / 'HMI_API_CHECKLIST.json').read_text(encoding='utf-8'))
        endpoints = json.loads((docs / 'API_ENDPOINTS.json').read_text(encoding='utf-8'))
        actual = {(e['path'], e['method']) for e in endpoints}
        rows = checklist['rows']
        self.assertEqual(len({r['id'] for r in rows}), len(rows))
        self.assertEqual({r['screen'] for r in rows},
                         {'Home', 'Plant', 'Trends', 'Controls', 'Alerts', 'Maintenance', 'Settings', 'Shared'})
        self.assertTrue({f'H{i:02}' for i in range(1, 14)} <= {r['id'] for r in rows})
        for row in rows:
            with self.subTest(case=row['id']):
                for key in ('source', 'quality', 'confirmation', 'acceptance_case', 'status', 'gap', 'owner', 'evidence'):
                    self.assertTrue(row[key])
                for key in ('backend', 'command'):
                    if row[key] is not None:
                        self.assertIn((row[key]['path'], row[key]['method']), actual)
        documented_actions = {(r['command']['path'], r['command']['method']) for r in rows if r['command']}
        self.assertEqual(documented_actions, {(e['path'], e['method']) for e in endpoints if e['method'] == 'POST'})

    def test_provisional_requirements_preserve_all_forty_official_rows(self):
        baseline = json.loads((ROOT / 'docs/phase0/REQUIREMENTS_BASELINE.json').read_text(encoding='utf-8'))
        rows = baseline['rows'][1:]
        ids = [row[2] for row in rows]
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertTrue(all(row[3] and row[8] in ('PARTIAL', 'MISSING') for row in rows))
        self.assertIn('provisional', baseline['version'].lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
