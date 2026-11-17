"""Explicit host-workspace SQLite repository. Never configured on import."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sqlite3
import threading
import time
import uuid

MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'
VERSION = 7


def utc(value):
    if not isinstance(value, str): raise ValueError('Explicit UTC timestamp required')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError('Explicit UTC timestamp required')
    return stamp.isoformat()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def bounded(value, maximum=1000):
    if type(value) is not int or not 1 <= value <= maximum: raise ValueError('Invalid query limit')
    return value


def _apply(db, script):
    pending = ''
    for line in script.splitlines():
        if line.strip().upper().startswith(('PRAGMA ', 'BEGIN;', 'COMMIT;')): continue
        pending += line+'\n'
        if sqlite3.complete_statement(pending):
            db.execute(pending)
            pending = ''
    if pending.strip(): raise ValueError('Incomplete migration')


def _schema(db):
    return [(r[0],r[1],re.sub(r'\s+',' ',r[2]).strip()) for r in db.execute(
        "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name")]


LEDGER = 'CREATE TABLE migration_history (version INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, applied_at_utc TEXT NOT NULL)'


class SQLiteRepository:
    def __init__(self, path, *, workspace_root, create=False, busy_timeout_ms=100):
        self.root = Path(workspace_root).resolve(strict=True)
        self.path = self.scoped(path)
        if type(busy_timeout_ms) is not int or not 0 <= busy_timeout_ms <= 3000: raise ValueError('Invalid busy timeout')
        self.timeout = busy_timeout_ms
        self.status, self.last_error = 'not_configured', None
        self.backups = []
        self._migration_lock = threading.Lock()
        if not self.path.exists() and not create: raise FileNotFoundError(self.path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            self._migrate()
            self.status = 'ready'
        except Exception as exc:
            self.status, self.last_error = 'error', type(exc).__name__
            raise

    def scoped(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root) or path == self.root: raise ValueError('Host path must stay in explicit workspace')
        return path

    @contextmanager
    def connection(self):
        # Resolve again to reject a redirected symlink after construction.
        path = self.scoped(self.path)
        db = sqlite3.connect(path,timeout=self.timeout/1000,isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.execute(f'PRAGMA busy_timeout={self.timeout}')
            yield db
        except Exception as exc:
            self.status, self.last_error = 'error', type(exc).__name__
            raise
        finally: db.close()

    @staticmethod
    def _integrity(db):
        if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok'] or list(db.execute('PRAGMA foreign_key_check')):
            raise ValueError('Database integrity/foreign-key failure')

    def integrity_check(self):
        with self.connection() as db:self._integrity(db)
        return True

    def _migrate(self):
        scripts = [(p, p.read_text(encoding='utf-8-sig')) for p in sorted(MIGRATIONS.glob('*.sql'))]
        if len(scripts) != VERSION:raise ValueError('Incomplete migration package')
        with self._migration_lock, self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > VERSION: raise ValueError('Future schema version; no downgrade')
            self._integrity(db)
            with closing(sqlite3.connect(':memory:')) as expected:
                for _,script in scripts[:version]:_apply(expected,script)
                names = {r[1] for r in _schema(db)}
                has_ledger = 'migration_history' in names
                if has_ledger:expected.execute(LEDGER)
                if _schema(db) != _schema(expected):raise ValueError('Unknown schema/drift; upgrade denied')
            if has_ledger:
                recorded = list(db.execute('SELECT version,sha256 FROM migration_history ORDER BY version'))
                wanted = [(i,hashlib.sha256(s.encode()).hexdigest()) for i,(_,s) in enumerate(scripts[:version],1)]
                if [tuple(r) for r in recorded] != wanted:raise ValueError('Migration checksum mismatch')
            elif version > 1:raise ValueError('Missing migration ledger')
            if version and version < VERSION:
                backup = self.path.with_name(self.path.name+'.before-v'+str(version)+'-'+uuid.uuid4().hex+'.sqlite')
                self.backup(backup)
                self.backups.append(backup)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            try:
                # A concurrent initializer must not apply an already-applied migration.
                if db.execute('PRAGMA user_version').fetchone()[0] != version:raise RuntimeError('Concurrent migration; reopen')
                if not has_ledger:
                    db.execute(LEDGER)
                    for i,(_,script) in enumerate(scripts[:version],1):
                        db.execute('INSERT INTO migration_history VALUES(?,?,?)',(i,hashlib.sha256(script.encode()).hexdigest(),datetime.now(timezone.utc).isoformat()))
                for i,(_,script) in enumerate(scripts,1):
                    if i <= version:continue
                    _apply(db,script)
                    db.execute('INSERT INTO migration_history VALUES(?,?,?)',(i,hashlib.sha256(script.encode()).hexdigest(),datetime.now(timezone.utc).isoformat()))
                    db.execute(f'PRAGMA user_version={i}')
                self._integrity(db)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

    def backup(self, destination):
        destination = self.scoped(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb'):pass  # exclusive: never replace history
        deadline = time.monotonic()+5
        def progress(*_):
            if time.monotonic() >= deadline:raise TimeoutError('Backup busy deadline')
        with self.connection() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target,pages=64,progress=progress,sleep=0.01)
            self._integrity(target)
        return destination

    @classmethod
    def restore(cls, source, destination, *, workspace_root):
        root=Path(workspace_root).resolve(strict=True)
        source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
        if not source.is_relative_to(root) or not destination.is_relative_to(root):raise ValueError('Host restore path outside workspace')
        # Validate source through a read-only connection before creating destination.
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
            cls._integrity(db)
            if db.execute('PRAGMA user_version').fetchone()[0] != VERSION:raise ValueError('Restore requires current schema')
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('xb'):pass
            with closing(sqlite3.connect(destination)) as target:db.backup(target)
        return cls(destination,workspace_root=root)

    def _rows(self, sql, args=()):
        with self.connection() as db:return [dict(r) for r in db.execute(sql,args)]

    def _write(self, sql, args=()):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                cursor=db.execute(sql,args)
                db.execute('COMMIT')
                return cursor.lastrowid, cursor.rowcount
            except Exception:
                db.execute('ROLLBACK')
                raise

    def get_latest_sensor_values(self):
        rows=self._rows('SELECT r.*,s.unit FROM sensors s JOIN sensor_readings r ON r.reading_id=(SELECT reading_id FROM sensor_readings WHERE sensor_id=s.sensor_id ORDER BY timestamp_utc DESC,reading_id DESC LIMIT 1) LIMIT 1000')
        return {r['sensor_id']:r for r in rows}

    def get_sensor_history(self,sensor,start_time=None,end_time=None,experiment_id=None):
        start=utc(start_time) if start_time else '0001'; end=utc(end_time) if end_time else '9999'
        if start>end:raise ValueError('Invalid time range')
        return self._rows('SELECT r.timestamp_utc,r.value,s.unit,r.quality_flag FROM sensor_readings r JOIN sensors s USING(sensor_id) WHERE r.sensor_id=? AND r.timestamp_utc>=? AND r.timestamp_utc<=? AND (? IS NULL OR r.experiment_id=?) ORDER BY r.timestamp_utc,r.reading_id LIMIT 1000',(sensor,start,end,experiment_id,experiment_id))

    def get_active_alerts(self):return self._rows('SELECT * FROM alerts WHERE clear_time_utc IS NULL ORDER BY timestamp_utc DESC,alert_id DESC LIMIT 1000')
    def get_alert_history(self,limit=50):return self._rows('SELECT * FROM alerts ORDER BY timestamp_utc DESC,alert_id DESC LIMIT ?',(bounded(limit),))
    def acknowledge_alert(self,alert_id):
        return self._write('UPDATE alerts SET ack_time_utc=COALESCE(ack_time_utc,?) WHERE alert_id=?',(datetime.now(timezone.utc).isoformat(),alert_id))[1]==1
    def get_experiments(self):return self._rows('SELECT * FROM experiments ORDER BY experiment_id DESC LIMIT 1000')
    def get_experiment_data(self,experiment_id):
        rows=self._rows('SELECT * FROM experiments WHERE experiment_id=?',(experiment_id,))
        if not rows:return None
        return dict(experiment=rows[0],plants=self._rows('SELECT * FROM plants WHERE experiment_id=? ORDER BY position',(experiment_id,)),reading_count=self._rows('SELECT COUNT(*) AS count FROM sensor_readings WHERE experiment_id=?',(experiment_id,))[0]['count'])
    def get_recent_images(self,limit=12):return self._rows('SELECT * FROM images ORDER BY timestamp_utc DESC,image_id DESC LIMIT ?',(bounded(limit),))

    def record_image(self,image):
        name=image['file_path']; path=PurePosixPath(name)
        if not isinstance(name,str) or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or not path.parts:raise ValueError('Unsafe relative image path')
        if not re.fullmatch('[a-fA-F0-9]{64}',image['sha256']):raise ValueError('Invalid image hash')
        for k in ('size_bytes','width_px','height_px'):
            if type(image.get(k)) is not int or image[k]<=0:raise ValueError('Missing/invalid image dimensions or size')
        return self._write('INSERT INTO images(experiment_id,plant_id,file_path,timestamp_utc,sha256,size_bytes,width_px,height_px,capture_reason,lighting_state) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (image.get('experiment_id'),image.get('plant_id'),name,utc(image['timestamp_utc']),image['sha256'].lower(),image['size_bytes'],image['width_px'],image['height_px'],image['capture_reason'],canonical(image['lighting_state']) if 'lighting_state' in image else None))[0]

    def log_sensor_reading(self,reading):
        value=reading.get('value'); quality=reading['quality_flag']
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):raise ValueError('Nonfinite sensor value')
        if quality in ('invalid','missing') and value is not None:raise ValueError('Invalid samples require null decision value')
        sequence=reading.get('source_sequence')
        if sequence is not None and (type(sequence) is not int or sequence<0):raise ValueError('Invalid source sequence')
        self._write('INSERT INTO sensor_readings(sensor_id,experiment_id,timestamp_utc,value,quality_flag,source_sequence) VALUES(?,?,?,?,?,?)',
            (reading['sensor_id'],reading.get('experiment_id'),utc(reading['timestamp_utc']),value,quality,sequence))
        return True

    def record_actuator_event(self,event):
        for key in ('firmware_confirmed','physically_verified'):
            if type(event.get(key)) is not bool:raise ValueError('Explicit ACK and physical flags required')
        self._write('INSERT INTO actuator_events(event_id,actuator_id,experiment_id,timestamp_utc,requested_state,reported_state,source,firmware_confirmed,physically_verified,reason,request_id,accepted_at_utc,acknowledged_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (event.get('event_id') or str(uuid.uuid4()),event['actuator'],event.get('experiment_id'),utc(event['timestamp_utc']),canonical(event['requested_state']),canonical(event['reported_state']) if event.get('reported_state') is not None else None,event['source'],int(event['firmware_confirmed']),int(event['physically_verified']),event.get('reason'),event.get('request_id'),utc(event['accepted_at_utc']) if event.get('accepted_at_utc') else None,utc(event['acknowledged_at_utc']) if event.get('acknowledged_at_utc') else None))
        return True

    def load_restart_state(self):
        rows=self._rows('SELECT * FROM restart_state WHERE singleton=1')
        if not rows:return None
        row=rows[0]; utc(row['updated_at_utc'])
        if row['restart_required']!=1 or row['schema_version']!=1:raise ValueError('Invalid restart record')
        return dict(generation=row['generation'],profile=row['profile'],maintenance=bool(row['maintenance']),estop_latched=bool(row['estop_latched']),restart_required=True)

    def save_restart_state(self,state,expected_generation):
        if type(expected_generation) is not int or expected_generation<0:raise ValueError('Invalid generation')
        if state['profile'] is not None and (not isinstance(state['profile'],str) or not 1<=len(state['profile'])<=128):raise ValueError('Invalid profile')
        if any(type(state[k]) is not bool for k in ('maintenance','estop_latched')):raise ValueError('Invalid restart flags')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT generation FROM restart_state WHERE singleton=1').fetchone()
                if (row[0] if row else 0)!=expected_generation:raise ValueError('Restart generation conflict')
                db.execute('INSERT INTO restart_state VALUES(1,?,1,?,?,?,1,?) ON CONFLICT(singleton) DO UPDATE SET generation=excluded.generation,profile=excluded.profile,maintenance=excluded.maintenance,estop_latched=excluded.estop_latched,restart_required=1,updated_at_utc=excluded.updated_at_utc',
                    (expected_generation+1,state['profile'],int(state['maintenance']),int(state['estop_latched']),datetime.now(timezone.utc).isoformat()))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');raise
        return expected_generation+1

    def load_seed_fixture(self):
        # Explicit synthetic opt-in, never called by migrations or application startup.
        with closing(sqlite3.connect(':memory:')) as seed, self.connection() as db:
            seed.executescript((MIGRATIONS/'001_baseline.sql').read_text(encoding='utf-8'))
            seed.executescript((MIGRATIONS.parent/'tests/fixtures/seed.sql').read_text(encoding='utf-8'))
            db.execute('BEGIN IMMEDIATE')
            try:
                for table in ('experiments','plants','sensors','sensor_readings','actuators','actuator_events','images','ml_inferences','alerts','maintenance_events','system_events'):
                    columns=[r[1] for r in seed.execute('PRAGMA table_info('+table+')')]
                    for row in seed.execute('SELECT * FROM '+table):
                        db.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');raise
        return True

    def log_event(self,event):
        from services.event_repository import persist_event
        return persist_event(self,event)
