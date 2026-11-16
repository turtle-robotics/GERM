"""Host-only profiles, cycle lifecycle and deterministic UTC scheduling via M1."""
import copy
from datetime import datetime,timedelta,timezone
import threading
import uuid
from services.event_service import HostPersistenceRuntime
from services.sqlite_repository import utc


def schedule_definitions(values):
    if not isinstance(values,list) or len(values)>2:raise ValueError('At most one pump and one lighting schedule')
    result=[];seen=set()
    for definition in values:
        if not isinstance(definition,dict):raise ValueError('Schedule must be an object')
        d=copy.deepcopy(definition);target=d.get('target')
        if target not in ('pump','lighting') or target in seen:raise ValueError('Conflicting/unsupported schedule target')
        seen.add(target)
        if d.get('enabled') is False:
            if set(d)!={'target','enabled'}:raise ValueError('Disabled schedule accepts no settings')
        elif target=='pump':
            if set(d)!={'target','enabled','interval_s'} or d['enabled'] is not True or type(d['interval_s']) is not int or not 10<=d['interval_s']<=86400:
                raise ValueError('Host pump interval must be an integer 10–86400 seconds; pulse is fixed 5 seconds')
        else:
            if set(d)!={'target','enabled','start_utc','end_utc','rgb'} or d['enabled'] is not True:raise ValueError('Invalid lighting schedule')
            for key in ('start_utc','end_utc'):
                text=d[key]
                if not isinstance(text,str) or len(text)!=5 or text[2]!=':' or not (text[:2]+text[3:]).isascii() or not (text[:2]+text[3:]).isdecimal() or not 0<=int(text[:2])<24 or not 0<=int(text[3:])<60:
                    raise ValueError('Lighting times must be HH:MM UTC')
            if d['start_utc']==d['end_utc']:raise ValueError('Lighting window cannot have identical start and end')
            rgb=d['rgb']
            if not isinstance(rgb,list) or len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb) or not any(rgb):raise ValueError('RGB requires three integers 0–255 and a nonzero channel')
        result.append(d)
    return result


