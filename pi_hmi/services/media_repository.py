"""M2-owned capture journal, model registry and atomic inference records."""
import json
import uuid
from datetime import datetime,timedelta
from services.grow_repository import GrowRepository
from services.sqlite_repository import canonical,utc


def request_uuid(value):
    if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError('Canonical UUID request_id required')
    return value


def scheduled_capture_id(generation,experiment_id,scheduled_at):
    identity='capture:'+str(generation)+':'+str(experiment_id)+':'+utc(scheduled_at)
    return str(uuid.uuid5(uuid.NAMESPACE_URL,identity))


def next_capture_slot(schedule,after):
    anchor=datetime.fromisoformat(utc(schedule['anchor_utc']))
    after=datetime.fromisoformat(utc(after))
    steps=max(0,int((after-anchor).total_seconds()//schedule['interval_s'])+1)
    return (anchor+timedelta(seconds=steps*schedule['interval_s'])).isoformat()


def capture_schedule_state(schedule,now):
    if not schedule:return 'not_configured'
    if schedule['clock_fault']:return 'clock_fault'
    if schedule['last_observed_utc'] and datetime.fromisoformat(utc(now))<datetime.fromisoformat(schedule['last_observed_utc']):return 'clock_behind_high_water'
    if not schedule['enabled']:return 'disabled'
    now=datetime.fromisoformat(utc(now))
    boundaries=[schedule['resume_not_before_utc'],schedule['anchor_utc']]
    if any(value and now<datetime.fromisoformat(value) for value in boundaries):return 'waiting_for_boundary'
    return 'ready'


class MediaRepository(GrowRepository):
    def plants_for_experiment(self,experiment_id):
        return self._rows('SELECT plant_id,position,species FROM plants WHERE experiment_id=? ORDER BY position',(experiment_id,))

    def claim_capture(self,request_id,experiment_id,plant_id,reason,now,scheduled_at=None,schedule_generation=None):
        request_uuid(request_id);now=utc(now)
        if type(experiment_id) is not int or experiment_id<1:raise ValueError('Active experiment required')
        if plant_id is not None and (type(plant_id) is not int or plant_id<1):raise ValueError('Invalid plant ID')
        if reason not in ('manual','scheduled','fault'):raise ValueError('Invalid capture reason')
        if scheduled_at is not None:scheduled_at=utc(scheduled_at)
        if reason=='scheduled':
            # Commit a rollback detected at the claim boundary before rejecting;
            # a rejected claim transaction must not roll the fault latch back.
            observed=self.observe_capture_clock(now)
            if not observed or capture_schedule_state(observed,now)!='ready':raise ValueError('Scheduled capture clock is inhibited')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if reason=='scheduled':
                    schedule=db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone()
                    if not schedule or schedule['generation']!=schedule_generation or capture_schedule_state(schedule,now)!='ready':raise ValueError('Scheduled capture permission changed')
                    if schedule['last_observed_utc'] and datetime.fromisoformat(now)<datetime.fromisoformat(schedule['last_observed_utc']):raise ValueError('Scheduled claim predates clock high-water')
                    if not scheduled_at or request_id!=scheduled_capture_id(schedule_generation,experiment_id,scheduled_at):raise ValueError('Scheduled occurrence identity mismatch')
                    due=datetime.fromisoformat(scheduled_at);anchor=datetime.fromisoformat(schedule['anchor_utc'])
                    elapsed=(due-anchor).total_seconds()
                    if elapsed<0 or elapsed%schedule['interval_s']!=0:raise ValueError('Occurrence is not an anchored schedule slot')
                    if schedule['resume_not_before_utc'] and due<datetime.fromisoformat(schedule['resume_not_before_utc']):raise ValueError('Occurrence precedes recovery boundary')
                previous=db.execute('SELECT * FROM capture_requests WHERE request_id=?',(request_id,)).fetchone()
                if previous:
                    if (previous['experiment_id'],previous['plant_id'],previous['capture_reason'],previous['scheduled_at_utc'])!=(experiment_id,plant_id,reason,scheduled_at):raise ValueError('Capture request ID/content conflict')
                    result=dict(previous);created=False
                else:
                    if plant_id is not None and not db.execute('SELECT plant_id FROM plants WHERE plant_id=? AND experiment_id=?',(plant_id,experiment_id)).fetchone():raise ValueError('Plant does not belong to active experiment')
                    db.execute("INSERT INTO capture_requests(request_id,experiment_id,plant_id,capture_reason,scheduled_at_utc,created_at_utc,status,schedule_generation) VALUES(?,?,?,?,?,?,'claimed',?)",
                        (request_id,experiment_id,plant_id,reason,scheduled_at,now,schedule_generation))
                    result=dict(db.execute('SELECT * FROM capture_requests WHERE request_id=?',(request_id,)).fetchone());created=True
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return result,created

    def capture_request(self,request_id):
        rows=self._rows('SELECT * FROM capture_requests WHERE request_id=?',(request_uuid(request_id),))
        return rows[0] if rows else None

    def prepare_capture(self,request_id,metadata):
        if self._write("UPDATE capture_requests SET status='prepared',metadata_json=? WHERE request_id=? AND status='claimed'",(canonical(metadata),request_id))[1]!=1:raise ValueError('Capture is no longer claimed')

    def capture_failed(self,request_id,status,error):
        if status not in ('failed','interrupted','needs_review','missed'):raise ValueError('Invalid capture failure status')
        self._write("UPDATE capture_requests SET status=?,error=? WHERE request_id=? AND status!='indexed'",(status,error,request_id))

    def capture_error(self,request_id,error):self._write('UPDATE capture_requests SET error=? WHERE request_id=?',(error,request_id))

    def index_capture(self,request_id,*,event_time,software_version):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM capture_requests WHERE request_id=?',(request_id,)).fetchone()
                if not row:raise ValueError('Unknown capture request')
                if row['status']=='indexed':image_id=row['image_id']
                else:
                    if row['status']!='prepared':raise ValueError('Capture is not prepared')
                    image=json.loads(row['metadata_json'])
                    image_id=db.execute('INSERT INTO images(experiment_id,plant_id,file_path,timestamp_utc,sha256,size_bytes,width_px,height_px,capture_reason,capture_request_id,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (row['experiment_id'],row['plant_id'],image['file_path'],utc(image['timestamp_utc']),image['sha256'],image['size_bytes'],image['width_px'],image['height_px'],row['capture_reason'],request_id,'synthetic')).lastrowid
                    self._link_capture(db,request_id,image_id)
                    self._outbox(db,'capture_indexed',dict(request_id=request_id,image_id=image_id,metadata_committed=True,source='synthetic'),row['experiment_id'],event_time,software_version,capture_request_id=request_id)
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return self.image(image_id)

    def _link_capture(self,db,request_id,image_id):
        db.execute("UPDATE capture_requests SET status='indexed',image_id=?,error=NULL WHERE request_id=?",(image_id,request_id))

    def image(self,image_id):
        if type(image_id) is not int or image_id<1:raise ValueError('Positive image_id required')
        rows=self._rows('SELECT * FROM images WHERE image_id=?',(image_id,))
        if not rows:raise ValueError('Unknown image')
        return rows[0]

    def image_by_path(self,path):
        rows=self._rows('SELECT * FROM images WHERE file_path=? AND capture_request_id IS NOT NULL',(path,))
        if not rows:raise ValueError('Image is not indexed by M5')
        return rows[0]

    def incomplete_captures(self):return self._rows("SELECT * FROM capture_requests WHERE status IN ('claimed','prepared') ORDER BY created_at_utc,request_id LIMIT 1000")
    def recent_capture_requests(self):return self._rows('SELECT c.*,(SELECT status FROM media_outbox o WHERE o.capture_request_id=c.request_id) AS event_status FROM capture_requests c ORDER BY created_at_utc DESC,request_id DESC LIMIT 20')

    def _outbox(self,db,kind,payload,experiment_id,event_time,software_version,*,capture_request_id=None,ml_request_id=None):
        event=dict(schema_version=1,event_id=str(uuid.uuid4()),timestamp_utc=utc(event_time),event_type=kind,source='media_service',software_version=software_version,experiment_id=experiment_id,payload=payload)
        db.execute("INSERT INTO media_outbox VALUES(?,?,'pending',?,?)",(event['event_id'],canonical(event),capture_request_id,ml_request_id))

    def pending_media_events(self):return self._rows("SELECT * FROM media_outbox WHERE status='pending' ORDER BY event_id LIMIT 1000")
    def acknowledge_media_event(self,event_id):
        if not self.event_committed(event_id):raise ValueError('M3 event commit not acknowledged')
        self._write("UPDATE media_outbox SET status='committed' WHERE event_id=?",(event_id,))

    def media_receipt(self,request_id):
        rows=self._rows('SELECT event_id,status FROM media_outbox WHERE capture_request_id=? OR ml_request_id=?',(request_id,request_id))
        return rows[0] if rows else None

    def set_capture_schedule(self,enabled,interval_s,anchor_utc):
        if type(enabled) is not bool or type(interval_s) is not int or not 60<=interval_s<=86400:raise ValueError('Capture interval must be 60–86400 integer seconds')
        anchor_utc=utc(anchor_utc)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone()
                if old and old['clock_fault']:
                    if enabled or interval_s!=old['interval_s'] or anchor_utc!=old['anchor_utc']:raise ValueError('Acknowledge the clock fault after UTC recovery before reconfiguring')
                    db.execute('UPDATE capture_schedule SET enabled=0 WHERE singleton=1')
                elif old:
                    # A configuration edit cannot manufacture another occurrence in an
                    # already-observed slot, even though its identity has a new generation.
                    cutoff=old['last_observed_utc']
                    not_before=next_capture_slot(dict(anchor_utc=anchor_utc,interval_s=interval_s),cutoff) if cutoff else None
                    if old['resume_not_before_utc'] and (not not_before or datetime.fromisoformat(old['resume_not_before_utc'])>datetime.fromisoformat(not_before)):
                        not_before=next_capture_slot(dict(anchor_utc=anchor_utc,interval_s=interval_s),(datetime.fromisoformat(old['resume_not_before_utc'])-timedelta(microseconds=1)).isoformat())
                    db.execute('UPDATE capture_schedule SET generation=generation+1,enabled=?,interval_s=?,anchor_utc=?,resume_not_before_utc=? WHERE singleton=1',(int(enabled),interval_s,anchor_utc,not_before))
                else:db.execute('INSERT INTO capture_schedule(singleton,generation,enabled,interval_s,anchor_utc) VALUES(1,1,?,?,?)',(int(enabled),interval_s,anchor_utc))
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return self.capture_schedule()

    def observe_capture_clock(self,now):
        now=utc(now)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone()
                if row:
                    high=row['last_observed_utc']
                    rollback=bool(high and datetime.fromisoformat(now)<datetime.fromisoformat(high))
                    if rollback:db.execute('UPDATE capture_schedule SET clock_fault=1 WHERE singleton=1')
                    elif high!=now:db.execute('UPDATE capture_schedule SET last_observed_utc=? WHERE singleton=1',(now,))
                    row=dict(db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone())
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return row

    def recover_capture_clock(self,now):
        now=utc(now)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone()
                if not row:raise ValueError('Capture schedule is not configured')
                if row['clock_fault']:
                    if row['last_observed_utc'] and datetime.fromisoformat(now)<datetime.fromisoformat(row['last_observed_utc']):raise ValueError('UTC has not reached the persisted clock high-water')
                    boundary=next_capture_slot(row,now)
                    if row['resume_not_before_utc'] and datetime.fromisoformat(row['resume_not_before_utc'])>datetime.fromisoformat(boundary):boundary=row['resume_not_before_utc']
                    db.execute('UPDATE capture_schedule SET clock_fault=0,last_observed_utc=?,resume_not_before_utc=? WHERE singleton=1',(now,boundary))
                row=dict(db.execute('SELECT * FROM capture_schedule WHERE singleton=1').fetchone())
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return row

    def capture_schedule(self):
        rows=self._rows('SELECT * FROM capture_schedule WHERE singleton=1')
        return rows[0] if rows else None

    def register_model(self,manifest):
        self._write('INSERT INTO model_manifests VALUES(?,?,?,?,?,?) ON CONFLICT(manifest_sha256) DO NOTHING',
            (manifest.digest,manifest.model_id,manifest.version,manifest.artifact_sha256,canonical(manifest.as_dict()),'synthetic-contract-only'))
        row=self._rows('SELECT * FROM model_manifests WHERE manifest_sha256=?',(manifest.digest,))[0]
        if row['manifest_json']!=canonical(manifest.as_dict()) or row['artifact_sha256']!=manifest.artifact_sha256:raise ValueError('Stored model manifest conflicts with its digest')

    def claim_ml_job(self,request_id,image_id,manifest_sha,policy_json,policy_sha,now):
        request_uuid(request_id)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                previous=db.execute('SELECT * FROM ml_jobs WHERE request_id=?',(request_id,)).fetchone()
                if previous and (previous['image_id'],previous['manifest_sha256'],previous['policy_sha256'])!=(image_id,manifest_sha,policy_sha):raise ValueError('ML request ID/content conflict')
                previous=previous or db.execute('SELECT * FROM ml_jobs WHERE image_id=? AND manifest_sha256=? AND policy_sha256=?',(image_id,manifest_sha,policy_sha)).fetchone()
                if previous:row=dict(previous);created=False
                else:
                    db.execute("INSERT INTO ml_jobs(request_id,image_id,manifest_sha256,policy_sha256,policy_json,created_at_utc,status) VALUES(?,?,?,?,?,?,'running')",(request_id,image_id,manifest_sha,policy_sha,policy_json,utc(now)))
                    row=dict(db.execute('SELECT * FROM ml_jobs WHERE request_id=?',(request_id,)).fetchone());created=True
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return row,created

    def fail_ml_job(self,request_id,status,error):
        if status not in ('error','timed_out','interrupted'):raise ValueError('Invalid inference failure status')
        self._write("UPDATE ml_jobs SET status=?,error=? WHERE request_id=? AND status='running'",(status,error,request_id))

    def recover_ml_jobs(self):return self._write("UPDATE ml_jobs SET status='interrupted',error='process ended before acknowledged inference commit' WHERE status='running'")[1]

    def ml_job(self,request_id):
        rows=self._rows('SELECT * FROM ml_jobs WHERE request_id=?',(request_uuid(request_id),))
        return rows[0] if rows else None

    def commit_inference(self,job,result,*,software_version):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current=db.execute('SELECT * FROM ml_jobs WHERE request_id=?',(job['request_id'],)).fetchone()
                if current['status']=='completed':
                    output=dict(db.execute('SELECT * FROM ml_inferences WHERE inference_id=?',(current['inference_id'],)).fetchone())
                else:
                    if current['status']!='running':raise ValueError('Inference job is no longer running')
                    image=db.execute('SELECT * FROM images WHERE image_id=?',(job['image_id'],)).fetchone()
                    prior=db.execute('SELECT j.status,i.abnormal_streak,i.assessment,p.timestamp_utc FROM ml_jobs j JOIN images p ON p.image_id=j.image_id LEFT JOIN ml_inferences i ON i.inference_id=j.inference_id WHERE j.job_seq<? AND j.manifest_sha256=? AND j.policy_sha256=? AND p.experiment_id IS ? AND p.plant_id IS ? ORDER BY j.job_seq DESC LIMIT 1',
                        (job['job_seq'],job['manifest_sha256'],job['policy_sha256'],image['experiment_id'],image['plant_id'])).fetchone()
                    result=dict(result)
                    if prior and image['timestamp_utc']<=prior['timestamp_utc']:
                        result.update(assessment='uncertain',review_required=True,predicted_class='uncertain')
                    streak=0
                    if result['assessment']=='abnormal':
                        streak=1+(prior['abnormal_streak'] if prior and prior['status']=='completed' and prior['assessment']=='abnormal' else 0)
                    eligible=streak>=2
                    inference_id=db.execute('INSERT INTO ml_inferences(image_id,timestamp_utc,predicted_class,confidence,model_version,review_required,inference_ms,request_id,manifest_sha256,raw_label,scores_json,assessment,abnormal_streak,alert_eligible,scope) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (job['image_id'],utc(result['timestamp_utc']),result['predicted_class'],result['confidence'],result['model_version'],int(result['review_required']),result['inference_ms'],job['request_id'],job['manifest_sha256'],result['raw_label'],canonical(result['scores']),result['assessment'],streak,int(eligible),'synthetic-contract-only')).lastrowid
                    self._complete_ml_job(db,job['request_id'],inference_id)
                    self._outbox(db,'ml_result',dict(request_id=job['request_id'],image_id=job['image_id'],inference_id=inference_id,assessment=result['assessment'],abnormal_streak=streak,alert_eligible=eligible,scope='synthetic-contract-only',result_committed=True,plant_diagnosis=False),
                        image['experiment_id'],result['timestamp_utc'],software_version,ml_request_id=job['request_id'])
                    output=dict(db.execute('SELECT * FROM ml_inferences WHERE inference_id=?',(inference_id,)).fetchone())
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return output

    def _complete_ml_job(self,db,request_id,inference_id):
        db.execute("UPDATE ml_jobs SET status='completed',inference_id=?,error=NULL WHERE request_id=?",(inference_id,request_id))

    def inference_for_job(self,request_id):
        rows=self._rows('SELECT i.* FROM ml_jobs j JOIN ml_inferences i ON i.inference_id=j.inference_id WHERE j.request_id=?',(request_id,))
        return rows[0] if rows else None

    def latest_inference(self):
        rows=self._rows('SELECT i.*,j.policy_sha256,p.timestamp_utc AS image_timestamp_utc FROM ml_jobs j JOIN ml_inferences i ON i.inference_id=j.inference_id JOIN images p ON p.image_id=j.image_id ORDER BY j.job_seq DESC LIMIT 1')
        return rows[0] if rows else None
