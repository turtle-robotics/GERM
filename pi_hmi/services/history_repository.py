"""Bounded read-only history over M2 tables; no command or hardware dependency."""
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
from functools import lru_cache
from services.sqlite_repository import canonical,utc,bounded


def time_key(value):
    if not isinstance(value,str):return None
    return _cached_time_key(value) if len(value)<=40 else _normalize_time_key(value)


def _normalize_time_key(value):
    try:return datetime.fromisoformat(utc(value)).isoformat(timespec='microseconds')
    except (ValueError,TypeError):return None


# SQLite evaluates the deterministic function repeatedly for sorting/keysets.
# Cap both entry count and cached input length; no timestamp semantics change.
_cached_time_key=lru_cache(maxsize=4096)(_normalize_time_key)


# table, stable identity, time, type column, joined projection; LEFT JOIN retains legacy rows.
SOURCES={
 'experiments':('experiments','experiment_id','start_time_utc','status',
   'LEFT JOIN grow_cycles c ON c.experiment_id=t.experiment_id',
   'c.cycle_id,c.profile_id,c.profile_snapshot_json,c.generation'),
 'sensors':('sensor_readings','reading_id','timestamp_utc','quality_flag',
   'LEFT JOIN sensors s ON s.sensor_id=t.sensor_id','s.unit,s.location,s.expected_period_s'),
 'images':('images','image_id','timestamp_utc','capture_reason',
   'LEFT JOIN capture_requests c ON c.request_id=t.capture_request_id LEFT JOIN media_outbox o ON o.capture_request_id=c.request_id',
   'c.schedule_generation,c.status AS capture_status,o.status AS event_status'),
 'inference':('ml_inferences','inference_id','timestamp_utc','predicted_class',
   'LEFT JOIN images i ON i.image_id=t.image_id LEFT JOIN ml_jobs j ON j.request_id=t.request_id LEFT JOIN model_manifests m ON m.manifest_sha256=t.manifest_sha256 LEFT JOIN media_outbox o ON o.ml_request_id=t.request_id',
   'i.experiment_id,i.plant_id,i.source AS image_source,j.policy_json,j.policy_sha256,m.manifest_json,m.artifact_sha256,o.status AS event_status'),
 'actuators':('actuator_events','event_id','timestamp_utc','actuator_id','',''),
 'maintenance':('maintenance_events','maintenance_id','timestamp_utc','action','',''),
 'events':('system_events','event_id','timestamp_utc','event_type',
   'LEFT JOIN media_outbox o ON o.event_id=t.event_id','o.status AS media_outbox_status')}


def filters(value):
    if not isinstance(value,dict) or set(value)-{'experiment','start_utc','end_utc','type','sensor','search'}:raise ValueError('Unsupported history filter')
    out={}
    for key,item in value.items():
        if item is None or item=='':continue
        if key=='experiment':
            if not isinstance(item,(int,str)) or isinstance(item,bool) or not str(item).isdigit() or int(item)<1:raise ValueError('Invalid experiment')
            out[key]=int(item)
        elif key.endswith('_utc'):out[key]=time_key(item);assert_time(out[key])
        elif not isinstance(item,str) or len(item)>120 or any(ord(c)<32 for c in item):raise ValueError('Invalid text filter')
        else:out[key]=item
    if out.get('start_utc') and out.get('end_utc') and out['start_utc']>=out['end_utc']:raise ValueError('Invalid half-open date range')
    return out


def assert_time(value):
    if value is None:raise ValueError('Explicit valid UTC required')


