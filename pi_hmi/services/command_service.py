"""Single permission/confirmation/dispatch boundary for host-side M1.

No physical adapter is enabled by this module. Authorities are object identities
supplied by trusted application code, never deserialized from an HTTP request.
"""
from collections import OrderedDict
from contextvars import ContextVar
import copy
from dataclasses import dataclass
from datetime import datetime
import json
import math
import secrets
import uuid

_dispatch = ContextVar('germ_command_dispatch', default=None)


def dispatch_authorized(action=None):
    context = _dispatch.get()
    return bool(context and context['simulated'] and (action is None or context['action'] == action))


def outputs_reported_off(packet):
    return (isinstance(packet, dict) and packet.get('pump') is False and packet.get('fan') is False
            and packet.get('rgb') == [0, 0, 0] and packet.get('fan_speed', 0) == 0
            and packet.get('lighting_mode', 'normal') != 'rainbow')


@dataclass(frozen=True)
class Intent:
    action: str
    target: str
    payload_json: str
    source: str
    request_id: str
    requested_at_utc: str
    expected_state_revision: int | None = None
    confirmation_id: str | None = None
    schema_version: int = 1

    @property
    def payload(self):
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class AdapterResult:
    acknowledged: bool
    reported_state: dict | None = None
    error: str | None = None


def command_model(message):
    if not isinstance(message, str) or any(c in message for c in '\r\n'):
        raise ValueError('Invalid command')
    simple = {'STATUS': ('read_status', 'controller', None, False),
              'STOP': ('stop', 'all', 'off', False),
              'FAN_ON': ('set_fan', 'fan', 'on', True), 'FAN_OFF': ('set_fan', 'fan', 'off', False),
              'PUMP_ON': ('set_pump', 'pump', 'on', True), 'PUMP_5S': ('set_pump', 'pump', '5s', True),
              'PUMP_OFF': ('set_pump', 'pump', 'off', False),
              'LED_ON': ('set_lighting', 'lighting', [255, 255, 255, 0], True),
              'LED_OFF': ('set_lighting', 'lighting', [0, 0, 0, 0], False),
              'MODE:normal': ('set_lighting_mode', 'lighting', 'normal', False),
              'MODE:rainbow': ('set_lighting_mode', 'lighting', 'rainbow', True)}
    if message in simple:
        return simple[message]
    if message.startswith('FAN_SPEED:'):
        value = message[10:]
        if not value or not value.isascii() or not value.isdecimal() or len(value) > 3 or int(value) > 255:
            raise ValueError('Invalid fan speed')
        return 'set_fan', 'fan', {'speed': int(value)}, int(value) > 0
    if message.startswith('LED:'):
        parts = message[4:].split(',')
        if len(parts) != 4 or any(not p or len(p) > 3 or not p.isascii() or not p.isdecimal() or int(p) > 255 for p in parts):
            raise ValueError('Invalid RGB values')
        values = list(map(int, parts))
        if values[3]:
            raise ValueError('White channel is unavailable in this software candidate')
        return 'set_lighting', 'lighting', values, any(values)
    raise ValueError('Unsupported command')


