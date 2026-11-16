"""Explicit host logging lifecycle. No import-time worker, database or device I/O."""
import copy
import threading
from services.event_repository import EventValidationError,EventConflictError
from services.restart_service import attach_restart_store


class EventPipeline:
    def __init__(self,state,repository):
        self.state,self.repository=state,repository
        self.lock=threading.Lock()
        self.poison={}
        with state.lock:state.logging_status.update(state='pending',last_error=None)

    def drain(self):
        if not self.lock.acquire(blocking=False):return False
        try:
            with self.state.lock:pending=copy.deepcopy(list(self.state.events))
            for event in pending:
                if event['event_id'] in self.poison:continue
                try:
                    if self.repository.log_event(event) is not True:raise OSError('Commit not acknowledged')
                except (EventValidationError,EventConflictError) as exc:
                    self.poison[event['event_id']]=type(exc).__name__
                    with self.state.lock:self.state.logging_status.update(state='error',last_error=type(exc).__name__)
                    continue  # Retained invalid envelope does not prevent later valid records.
                except Exception as exc:
                    with self.state.lock:self.state.logging_status.update(state='error',last_error=type(exc).__name__)
                    return False
                with self.state.lock:
                    for queued in self.state.events:
                        if queued['event_id']==event['event_id']:
                            self.state.events.remove(queued);break
                    self.state.logging_status.update(last_durable_event_id=event['event_id'],last_durable_at_utc=self.state.utc_now().isoformat())
            with self.state.lock:
                remaining={e['event_id'] for e in self.state.events}
                self.poison={key:value for key,value in self.poison.items() if key in remaining}
                status='error' if self.poison or self.state.dropped_events else ('pending' if remaining else 'durable')
                self.state.logging_status.update(state=status,poison_events=len(self.poison),last_error=self.state.logging_status.get('last_error') if status=='error' else None)
                return status=='durable'
        finally:self.lock.release()


class HostPersistenceRuntime:
    def __init__(self,gateway,repository):
        self.gateway,self.repository=gateway,repository
        self.restart=attach_restart_store(gateway,repository)
        # Explicit symbolic dictionaries only. No physical policy or healthy sample is seeded.
        with repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                for name,policy in gateway.state.validator.policies.items():
                    db.execute('INSERT INTO sensors(sensor_id,unit,location,expected_period_s) VALUES(?,?,?,?) ON CONFLICT(sensor_id) DO NOTHING',
                        (name,policy.unit,policy.location,policy.expected_period_s))
                    row=db.execute('SELECT unit,location,expected_period_s FROM sensors WHERE sensor_id=?',(name,)).fetchone()
                    if tuple(row)!=(policy.unit,policy.location,policy.expected_period_s):raise ValueError('Sensor dictionary/policy conflict')
                for name in ('pump','fan','lighting'):
                    db.execute('INSERT INTO actuators(actuator_id,description) VALUES(?,?) ON CONFLICT(actuator_id) DO NOTHING',(name,'Symbolic host actuator; physical safe policy unapproved'))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                with gateway.state.lock:
                    gateway.state.persistence_status='error'
                    gateway.state.restart_required=True
                raise
        self.events=EventPipeline(gateway.state,repository)
        gateway.event_pipeline=self.events

    def tick(self):
        durable=self.restart.checkpoint()
        logged=self.events.drain()
        return durable and logged

    def record_sensor_snapshot(self):
        with self.gateway.state.lock:
            for sensor_id,reading in self.gateway.state.snapshot()['sensors'].items():
                self.gateway.state.emit('sensor_sample',dict(sensor_id=sensor_id,reading=reading),'acquisition')

    def run(self,stop_event,period_s=1):
        if type(period_s) not in (int,float) or not 0<period_s<=60:raise ValueError('Invalid host drain period')
        while not stop_event.is_set():
            self.tick()
            stop_event.wait(period_s)
