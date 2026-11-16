"""Authoritative, lock-protected symbolic state. No hardware imports or writes."""
from collections import deque
import copy
from datetime import datetime, timezone
import threading
import time
import uuid

from services.sensor_policy import SensorValidator

STATES = ('STARTUP CHECK', 'NORMAL', 'WARNING', 'DEGRADED', 'MAINTENANCE', 'SAFE STOP', 'E STOP')
REQUIRED_INTERLOCKS = ('door', 'water_level', 'leak', 'estop')
REQUIRED_SENSORS = REQUIRED_INTERLOCKS + ('air_temperature', 'humidity')


class StateManager:
    def __init__(self, policies=None, *, monotonic=time.monotonic,
                 utc_now=lambda: datetime.now(timezone.utc), software_version='m1-host-review', event_capacity=1024):
        self.lock = threading.RLock()
        self.clock, self.utc_now = monotonic, utc_now
        self.validator = SensorValidator(policies or {}, monotonic, utc_now)
        self.software_version = software_version
        self.revision = 0
        self.state = 'STARTUP CHECK'
        self.startup_complete = False
        self.controller = None
        self.controller_at = None
        self.controller_deadline_s = 6  # existing software packet expiry, not an electrical deadline
        self.maintenance = False
        self.restart_required = True
        self.estop_latched = False
        self.profile = None
        self.warning = None
        self._fingerprint = None
        self.events = deque(maxlen=event_capacity)
        self.dropped_events = 0
        self.requested_states = {'lighting': None, 'fan': None, 'pump': None}
        self.last_command = None
        self.stop_generation = 0
        self._sensor_health = {}

    def emit(self, event_type, payload, source='state'):
        if len(self.events) == self.events.maxlen:
            self.dropped_events += 1
        event = dict(schema_version=1, event_id=str(uuid.uuid4()), timestamp_utc=self.utc_now().isoformat(),
                     event_type=event_type, source=source, software_version=self.software_version,
                     experiment_id=None, payload=copy.deepcopy(payload))
        self.events.append(event)
        return event

    def observe(self, sensor_id, value, sample_time_utc, **metadata):
        with self.lock:
            result = self.validator.submit(sensor_id, value, sample_time_utc, **metadata)
            self._evaluate()
            return copy.deepcopy(result)

    def controller_feedback(self, packet):
        with self.lock:
            if packet is not None and not self.valid_feedback(packet):
                packet = None
            self.controller = copy.deepcopy(packet)
            self.controller_at = self.clock() if packet is not None else None
            self._evaluate()

    @staticmethod
    def valid_feedback(packet):
        return (isinstance(packet, dict) and type(packet.get('protocol')) is int and packet['protocol'] == 2
                and type(packet.get('id')) is int and 0 <= packet['id'] <= 60000
                and all(type(packet.get(k)) is bool for k in ('fan', 'pump'))
                and isinstance(packet.get('rgb'), list) and len(packet['rgb']) == 3
                and all(type(v) is int and 0 <= v <= 255 for v in packet['rgb']))

    def set_profile(self, profile):
        if profile is not None and (not isinstance(profile, str) or not 1 <= len(profile) <= 128):
            raise ValueError('Profile must be a stable configured identifier')
        with self.lock:
            if profile != self.profile:
                self.profile = profile
                self.revision += 1
                self.restart_required = True
                self.emit('profile_changed', {'profile': profile, 'durable': False})
            self._evaluate()

    def set_warning(self, reason):
        with self.lock:
            self.warning = reason
            self._evaluate()

    def complete_startup(self):
        with self.lock:
            self.startup_complete = True
            self._evaluate()

    def _evaluate(self):
        sensors = self.validator.snapshot()
        connected = self.controller_at is not None and self.clock() < self.controller_at + self.controller_deadline_s
        inhibits = []
        if not self.validator.policies:
            inhibits.append('sensor_policies_unconfigured')
        for name in REQUIRED_SENSORS:
            if name not in sensors:
                inhibits.append('sensor_policy_missing:' + name)
        for name in REQUIRED_INTERLOCKS:
            reading = sensors.get(name)
            if reading is None or reading['safe'] is None:
                inhibits.append(name + '_unknown')
            elif reading['safe'] is False:
                inhibits.append(name + '_unsafe')
        for name, reading in sensors.items():
            health = (reading['quality_flag'], reading['fault_reason'], reading['safe'])
            if health != self._sensor_health.get(name):
                self._sensor_health[name] = health
                self.emit('sensor_quality', dict(sensor_id=name, reading=reading,
                          raw_value=repr(self.validator.samples.get(name, {}).get('raw_value'))))
            if reading['quality_flag'] != 'good':
                inhibits.append('sensor:' + name + ':' + str(reading['fault_reason']))
        if not connected:
            inhibits.append('controller_unavailable')
        if not self.startup_complete:
            inhibits.append('startup_incomplete')
        estop_asserted = sensors.get('estop', {}).get('safe') is False
        if estop_asserted:
            self.estop_latched = True
        faulted = bool(inhibits)
        if faulted:
            self.restart_required = True
        old = self.state
        if self.estop_latched:
            self.state = 'E STOP'
        elif self.maintenance:
            self.state = 'MAINTENANCE'
        elif not self.startup_complete:
            self.state = 'STARTUP CHECK'
        elif faulted:
            # No actuator-specific conservative policy means safe stop, not a guessed fallback.
            self.state = 'SAFE STOP' if 'controller_unavailable' in inhibits or any(x.endswith('_unsafe') for x in inhibits) else 'DEGRADED'
        elif self.restart_required:
            self.state = 'SAFE STOP'
        else:
            self.state = 'WARNING' if self.warning else 'NORMAL'
        if self.maintenance:
            inhibits.append('maintenance')
        if self.restart_required:
            inhibits.append('restart_required')
        if self.estop_latched:
            inhibits.append('estop_latched')
        fingerprint = (self.state, tuple(sorted(inhibits)), self.profile, self.warning)
        if fingerprint != self._fingerprint:
            self.revision += 1
            self._fingerprint = fingerprint
            self.emit('state_transition', dict(prior_state=old, new_state=self.state,
                      cause=sorted(inhibits) or [self.warning or 'checks_valid'], inhibits=sorted(inhibits),
                      controller_feedback=self.controller if connected else None))
            if faulted or self.maintenance or self.restart_required or self.estop_latched:
                self.stop_generation += 1
        return sensors, connected, sorted(inhibits)

    def snapshot(self):
        with self.lock:
            sensors, connected, inhibits = self._evaluate()
            return copy.deepcopy(dict(system_state=self.state, state_revision=self.revision,
                inhibits=inhibits, sensors=sensors, controller_connected=connected,
                controller_feedback=self.controller if connected else None,
                maintenance=self.maintenance, maintenance_banner='MAINTENANCE - OUTPUTS INHIBITED' if self.maintenance else None,
                restart_required=self.restart_required, profile=self.profile,
                estop='asserted' if sensors.get('estop', {}).get('safe') is False else
                      ('reset_restart_required' if self.estop_latched else ('clear' if sensors.get('estop', {}).get('safe') is True else 'not_connected')),
                requested_states=self.requested_states, last_command=self.last_command,
                logging={'state': 'buffered_not_durable', 'pending': len(self.events), 'dropped': self.dropped_events},
                persistence={'state': 'not_configured', 'restart_recovery_verified': False}))

    def flush_events(self, sink):
        """Explicit optional drain; slow/failed storage is never called under the control lock."""
        with self.lock:
            pending = list(self.events)
        for event in pending:
            try:
                if not sink(copy.deepcopy(event)):
                    return False
            except Exception:
                return False
            with self.lock:
                if self.events and self.events[0]['event_id'] == event['event_id']:
                    self.events.popleft()
        return True