class CommandGateway:
    def __init__(self, state, adapter, *, safe_commands=(), safe_manual_commands=(),
                 firmware_reviewed=False, confirmation_ttl_s=30, cache_limit=1024):
        if (type(confirmation_ttl_s) not in (int, float) or not math.isfinite(confirmation_ttl_s) or confirmation_ttl_s <= 0
                or type(cache_limit) is not int or cache_limit < 1):
            raise ValueError('Invalid confirmation/cache policy')
        self.state, self.adapter = state, adapter
        self.safe_commands = tuple(safe_commands)
        self.safe_manual_commands = tuple(safe_manual_commands)
        self.firmware_reviewed = firmware_reviewed
        self.ttl, self.limit = confirmation_ttl_s, cache_limit
        self.confirmations, self.requests = OrderedDict(), OrderedDict()
        self.operator_authority = object()
        self.automatic_authority = object()
        self.safety_authority = object()
        self.service_authority = object()
        self._authorities = {self.operator_authority: 'touchscreen', self.automatic_authority: 'automatic',
                             self.safety_authority: 'safety', self.service_authority: 'service'}
        self._stopped_generation = -1

    def intent(self, action, payload=None, *, source='touchscreen', request_id=None,
               expected_state_revision=None, confirmation_id=None):
        if payload is not None and not isinstance(payload, dict):
            raise ValueError('Expected object payload')
        payload = copy.deepcopy(payload or {})
        if action == 'command':
            action, target, _, _ = command_model(payload.get('command'))
        elif action == 'safe_manual_test':
            _, target, _, energizing = command_model(payload.get('command'))
            if not energizing:
                raise ValueError('Safe manual test must identify a reviewed test command')
        elif action == 'firmware_update':
            target = 'controller'
            if set(payload) != {'mode'} or payload['mode'] not in ('normal', 'rainbow'):
                raise ValueError('Custom or unknown firmware is denied')
        elif action in ('start', 'pause', 'enter_maintenance', 'exit_maintenance'):
            target = 'system'
            if payload:
                raise ValueError('Workflow does not accept extra payload fields')
        else:
            raise ValueError('Unsupported action')
        if expected_state_revision is not None and (type(expected_state_revision) is not int or expected_state_revision < 0):
            raise ValueError('Invalid state revision')
        if confirmation_id is not None and (not isinstance(confirmation_id, str) or not 1 <= len(confirmation_id) <= 256):
            raise ValueError('Invalid confirmation ID')
        if request_id is not None and (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128):
            raise ValueError('Invalid request ID')
        return Intent(action, target, json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False), source,
                      request_id or str(uuid.uuid4()), self.state.utc_now().isoformat(),
                      expected_state_revision, confirmation_id)

    def _key(self, intent, authority):
        return intent.action, intent.target, intent.payload_json, intent.source, authority

    def _validate(self, intent):
        if not isinstance(intent, Intent) or type(intent.schema_version) is not int or intent.schema_version != 1:
            raise ValueError('Invalid intent schema')
        payload = intent.payload
        action = 'command' if 'command' in payload and intent.action != 'safe_manual_test' else intent.action
        normalized = self.intent(action, payload, source=intent.source, request_id=intent.request_id,
                                 expected_state_revision=intent.expected_state_revision, confirmation_id=intent.confirmation_id)
        if normalized.action != intent.action or normalized.target != intent.target or normalized.payload_json != intent.payload_json:
            raise ValueError('Intent does not match its normalized command')
        if 'command' in payload and set(payload) != {'command'}:
            raise ValueError('Unexpected command fields')
        try:
            stamp = datetime.fromisoformat(intent.requested_at_utc)
            if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0 or not 0 <= (self.state.utc_now() - stamp).total_seconds() <= self.ttl:
                raise ValueError('Stale, future or non-UTC intent')
        except (TypeError, OverflowError):
            raise ValueError('Invalid intent time') from None

    def _permission(self, intent, authority, snapshot):
        if self._authorities.get(authority) != intent.source:
            return ['unauthorized_source'], 403
        if intent.source in ('safety', 'service') and intent.action not in ('stop', 'read_status', 'set_fan', 'set_lighting', 'set_pump', 'set_lighting_mode'):
            return ['unauthorized_action'], 403
        if intent.action in ('start', 'enter_maintenance', 'exit_maintenance') and intent.source != 'touchscreen':
            return ['operator_action_required'], 403
        command = intent.payload.get('command')
        energizing = command_model(command)[3] if command else False
        if intent.source in ('safety', 'service') and energizing:
            return ['unauthorized_energization'], 403
        if intent.action in ('pause', 'enter_maintenance'):
            return [], 200
        if not getattr(self.adapter, 'simulated', False):
            return ['hardware_integration_not_authorized'], 423
        if intent.action == 'read_status':
            return [], 200
        if command and not energizing:
            return ([], 200) if command in self.safe_commands else (['safe_output_policy_unconfirmed'], 423)
        blocking = [x for x in snapshot['inhibits'] if x not in ('maintenance', 'restart_required', 'estop_latched')]
        if blocking:
            return blocking, 423
        if intent.action == 'exit_maintenance':
            return ([], 200) if snapshot['maintenance'] else (['not_in_maintenance'], 409)
        if intent.action == 'start':
            if snapshot['maintenance']:
                return ['maintenance'], 423
            return ([], 200) if snapshot['profile'] else (['profile_unconfigured'], 423)
        if intent.action == 'firmware_update':
            if intent.payload['mode'] != 'normal':
                return ['firmware_boot_energization_denied'], 423
            if not self.firmware_reviewed or not callable(getattr(self.adapter, 'firmware_update', None)):
                return ['firmware_safety_review_required'], 423
            if not snapshot['maintenance']:
                return ['maintenance_required'], 423
            return [], 200
        if intent.action == 'safe_manual_test':
            if snapshot['estop'] != 'clear':
                return ['estop_restart_required'], 423
            if intent.source != 'touchscreen' or not snapshot['maintenance'] or command not in self.safe_manual_commands:
                return ['manual_test_policy_denied'], 423
            return [], 200
        if snapshot['system_state'] not in ('NORMAL', 'WARNING') or snapshot['restart_required']:
            return snapshot['inhibits'] or ['state_inhibited'], 423
        return [], 200

    def _requires_confirmation(self, intent):
        command = intent.payload.get('command')
        return (intent.source != 'automatic' and
                (intent.action in ('start', 'enter_maintenance', 'exit_maintenance', 'safe_manual_test', 'firmware_update')
                 or bool(command and command_model(command)[3])))

    def _result(self, intent, allowed, reasons, http_code, **changes):
        result = dict(request_id=intent.request_id, allowed=allowed, reason_codes=list(reasons),
                      state_revision=self.state.revision, inhibits=self.state.snapshot()['inhibits'],
                      requested_state=None, accepted=False, accepted_at_utc=None, acknowledged_at_utc=None,
                      reported_state=None, firmware_confirmed=False, physically_verified=False, verified=False,
                      logged=False, logging_status='buffered_not_durable', status='rejected', http_status=http_code)
        result.update(changes)
        return result

    def prepare(self, intent, authority=None):
        self._validate(intent)
        with self.state.lock:
            snapshot = self.state.snapshot()
            reasons, status = self._permission(intent, authority, snapshot)
            if reasons:
                self.state.emit('command_rejected', {'action': intent.action, 'reasons': reasons}, intent.source)
                return self._result(intent, False, reasons, status)
            if not self._requires_confirmation(intent):
                return self._result(intent, True, [], 200, status='confirmation_not_required')
            nonce = secrets.token_urlsafe(32)
            self.confirmations[nonce] = (self._key(intent, authority), snapshot['state_revision'], self.state.clock() + self.ttl)
            while len(self.confirmations) > self.limit:
                self.confirmations.popitem(last=False)
            return self._result(intent, True, [], 200, status='confirmation_required', confirmation_id=nonce,
                                expires_in_s=self.ttl, description=intent.action + ': ' + intent.payload_json)

    def execute(self, intent, authority=None):
        self._validate(intent)
        with self.state.lock:
            snapshot = self.state.snapshot()
            reasons, status = self._permission(intent, authority, snapshot)
            if not reasons and intent.expected_state_revision is not None and intent.expected_state_revision != snapshot['state_revision']:
                reasons, status = ['state_changed'], 409
            if not reasons and intent.request_id in self.requests:
                reasons, status = ['duplicate_request'], 409
            if not reasons and self._requires_confirmation(intent):
                record = self.confirmations.pop(intent.confirmation_id, None)
                if (record is None or record[0] != self._key(intent, authority)
                        or record[1] != snapshot['state_revision'] or self.state.clock() >= record[2]
                        or intent.expected_state_revision != snapshot['state_revision']):
                    reasons, status = ['confirmation_missing_expired_or_changed'], 409
            if reasons:
                self.state.emit('command_rejected', {'request_id': intent.request_id, 'action': intent.action, 'reasons': reasons}, intent.source)
                return self._result(intent, False, reasons, status)
            diagnostic = intent.action == 'read_status'
            self.requests[intent.request_id] = True
            while len(self.requests) > self.limit:
                self.requests.popitem(last=False)
            if not diagnostic:
                self.state.emit('command_accepted', {'request_id': intent.request_id, 'action': intent.action, 'payload': intent.payload}, intent.source)
            accepted_at = self.state.utc_now().isoformat()
            if not diagnostic:
                self.state.revision += 1
            command = intent.payload.get('command')
            requested = command_model(command)[2] if command else intent.action
            if intent.target in self.state.requested_states:
                self.state.requested_states[intent.target] = copy.deepcopy(requested)
            result = self._result(intent, True, [], 200, accepted=True, accepted_at_utc=accepted_at,
                                  requested_state=requested, status='accepted')
            if intent.action in ('pause', 'enter_maintenance', 'exit_maintenance', 'start'):
                if intent.action == 'enter_maintenance':
                    self.state.maintenance = True
                    self.state.restart_required = True
                elif intent.action == 'exit_maintenance':
                    self.state.maintenance = False
                    self.state.restart_required = True
                elif intent.action == 'start':
                    self.state.estop_latched = False
                    self.state.restart_required = False
                else:
                    self.state.restart_required = True
                self.state.snapshot()
                if intent.action in ('pause', 'enter_maintenance'):
                    stop = self._safe_stop()
                    result.update(stop)
            elif intent.action == 'firmware_update':
                stop = self._safe_stop(force=True)
                if not stop['firmware_confirmed']:
                    result.update(stop)
                else:
                    result.update(self._dispatch_update(intent.payload['mode']))
                self.state.restart_required = True
            else:
                result.update(self._send(command))
                if intent.action == 'stop':
                    self.state.restart_required = True
                if command == 'PUMP_OFF' and intent.source == 'touchscreen':
                    self.state.restart_required = True
                if intent.action == 'safe_manual_test':
                    self.state.restart_required = True
            result['state_revision'] = self.state.snapshot()['state_revision']
            result['inhibits'] = self.state.snapshot()['inhibits']
            if not diagnostic:
                self.state.last_command = copy.deepcopy(result)
                self.state.emit('command_outcome', result, intent.source)
            return copy.deepcopy(result)

    def _send(self, command):
        token = _dispatch.set({'simulated': bool(getattr(self.adapter, 'simulated', False)), 'action': 'command'})
        try:
            ack = self.adapter.send(command)
            if not isinstance(ack, AdapterResult):
                raise TypeError('Adapter must return an explicit acknowledgement result')
            if ack.acknowledged and not self.state.valid_feedback(ack.reported_state):
                ack = AdapterResult(False, error='Invalid acknowledgement feedback')
        except Exception as exc:
            ack = AdapterResult(False, error=type(exc).__name__ + ': ' + str(exc))
        finally:
            _dispatch.reset(token)
        if ack.acknowledged and ack.reported_state is not None:
            self.state.controller_feedback(ack.reported_state)
        elif not ack.acknowledged:
            self.state.controller_feedback(None)
        return dict(firmware_confirmed=bool(ack.acknowledged), reported_state=copy.deepcopy(ack.reported_state) if ack.acknowledged else None,
                    acknowledged_at_utc=self.state.utc_now().isoformat() if ack.acknowledged else None,
                    http_status=200 if ack.acknowledged else 503, status='confirmed' if ack.acknowledged else 'unavailable',
                    error=ack.error, physically_verified=False, verified=False)

    def _safe_stop(self, force=False):
        if 'STOP' not in self.safe_commands or not getattr(self.adapter, 'simulated', False):
            self.state.emit('safe_state_unavailable', {'reason': 'physical_safe_output_policy_not_approved'})
            return dict(firmware_confirmed=False, status='unavailable', http_status=503, error='Safe output policy/adapter unavailable')
        result = self._send('STOP')
        if result['firmware_confirmed'] and not outputs_reported_off(result['reported_state']):
            result.update(firmware_confirmed=False, http_status=503, status='unavailable',
                          error='STOP acknowledgement did not report all outputs off')
            self.state.restart_required = True
        self.state.emit('safe_state_request', result, 'safety')
        if result['firmware_confirmed']:
            self._stopped_generation = self.state.stop_generation
        return result

    def _dispatch_update(self, mode):
        token = _dispatch.set({'simulated': True, 'action': 'firmware_update'})
        try:
            ack = self.adapter.firmware_update(mode)
            if not isinstance(ack, AdapterResult):
                raise TypeError('Explicit post-update acknowledgement required')
            if ack.acknowledged and (not self.state.valid_feedback(ack.reported_state) or not outputs_reported_off(ack.reported_state)):
                raise ValueError('Post-update feedback is invalid or not off; restart remains inhibited')
            self.state.controller_feedback(ack.reported_state if ack.acknowledged else None)
            return dict(uploaded=True, compatible=ack.acknowledged, firmware_confirmed=ack.acknowledged,
                        reported_state=ack.reported_state, status='confirmed' if ack.acknowledged else 'unavailable',
                        http_status=200 if ack.acknowledged else 503, error=ack.error, physically_verified=False, verified=False)
        except Exception as exc:
            self.state.controller_feedback(None)
            return dict(uploaded=False, compatible=False, status='unavailable', http_status=503, error=str(exc))
        finally:
            _dispatch.reset(token)

    def poll_status(self):
        """Faults request safe state before a STATUS can renew the controller watchdog."""
        with self.state.lock:
            snapshot = self.state.snapshot()
            if snapshot['inhibits'] and not self._safe_stop()['firmware_confirmed']:
                return False
            intent = self.intent('command', {'command': 'STATUS'}, source='service')
            result = self.execute(intent, self.service_authority)
            return result['firmware_confirmed']

    def observe_sensor(self, sensor_id, value, sample_time_utc, **metadata):
        """Trusted normalized acquisition entry: commit quality then request reviewed safe state."""
        with self.state.lock:
            reading = self.state.observe(sensor_id, value, sample_time_utc, **metadata)
            if self.state.snapshot()['inhibits']:
                self._safe_stop()
            return reading

    def command(self, message, *, authority=None, source='service', **context):
        try:
            return self.execute(self.intent('command', {'command': message}, source=source, **context), authority)
        except (ValueError, TypeError):
            return {'firmware_confirmed': False, 'allowed': False, 'http_status': 400, 'reason_codes': ['invalid_command']}
