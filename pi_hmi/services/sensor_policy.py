"""Pure sensor validation. Policies describe normalized inputs, never GPIO pins."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class SensorPolicy:
    sensor_id: str
    unit: str
    expected_period_s: float
    maximum_age_s: float
    minimum: float = float('-inf')
    maximum: float = float('inf')
    max_rate_per_s: float | None = None
    recovery_samples: int = 2
    affected_actions: tuple = ('set_pump', 'set_lighting', 'set_fan', 'set_lighting_mode')
    boolean: bool = False
    safe_value: bool | None = None
    location: str = 'unconfirmed'
    failure_window_s: float = 30
    failure_limit: int = 3

    def __post_init__(self):
        if (not self.sensor_id or not finite(self.expected_period_s) or self.expected_period_s <= 0
                or not finite(self.maximum_age_s) or not 0 < self.maximum_age_s <= 2 * self.expected_period_s
                or self.recovery_samples < 1 or self.minimum > self.maximum
                or (self.max_rate_per_s is not None and (not finite(self.max_rate_per_s) or self.max_rate_per_s <= 0))
                or not finite(self.failure_window_s) or self.failure_window_s <= 0 or self.failure_limit < 1
                or (not self.boolean and (not finite(self.minimum) or not finite(self.maximum)))
                or (self.boolean and type(self.safe_value) is not bool)):
            raise ValueError('Invalid sensor policy; fault deadline must be <= two expected periods')


class SensorValidator:
    def __init__(self, policies, monotonic, utc_now):
        self.policies = dict(policies)
        self.clock, self.utc_now = monotonic, utc_now
        self.samples, self.good, self.failures, self.previous = {}, {}, {}, {}

    def submit(self, sensor_id, value, sample_time_utc, *, source, adapter_status='ready', sequence=None):
        p = self.policies[sensor_id]
        now = self.clock()
        reason = None
        stamp = None
        try:
            stamp = datetime.fromisoformat(sample_time_utc)
            if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError('UTC offset required')
            age = (self.utc_now() - stamp).total_seconds()
        except (TypeError, ValueError, OverflowError):
            age, reason = 0, 'invalid_timestamp'
        if adapter_status != 'ready':
            reason = 'adapter_' + str(adapter_status)
        elif value is None:
            reason = 'missing'
        elif reason is None:
            if age < 0:
                reason = 'future_timestamp'
            elif age >= p.maximum_age_s:
                reason = 'stale'
            elif p.boolean and type(value) is not bool:
                reason = 'invalid_type'
            elif not p.boolean and not finite(value):
                reason = 'nonfinite_or_invalid_type'
            elif not p.boolean and not p.minimum <= value <= p.maximum:
                reason = 'out_of_range'
        prior = self.previous.get(sensor_id)
        if reason is None and prior:
            if stamp <= prior['stamp'] or (sequence is not None and prior['sequence'] is not None and sequence <= prior['sequence']):
                reason = 'replayed_or_out_of_order'
            elif p.max_rate_per_s is not None:
                elapsed = (stamp - prior['stamp']).total_seconds()
                if abs(value - prior['value']) / elapsed > p.max_rate_per_s:
                    reason = 'implausible_rate'
        failures = [t for t in self.failures.get(sensor_id, []) if now - t < p.failure_window_s]
        if reason:
            failures.append(now)
            self.good[sensor_id] = 0
        else:
            self.previous[sensor_id] = dict(stamp=stamp, sequence=sequence, value=value)
            self.good[sensor_id] = self.good.get(sensor_id, 0) + 1
            if len(failures) >= p.failure_limit:
                reason = 'intermittent'
            elif self.good[sensor_id] < p.recovery_samples:
                reason = 'recovering'
        self.failures[sensor_id] = failures
        self.samples[sensor_id] = dict(value=value if reason is None else None, raw_value=value,
                                      timestamp_utc=stamp.isoformat() if stamp else None,
                                      received_monotonic=now, initial_age_s=max(0, age), source=source,
                                      sequence=sequence, adapter_status=adapter_status, fault_reason=reason)
        return self.read(sensor_id)

    def read(self, sensor_id):
        p = self.policies[sensor_id]
        sample = self.samples.get(sensor_id)
        age = None if sample is None else max(0, self.clock() - sample['received_monotonic']) + sample['initial_age_s']
        reason = 'missing' if sample is None else sample['fault_reason']
        if sample is not None and self.clock() >= sample['received_monotonic'] + p.maximum_age_s - sample['initial_age_s']:
            reason = 'stale'
            self.good[sensor_id] = 0
        quality = 'good' if reason is None else ('stale' if reason == 'stale' else 'invalid')
        if reason == 'missing':
            quality = 'missing'
        return dict(value=sample['value'] if sample and quality == 'good' else None,
                    unit=p.unit, timestamp_utc=sample['timestamp_utc'] if sample else None,
                    age_seconds=age, quality_flag=quality, fault_reason=reason,
                    expected_period_s=p.expected_period_s, location=p.location,
                    state='fresh' if quality == 'good' else ('stale' if quality == 'stale' else 'unavailable'),
                    source=sample['source'] if sample else 'No sample',
                    safe=(sample['value'] == p.safe_value) if sample and quality == 'good' and p.boolean else None)

    def snapshot(self):
        return {name: self.read(name) for name in self.policies}
