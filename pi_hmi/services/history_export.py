"""Explicit host-only snapshot exports. Own artifacts are retained; no pruning."""
from contextlib import closing
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import stat
import threading
import time
import unicodedata
import uuid
import zipfile
from services.history_repository import HistoryRepository,SOURCES,filters
from services.image_validation import inspect_jpeg,MAX_BYTES
from services.media_repository import request_uuid
from services.sqlite_repository import canonical


def now():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()


def spreadsheet(value):
    if value is None:return ''
    if not isinstance(value,str):return value
    normalized=unicodedata.normalize('NFKC',value)
    probe=normalized.lstrip()
    while probe and unicodedata.category(probe[0])[0] in ('C','Z'):probe=probe[1:].lstrip()
    return "'"+value if probe.startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


class ExportBusy(RuntimeError):pass


class HistoryService:
    def __init__(self,repository,image_root,export_root,*,software_version,max_rows=200000,max_bytes=256*1024*1024,max_total_bytes=1024*1024*1024,max_jobs=20,max_seconds=60):
        self.repo=repository;self.history=HistoryRepository(repository)
        self.images=repository.scoped(image_root);self.root=repository.scoped(export_root)
        if self.root==self.images or self.root.is_relative_to(self.images) or self.images.is_relative_to(self.root):raise ValueError('Separate export and image roots required')
        self.root.mkdir(parents=True,exist_ok=True)
        self.version=software_version
        self.max_rows,self.max_bytes,self.max_total_bytes,self.max_jobs,self.max_seconds=max_rows,max_bytes,max_total_bytes,max_jobs,max_seconds
        self.lock=threading.Lock();self.active=False;self.thread=None
        self.owner=repository.scoped(repository.path.with_name(repository.path.name+'.export-owner.lock')).open('a+b')
        try:
            if self.owner.seek(0,2)==0:self.owner.write(b'0');self.owner.flush()
            self.owner.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.owner.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.owner.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.owner.close();raise ExportBusy('Another export service owns this database') from None
        # Startup never declares an interrupted output complete, even if a final
        # file exists. Explicit retry uses a fresh attempt directory, not overwrite.
        try:self.repo._write("UPDATE export_jobs SET status='interrupted',error='Process restart before durable completion',updated_at_utc=? WHERE status IN ('queued','running')",(now(),))
        except Exception:self.close();raise

    def close(self):
        self.wait()
        if self.thread and self.thread.is_alive():raise ExportBusy('Export worker still active; ownership retained')
        if not self.owner.closed:self.owner.close()  # OS releases the advisory ownership lock.

    def definition(self,data):
        if not isinstance(data,dict) or set(data)-{'resources','filters','strict_images'}:raise ValueError('Unsupported export definition')
        resources=data.get('resources',list(SOURCES))
        if not isinstance(resources,list) or not resources or len(resources)>len(SOURCES) or any(not isinstance(r,str) or r not in SOURCES for r in resources) or len(set(resources))!=len(resources):raise ValueError('Invalid export resources')
        query=filters(data.get('filters',{}))
        if query.get('sensor') and resources!=['sensors']:raise ValueError('Sensor export filter requires sensors only')
        if type(data.get('strict_images',False)) is not bool:raise ValueError('strict_images must be boolean')
        return dict(resources=sorted(resources),filters=query,strict_images=data.get('strict_images',False))

    def job(self,request_id):
        rows=self.repo._rows('SELECT * FROM export_jobs WHERE request_id=?',(request_uuid(request_id),))
        if not rows:raise LookupError('Unknown export job')
        row=rows[0]
        row['definition']=json.loads(row.pop('definition_json'));result=row.pop('result_json');row['result']=json.loads(result) if result else None
        row['download_url']='/api/exports/'+request_id+'/download' if row['status'] in ('complete','complete_with_errors') else None
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
            if retry and (not old or old['status'] not in ('failed','interrupted') or old['attempt']>=3):raise ValueError('Retry requires failed/interrupted job with fewer than three attempts')
            if self.active:raise ExportBusy('One export at a time; retry after the active job finishes')
            if self._usage()>=self.max_total_bytes:raise ExportBusy('Export disk quota reached; no deletion performed')
            if not old and self.repo._rows('SELECT COUNT(*) AS n FROM export_jobs')[0]['n']>=self.max_jobs:raise ExportBusy('Export job quota reached; no deletion performed')
            attempt=old['attempt']+1 if old else 1;stamp=now()
            if old:self.repo._write("UPDATE export_jobs SET status='queued',attempt=?,updated_at_utc=?,result_json=NULL,error=NULL WHERE request_id=?",(attempt,stamp,request_id))
            else:self.repo._write("INSERT INTO export_jobs VALUES(?,?,'queued',1,?,?,NULL,NULL)",(request_id,encoded,stamp,stamp))
            self.active=True
            self.thread=threading.Thread(target=self._run,args=(request_id,definition,attempt),daemon=True,name='germ-host-export')
            try:self.thread.start()
            except Exception:
                self.active=False
                self.repo._write("UPDATE export_jobs SET status='interrupted',error='Worker start failed',updated_at_utc=? WHERE request_id=?",(now(),request_id));raise
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

    def _image(self,row):
        relative=row['file_path'];rel=PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts or '\\' in relative or ':' in relative:raise ValueError('Unsafe image path')
        path=self.images/relative
        for part in [path,*path.parents]:
            if part==self.images.parent:break
            if part.is_symlink():raise ValueError('Image symbolic link denied')
        resolved=path.resolve(strict=True)
        if not resolved.is_relative_to(self.images):raise ValueError('Image escapes configured root')
        with resolved.open('rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>MAX_BYTES:raise ValueError('Invalid image file/size')
            data=stream.read(MAX_BYTES+1);after=os.fstat(stream.fileno())
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Image changed during export')
        actual=inspect_jpeg(data)
        if any(actual[k]!=row[k] for k in actual):raise ValueError('Image hash, byte size or dimensions mismatch')
        return data

    def _run(self,request_id,definition,attempt):
        try:
            self.repo._write("UPDATE export_jobs SET status='running',updated_at_utc=? WHERE request_id=?",(now(),request_id))
            result=self._build(request_id,definition,attempt)
            self.repo._write('UPDATE export_jobs SET status=?,result_json=?,updated_at_utc=?,error=NULL WHERE request_id=?',
                             (result['status'],canonical(result),now(),request_id))
        except Exception as exc:
            # If even the failure receipt cannot commit, the durable job stays
            # queued/running and is recovered as interrupted on restart.
            try:self.repo._write("UPDATE export_jobs SET status='failed',updated_at_utc=?,error=? WHERE request_id=?",(now(),type(exc).__name__+': '+str(exc)[:240],request_id))
            except Exception:pass
        finally:
            with self.lock:self.active=False

    def _build(self,request_id,definition,attempt):
        directory=self._safe_artifact(f'{request_id}/attempt-{attempt}');directory.mkdir(parents=True,exist_ok=False)
        deadline=time.monotonic()+self.max_seconds;budget=0;count=0
        usage=self._usage();allowance=min(self.max_bytes,self.max_total_bytes-usage)
        def check(size=0):
            nonlocal budget
            budget+=size
            if budget>allowance:raise OSError('Export byte quota exceeded; files retained')
            if time.monotonic()>deadline:raise TimeoutError('Export deadline exceeded')
        with self.repo.connection() as db:pages=db.execute('PRAGMA page_count').fetchone()[0];page_size=db.execute('PRAGMA page_size').fetchone()[0]
        check(pages*page_size)
        snapshot=self.repo.backup(directory/'snapshot.sqlite')
        check(max(0,snapshot.stat().st_size-pages*page_size))
        history=HistoryRepository(self.repo,snapshot=snapshot);snapshot_at=now()
        manifest=dict(schema='germ-history-export-v1',csv_schema='germ-history-csv-v1',encoding='UTF-8',timestamps='UTC ISO-8601; history_time_utc normalized to microseconds; invalid source time explicitly flagged',
                      software_version=self.version,snapshot_at_utc=snapshot_at,snapshot_sha256=self._file_hash(snapshot),
                      filters=definition['filters'],resources=definition['resources'],csv_formula_policy='prefix apostrophe for dangerous text, including NFKC/leading control variants; typed numerics unchanged; raw JSONL preserved',
                      consistency='All tables and provenance from one verified SQLite backup; JPEG bytes individually verified against that snapshot',tables={},images=[],errors=[],members={})
        with history.connection() as db:
            manifest['sqlite_schema_version']=db.execute('PRAGMA user_version').fetchone()[0]
            manifest['migration_history']=[dict(r) for r in db.execute('SELECT * FROM migration_history ORDER BY version')]
        archive=directory/'archive.part'
        # ZIP_STORED bounds compression CPU; ZIP64 streaming remains enabled.
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as package:
            def add(name,data):
                check(len(data)+256)
                package.writestr(name,data)
                manifest['members'][name]=dict(sha256=sha(data),size_bytes=len(data))
            for resource in definition['resources']:
                check();cursor=None;rows=0;columns=None
                csv_path=directory/(resource+'.csv');raw_path=directory/(resource+'.jsonl')
                with csv_path.open('xb') as csv_file,raw_path.open('xb') as raw_file:
                    for page in history.scan(resource,definition['filters'],deadline=deadline):
                        if columns is None:
                            columns=page['columns'];text=io.StringIO(newline='');csv.writer(text).writerow(columns)
                            data=text.getvalue().encode('utf-8');check(len(data));csv_file.write(data)
                        for row in page['rows']:
                            check();count+=1;rows+=1
                            if count>self.max_rows:raise ValueError('Export row quota exceeded; narrow filters')
                            raw=(canonical(row)+'\n').encode('utf-8');check(len(raw));raw_file.write(raw)
                            text=io.StringIO(newline='');csv.writer(text).writerow([spreadsheet(row.get(k)) for k in columns])
                            data=text.getvalue().encode('utf-8');check(len(data));csv_file.write(data)
                            if resource=='images':
                                image=dict(image_id=row['image_id'],expected_sha256=row['sha256'],expected_size_bytes=row['size_bytes'])
                                try:data=self._image(row)
                                except (OSError,ValueError) as exc:
                                    error=dict(image_id=row['image_id'],expected_sha256=row['sha256'],error=type(exc).__name__+': '+str(exc)[:240])
                                    manifest['errors'].append(error);image['state']='missing_or_corrupt';image['error']=error['error']
                                    if definition['strict_images']:raise ValueError('Strict image export failed: '+error['error']) from exc
                                else:
                                    name=f"images/{row['experiment_id'] or 'unknown'}/{row['image_id']}_{row['sha256']}.jpg"
                                    add(name,data);image.update(state='verified',member=name)
                                manifest['images'].append(image)
                manifest['tables'][resource]=dict(rows=rows,columns=columns)
                for source,name in ((csv_path,'tables/'+resource+'.v1.csv'),(raw_path,'provenance/'+resource+'.jsonl')):
                    check(source.stat().st_size+256)
                    package.write(source,name)
                    manifest['members'][name]=dict(sha256=self._file_hash(source),size_bytes=source.stat().st_size)
            manifest['status']='complete_with_errors' if manifest['errors'] else 'complete'
            add('provenance/dictionaries.json',self._dictionaries(history))
            # The manifest hashes every other member, never itself.
            data=canonical(manifest).encode('utf-8');check(len(data)+512);package.writestr('manifest.json',data)
        with archive.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())
        self._verify_archive(archive,manifest,check)
        final=directory/'archive.zip'
        if os.name=='nt':os.rename(archive,final)
        else:os.link(archive,final)
        if os.name=='posix':
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        return dict(status=manifest['status'],file=final.relative_to(self.root).as_posix(),sha256=self._file_hash(final),size_bytes=final.stat().st_size,
                    snapshot_at_utc=snapshot_at,rows=count,image_errors=manifest['errors'],schema=manifest['schema'])

    @staticmethod
    def _file_hash(path):
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(65536),b''):digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _dictionaries(history):
        with history.connection() as db:
            result={}
            for table in ('sensors','actuators','grow_profiles','model_manifests'):
                rows=[dict(r) for r in db.execute('SELECT * FROM '+table+' LIMIT 10001')]
                if len(rows)>10000:raise ValueError('Dictionary row quota exceeded')
                result[table]=rows
            data=canonical(result).encode('utf-8')
            if len(data)>8*1024*1024:raise ValueError('Dictionary byte quota exceeded')
            return data

    @staticmethod
    def _verify_archive(path,manifest,check=lambda:None):
        with zipfile.ZipFile(path) as package:
            if len(package.namelist())!=len(set(package.namelist())) or set(package.namelist())!=set(manifest['members'])|{'manifest.json'}:raise ValueError('Archive members mismatch')
            if json.loads(package.read('manifest.json'))!=manifest:raise ValueError('Archive manifest mismatch')
            for name,meta in manifest['members'].items():
                rel=PurePosixPath(name)
                if rel.is_absolute() or '..' in rel.parts or '\\' in name:raise ValueError('Unsafe archive member')
                digest=hashlib.sha256();size=0
                with package.open(name) as stream:
                    for block in iter(lambda:stream.read(65536),b''):check();digest.update(block);size+=len(block)
                if digest.hexdigest()!=meta['sha256'] or size!=meta['size_bytes']:raise ValueError('Archive integrity failure')

    def download(self,request_id):
        job=self.job(request_id)
        if job['status'] not in ('complete','complete_with_errors') or not job['result']:raise ValueError('Export has no durable completed receipt')
        result=job['result'];path=self._safe_artifact(result['file'])
        # Read bounded bytes once; the response serves exactly the verified bytes,
        # avoiding a hash-then-reopen race. No arbitrary path is accepted from HTTP.
        if path.stat().st_size>self.max_bytes:raise ValueError('Export exceeds download limit')
        with path.open('rb') as stream:data=stream.read(self.max_bytes+1)
        if len(data)>self.max_bytes:raise ValueError('Export exceeds download limit')
        if len(data)!=result['size_bytes'] or sha(data)!=result['sha256']:raise ValueError('Export artifact missing/corrupt')
        return data,result
