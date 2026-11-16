"""Explicit synthetic policies and controller; not an installed wiring map."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.command_service import AdapterResult, CommandGateway
from services.sensor_policy import SensorPolicy
from services.state_service import StateManager
from sim.run_sim import FakeUno


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def utc(self):
        return datetime(2026, 11, 15, tzinfo=timezone.utc) + timedelta(seconds=self.value)

    def advance(self, seconds):
        self.value += seconds


class SyntheticAdapter:
    simulated = True

    def __init__(self, clock):
        self.uno = FakeUno(clock=clock.monotonic)
        self.commands, self.update_steps = [], []
        self.fail = False

    def send(self, command):
        self.commands.append(command)
        if self.fail:
            return AdapterResult(False, error='Injected timeout')
        with contextlib.redirect_stdout(io.StringIO()):
            self.uno.handle('CMD:1:' + command)
        packet = json.loads(self.uno.out)
        self.uno.out.clear()
        return AdapterResult(not bool(packet.get('error')), packet, packet.get('error'))

    def firmware_update(self, mode):
        # Abstract simulated session only: no CLI, subprocess, serial release or flash.
        self.update_steps.extend(['compile_synthetic', 'release_synthetic', 'upload_synthetic', 'status_synthetic'])
        return self.send('STATUS')


SAFE_COMMANDS = ('STOP', 'FAN_OFF', 'FAN_SPEED:0', 'PUMP_OFF', 'LED_OFF', 'LED:0,0,0,0', 'MODE:normal')


def fixture(*, started=True, firmware_reviewed=False):
    clock = Clock()
    policies = {name: SensorPolicy(name, 'normalized boolean', 2, 4, boolean=True,
                                  safe_value=safe, recovery_samples=1, location='SYNTHETIC ONLY')
                for name, safe in [('door', True), ('water_level', True), ('leak', False), ('estop', False)]}
    policies['air_temperature'] = SensorPolicy('air_temperature', 'degC', 2, 4, minimum=10, maximum=40,
                                              max_rate_per_s=10, location='SYNTHETIC ONLY')
    policies['humidity'] = SensorPolicy('humidity', '%RH', 2, 4, minimum=20, maximum=95, location='SYNTHETIC ONLY')
    state = StateManager(policies, monotonic=clock.monotonic, utc_now=clock.utc)
    adapter = SyntheticAdapter(clock)
    gateway = CommandGateway(state, adapter, safe_commands=SAFE_COMMANDS, safe_manual_commands=('PUMP_5S',),
                             firmware_reviewed=firmware_reviewed)
    feed(gateway)
    clock.advance(0.1)
    feed(gateway)
    state.set_profile('synthetic-basil')
    state.complete_startup()
    if started:
        confirmed(gateway, 'start')
    adapter.commands.clear()
    return clock, state, adapter, gateway


def feed(gateway, overrides=None):
    values = dict(door=True, water_level=True, leak=False, estop=False, air_temperature=24, humidity=55)
    values.update(overrides or {})
    for name, value in values.items():
        gateway.state.observe(name, value, gateway.state.utc_now().isoformat(), source='SYNTHETIC FIXTURE')
    result = gateway.adapter.send('STATUS')
    gateway.state.controller_feedback(result.reported_state if result.acknowledged else None)


def confirmed(gateway, action, payload=None, *, authority=None, source='touchscreen', **extra):
    authority = authority or gateway.operator_authority
    intent = gateway.intent(action, payload, source=source)
    prepared = gateway.prepare(intent, authority)
    if not prepared['allowed']:
        return prepared
    return gateway.execute(gateway.intent(action, payload, source=source,
        expected_state_revision=prepared['state_revision'], confirmation_id=prepared.get('confirmation_id'), **extra), authority)
