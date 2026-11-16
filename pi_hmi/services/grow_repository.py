"""Grow data belongs to the M2 repository; no scheduling/hardware here."""
import json
import uuid
from services.sqlite_repository import SQLiteRepository,utc,canonical


class GrowRepository(SQLiteRepository):
    def profiles(self):
        rows=self._rows('SELECT * FROM grow_profiles ORDER BY name')
        for row in rows:row['definition']=json.loads(row.pop('definition_json'))
        return rows

    def active_cycle(self):
        rows=self._rows("SELECT * FROM grow_cycles WHERE status!='complete'")
        return rows[0] if rows else None

    def schedules(self,cycle_id):
        rows=self._rows('SELECT * FROM grow_schedules WHERE cycle_id=? ORDER BY target',(cycle_id,))
        for row in rows:row['definition']=json.loads(row.pop('definition_json'))
        return rows

    def recent_runs(self,cycle_id):
        return self._rows('SELECT * FROM schedule_runs WHERE cycle_id=? ORDER BY created_at_utc DESC,occurrence_id DESC LIMIT 20',(cycle_id,))

    def last_maintenance(self):
        rows=self._rows('SELECT timestamp_utc,action FROM maintenance_events ORDER BY timestamp_utc DESC,maintenance_id DESC LIMIT 1')
        return rows[0] if rows else None

    def create_cycle(self,profile_id,name,now):
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('Cycle name must be 1–80 characters')
        profiles={p['profile_id']:p for p in self.profiles()}
        if profile_id not in profiles:raise ValueError('Unknown profile')
        now=utc(now);cycle_id=str(uuid.uuid4())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                experiment=db.execute("INSERT INTO experiments(name,plant_profile,status,start_time_utc) VALUES(?,?,'planned',?)",(name.strip(),profile_id,now)).lastrowid
                db.execute("INSERT INTO grow_cycles VALUES(?,?,?,?,'paused',1,?,NULL,NULL)",(cycle_id,experiment,profile_id,canonical(profiles[profile_id]),now))
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return self.active_cycle()

    def transition_cycle(self,cycle_id,generation,status,now):
        if status not in ('running','paused','complete'):raise ValueError('Invalid cycle state')
        now=utc(now)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                changed=db.execute("UPDATE grow_cycles SET status=?,generation=generation+1,started_at_utc=CASE WHEN ?='running' THEN COALESCE(started_at_utc,?) ELSE started_at_utc END,ended_at_utc=CASE WHEN ?='complete' THEN ? ELSE ended_at_utc END WHERE cycle_id=? AND generation=? AND status!='complete'",
                    (status,status,now,status,now,cycle_id,generation)).rowcount
                if changed!=1:raise ValueError('Cycle generation changed')
                db.execute("UPDATE experiments SET status=?,end_time_utc=CASE WHEN ?='complete' THEN ? ELSE NULL END WHERE experiment_id=(SELECT experiment_id FROM grow_cycles WHERE cycle_id=?)",
                    ({'running':'active','paused':'paused','complete':'complete'}[status],status,now,cycle_id))
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        rows=self._rows('SELECT * FROM grow_cycles WHERE cycle_id=?',(cycle_id,))
        return rows[0]

    def replace_schedules(self,cycle_id,generation,definitions):
        # Stable IDs, cycle generation and per-run definition snapshots preserve history.
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute("UPDATE grow_cycles SET generation=generation+1 WHERE cycle_id=? AND generation=? AND status='paused'",(cycle_id,generation)).rowcount!=1:
                    raise ValueError('Pause cycle before editing schedules')
                for definition in definitions:
                    target=definition['target'];new_id=str(uuid.uuid4())
                    previous=db.execute('SELECT schedule_id FROM grow_schedules WHERE cycle_id=? AND target=?',(cycle_id,target)).fetchone()
                    if previous:
                        # Referenced historical schedule identities must not be overwritten.
                        db.execute('UPDATE grow_schedules SET definition_json=? WHERE schedule_id=?',(canonical(definition),previous[0]))
                    else:db.execute('INSERT INTO grow_schedules VALUES(?,?,?,?)',(new_id,cycle_id,target,canonical(definition)))
                # Disabled entries are explicit definitions, not deleted rows.
                present={d['target'] for d in definitions}
                for target in ('pump','lighting'):
                    if target not in present:db.execute('UPDATE grow_schedules SET definition_json=? WHERE cycle_id=? AND target=?',(canonical(dict(target=target,enabled=False)),cycle_id,target))
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return self.active_cycle()

    def claim_run(self,occurrence_id,cycle,schedule,due,command,now):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute("SELECT generation,status FROM grow_cycles WHERE cycle_id=?",(cycle['cycle_id'],)).fetchone()
                if not row or tuple(row)!=(cycle['generation'],'running'):raise ValueError('Cycle changed before claim')
                changed=db.execute("INSERT INTO schedule_runs VALUES(?,?,?,?,?,?,'claimed',NULL,?,?) ON CONFLICT(occurrence_id) DO NOTHING",
                    (occurrence_id,cycle['cycle_id'],schedule['schedule_id'],cycle['generation'],utc(due),command,utc(now),canonical(schedule['definition']))).rowcount
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return changed==1

    def finish_run(self,occurrence_id,status,result):
        if status not in ('inhibited','acknowledged','unavailable','missed','uncertain'):raise ValueError('Invalid occurrence result')
        return self._write("UPDATE schedule_runs SET status=?,result_json=? WHERE occurrence_id=? AND status='claimed'",(status,canonical(result),occurrence_id))[1]==1

    def event_committed(self,event_id):
        return bool(event_id and self._rows('SELECT event_id FROM system_events WHERE event_id=? AND envelope_json IS NOT NULL',(event_id,)))
