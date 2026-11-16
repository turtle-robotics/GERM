"""Explicit host-only snapshot exports. Own artifacts are retained; no pruning."""
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import stat
import time
import unicodedata
import zipfile
from services.history_repository import HistoryRepository,SOURCES,filters
from services.image_validation import inspect_jpeg,MAX_BYTES
from services.sqlite_repository import canonical
from services.artifact_jobs import ArtifactJobs,ExportBusy


def now():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()


def spreadsheet(value):
    if value is None:return ''
    if not isinstance(value,str):return value
    normalized=unicodedata.normalize('NFKC',value)
    probe=normalized.lstrip()
    while probe and unicodedata.category(probe[0])[0] in ('C','Z'):probe=probe[1:].lstrip()
    return "'"+value if probe.startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


class HistoryService(ArtifactJobs):
    def __init__(self,repository,image_root,export_root,*,software_version,max_rows=200000,max_bytes=256*1024*1024,max_total_bytes=1024*1024*1024,max_jobs=20,max_seconds=60):
        self.history=HistoryRepository(repository);self.images=repository.scoped(image_root)
        root=repository.scoped(export_root)
        if root==self.images or root.is_relative_to(self.images) or self.images.is_relative_to(root):raise ValueError('Separate export and image roots required')
        self.max_rows=max_rows
        super().__init__(repository,root,software_version=software_version,max_bytes=max_bytes,max_total_bytes=max_total_bytes,max_jobs=max_jobs,max_seconds=max_seconds)


    def definition(self,data):
        if not isinstance(data,dict) or set(data)-{'resources','filters','strict_images'}:raise ValueError('Unsupported export definition')
        resources=data.get('resources',list(SOURCES))
        if not isinstance(resources,list) or not resources or len(resources)>len(SOURCES) or any(not isinstance(r,str) or r not in SOURCES for r in resources) or len(set(resources))!=len(resources):raise ValueError('Invalid export resources')
        query=filters(data.get('filters',{}))
        if query.get('sensor') and resources!=['sensors']:raise ValueError('Sensor export filter requires sensors only')
        if type(data.get('strict_images',False)) is not bool:raise ValueError('strict_images must be boolean')
        return dict(resources=sorted(resources),filters=query,strict_images=data.get('strict_images',False))






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
