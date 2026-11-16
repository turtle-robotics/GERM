"""Bounded single-flight local inference. Late workers cannot commit results."""
from datetime import datetime
import hashlib
import io
import math
from pathlib import Path
import threading
import time
import uuid
from PIL import Image
from services.sqlite_repository import canonical
from services.model_contract import ModelManifest,ClassificationPolicy
from services.media_repository import request_uuid


class LocalMLService:
    def __init__(self,captures,adapter,manifest,artifact_path,*,policy=None,timeout_s=1.0):
        if getattr(adapter,'synthetic',False) is not True:raise ValueError('Only explicit synthetic inference adapters are authorized')
        if getattr(adapter,'_germ_ml_owner',None) is not None:raise ValueError('Inference adapter already has an owner')
        if not isinstance(manifest,ModelManifest):raise ValueError('Validated manifest required')
        if policy is not None and not isinstance(policy,ClassificationPolicy):raise ValueError('Reviewed classification policy required')
        if policy and not set(policy.normal_labels+policy.abnormal_labels)<=set(manifest.labels):raise ValueError('Reviewed labels must exist in manifest')
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:raise ValueError('Bounded inference timeout required')
        self.captures,self.repo,self.state=captures,captures.repo,captures.state
        self.adapter,self.manifest,self.policy=adapter,manifest,policy
        self.artifact=self.repo.scoped(artifact_path);self.timeout=timeout_s
        self.lock=threading.Lock();self.worker=None;self.status='ready';self.last_error=None
        self._verify_artifact();self.repo.register_model(manifest)
        adapter._germ_ml_owner=self
        interrupted=self.repo.recover_ml_jobs()
        if interrupted:captures.emit('ml_recovery',{'interrupted_jobs':interrupted,'rerun':False})

    def _verify_artifact(self):
        self.repo.scoped(self.artifact)
        if not self.artifact.is_file() or self.artifact.stat().st_size>250*1024*1024:raise ValueError('Bounded local artifact required')
        digest=hashlib.sha256()
        with self.artifact.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=self.manifest.artifact_sha256:raise ValueError('Model artifact hash mismatch')

    def get_model_info(self):return dict(self.manifest.as_dict(),manifest_sha256=self.manifest.digest,scope='synthetic-contract-only',classification_review=self.policy.review_ref if self.policy else 'unreviewed')

    def _input(self,image_id):
        data=self.captures.image_bytes(image_id)
        with Image.open(io.BytesIO(data)) as image:
            pixels=image.convert('RGB').resize((self.manifest.width,self.manifest.height),Image.Resampling.BILINEAR).tobytes()
        return dict(pixels=pixels,width=self.manifest.width,height=self.manifest.height,color_mode='RGB',dtype='uint8',layout='HWC')

    def analyze_image(self,image_id,image_path=None,*,request_id=None):
        # image_path is accepted for old interface compatibility but never trusted for file access.
        image=self.repo.image(image_id)
        if image.get('source')!='synthetic':raise ValueError('Host inference requires explicitly synthetic image provenance')
        policy=self.policy.as_dict() if self.policy else dict(scope='unreviewed',normal_labels=[],abnormal_labels=[])
        policy_json=canonical(policy);policy_sha=hashlib.sha256(policy_json.encode()).hexdigest()
        request_id=request_uuid(request_id) if request_id is not None else str(uuid.uuid5(uuid.NAMESPACE_URL,'ml:'+str(image_id)+':'+self.manifest.digest+':'+policy_sha))
        if not self.lock.acquire(blocking=False):return dict(state='busy',committed=False,error='Inference already in flight')
        try:
            if self.worker is not None and self.worker.is_alive():return dict(state='busy',committed=False,error='Timed-out adapter has not returned')
            job,created=self.repo.claim_ml_job(request_id,image_id,self.manifest.digest,policy_json,policy_sha,self.state.utc_now().isoformat())
            if not created:
                result=self.repo.inference_for_job(job['request_id'])
                return dict(state=job['status'],committed=job['status']=='completed',request_id=job['request_id'],result=result,error=job['error'])
            started=time.monotonic();self.status='running';self.last_error=None
            try:
                self._verify_artifact();inputs=self._input(image_id)
                completed=threading.Event();box={}
                def infer():
                    try:box['output']=self.adapter.infer(inputs)
                    except Exception as exc:box['error']=type(exc).__name__
                    finally:completed.set()
                self.worker=threading.Thread(target=infer,daemon=True);self.worker.start()
                if not completed.wait(self.timeout):
                    self.repo.fail_ml_job(request_id,'timed_out','Adapter exceeded host timeout; late result is discarded')
                    self.status='timed_out';self.last_error='inference_timeout'
                    self.captures.emit('ml_failed',{'request_id':request_id,'image_id':image_id,'error':self.last_error},image['experiment_id'])
                    return dict(state='timed_out',request_id=request_id,committed=False,error=self.last_error)
                if 'error' in box:raise RuntimeError(box['error'])
                output=box['output']
                if not isinstance(output,dict) or set(output)!={'label','scores'}:raise ValueError('Expected label + complete probability vector')
                scores=output['scores']
                if not isinstance(scores,dict) or set(scores)!=set(self.manifest.labels) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in scores.values()) or abs(sum(scores.values())-1)>1e-6:raise ValueError('Invalid inference scores')
                label=output['label']
                if label not in scores or scores[label]!=max(scores.values()):raise ValueError('Label does not match maximum score')
                confidence=scores[label]
                assessment='uncertain'
                if confidence>=0.70 and self.policy:
                    if label in self.policy.normal_labels:assessment='normal'
                    elif label in self.policy.abnormal_labels:assessment='abnormal'
                result=dict(timestamp_utc=self.state.utc_now().isoformat(),raw_label=label,scores=scores,confidence=confidence,
                    assessment=assessment,predicted_class=label if assessment!='uncertain' else 'uncertain',review_required=assessment=='uncertain',
                    model_version=self.manifest.version,inference_ms=(time.monotonic()-started)*1000)
                durable=self.repo.commit_inference(job,result,software_version=self.state.software_version)
                self.status='ready'
                self.captures.enqueue_outbox()
                return dict(state='completed',request_id=request_id,committed=True,result=durable,event_status='pending')
            except Exception as exc:
                self.status='error';self.last_error=type(exc).__name__
                try:self.repo.fail_ml_job(request_id,'error',self.last_error)
                except Exception:pass
                self.captures.emit('ml_failed',{'request_id':request_id,'image_id':image_id,'error':self.last_error,'result_committed':False},image['experiment_id'])
                return dict(state='error',request_id=request_id,committed=False,error=self.last_error)
        except Exception as exc:
            self.status='error';self.last_error=type(exc).__name__
            self.captures.emit('ml_failed',{'request_id':request_id,'image_id':image_id,'error':self.last_error,'result_committed':False},image['experiment_id'])
            return dict(state='error',request_id=request_id,committed=False,error=self.last_error)
        finally:self.lock.release()

    def get_latest_result(self):
        result=self.repo.latest_inference()
        if result:
            age=(self.state.utc_now()-datetime.fromisoformat(result['image_timestamp_utc'])).total_seconds()
            result['age_seconds']=age if age>=0 else None
            result['clock_fault']=age<0
            result['stale']=age<0 or age>=300
            result['historical_model']=result['manifest_sha256']!=self.manifest.digest
            policy=self.policy.as_dict() if self.policy else dict(scope='unreviewed',normal_labels=[],abnormal_labels=[])
            result['historical_policy']=result['policy_sha256']!=hashlib.sha256(canonical(policy).encode()).hexdigest()
            result['stale']=result['stale'] or result['historical_model'] or result['historical_policy']
            receipt=self.repo.media_receipt(result['request_id'])
            result['event_status']=receipt['status'] if receipt else 'unknown'
        return result

    def snapshot(self):return dict(state=self.status,latest_result=self.get_latest_result(),model=self.get_model_info(),error=self.last_error,scope='synthetic-contract-only')
