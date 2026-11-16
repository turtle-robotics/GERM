"""Shared M6/M7 retained artifact job journal; no gateway or hardware dependency."""
from datetime import datetime,timezone
import hashlib,json,os,threading
from pathlib import PurePosixPath
from services.media_repository import request_uuid
from services.sqlite_repository import canonical
from services.file_lease import FileLease

def now():return datetime.now(timezone.utc).isoformat()
class ExportBusy(RuntimeError):pass

class ArtifactJobs:
    def __init__(self,repository,root,*,software_version,table='export_jobs',url='/api/exports',max_bytes=256*1024*1024,max_total_bytes=1024*1024*1024,max_jobs=20,max_seconds=60):
        if table not in ('export_jobs','storage_jobs'):raise ValueError('Unknown artifact journal')
        self.repo=repository;self.root=repository.scoped(root);self.root.mkdir(parents=True,exist_ok=True)
        self.version,self.table,self.url=software_version,table,url
        self.max_bytes,self.max_total_bytes,self.max_jobs,self.max_seconds=max_bytes,max_total_bytes,max_jobs,max_seconds
        self.retry_states=('failed','interrupted') if table=='export_jobs' else ('failed','interrupted','incomplete')
        self.lock=threading.Lock();self.active=False;self.thread=None
        suffix='export-owner.lock' if table=='export_jobs' else 'storage-owner.lock'
        try:
            self.owner=FileLease(repository.scoped(repository.path.with_name(repository.path.name+'.'+suffix)))
        except Exception:raise ExportBusy('Another artifact service owns this journal') from None
        try:self.repo._write(f"UPDATE {self.table} SET status='interrupted',error='Process restart before durable completion',updated_at_utc=? WHERE status IN ('queued','running')",(now(),))
        except Exception:self.close();raise

    def close(self):
        self.wait()
        if self.thread and self.thread.is_alive():raise ExportBusy('Export worker still active; ownership retained')
        if not self.owner.closed:self.owner.close()  # OS releases the advisory ownership lock.

    def job(self,request_id):
        rows=self.repo._rows(f'SELECT * FROM {self.table} WHERE request_id=?',(request_uuid(request_id),))
        if not rows:raise LookupError('Unknown export job')
        row=rows[0]
        row['definition']=json.loads(row.pop('definition_json'));result=row.pop('result_json');row['result']=json.loads(result) if result else None
        row['download_url']=self.url+'/'+request_id+'/download' if row['status'] in ('complete','complete_with_errors') else None
        return row

    def _usage(self):
        size=0
        for count,path in enumerate(self.root.rglob('*')):
            if count>=10000:raise ExportBusy('Artifact count quota reached; no deletion performed')
            if path.is_symlink():raise ValueError('Export root contains a symbolic link')
            if path.is_file():size+=path.stat().st_size
        return size

    def start(self,request_id,data,*,retry=False):
        if self.owner.closed:raise ExportBusy('Export service is closed')
        request_uuid(request_id);definition=self.definition(data);encoded=canonical(definition)
        with self.lock:
            try:old=self.job(request_id)
            except LookupError:old=None
            if old and canonical(old['definition'])!=encoded:raise ValueError('Export request identity/content conflict')
            if old and not retry:return old
            if retry and (not old or old['status'] not in self.retry_states or old['attempt']>=3):raise ValueError('Retry requires failed/interrupted job with fewer than three attempts')
            if self.active:raise ExportBusy('One export at a time; retry after the active job finishes')
            if self._usage()>=self.max_total_bytes:raise ExportBusy('Export disk quota reached; no deletion performed')
            if not old and self.repo._rows(f'SELECT COUNT(*) AS n FROM {self.table}')[0]['n']>=self.max_jobs:raise ExportBusy('Export job quota reached; no deletion performed')
            attempt=old['attempt']+1 if old else 1;stamp=now()
            if old:self.repo._write(f"UPDATE {self.table} SET status='queued',attempt=?,updated_at_utc=?,result_json=NULL,error=NULL WHERE request_id=?",(attempt,stamp,request_id))
            else:self.repo._write(f"INSERT INTO {self.table} VALUES(?,?,'queued',1,?,?,NULL,NULL)",(request_id,encoded,stamp,stamp))
            self.active=True
            self.thread=threading.Thread(target=self._run,args=(request_id,definition,attempt),daemon=True,name='germ-host-export')
            try:self.thread.start()
            except Exception:
                self.active=False
                self.repo._write(f"UPDATE {self.table} SET status='interrupted',error='Worker start failed',updated_at_utc=? WHERE request_id=?",(now(),request_id));raise
        return self.job(request_id)

    def wait(self,timeout=65):
        if self.thread:self.thread.join(timeout)

    def _safe_artifact(self,relative):
        rel=PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts or '\\' in relative or ':' in relative:raise ValueError('Unsafe artifact path')
        path=self.root/relative
        for part in [path,*path.parents]:
            if part==self.root.parent:break
            if part.is_symlink():raise ValueError('Artifact symbolic link denied')
        resolved=path.resolve()
        if not resolved.is_relative_to(self.root):raise ValueError('Artifact escapes export root')
        return resolved

    def _run(self,request_id,definition,attempt):
        try:
            self.repo._write(f"UPDATE {self.table} SET status='running',updated_at_utc=? WHERE request_id=?",(now(),request_id))
            result=self._build(request_id,definition,attempt)
            self.repo._write(f'UPDATE {self.table} SET status=?,result_json=?,updated_at_utc=?,error=NULL WHERE request_id=?',
                             (result['status'],canonical(result),now(),request_id))
        except Exception as exc:
            # If even the failure receipt cannot commit, the durable job stays
            # queued/running and is recovered as interrupted on restart.
            try:self.repo._write(f"UPDATE {self.table} SET status='failed',updated_at_utc=?,error=? WHERE request_id=?",(now(),type(exc).__name__+': '+str(exc)[:240],request_id))
            except Exception:pass
        finally:
            with self.lock:self.active=False

    @staticmethod
    def _file_hash(path):
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(65536),b''):digest.update(block)
        return digest.hexdigest()