class GrowService:
    def __init__(self,gateway,repository):
        self.gateway,self.repo=gateway,repository
        self.persistence=HostPersistenceRuntime(gateway,repository)
        self.operations=threading.RLock();self.scheduler_lock=threading.Lock()
        self.cycle=None;self.schedules=[];self.armed=False;self.pending_start=False
        self._grant=None;self.last_tick=None
        gateway.grow_service=self
        self.recover()

    def _authorize(self,authority):
        if authority is not self.gateway.operator_authority:raise PermissionError('Operator authorization required')

    def _emit(self,kind,payload):return self.gateway.state.emit(kind,payload,'grow_manager')

    def _inhibit(self,reason=None):
        with self.gateway.state.lock:
            self.armed=False;self._grant=None
            self.gateway.state.restart_required=True
            self.gateway.state.revision+=1
            if reason:self.gateway.state.service_inhibits.add(reason)
        return self.gateway.command('STOP',source='safety',authority=self.gateway.safety_authority)

    def _fault(self,exc):
        self._inhibit('grow_storage_unavailable')
        self._emit('grow_fault',{'error':type(exc).__name__,'restart_required':True})

    def recover(self):
        self._inhibit()
        try:
            with self.operations:
                self.repo.integrity_check()
                cycle=self.repo.active_cycle()
                if cycle and cycle['status']=='running':cycle=self.repo.transition_cycle(cycle['cycle_id'],cycle['generation'],'paused',self.now())
                definitions=self.repo.schedules(cycle['cycle_id']) if cycle else []
                schedule_definitions([s['definition'] for s in definitions])
                with self.gateway.state.lock:
                    self.cycle,self.schedules=cycle,definitions
                    self.gateway.state.experiment_id=cycle['experiment_id'] if cycle else None
                    if cycle:self.gateway.state.set_profile(cycle['profile_id'])
                    self.gateway.state.service_inhibits.discard('grow_storage_unavailable')
                    self.gateway.state.service_inhibits.discard('schedule_clock_fault')
                    self.last_tick=None
                self.repo.status='ready'
                self._emit('grow_recovery',{'cycle_id':cycle['cycle_id'] if cycle else None,'restart_required':True,'schedules_armed':False})
                if not self.persistence.restart.checkpoint():raise OSError('Restart checkpoint failed')
                return True
        except Exception as exc:
            self._fault(exc);return False

    def now(self):return self.gateway.state.utc_now().isoformat()

    def create_cycle(self,profile_id,name,authority):
        self._authorize(authority)
        with self.operations:
            if self.cycle and self.cycle['status']!='complete':raise ValueError('Complete existing cycle before selecting another profile')
            self._inhibit()
            try:
                cycle=self.repo.create_cycle(profile_id,name,self.now())
                with self.gateway.state.lock:
                    self.cycle=cycle;self.schedules=[]
                    self.gateway.state.revision+=1
                    self.gateway.state.experiment_id=cycle['experiment_id']
                    self.gateway.state.set_profile(profile_id)
                self._emit('grow_cycle_created',{'cycle_id':cycle['cycle_id'],'profile_id':profile_id,'configuration_scope':'host-only'})
                if not self.persistence.restart.checkpoint():raise OSError('Profile checkpoint not committed')
                return self.snapshot()
            except ValueError:raise
            except Exception as exc:self._fault(exc);raise

    def configure(self,definitions,authority):
        self._authorize(authority);definitions=schedule_definitions(definitions)
        with self.operations:
            if not self.cycle or self.cycle['status']!='paused':raise ValueError('Pause an active cycle before editing schedules')
            self._inhibit()
            try:
                cycle=self.repo.replace_schedules(self.cycle['cycle_id'],self.cycle['generation'],definitions)
                rows=self.repo.schedules(cycle['cycle_id'])
                with self.gateway.state.lock:
                    self.cycle,self.schedules=cycle,rows
                    self.gateway.state.revision+=1
                self._emit('grow_schedule_configured',{'cycle_id':cycle['cycle_id'],'generation':cycle['generation'],'definitions':definitions,'approval':'host simulation only'})
                return self.snapshot()
            except Exception as exc:self._fault(exc);raise

    def start_permission(self):
        if not self.cycle or self.cycle['status']=='complete':return ['grow_cycle_missing']
        if self.armed and not self.gateway.state.restart_required:return ['grow_cycle_already_running']
        if not any(s['definition'].get('enabled') for s in self.schedules):return ['grow_schedules_unconfigured']
        return []

    def confirmation_description(self,action):
        if action!='start' or not self.cycle:return action.replace('_',' ')+' · host simulation only'
        settings=[]
        for row in self.schedules:
            d=row['definition']
            if not d.get('enabled'):continue
            settings.append('pump 5 s every '+str(d['interval_s'])+' s' if d['target']=='pump' else 'lighting '+d['start_utc']+'–'+d['end_utc']+' UTC RGB '+str(d['rgb']))
        return 'Start '+self.cycle['profile_id']+' host cycle: '+('; '.join(settings))+'? This can activate synthetic outputs; physical control is disabled.'

    def automatic_permission(self,intent):
        # Called inside the gateway lock, including for arbitrary trusted automatic callers.
        grant=self._grant
        if not self.armed or self.pending_start or not self.cycle or self.cycle['status']!='running':return ['grow_cycle_not_armed']
        if not grant or grant!=(intent.request_id,intent.payload.get('command'),self.cycle['generation']):return ['schedule_grant_missing']
        if self.gateway.state.profile!=self.cycle['profile_id']:return ['grow_profile_changed']
        return []

    def workflow(self,action,context,authority):
        self._authorize(authority)
        if action=='start':
            with self.operations:
                if self.armed and not self.gateway.state.restart_required:
                    return self.gateway.execute(self.gateway.intent(action,**context),authority)
                with self.gateway.state.lock:self.pending_start=True;self.armed=False
                try:
                    result=self.gateway.execute(self.gateway.intent(action,**context),authority)
                    if not result['accepted'] or result['http_status']!=200:return result
                    revision=result['state_revision']
                    cycle=self.repo.transition_cycle(self.cycle['cycle_id'],self.cycle['generation'],'running',self.now())
                    with self.gateway.state.lock:
                        current=self.gateway.state.snapshot()
                        safe=current['system_state'] in ('NORMAL','WARNING') and not current['inhibits'] and self.gateway.state.revision==revision
                        if safe:self.cycle=cycle;self.armed=True
                    if not safe:
                        cycle=self.repo.transition_cycle(cycle['cycle_id'],cycle['generation'],'paused',self.now())
                        with self.gateway.state.lock:self.cycle=cycle
                        result.update(status='restart_inhibited',http_status=409)
                    self._emit('grow_cycle_transition',{'cycle_id':cycle['cycle_id'],'status':cycle['status'],'generation':cycle['generation'],'gateway_request_id':result['request_id']})
                    result['cycle_status']=cycle['status'];return result
                except Exception as exc:self._fault(exc);raise
                finally:
                    with self.gateway.state.lock:self.pending_start=False
        # Urgent safe stop happens before waiting on the cycle/database mutex.
        if action in ('pause','enter_maintenance','complete_cycle'):
            result=self.gateway.execute(self.gateway.intent(action,**context),authority)
            if not result['accepted']:return result
            with self.gateway.state.lock:self.armed=False;self._grant=None
            with self.operations:
                if self.cycle and self.cycle['status']!='complete':
                    try:
                        status='complete' if action=='complete_cycle' and result['firmware_confirmed'] else 'paused'
                        cycle=self.repo.transition_cycle(self.cycle['cycle_id'],self.cycle['generation'],status,self.now())
                        with self.gateway.state.lock:self.cycle=cycle
                        self._emit('grow_cycle_transition',{'cycle_id':cycle['cycle_id'],'status':status,'generation':cycle['generation'],'gateway_request_id':result['request_id']})
                        if status=='complete':
                            with self.gateway.state.lock:self.gateway.state.experiment_id=None
                    except Exception as exc:self._fault(exc);raise
            return result
        return self.gateway.execute(self.gateway.intent(action,**context),authority)

    def _due(self,schedule,now,cycle):
        definition=schedule['definition']
        if not definition.get('enabled'):return None
        if definition['target']=='pump':
            start=datetime.fromisoformat(cycle['started_at_utc'])
            elapsed=(now-start).total_seconds()
            if elapsed<0:raise ValueError('Cycle start is in the future')
            due=start+timedelta(seconds=int(elapsed//definition['interval_s'])*definition['interval_s'])
            return due,'PUMP_5S',(now-due).total_seconds()>1
        minutes=now.hour*60+now.minute
        a,b=(int(definition[k][:2])*60+int(definition[k][3:]) for k in ('start_utc','end_utc'))
        on=a<=minutes<b if a<b else (minutes>=a or minutes<b)
        edge=a if on else b
        due=now.replace(hour=edge//60,minute=edge%60,second=0,microsecond=0)
        if due>now:due-=timedelta(days=1)
        command='LED:'+','.join(map(str,definition['rgb']))+',0' if on else 'LED_OFF'
        return due,command,False

    def scheduler_tick(self):
        if not self.scheduler_lock.acquire(blocking=False):return []
        results=[]
        try:
            now=datetime.fromisoformat(utc(self.now()))
            if self.last_tick is not None and now<self.last_tick:
                self._inhibit('schedule_clock_fault');self._emit('schedule_clock_fault',{'restart_required':True});return []
            self.last_tick=now
            with self.gateway.state.lock:
                if not self.armed or not self.cycle or self.cycle['status']!='running':return []
                inhibits=self.gateway.state.snapshot()['inhibits']
                cycle=copy.deepcopy(self.cycle);schedules=copy.deepcopy(self.schedules)
            if inhibits:
                self._inhibit();self._emit('schedule_inhibited',{'inhibits':inhibits,'restart_required':True});return []
            for schedule in schedules:
                due=self._due(schedule,now,cycle)
                if due is None:continue
                stamp,command,missed=due
                identity=':'.join((cycle['cycle_id'],str(cycle['generation']),schedule['schedule_id'],stamp.isoformat(),command))
                occurrence=str(uuid.uuid5(uuid.NAMESPACE_URL,identity))
                try:
                    if not self.repo.claim_run(occurrence,cycle,schedule,stamp.isoformat(),command,now.isoformat()):continue
                    if missed:result={'status':'missed','reason_codes':['late_pulse_not_replayed'],'accepted':False};status='missed'
                    else:
                        with self.gateway.state.lock:
                            if not self.armed or self.cycle['generation']!=cycle['generation']:
                                result={'status':'inhibited','accepted':False,'reason_codes':['cycle_changed']}
                            else:
                                self._grant=(occurrence,command,cycle['generation'])
                                try:result=self.gateway.command(command,source='automatic',authority=self.gateway.automatic_authority,request_id=occurrence)
                                finally:self._grant=None
                        status='acknowledged' if result.get('firmware_confirmed') else ('unavailable' if result.get('accepted') else 'inhibited')
                    if not self.repo.finish_run(occurrence,status,result):raise OSError('Schedule outcome not committed')
                    self._emit('schedule_decision',{'occurrence_id':occurrence,'scheduled_at_utc':stamp.isoformat(),'command':command,'cycle_generation':cycle['generation'],'outcome':result,'ledger_status':status})
                    results.append(result)
                    if result.get('accepted') and not result.get('firmware_confirmed'):self._inhibit()
                except Exception as exc:self._fault(exc);break
            return results
        except Exception as exc:
            self._fault(exc);return results
        finally:self.scheduler_lock.release()

    def snapshot(self):
        with self.gateway.state.lock:
            cycle=copy.deepcopy(self.cycle);schedules=copy.deepcopy(self.schedules)
            armed=self.armed;last=copy.deepcopy(self.gateway.state.last_command)
            logging=copy.deepcopy(self.gateway.state.snapshot()['logging'])
            unavailable='grow_storage_unavailable' in self.gateway.state.service_inhibits
        try:
            profiles=self.repo.profiles();maintenance=self.repo.last_maintenance()
            committed=self.repo.event_committed(last.get('event_id')) if last else False
            runs=self.repo.recent_runs(cycle['cycle_id']) if cycle else []
            day=None
            if cycle and cycle['started_at_utc']:
                day=max(1,1+int((datetime.fromisoformat(utc(self.now()))-datetime.fromisoformat(cycle['started_at_utc'])).total_seconds()//86400))
            return dict(state='error' if unavailable else self.repo.status,scope='host simulation only',profiles=profiles,cycle=cycle,schedules=schedules,schedules_armed=armed,
                        grow_day=day,last_maintenance=maintenance,recent_runs=runs,logging=logging,last_command_event='committed' if committed else ('queued' if last else 'none'),
                        configuration_notice='Basil and spearmint timings await review; entered schedules are host simulation settings')
        except Exception as exc:self._fault(exc);raise

    def tick(self):
        results=self.scheduler_tick();self.persistence.tick();return results
