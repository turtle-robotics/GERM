"""Phase 0 host contracts. Hardware modules are replaced before app import.

Run separately from check_integration.py; that suite intentionally replaces services.
No serial ports, GPIO, network connections, camera devices or firmware uploads occur.
"""
import hashlib
from contextlib import closing
import importlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / 'fixtures'
sys.path.insert(0, str(ROOT))


def fixture(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def module(name, **attrs):
    value = types.ModuleType(name)
    value.__dict__.update(attrs)
    sys.modules[name] = value


# Only the physical adapters are replaced; real services, Flask routes and serial
# parser are exercised. Patches remain confined to this dedicated test process.
module('camera', Camera=lambda: None)
module('dht11_reader', read_dht=lambda: None,
       latest_dht=dict(temperature=None, humidity=None, temperature_at=None, humidity_at=None))
module('sensor_reader', read_serial=lambda: None, latest_data=dict(A0=None, A0_at=None))
import arduino_serial as bridge
from services import camera_service, sensor_service
from services.database_service import DatabaseUnavailable
from services.ml_service import MLUnavailable
with patch('threading.Thread.start'):
    import app
import dashboard


class ReplaySerial:
    is_open = True
    port = '/dev/fixture-never-opened'

    def __init__(self, chunks=(), error=None, stale_first=False):
        self.chunks = list(chunks)
        self.error = error
        self.stale_first = stale_first
        self.writes = []

    def read_until(self, *args):
        return self.chunks.pop(0) if self.chunks else b''

    def write(self, data):
        self.writes.append(data)
        seq = int(data.decode().split(':', 2)[1])
        state = fixture('serial.json')['valid']
        if self.stale_first:
            self.chunks.append(json.dumps(dict(state, id=seq-1)).encode()+b'\n')
        state['id'] = seq
        if self.error:
            state['error'] = self.error
        self.chunks.append(json.dumps(state).encode()+b'\n')

    def close(self):
        self.is_open = False


class SerialContractTests(unittest.TestCase):
    def tearDown(self):
        bridge._reconnect()

    def test_partial_and_malformed_frames(self):
        raw = json.dumps(fixture('serial.json')['valid']).encode()+b'\n'
        replay = ReplaySerial([b'not json\n', raw[:20], raw[20:]])
        self.assertIsNone(bridge._read_packet(replay))
        self.assertIsNone(bridge._read_packet(replay))
        self.assertEqual(bridge._read_packet(replay)['protocol'], 2)

    def test_invalid_packets_and_overflow_are_rejected(self):
        for packet in fixture('serial.json')['reject']:
            with self.subTest(packet=packet):
                self.assertIsNone(bridge._read_packet(ReplaySerial([json.dumps(packet).encode()+b'\n'])))
        self.assertIsNone(bridge._read_packet(ReplaySerial([b'x'*2049])))
        self.assertEqual(bridge._partial, b'')

    def test_matched_ack_and_error_reply(self):
        bridge._ser = ReplaySerial(stale_first=True)
        self.assertTrue(bridge.send('STOP'))
        self.assertEqual(bridge.reported_state()['rgb'], [0, 0, 0])
        bridge._ser = ReplaySerial(error='Unknown command')
        self.assertFalse(bridge.send('BOGUS'))
        self.assertEqual(bridge.last_error(), 'Unknown command')

    def test_no_ack_timeout_invalidates_report(self):
        bridge._packet = fixture('serial.json')['valid']
        bridge._packet_at = 10
        bridge._ser = ReplaySerial()
        with patch.object(bridge._ser, 'write'), patch.object(bridge.time, 'monotonic', side_effect=[0, 0, 4]):
            self.assertFalse(bridge.send('STOP'))
        self.assertEqual(bridge._packet_at, 0)

    def test_expiry_and_copy(self):
        bridge._packet = fixture('serial.json')['valid']
        bridge._packet_at = 100
        with patch.object(bridge.time, 'monotonic', return_value=106):
            result = bridge.reported_state()
            self.assertIsNotNone(result)
            result['rgb'][0] = 255
            self.assertEqual(bridge._packet['rgb'][0], 0)
        with patch.object(bridge.time, 'monotonic', return_value=106.01):
            self.assertIsNone(bridge.reported_state())

    def test_newline_injection_never_opens_port(self):
        with patch.object(bridge, 'get_serial') as opened:
            self.assertFalse(bridge.send('STOP\nPUMP_ON'))
            opened.assert_not_called()


class SensorTests(unittest.TestCase):
    def test_fixtures_record_observed_quality_and_known_gaps(self):
        for case in fixture('sensors.json'):
            with self.subTest(case=case['name']), patch.object(sensor_service.time, 'time', return_value=case['now']):
                reading = sensor_service.reading(case['value'], '°C', case['sampled_at'], 'fixture')
                self.assertEqual(reading['state'], case['expected_state'])
                if case['value'] is None:
                    self.assertIsNone(reading['timestamp_utc'])
                else:
                    self.assertTrue(reading['timestamp_utc'].endswith('+00:00'))

    def test_uninstalled_values_are_explicit(self):
        readings = sensor_service.current_readings()
        self.assertEqual(readings['water_temperature']['state'], 'unavailable')
        self.assertIsNone(readings['water_temperature']['value'])


class APIContractTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_all_documented_paths_have_matching_methods(self):
        catalog = json.loads((ROOT.parent/'docs/phase0/API_ENDPOINTS.json').read_text())
        observed = {(rule.rule, method) for rule in app.app.url_map.iter_rules()
                    for method in rule.methods - {'HEAD', 'OPTIONS'} if rule.endpoint != 'static'}
        expected = {(row['path'], row['method']) for row in catalog}
        self.assertEqual(observed, expected)

    def test_safe_off_examples_keep_physical_state_unverified(self):
        for case in fixture('api_requests.json'):
            with self.subTest(path=case['path']), patch.object(app, 'send_command', return_value=True) as send:
                response = self.client.post(case['path'], json=case['request'])
                self.assertEqual(response.status_code, 200)
                send.assert_called_once_with(case['command'])
                self.assertTrue(response.json['firmware_confirmed'])
                self.assertFalse(response.json['verified'])
                self.assertFalse(response.json['logged'])

    def test_disconnected_controller_returns_503(self):
        with patch.object(app, 'send_command', return_value=False):
            response = self.client.post('/api/pump', json={'state':'off'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['status'], 'unavailable')

    def test_control_log_failure_keeps_ack_and_emits_diagnostic(self):
        with patch.object(app, 'send_command', return_value=True), \
             patch.object(app.repository, 'record_actuator_event', side_effect=OSError('storage offline')), \
             self.assertLogs(app.app.logger, level='ERROR') as logs:
            result = self.client.post('/api/pump', json={'state':'off'})
        self.assertTrue(result.json['firmware_confirmed'])
        self.assertFalse(result.json['logged'])
        self.assertFalse(result.json['verified'])
        expected = fixture('scenarios.json')['expected_logs'][-1]
        self.assertIn(expected, '\n'.join(logs.output))

    def test_offline_pages_and_unavailable_data(self):
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network denied')):
            for path in ['/', '/plant', '/trends', '/controls', '/alerts', '/maintenance', '/settings']:
                self.assertEqual(self.client.get(path).status_code, 200, path)
            response = self.client.get('/api/state')
            self.assertEqual(response.json['database']['state'], 'not_configured')
            self.assertIsNone(response.json['alerts']['active'])
            self.assertEqual(response.json['estop'], 'not_connected')
            self.assertEqual(self.client.get('/api/camera/capture').status_code, 405)
            self.assertEqual(self.client.post('/api/camera/capture').status_code, 503)
        for path in ['/api/trends', '/api/alerts', '/api/experiments', '/api/captures']:
            self.assertEqual(self.client.get(path).json['state'], 'not_configured')
        self.assertEqual(self.client.post('/api/alerts/1/ack').status_code, 503)

    def test_ml_and_alert_exceptions_stay_explicit(self):
        with patch.object(dashboard.repository, 'get_active_alerts', side_effect=OSError('fixture read fault')), \
             patch.object(dashboard.ml_service, 'get_latest_result', side_effect=RuntimeError('fixture model fault')), \
             self.assertLogs(app.app.logger, level='ERROR') as logs:
            result = self.client.get('/api/state')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['database']['state'], 'error')
        self.assertIsNone(result.json['alerts']['active'])
        self.assertEqual(result.json['ml']['state'], 'error')
        self.assertIn('Alert read failed', '\n'.join(logs.output))
        self.assertIn('ML status read failed', '\n'.join(logs.output))

    def test_capture_index_and_disk_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(camera_service, 'IMAGE_ROOT', Path(folder)):
            cam = types.SimpleNamespace(get_frame=lambda: (FIX/'camera.jpg').read_bytes())
            fresh_app = app.Flask('capture-test')
            fresh_app.register_blueprint(dashboard.create_dashboard(cam, {}))
            client = fresh_app.test_client()
            with patch.object(dashboard.repository, 'record_image', side_effect=OSError('SQL offline')), \
                 self.assertLogs(fresh_app.logger, level='ERROR') as logs:
                response = client.post('/api/camera/capture')
            self.assertEqual(response.status_code, 201)
            image = response.json['image']
            self.assertFalse(image['indexed'])
            self.assertIsNone(image['image_id'])
            self.assertTrue((Path(folder)/image['file_path']).exists())
            self.assertIn('Capture saved but SQL indexing failed', '\n'.join(logs.output))
            with patch.object(dashboard, 'save_manual_capture', side_effect=OSError('Disk full')), \
                 self.assertLogs(fresh_app.logger, level='ERROR'):
                self.assertEqual(client.post('/api/camera/capture').status_code, 500)

    def test_acknowledgement_does_not_call_condition_clear(self):
        repository = types.SimpleNamespace(status='ready', acknowledge_alert=lambda alert_id: True)
        with patch.object(dashboard, 'repository', repository):
            self.assertEqual(self.client.post('/api/alerts/1/ack').json, {'ok':True, 'alert_id':1})


class StorageFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'sample.sqlite3'
        self.db = sqlite3.connect(self.path)
        self.db.executescript((FIX/'schema_v1.sql').read_text(encoding='utf-8'))
        self.db.executescript((FIX/'seed.sql').read_text(encoding='utf-8'))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_schema_settings_integrity_and_all_entities(self):
        for pragma, expected in [('foreign_keys',1), ('journal_mode','wal'), ('synchronous',2), ('busy_timeout',3000), ('user_version',1)]:
            self.assertEqual(self.db.execute('PRAGMA '+pragma).fetchone()[0], expected)
        expected = {'experiments','plants','sensors','sensor_readings','actuators','actuator_events','images','ml_inferences','alerts','maintenance_events','system_events'}
        self.assertEqual({r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")},expected)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_fk_quality_and_event_deduplication(self):
        for sql in ["INSERT INTO sensor_readings VALUES(50,'unknown',1,'2026-10-01T00:00:00+00:00',24,'good')",
                    "INSERT INTO sensor_readings VALUES(50,'humidity',1,'2026-10-01T00:00:00+00:00',NULL,'invented')",
                    "INSERT INTO sensor_readings VALUES(50,'humidity',1,'2026-10-01T00:00:00+00:00',50,'missing')",
                    "INSERT INTO actuator_events SELECT * FROM actuator_events"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
            self.db.rollback()

    def test_ack_does_not_clear_and_restart_restore_retains_records(self):
        self.db.execute("UPDATE alerts SET ack_time_utc='2026-10-01T00:01:00+00:00' WHERE alert_id=1")
        self.db.commit()
        self.assertIsNone(self.db.execute('SELECT clear_time_utc FROM alerts').fetchone()[0])
        backup = sqlite3.connect(Path(self.temp.name)/'restored.sqlite3')
        try:
            self.db.backup(backup)
            self.db.close()
            self.db = sqlite3.connect(self.path)
            for table in ['sensor_readings','actuator_events','alerts','system_events']:
                self.assertEqual(self.db.execute('SELECT * FROM '+table).fetchall(), backup.execute('SELECT * FROM '+table).fetchall())
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            backup.close()

    def test_wal_reader_during_uncommitted_write(self):
        reader = sqlite3.connect(self.path)
        try:
            self.db.execute("INSERT INTO sensor_readings VALUES(9,'humidity',1,'2026-10-01T00:01:00+00:00',50,'good')")
            self.assertEqual(reader.execute('SELECT count(*) FROM sensor_readings').fetchone()[0],4)
            self.db.commit()
            self.assertEqual(reader.execute('SELECT count(*) FROM sensor_readings').fetchone()[0],5)
        finally:
            reader.close()

    def test_jpeg_and_inference_linkage(self):
        metadata = fixture('camera_metadata.json')
        data = (FIX/'camera.jpg').read_bytes()
        self.assertTrue(data.startswith(b'\xff\xd8'))
        self.assertEqual(hashlib.sha256(data).hexdigest(), metadata['sha256'])
        self.assertEqual(len(data), metadata['size_bytes'])
        self.db.execute('INSERT INTO images VALUES(1,1,1,?,?,?,?,?,?,?)',
                        [metadata[k] for k in ['file_path','timestamp_utc','sha256','size_bytes','width_px','height_px','capture_reason']])
        self.db.execute("INSERT INTO ml_inferences VALUES(1,1,'2026-10-01T00:00:01+00:00','uncertain / out-of-scope',0.5,'fixture-only',1,10)")
        self.assertEqual(self.db.execute('SELECT images.sha256 FROM images JOIN ml_inferences USING(image_id)').fetchone()[0], metadata['sha256'])

    def test_sample_builder_refuses_overwrite_and_contains_all_entities(self):
        from build_sample_db import build
        target = Path(self.temp.name)/'built.sqlite3'
        build(target)
        with self.assertRaises(FileExistsError):
            build(target)
        with closing(sqlite3.connect(target)) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                self.assertGreater(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0, table)
            event = json.loads(db.execute("SELECT payload_json FROM system_events WHERE event_id='state-1'").fetchone()[0])
            self.assertEqual(event, fixture('scenarios.json')['state_event']['payload'])


class CameraAndPlaceholderTests(unittest.TestCase):
    def test_capture_hash_and_module_restart_recovery(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GERM_IMAGE_ROOT=folder):
            importlib.reload(camera_service)
            frame = (FIX/'camera.jpg').read_bytes()
            image = camera_service.save_manual_capture(frame)
            self.assertEqual(image['sha256'], hashlib.sha256(frame).hexdigest())
            importlib.reload(camera_service)
            recovered = camera_service.latest_local_manual_capture()
            self.assertEqual(recovered['file_path'], image['file_path'])
            self.assertFalse(recovered['indexed'])
        importlib.reload(camera_service)

    def test_unavailable_adapters_never_claim_durability_or_model(self):
        db, ml = DatabaseUnavailable(), MLUnavailable()
        self.assertEqual(db.status, 'not_configured')
        self.assertFalse(db.log_event({}))
        self.assertFalse(db.log_sensor_reading({}))
        self.assertIsNone(db.record_image({}))
        self.assertIsNone(ml.get_latest_result())
        with self.assertRaises(RuntimeError):
            ml.analyze_image(1, 'fixture.jpg')


if __name__ == '__main__':
    unittest.main(verbosity=2)
