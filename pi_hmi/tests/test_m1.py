"""Deterministic fault/permission/concurrency tests; no device integration."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

from m1_fixtures import fixture, feed, confirmed, Clock, SyntheticAdapter, SAFE_COMMANDS
from services.command_service import CommandGateway, Intent, AdapterResult
from services.sensor_policy import SensorPolicy
from services.state_service import StateManager
from services.control_runtime import UnavailableAdapter


class StateAndFaultTests(unittest.TestCase):
    def test_startup_unknown_interlocks_never_normal(self):
        s = StateManager()
        self.assertEqual(s.snapshot()['system_state'], 'STARTUP CHECK')
        s.complete_startup()
        self.assertEqual(s.snapshot()['system_state'], 'SAFE STOP')
        self.assertIn('door_unknown', s.snapshot()['inhibits'])
        self.assertEqual(s.snapshot()['estop'], 'not_connected')

    def test_each_sensor_failure_detected_by_two_periods(self):
        for name in ('door', 'water_level', 'leak', 'estop', 'air_temperature', 'humidity'):
            with self.subTest(name=name):
                clock, state, adapter, gateway = fixture()
                clock.advance(2)
                for other, policy in state.validator.policies.items():
                    if other != name:
                        state.observe(other, policy.safe_value if policy.boolean else (24 if other=='air_temperature' else 55), clock.utc().isoformat(),source='synthetic refreshed')
                state.controller_feedback(adapter.send('STATUS').reported_state)
                clock.advance(2)
                adapter.commands.clear()
                snapshot = state.snapshot()
                self.assertEqual(snapshot['sensors'][name]['quality_flag'], 'stale')
                self.assertTrue(all(r['quality_flag']=='good' for key,r in snapshot['sensors'].items() if key != name))
                result = gateway.command('PUMP_ON', authority=gateway.automatic_authority, source='automatic')
                self.assertFalse(result['allowed'])
                self.assertEqual(adapter.commands, [])
                self.assertTrue(any(name in str(e['payload']) for e in state.events))

    def test_each_unsafe_interlock_inhibits_and_reset_never_restarts(self):
        for name, value in [('door', False), ('water_level', False), ('leak', True), ('estop', True)]:
            with self.subTest(name=name):
                clock, state, adapter, gateway = fixture()
                clock.advance(0.1)
                feed(gateway, {name: value})
                adapter.commands.clear()
                self.assertNotIn(state.snapshot()['system_state'], ('NORMAL', 'WARNING'))
                self.assertFalse(confirmed(gateway, 'command', {'command': 'PUMP_ON'})['allowed'])
                clock.advance(0.1)
                feed(gateway)
                self.assertTrue(state.snapshot()['restart_required'])
                if name == 'estop':
                    self.assertEqual(state.snapshot()['system_state'], 'E STOP')
                self.assertTrue(confirmed(gateway, 'start')['allowed'])
                self.assertEqual(state.snapshot()['system_state'], 'NORMAL')

    def test_invalid_and_future_samples_need_valid_recovery(self):
        for value in (None, float('nan'), float('inf'), -999, 999, True):
            with self.subTest(value=value):
                clock, state, adapter, gateway = fixture()
                clock.advance(0.1)
                reading = state.observe('air_temperature', value, clock.utc().isoformat(), source='fault')
                self.assertNotEqual(reading['quality_flag'], 'good')
                self.assertFalse(confirmed(gateway, 'command', {'command': 'LED:1,2,3,0'})['allowed'])
                self.assertEqual(adapter.commands, [])
                clock.advance(0.1)
                feed(gateway)
                self.assertEqual(state.snapshot()['sensors']['air_temperature']['fault_reason'],'recovering')
                clock.advance(0.1)
                feed(gateway)
                self.assertEqual(state.snapshot()['sensors']['air_temperature']['quality_flag'],'good')
                self.assertTrue(state.snapshot()['restart_required'])
        clock, state, _, _ = fixture()
        future = '2099-01-01T00:00:00+00:00'
        self.assertEqual(state.observe('humidity', 50, future, source='fault')['fault_reason'], 'future_timestamp')
        self.assertEqual(state.observe('humidity', 50, '2026-01-01T00:00:00', source='fault')['fault_reason'], 'invalid_timestamp')

    def test_rate_replay_adapter_fault_and_intermittency(self):
        clock, state, _, _ = fixture()
        clock.advance(0.1)
        self.assertEqual(state.observe('air_temperature', 39, clock.utc().isoformat(), source='fault')['fault_reason'], 'implausible_rate')
        self.assertEqual(state.observe('humidity', 55, '2026-11-15T00:00:00+00:00', source='fault')['fault_reason'], 'replayed_or_out_of_order')
        self.assertEqual(state.observe('door', True, clock.utc().isoformat(), source='fault', adapter_status='error')['fault_reason'], 'adapter_error')
        for _ in range(3):
            clock.advance(0.1)
            state.observe('humidity', None, clock.utc().isoformat(), source='fault')
        clock.advance(0.1)
        self.assertEqual(state.observe('humidity', 55, clock.utc().isoformat(), source='fixture')['fault_reason'], 'intermittent')

    def test_warning_snapshot_isolation_and_conservative_reboot(self):
        _, state, _, _ = fixture()
        state.set_warning('optional model unavailable')
        self.assertEqual(state.snapshot()['system_state'], 'WARNING')
        snapshot = state.snapshot()
        snapshot['sensors']['door']['safe'] = False
        snapshot['requested_states']['pump'] = 'on'
        self.assertTrue(state.snapshot()['sensors']['door']['safe'])
        self.assertIsNone(state.snapshot()['requested_states']['pump'])
        reboot = StateManager(state.validator.policies)
        self.assertEqual(reboot.snapshot()['system_state'], 'STARTUP CHECK')
        self.assertTrue(reboot.snapshot()['restart_required'])
        self.assertFalse(reboot.snapshot()['persistence']['restart_recovery_verified'])


class PermissionTests(unittest.TestCase):
    def test_acquisition_fault_requests_safe_state_immediately_without_browser(self):
        clock,state,adapter,gateway=fixture()
        self.assertTrue(confirmed(gateway,'command',{'command':'PUMP_ON'})['firmware_confirmed'])
        clock.advance(0.1)
        adapter.commands.clear()
        gateway.observe_sensor('leak',True,clock.utc().isoformat(),source='SYNTHETIC FAULT')
        self.assertEqual(adapter.commands,['STOP'])
        self.assertFalse(adapter.uno.pump)
        self.assertTrue(state.snapshot()['restart_required'])
        self.assertTrue(any(e['event_type']=='safe_state_request' for e in state.events))

    def test_status_heartbeat_preserves_pending_confirmation_and_operator_outcome(self):
        _, state, adapter, gateway = fixture()
        prepared = gateway.prepare(gateway.intent('command', {'command': 'PUMP_ON'}), gateway.operator_authority)
        before = state.snapshot()['last_command']
        self.assertTrue(gateway.poll_status())
        self.assertEqual(state.revision, prepared['state_revision'])
        self.assertEqual(state.snapshot()['last_command'], before)
        result = gateway.command('PUMP_ON',authority=gateway.operator_authority,source='touchscreen',
                                 expected_state_revision=prepared['state_revision'],confirmation_id=prepared['confirmation_id'])
        self.assertTrue(result['firmware_confirmed'])

    def test_contradictory_stop_feedback_never_releases_update_or_renews_status(self):
        _, state, adapter, gateway = fixture(firmware_reviewed=True)
        confirmed(gateway,'enter_maintenance')
        adapter.commands.clear()
        bad = dict(protocol=2,id=1,fan=False,pump=True,rgb=[0,0,0])
        with patch.object(adapter,'send',return_value=AdapterResult(True,bad)):
            result=confirmed(gateway,'firmware_update',{'mode':'normal'})
            self.assertFalse(result['firmware_confirmed'])
            self.assertEqual(adapter.update_steps,[])
            self.assertFalse(gateway.poll_status())

    def test_policy_and_intent_validation_cannot_create_nonexpiring_or_forged_grants(self):
        _, state, adapter, gateway = fixture()
        for ttl in (float('nan'),float('inf'),0,-1,True):
            with self.assertRaises(ValueError): CommandGateway(state,adapter,confirmation_ttl_s=ttl)
        intent=gateway.intent('command',{'command':'PUMP_ON'})
        for altered in (replace(intent,schema_version=True),replace(intent,requested_at_utc='2099-01-01T00:00:00+00:00')):
            with self.assertRaises(ValueError):gateway.execute(altered,gateway.operator_authority)
        with self.assertRaises(ValueError): state.set_profile({'mutable':'value'})

    def test_unauthorized_source_or_forged_intent_cannot_dispatch(self):
        _, _, adapter, gateway = fixture()
        for source in ('touchscreen', 'automatic', 'safety', 'service', 'invented'):
            self.assertFalse(gateway.command('PUMP_ON', authority=object(), source=source)['allowed'])
        intent = gateway.intent('command', {'command': 'PUMP_ON'})
        with self.assertRaises(ValueError):
            gateway.execute(replace(intent, action='read_status'), gateway.operator_authority)
        self.assertEqual(adapter.commands, [])

    def test_confirmation_once_bound_to_payload_authority_revision_and_expiry(self):
        for changed in ('payload', 'authority', 'state', 'expiry', 'missing'):
            with self.subTest(changed=changed):
                clock, state, adapter, gateway = fixture()
                prepared = gateway.prepare(gateway.intent('command', {'command': 'PUMP_ON'}), gateway.operator_authority)
                command, authority = 'PUMP_ON', gateway.operator_authority
                if changed == 'payload': command = 'PUMP_5S'
                if changed == 'authority': authority = object()
                if changed == 'state': state.set_warning('changed')
                if changed == 'expiry': clock.advance(30)
                nonce = prepared['confirmation_id'] if changed != 'missing' else None
                result = gateway.command(command, authority=authority, source='touchscreen',
                    confirmation_id=nonce, expected_state_revision=prepared['state_revision'])
                self.assertFalse(result['allowed'])
                self.assertEqual(adapter.commands, [])
        _, state, adapter, gateway = fixture()
        prepared = gateway.prepare(gateway.intent('command', {'command': 'PUMP_ON'}), gateway.operator_authority)
        args = dict(authority=gateway.operator_authority, source='touchscreen', confirmation_id=prepared['confirmation_id'], expected_state_revision=prepared['state_revision'])
        self.assertTrue(gateway.command('PUMP_ON', **args)['firmware_confirmed'])
        self.assertFalse(gateway.command('PUMP_ON', **args)['allowed'])
        self.assertEqual(adapter.commands, ['PUMP_ON'])

    def test_requested_ack_and_physical_outcomes_are_separate(self):
        _, state, adapter, gateway = fixture()
        adapter.fail = True
        result = confirmed(gateway, 'command', {'command': 'PUMP_ON'})
        self.assertTrue(result['accepted'])
        self.assertFalse(result['firmware_confirmed'])
        self.assertFalse(result['physically_verified'])
        self.assertIsNone(result['reported_state'])
        self.assertEqual(state.snapshot()['requested_states']['pump'], 'on')
        self.assertTrue(state.snapshot()['restart_required'])

    def test_missing_physical_and_safe_output_policies_are_denied(self):
        _, state, adapter, _ = fixture()
        physical = CommandGateway(state, UnavailableAdapter())
        self.assertFalse(physical.command('PUMP_OFF', authority=physical.safety_authority, source='safety')['allowed'])
        unknown = CommandGateway(state, adapter)
        self.assertFalse(unknown.command('STOP', authority=unknown.safety_authority, source='safety')['allowed'])
        self.assertEqual(adapter.commands, [])

    def test_maintenance_exit_and_manual_test_never_authorize_automatic_restart(self):
        clock, state, adapter, gateway = fixture()
        self.assertTrue(confirmed(gateway, 'enter_maintenance')['accepted'])
        self.assertEqual(state.snapshot()['maintenance_banner'], 'MAINTENANCE - OUTPUTS INHIBITED')
        adapter.commands.clear()
        self.assertFalse(gateway.command('PUMP_ON', authority=gateway.automatic_authority, source='automatic')['allowed'])
        self.assertTrue(confirmed(gateway, 'safe_manual_test', {'command': 'PUMP_5S'})['firmware_confirmed'])
        self.assertEqual(state.snapshot()['system_state'], 'MAINTENANCE')
        self.assertTrue(confirmed(gateway, 'exit_maintenance')['allowed'])
        self.assertEqual(state.snapshot()['system_state'], 'SAFE STOP')
        self.assertFalse(confirmed(gateway, 'command', {'command': 'PUMP_ON'})['allowed'])
        self.assertTrue(confirmed(gateway, 'start')['allowed'])

    def test_estop_latch_blocks_maintenance_test_after_signal_reset(self):
        clock, state, adapter, gateway = fixture()
        confirmed(gateway, 'enter_maintenance')
        clock.advance(0.1)
        feed(gateway, {'estop': True})
        for _ in range(2):
            clock.advance(0.1)
            feed(gateway)
        adapter.commands.clear()
        self.assertEqual(state.snapshot()['estop'], 'reset_restart_required')
        self.assertFalse(confirmed(gateway,'safe_manual_test',{'command':'PUMP_5S'})['allowed'])
        self.assertEqual(adapter.commands, [])

    def test_failed_safe_stop_blocks_watchdog_heartbeat(self):
        clock, state, adapter, gateway = fixture()
        clock.advance(0.1)
        feed(gateway, {'door': False})
        adapter.commands.clear()
        adapter.fail = True
        self.assertFalse(gateway.poll_status())
        self.assertEqual(adapter.commands, ['STOP'])
        self.assertFalse(state.snapshot()['controller_connected'])

    def test_firmware_is_review_gated_and_stop_failure_prevents_update(self):
        for reviewed, fail in ((False, False), (True, True), (True, False)):
            _, state, adapter, gateway = fixture(firmware_reviewed=reviewed)
            confirmed(gateway, 'enter_maintenance')
            adapter.commands.clear()
            adapter.fail = fail
            result = confirmed(gateway, 'firmware_update', {'mode': 'normal'})
            if not reviewed:
                self.assertFalse(result['allowed'])
                self.assertEqual(adapter.commands, [])
            elif fail:
                self.assertFalse(result['firmware_confirmed'])
            else:
                self.assertTrue(result['firmware_confirmed'])
                self.assertEqual(adapter.commands[:1], ['STOP'])
            self.assertEqual(bool(adapter.update_steps), reviewed and not fail)
            self.assertFalse(confirmed(gateway, 'firmware_update', {'mode': 'rainbow'})['allowed'])
        with self.assertRaises(ValueError):
            gateway.intent('firmware_update', {'custom': 'sketch'})

    def test_duplicate_request_does_not_repeat_dispatch(self):
        _, _, adapter, gateway = fixture()
        args = dict(authority=gateway.operator_authority, source='touchscreen', request_id='same')
        self.assertTrue(gateway.command('PUMP_OFF', **args)['accepted'])
        self.assertFalse(gateway.command('PUMP_OFF', **args)['allowed'])
        self.assertEqual(adapter.commands, ['PUMP_OFF'])

    def test_concurrent_confirmation_replay_dispatches_at_most_once(self):
        _, _, adapter, gateway = fixture()
        prepared = gateway.prepare(gateway.intent('command', {'command': 'PUMP_ON'}), gateway.operator_authority)
        barrier = threading.Barrier(9)
        results = []
        def worker():
            barrier.wait()
            results.append(gateway.command('PUMP_ON', authority=gateway.operator_authority, source='touchscreen',
                expected_state_revision=prepared['state_revision'], confirmation_id=prepared['confirmation_id']))
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(r['accepted'] for r in results), 1)
        self.assertEqual(adapter.commands, ['PUMP_ON'])

    def test_fault_committed_before_concurrent_requests_has_zero_writes(self):
        clock, state, adapter, gateway = fixture()
        clock.advance(0.1)
        feed(gateway, {'leak': True})
        adapter.commands.clear()
        threads = [threading.Thread(target=lambda: gateway.command('PUMP_ON', source='automatic', authority=gateway.automatic_authority)) for _ in range(12)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(2)
        self.assertEqual(adapter.commands, [])

    def test_optional_storage_failure_cannot_block_control_or_grant_permission(self):
        _, state, adapter, gateway = fixture()
        entered, release = threading.Event(), threading.Event()
        def blocked_sink(event):
            entered.set()
            release.wait(2)
            return False
        thread = threading.Thread(target=lambda: state.flush_events(blocked_sink))
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
            self.assertTrue(gateway.command('PUMP_OFF', authority=gateway.operator_authority, source='touchscreen')['firmware_confirmed'])
        finally:
            release.set()
            thread.join(2)
        self.assertGreater(len(state.events), 0)
        self.assertEqual(adapter.commands, ['PUMP_OFF'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
