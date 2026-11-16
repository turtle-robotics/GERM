"""Journaled host image capture. Final names never overwrite existing files."""
from datetime import datetime,timedelta
import json
import copy
import os
from pathlib import Path,PurePosixPath
import threading
import uuid
from services.image_validation import inspect_jpeg,MAX_BYTES
from services.media_repository import request_uuid,scheduled_capture_id,capture_schedule_state
from services.sqlite_repository import utc


class CaptureService:
    def __init__(self,state,repository,camera,image_root):
        self.state,self.repo,self.camera=state,repository,camera
        self.root=repository.scoped(image_root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.schedule_lock=threading.Lock()
        self.last_error=None;self.recovery_report=None
        self.scheduling_error=None;self.reported_clock_fault=False

    def path(self,relative):
        if not isinstance(relative,str) or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts or '\\' in relative or ':' in relative:raise ValueError('Invalid image path')
        path=(self.root/relative).resolve()
        if not path.is_relative_to(self.root) or path==self.root:raise ValueError('Image path escapes configured host root')
        return path

    def emit(self,kind,payload,experiment_id=None):
        with self.state.lock:
            event=self.state.emit(kind,payload,'capture_service')
            event['experiment_id']=experiment_id
            return event

    @staticmethod
    def names(request_id,timestamp):
        date=datetime.fromisoformat(utc(timestamp))
        request_uuid(request_id)
        return '.staging/'+request_id+'.part',date.strftime('%Y/%m/%d/')+'capture_'+request_id+'.jpg'

    def _write_stage(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())

    def _finalize(self,stage,final):
        final.parent.mkdir(parents=True,exist_ok=True)
        if not final.exists():
            if os.name=='nt':os.rename(stage,final)  # Windows rename is exclusive; finalize only this owned stage.
            else:os.link(stage,final)  # POSIX exclusive publication; retain staging link.
        if os.name=='posix':
            descriptor=os.open(final.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)

    def verify(self,metadata):
        path=self.path(metadata['file_path'])
        if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Image file missing or oversized')
        data=path.read_bytes();actual=inspect_jpeg(data)
        if any(actual[k]!=metadata[k] for k in actual):raise ValueError('Image content/metadata mismatch')
        return data

    def image_bytes(self,image_id):return self.verify(self.repo.image(image_id))

    def _recover_request(self,row):
        if row['status']=='indexed':
            image=self.repo.image(row['image_id']);self.verify(image);return image
        if not row['metadata_json']:
            self.repo.capture_failed(row['request_id'],'interrupted','No committed frame metadata; fresh acquisition is not replayed')
            return None
        metadata=json.loads(row['metadata_json'])
        stage_name,final_name=self.names(row['request_id'],metadata['timestamp_utc'])
        if metadata['stage_path']!=stage_name or metadata['file_path']!=final_name:raise ValueError('Capture journal path mismatch')
        if datetime.fromisoformat(metadata['timestamp_utc'])>self.state.utc_now():raise ValueError('Future capture timestamp')
        stage,final=self.path(stage_name),self.path(final_name)
        if not final.exists():
            stage_metadata=dict(metadata,file_path=stage_name)
            self.verify(stage_metadata)
            self._finalize(stage,final)
        self.verify(metadata)
        image=self.repo.index_capture(row['request_id'],event_time=self.state.utc_now().isoformat(),software_version=self.state.software_version)
        self.enqueue_outbox()
        return image

    def enqueue_outbox(self):
        rows=self.repo.pending_media_events()
        with self.state.lock:
            queued={e['event_id'] for e in self.state.events}
            for row in rows:
                if row['event_id'] in queued:continue
                if len(self.state.events)==self.state.events.maxlen:self.state.dropped_events+=1
                self.state.events.append(copy.deepcopy(json.loads(row['event_json'])))
                queued.add(row['event_id'])
                if self.state.logging_status['state']=='durable':self.state.logging_status['state']='pending'

    def flush_outbox(self,pipeline):
        self.enqueue_outbox();pipeline.drain()
        for row in self.repo.pending_media_events():
            if self.repo.event_committed(row['event_id']):self.repo.acknowledge_media_event(row['event_id'])

    def capture(self,request_id,*,plant_id=None,reason='manual',scheduled_at=None,missed=False,schedule_generation=None):
        request_uuid(request_id)
        with self.lock:
            with self.state.lock:experiment_id=self.state.experiment_id
            try:
                if reason=='scheduled':self._check_scheduled_acquisition(schedule_generation,scheduled_at,missed=missed)
                row,created=self.repo.claim_capture(request_id,experiment_id,plant_id,reason,self.state.utc_now().isoformat(),scheduled_at,schedule_generation)
                if not created:
                    if row['status'] not in ('claimed','prepared','indexed'):return dict(status=row['status'],request_id=request_id,indexed=False,error=row['error'])
                    image=self._recover_request(row)
                    return self._response(request_id,image) if image else dict(status='interrupted',request_id=request_id,indexed=False)
                if missed:
                    self.repo.capture_failed(request_id,'missed','Capture slot expired; no catch-up acquisition')
                    self.emit('capture_missed',{'request_id':request_id,'scheduled_at_utc':scheduled_at},experiment_id)
                    return dict(status='missed',request_id=request_id,indexed=False)
                frame=self.camera.read()
                if reason=='scheduled':self._check_scheduled_acquisition(schedule_generation,scheduled_at)
                metadata=inspect_jpeg(frame.jpeg)
                stage_name,final_name=self.names(request_id,frame.captured_at_utc)
                metadata.update(timestamp_utc=utc(frame.captured_at_utc),stage_path=stage_name,file_path=final_name,source='synthetic',frame_sequence=frame.sequence)
                self.repo.prepare_capture(request_id,metadata)
                self._write_stage(self.path(stage_name),frame.jpeg)
                image=self._recover_request(self.repo.capture_request(request_id))
                self.last_error=None
                return self._response(request_id,image)
            except Exception as exc:
                self.last_error=type(exc).__name__
                try:
                    current=self.repo.capture_request(request_id)
                    if current and current['metadata_json']:self.repo.capture_error(request_id,self.last_error)
                    else:self.repo.capture_failed(request_id,'failed',self.last_error)
                except Exception:pass  # Never claim an error record committed if storage also failed.
                self.emit('capture_failed',{'request_id':request_id,'error':self.last_error,'metadata_committed':False},experiment_id)
                raise

    def _response(self,request_id,image):
        image=dict(image,indexed=True,url='/captures/'+image['file_path'],source='synthetic')
        receipt=self.repo.media_receipt(request_id)
        return dict(status='indexed',request_id=request_id,indexed=True,image=image,metadata_committed=True,event_status=receipt['status'] if receipt else 'unknown',event_id=receipt['event_id'] if receipt else None)

    def recover(self):
        with self.lock:
            report=dict(indexed=[],interrupted=[],needs_review=[],orphaned_files=[],scan_truncated=False)
            for row in self.repo.incomplete_captures():
                try:
                    image=self._recover_request(row)
                    report['indexed' if image else 'interrupted'].append(row['request_id'])
                except (ValueError,OSError) as exc:
                    self.repo.capture_failed(row['request_id'],'needs_review',type(exc).__name__)
                    report['needs_review'].append(row['request_id'])
            for count,path in enumerate(p for p in self.root.rglob('*') if p.suffix in ('.jpg','.part')):
                if count>=1000:report['scan_truncated']=True;break
                relative=path.relative_to(self.root).as_posix()
                known=bool(self.repo._rows('SELECT image_id FROM images WHERE file_path=? LIMIT 1',(relative,)))
                if not known:
                    try:
                        candidate=path.stem.removeprefix('capture_')
                        row=self.repo.capture_request(candidate)
                        metadata=json.loads(row['metadata_json']) if row and row['metadata_json'] else {}
                        known=relative in (metadata.get('file_path'),metadata.get('stage_path'))
                    except (ValueError,KeyError):pass
                if not known:report['orphaned_files'].append(relative)
            report['journal_remaining']=self.repo._rows("SELECT COUNT(*) AS count FROM capture_requests WHERE status IN ('claimed','prepared')")[0]['count']
            report['journal_scan_truncated']=report['journal_remaining']>0
            self.recovery_report=report
            self.emit('capture_recovery',report)
            return report

    def configure_schedule(self,enabled,interval_s,anchor_utc):
        with self.schedule_lock:
            self._observe_schedule()
            row=self.repo.set_capture_schedule(enabled,interval_s,anchor_utc)
            row=self._observe_schedule()
            self.emit('capture_schedule_configured',dict(row))
            return row

    def _observe_schedule(self,now=None):
        row=self.repo.observe_capture_clock(now if now is not None else self.state.utc_now().isoformat())
        if row and row['clock_fault']:
            if not self.reported_clock_fault:
                self.emit('capture_clock_fault',dict(state='inhibited',high_water_utc=row['last_observed_utc'],operator_recovery_required=True))
            self.reported_clock_fault=True
        return row

    def _check_scheduled_acquisition(self,generation,scheduled_at,*,missed=False):
        now=self.state.utc_now()
        row=self._observe_schedule(now.isoformat())
        if not row or row['generation']!=generation or capture_schedule_state(row,now.isoformat())!='ready':raise ValueError('Capture scheduling is inhibited or configuration changed')
        due=datetime.fromisoformat(utc(scheduled_at))
        if row['resume_not_before_utc'] and due<datetime.fromisoformat(row['resume_not_before_utc']):raise ValueError('Occurrence precedes recovery boundary')
        anchor=datetime.fromisoformat(row['anchor_utc'])
        expected=anchor+timedelta(seconds=int((now-anchor).total_seconds()//row['interval_s'])*row['interval_s'])
        if due!=expected or (not missed and (now-due).total_seconds()>5):raise ValueError('Scheduled capture slot is no longer eligible')

    def recover_schedule_clock(self):
        with self.schedule_lock:
            self._observe_schedule()
            row=self.repo.recover_capture_clock(self.state.utc_now().isoformat())
            self.scheduling_error=None;self.reported_clock_fault=False
            self.emit('capture_clock_recovered',dict(generation=row['generation'],resume_not_before_utc=row['resume_not_before_utc'],captures_started=False))
            return row

    def scheduler_tick(self):
        if not self.schedule_lock.acquire(blocking=False):return None
        try:
            schedule=self._observe_schedule()
            self.scheduling_error=None
            if not schedule or not schedule['enabled']:return None
            now=self.state.utc_now()
            if capture_schedule_state(schedule,now.isoformat())!='ready':return None
            anchor=datetime.fromisoformat(utc(schedule['anchor_utc']))
            if now<anchor:return None
            with self.state.lock:experiment=self.state.experiment_id
            if experiment is None:return None
            elapsed=(now-anchor).total_seconds()
            due=anchor+timedelta(seconds=int(elapsed//schedule['interval_s'])*schedule['interval_s'])
            if schedule['resume_not_before_utc'] and due<datetime.fromisoformat(schedule['resume_not_before_utc']):return None
            request_id=scheduled_capture_id(schedule['generation'],experiment,due.isoformat())
            return self.capture(request_id,reason='scheduled',scheduled_at=due.isoformat(),missed=(now-due).total_seconds()>5,schedule_generation=schedule['generation'])
        except Exception as exc:
            self.scheduling_error=type(exc).__name__;self.last_error=self.scheduling_error
            self.emit('capture_schedule_failed',{'error':self.last_error});return None
        finally:self.schedule_lock.release()

    def scheduling_snapshot(self):
        schedule=self.repo.capture_schedule()
        return dict(state=capture_schedule_state(schedule,self.state.utc_now().isoformat()) if schedule and schedule['clock_fault'] else ('unavailable' if self.scheduling_error else capture_schedule_state(schedule,self.state.utc_now().isoformat())),
                    inhibited=bool(self.scheduling_error) or capture_schedule_state(schedule,self.state.utc_now().isoformat())!='ready',
                    clock_fault=bool(schedule and schedule['clock_fault']),high_water_utc=schedule['last_observed_utc'] if schedule else None,
                    resume_not_before_utc=schedule['resume_not_before_utc'] if schedule else None,
                    operator_recovery_required=bool(schedule and schedule['clock_fault']),error=self.scheduling_error)

    def snapshot(self):
        with self.state.lock:experiment=self.state.experiment_id
        recent=self.repo.get_recent_images()
        for index,image in enumerate(recent):
            age=(self.state.utc_now()-datetime.fromisoformat(image['timestamp_utc'])).total_seconds()
            image.update(indexed=True,url='/captures/'+image['file_path'],age_seconds=age if age>=0 else None,clock_fault=age<0,file_state='not_checked')
            if index==0:
                try:self.verify(image);image['file_state']='available'
                except Exception:image['file_state']='unavailable_or_corrupt'
            receipt=self.repo.media_receipt(image.get('capture_request_id'))
            image['event_status']=receipt['status'] if receipt else 'unknown'
        schedule=self.repo.capture_schedule()
        scheduling=self.scheduling_snapshot()
        return dict(camera=self.camera.snapshot(),capture_error=self.last_error,requests=self.repo.recent_capture_requests(),
                    recent=recent,schedule=schedule,scheduling=scheduling,recovery=self.recovery_report,
                    plants=self.repo.plants_for_experiment(experiment) if experiment is not None else [],experiment_id=experiment,source='synthetic')
