"""Atomic durable event-v1 commit and derived records. No control permissions."""
import uuid
from services.sqlite_repository import canonical,utc


class EventValidationError(ValueError):pass
class EventConflictError(ValueError):pass


def normalize_event(event):
    try:
        required={'schema_version','event_id','timestamp_utc','event_type','source','software_version','experiment_id','payload'}
        if not isinstance(event,dict) or not required<=set(event) or set(event)-required-{'severity'}:raise ValueError('Invalid envelope fields')
        if type(event['schema_version']) is not int or event['schema_version']!=1:raise ValueError('Unsupported event version')
        if not isinstance(event['event_id'],str) or str(uuid.UUID(event['event_id']))!=event['event_id']:raise ValueError('Canonical UUID event_id required')
        for key in ('event_type','source','software_version'):
            if not isinstance(event[key],str) or not 1<=len(event[key])<=128:raise ValueError('Missing event identity')
        if not isinstance(event['payload'],dict):raise ValueError('Object payload required')
        if event['experiment_id'] is not None and (type(event['experiment_id']) is not int or event['experiment_id']<1):raise ValueError('Invalid experiment linkage')
        if event.get('severity') not in (None,'info','warning','critical'):raise ValueError('Invalid severity')
        result=dict(event,timestamp_utc=utc(event['timestamp_utc']),severity=event.get('severity'))
        text=canonical(result)
        if len(text.encode('utf-8'))>262144:raise ValueError('Event exceeds 256 KiB')
        if event['event_type']=='command_outcome':
            payload=event['payload']
            if any(type(payload.get(k)) is not bool for k in ('accepted','firmware_confirmed','physically_verified')):raise ValueError('Explicit actuator outcome flags required')
            if payload['physically_verified']:raise ValueError('Host pipeline cannot attest physical verification')
            if payload.get('accepted_at_utc'):utc(payload['accepted_at_utc'])
            if payload.get('acknowledged_at_utc'):utc(payload['acknowledged_at_utc'])
            if payload['firmware_confirmed'] and not payload.get('acknowledged_at_utc'):raise ValueError('ACK timestamp required')
        if event['event_type'] in ('sensor_quality','sensor_sample'):
            payload=event['payload'];reading=payload['reading']
            if not isinstance(payload['sensor_id'],str) or not payload['sensor_id']:raise ValueError('Sensor identity required')
            if reading['quality_flag'] not in ('good','stale','suspect','invalid','missing'):raise ValueError('Unknown sensor quality')
            if reading['quality_flag']=='good' and type(reading['value']) not in (int,float,bool):raise ValueError('Good reading requires a value')
        if event['event_type']=='safe_state_request':
            if type(event['payload'].get('firmware_confirmed')) is not bool:raise ValueError('Safe-state ACK flag required')
            if event['payload'].get('physically_verified') is not False:raise ValueError('Safe-state physical outcome is unverified')
        return result,text
    except (ValueError,TypeError,KeyError,OverflowError) as exc:raise EventValidationError(str(exc)) from exc


def _project(db,event):
    payload=event['payload'];kind=event['event_type'];event_id=event['event_id']
    targets=[]
    if kind=='command_outcome' and payload['accepted']:
        target=payload.get('target')
        targets=['pump','fan','lighting'] if payload.get('action')=='stop' else ([target] if target in ('pump','fan','lighting') else [])
    elif kind=='safe_state_request':targets=['pump','fan','lighting']
    for target in targets:
        reported=payload.get('reported_state')
        key={'lighting':'rgb','pump':'pump','fan':'fan'}[target]
        reported=reported.get(key) if isinstance(reported,dict) else None
        requested='off' if kind=='safe_state_request' or payload.get('action')=='stop' else payload.get('requested_state')
        db.execute('INSERT INTO actuator_events(event_id,actuator_id,experiment_id,timestamp_utc,requested_state,reported_state,source,firmware_confirmed,physically_verified,reason,request_id,accepted_at_utc,acknowledged_at_utc,system_event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (event_id+':'+target,target,event['experiment_id'],event['timestamp_utc'],canonical(requested),canonical(reported) if reported is not None else None,event['source'],int(payload['firmware_confirmed']),0,payload.get('error'),payload.get('request_id'),payload.get('accepted_at_utc'),payload.get('acknowledged_at_utc'),event_id))
    if kind=='command_outcome' and payload['accepted'] and payload.get('action') in ('enter_maintenance','exit_maintenance'):
        db.execute('INSERT INTO maintenance_events(experiment_id,timestamp_utc,action,component,details_json,system_event_id) VALUES(?,?,?,?,?,?)',
            (event['experiment_id'],event['timestamp_utc'],payload['action'],'system',canonical(payload),event_id))
    if kind in ('sensor_quality','sensor_sample'):
        reading=payload['reading'];value=reading['value'];quality=reading['quality_flag']
        if quality not in ('good','stale','suspect','invalid','missing'):raise EventValidationError('Unknown sensor quality')
        if quality!='good':value=None
        elif type(value) is bool:value=int(value)
        db.execute('INSERT INTO sensor_readings(sensor_id,experiment_id,timestamp_utc,value,quality_flag,system_event_id) VALUES(?,?,?,?,?,?)',
            (payload['sensor_id'],event['experiment_id'],event['timestamp_utc'],value,quality,event_id))


def persist_event(repository,event):
    normalized,text=normalize_event(event)
    with repository.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            previous=db.execute('SELECT envelope_json FROM system_events WHERE event_id=?',(normalized['event_id'],)).fetchone()
            if previous:
                if previous[0]!=text:raise EventConflictError('Event ID reused with different content or legacy envelope')
            else:
                db.execute('INSERT INTO system_events(event_id,experiment_id,schema_version,timestamp_utc,event_type,source,software_version,payload_json,severity,envelope_json) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (normalized['event_id'],normalized['experiment_id'],1,normalized['timestamp_utc'],normalized['event_type'],normalized['source'],normalized['software_version'],canonical(normalized['payload']),normalized['severity'],text))
                _project(db,normalized)
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK');raise
    return True  # Only a committed identical envelope is acknowledged.