class HistoryRepository:
    def __init__(self,repository,*,snapshot=None):
        self.repo,self.snapshot=repository,snapshot
        if not hasattr(repository,'_history_cursor_key'):repository._history_cursor_key=secrets.token_bytes(32)
        self.key=repository._history_cursor_key

    @contextmanager
    def connection(self):
        path=self.repo.scoped(self.snapshot or self.repo.path)
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=self.repo.timeout/1000)
        db.row_factory=sqlite3.Row
        db.create_function('UTC_KEY',1,time_key,deterministic=True)
        try:
            db.execute('PRAGMA query_only=ON');db.execute(f'PRAGMA busy_timeout={self.repo.timeout}')
            yield db
        finally:db.close()

    def page(self,resource,query=None,*,limit=100,cursor=None):
        if resource not in SOURCES:raise ValueError('Unknown history resource')
        limit=bounded(limit,500);query=filters(query or {})
        if query.get('sensor') and resource!='sensors':raise ValueError('Sensor filter requires sensor history')
        table,identity,stamp,type_col,joins,extra=SOURCES[resource]
        binding=hashlib.sha256(canonical(dict(resource=resource,filters=query,limit=limit)).encode()).hexdigest()
        previous=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                encoded,signature=cursor.split('.')
                if not hmac.compare_digest(signature,hmac.new(self.key,encoded.encode(),'sha256').hexdigest()):raise ValueError()
                previous=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
                if set(previous)!={'v','binding','high','time','id'} or previous['v']!=1 or previous['binding']!=binding or type(previous['high']) is not int or previous['high']<0:raise ValueError()
                if not isinstance(previous['time'],str) or len(previous['time'])>40 or not isinstance(previous['id'],(str,int)):raise ValueError()
            except Exception:raise ValueError('Invalid cursor or changed filters/page size') from None
        with self.connection() as db:
            db.execute('BEGIN')
            high=previous['high'] if previous else db.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table}').fetchone()[0]
            conditions=['t.rowid<=?'];args=[high]
            experiment='i.experiment_id' if resource=='inference' else 't.experiment_id'
            if 'experiment' in query:conditions.append(experiment+'=?');args.append(query['experiment'])
            key=f"COALESCE(UTC_KEY(t.{stamp}),'')"
            for name,op in (('start_utc','>='),('end_utc','<')):
                if name in query:conditions.append(f'{key}{op}?');args.append(query[name])
            if 'type' in query:conditions.append(f't.{type_col}=?');args.append(query['type'])
            if 'sensor' in query:conditions.append('t.sensor_id=?');args.append(query['sensor'])
            if 'search' in query:
                # Literal substring; no SQL/LIKE wildcard interpretation. Bounded pages,
                # time budget and export row quotas also apply to searches.
                columns={'experiments':'name','sensors':'sensor_id','images':'file_path','inference':'predicted_class','actuators':'requested_state','maintenance':'details_json','events':'payload_json'}
                conditions.append(f'instr(lower(t.{columns[resource]}),lower(?))>0');args.append(query['search'])
            if previous:
                conditions.append(f'({key}>? OR ({key}=? AND t.{identity}>?))');args.extend([previous['time'],previous['time'],previous['id']])
            import time
            deadline=time.monotonic()+3
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
            sql=f"SELECT t.*,{key} AS history_time_utc,t.rowid AS history_rowid"+(','+extra if extra else '')+f" FROM {table} t {joins} WHERE "+' AND '.join(conditions)+f' ORDER BY {key},t.{identity} LIMIT ?'
            result=db.execute(sql,args+[limit+1]);columns=[c[0] for c in result.description]
            records=[dict(row) for row in result]
            db.execute('COMMIT')
        more=len(records)>limit;records=records[:limit]
        for row in records:
            row['metadata_provenance']='durable_sqlite_snapshot' if self.snapshot else 'durable_sqlite_live'
            row['timestamp_quality']='valid_utc' if row['history_time_utc'] else 'unknown_or_invalid'
            row['record_persistence']='committed'  # These rows are read from SQLite, never from volatile queues.
            if resource in ('images','inference'):row['source_quality']='known' if row.get('source',row.get('image_source')) else 'legacy_unknown'
        next_cursor=None
        if more:
            last=records[-1]
            value=dict(v=1,binding=binding,high=high,time=last['history_time_utc'],id=last[identity])
            encoded=base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip('=')
            next_cursor=encoded+'.'+hmac.new(self.key,encoded.encode(),'sha256').hexdigest()
        columns+=['metadata_provenance','timestamp_quality','record_persistence']
        if resource in ('images','inference'):columns+=['source_quality']
        return dict(resource=resource,rows=records,columns=columns,next_cursor=next_cursor,high_water_rowid=high,filters=query,
                    retrieved_at_utc=datetime.now(timezone.utc).isoformat(),consistency='snapshot' if self.snapshot else 'bounded live view; mutable fields may change between pages')

    def scan(self,resource,query,*,deadline=None):
        """Snapshot-only streaming query; avoids repeatedly sorting large exports."""
        if self.snapshot is None:raise ValueError('Streaming export requires a snapshot')
        if resource not in SOURCES:raise ValueError('Unknown resource')
        query=filters(query);table,identity,stamp,type_col,joins,extra=SOURCES[resource]
        if query.get('sensor') and resource!='sensors':raise ValueError('Sensor filter requires sensor history')
        key=f"COALESCE(UTC_KEY(t.{stamp}),'')";conditions=[];args=[]
        if 'experiment' in query:conditions.append(('i' if resource=='inference' else 't')+'.experiment_id=?');args.append(query['experiment'])
        for name,op in (('start_utc','>='),('end_utc','<')):
            if name in query:conditions.append(f'{key}{op}?');args.append(query[name])
        if 'type' in query:conditions.append(f't.{type_col}=?');args.append(query['type'])
        if 'sensor' in query:conditions.append('t.sensor_id=?');args.append(query['sensor'])
        if 'search' in query:
            column={'experiments':'name','sensors':'sensor_id','images':'file_path','inference':'predicted_class','actuators':'requested_state','maintenance':'details_json','events':'payload_json'}[resource]
            conditions.append(f'instr(lower(t.{column}),lower(?))>0');args.append(query['search'])
        sql=f'SELECT t.*,{key} AS history_time_utc,t.rowid AS history_rowid'+(','+extra if extra else '')+f' FROM {table} t {joins}'
        if conditions:sql+=' WHERE '+' AND '.join(conditions)
        sql+=f' ORDER BY {key},t.{identity}'
        with self.connection() as db:
            import time
            deadline=deadline if deadline is not None else time.monotonic()+60
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
            result=db.execute(sql,args);columns=[c[0] for c in result.description]+['metadata_provenance','timestamp_quality','record_persistence']
            if resource in ('images','inference'):columns+=['source_quality']
            yield dict(columns=columns,rows=[])
            while True:
                rows=[dict(r) for r in result.fetchmany(500)]
                if not rows:break
                for row in rows:
                    row.update(metadata_provenance='durable_sqlite_snapshot',timestamp_quality='valid_utc' if row['history_time_utc'] else 'unknown_or_invalid',record_persistence='committed')
                    if resource in ('images','inference'):row['source_quality']='known' if row.get('source',row.get('image_source')) else 'legacy_unknown'
                yield dict(columns=columns,rows=rows)
