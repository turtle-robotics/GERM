"""One locked USB connection, matched command acknowledgements, and upload pause."""
from contextlib import contextmanager
import copy
import json
import os
import threading
import time
import serial
import serial.tools.list_ports

_lock = threading.RLock()
_ser = None
_packet = None
_packet_at = 0
_sequence = 0
_partial = bytearray()
_last_error = 'Waiting for GERM firmware'


def find_arduino_port():
    configured = os.environ.get('GERM_SERIAL_PORT')
    if configured:
        return configured
    ports = [p.device for p in serial.tools.list_ports.comports()]
    for candidate in ('/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1'):
        if candidate in ports:
            return candidate
    return next((p for p in ports if 'ttyUSB' in p or 'ttyACM' in p), None)


def _reconnect():
    global _ser, _packet, _packet_at
    if _ser is not None:
        try:
            _ser.close()
        except OSError:
            pass
    _ser = None
    _packet = None
    _packet_at = 0
    _partial.clear()


def get_serial():
    global _ser
    with _lock:
        if _ser is None or not _ser.is_open:
            port = find_arduino_port()
            if port is None:
                raise serial.SerialException('Arduino USB port not found')
            _ser = serial.Serial(port, 9600, timeout=0.2, write_timeout=2)
            time.sleep(2)
        return _ser


def _read_packet(ser):
    global _packet, _packet_at
    _partial.extend(ser.read_until(b'\n', 512))
    if len(_partial) > 2048:
        _partial.clear()
        return None
    if not _partial.endswith(b'\n'):
        return None
    line = bytes(_partial)
    _partial.clear()
    try:
        packet = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(packet, dict) or packet.get('protocol') != 2:
        return None
    if all(type(packet.get(k)) is bool for k in ('fan', 'pump')) and isinstance(packet.get('rgb'), list) and len(packet['rgb']) == 3 and all(type(v) is int and 0 <= v <= 255 for v in packet['rgb']):
        _packet = packet
        _packet_at = time.monotonic()
        return packet
    return None


def send(message):
    """True only when firmware acknowledges this exact command ID."""
    global _sequence, _last_error, _packet_at
    if not isinstance(message, str) or '\n' in message or '\r' in message:
        _last_error = 'Invalid command'
        return False
    with _lock:
        try:
            ser = get_serial()
            _sequence = (_sequence % 60000) + 1
            command_id = _sequence
            ser.write(f'CMD:{command_id}:{message}\n'.encode('ascii'))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                packet = _read_packet(ser)
                if packet and packet.get('id') == command_id:
                    _last_error = packet.get('error', '')
                    return not bool(_last_error)
            _last_error = 'Arduino did not acknowledge the command; check firmware and USB'
            _packet_at = 0
        except (serial.SerialException, OSError, UnicodeError) as exc:
            _last_error = str(exc)
            _reconnect()
        return False


def read_line():
    # STATUS supplies a heartbeat and updates state without a competing reader.
    if send('STATUS'):
        packet = reported_state()
        if packet is not None and packet.get('a0') is not None:
            return 'A0:' + str(packet['a0'])
    return None


def reported_state():
    with _lock:
        if _packet is None or time.monotonic() - _packet_at > 6:
            return None
        return copy.deepcopy(_packet)


def is_connected():
    return reported_state() is not None


def last_error():
    with _lock:
        return _last_error


@contextmanager
def firmware_port():
    """Pause the reader, turn outputs off, and release USB for the uploader."""
    with _lock:
        port = _ser.port if _ser is not None else find_arduino_port()
        if not port:
            raise RuntimeError('Arduino USB port not found')
        try:
            send('STOP')
        finally:
            _reconnect()
        try:
            yield port
        finally:
            _reconnect()
