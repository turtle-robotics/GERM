"""M7 host storage/backup/offline restore; no actuator or deletion operations."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import sqlite3
import stat
import time
import uuid
import zipfile
from services.artifact_jobs import ArtifactJobs,ExportBusy,now
from services.history_export import HistoryService,sha
from services.media_repository import request_uuid
from services.sqlite_repository import SQLiteRepository,VERSION,canonical,utc


def safe_member(name):
    if not isinstance(name,str) or len(name)>512 or not name or '\\' in name or ':' in name or name.startswith('/') or '\x00' in name:raise ValueError('Unsafe archive path')
    parts=name.split('/')
    for part in parts:
        if not part or part in ('.','..') or part.endswith(('.', ' ')) or any(ord(c)<32 for c in part):raise ValueError('Unsafe archive component')
        if part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:raise ValueError('Reserved archive path')
    return name


def sync_file(path):
    with path.open('r+b') as stream:stream.flush();os.fsync(stream.fileno())


def sync_directory(path):
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


class StorageService(ArtifactJobs):
    def __init__(self,history_service,storage_root,*,software_version,max_images=10000,max_bytes=256*1024*1024,max_total_bytes=1024*1024*1024,max_jobs=20,max_seconds=60,reserve_bytes=1024*1024):
        self.history_service=history_service;repo=history_service.repo
        self.repo=repo;self._assert_root(Path(storage_root))
        self.images=history_service.images;self.exports=history_service.root
        root=repo.scoped(storage_root)
        for other in (self.images,self.exports):
            if root==other or root.is_relative_to(other) or other.is_relative_to(root):raise ValueError('Storage must be disjoint from live images and exports')
        if repo.path.is_relative_to(root):raise ValueError('Storage root cannot contain the live database')
        self.max_images,self.reserve_bytes=max_images,reserve_bytes
        super().__init__(repo,root,software_version=software_version,table='storage_jobs',url='/api/storage/jobs',max_bytes=max_bytes,max_total_bytes=max_total_bytes,max_jobs=max_jobs,max_seconds=max_seconds)

    def definition(self,data):
        if not isinstance(data,dict) or data.get('kind') not in ('backup','verify','preflight','restore'):raise ValueError('Expected backup, verify, preflight or restore kind')
        kind=data['kind']
        if set(data)!=({'kind'} if kind=='backup' else {'kind','backup_id'}):raise ValueError('Unexpected storage job fields; arbitrary restore paths/uploads are not accepted')
        result=dict(kind=kind)
        if kind!='backup':result['backup_id']=request_uuid(data['backup_id'])
        return result

    def job(self,request_id):
        row=super().job(request_id);result=row['result']
        row['download_url']=self.url+'/'+request_id+'/download' if row['definition']['kind']=='backup' and row['status']=='complete' and result and result.get('verified') else None
        return row

    def _scan(self,root):
        result=dict(logical_bytes=0,files=0,observed_at_utc=now(),measurement='observed filesystem logical sizes; not physical allocation',complete=True,errors=[])
        try:
            self._assert_root(root)
            if not root.exists():result['exists']=False;return result
            paths=[root] if root.is_file() else root.rglob('*')
            for count,path in enumerate(paths):
                if count>=10000:result['complete']=False;result['errors'].append('Inventory entry limit reached');break
                try:
                    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Link not traversed')
                    info=path.stat()
                    if stat.S_ISREG(info.st_mode):result['logical_bytes']+=info.st_size;result['files']+=1
                except (OSError,ValueError) as exc:result['errors'].append(type(exc).__name__+': '+str(exc)[:120]);result['complete']=False
        except (OSError,ValueError) as exc:result.update(complete=False,errors=[str(exc)[:160]])
        return result

    def _assert_root(self,path):
        # Recheck ancestors each operation, including Windows junctions.
        path=Path(path)
        for ancestor in [path,*path.parents]:
            if ancestor.is_symlink() or (hasattr(ancestor,'is_junction') and ancestor.is_junction()):raise ValueError('Symbolic links/junctions are denied')
            if ancestor==self.repo.root:break
        if not path.resolve().is_relative_to(self.repo.root):raise ValueError('Path escapes host workspace')

    def _safe_artifact(self,relative):
        safe_member(relative);self._assert_root(self.root)
        path=super()._safe_artifact(relative);self._assert_root(path);return path

    def inventory(self):
        categories={'database':self._scan(self.repo.path),'database_wal':self._scan(Path(str(self.repo.path)+'-wal')),'database_shm':self._scan(Path(str(self.repo.path)+'-shm')),
                    'images':self._scan(self.images),'exports':self._scan(self.exports),'backups':self._scan(self.root/'backups'),
                    'restores':self._scan(self.root/'restores'),'verification_artifacts':self._scan(self.root/'verification')}
        legacy=dict(logical_bytes=0,files=0,observed_at_utc=now(),measurement='observed known M2 pre-upgrade database backup sizes',complete=True,errors=[])
        for count,path in enumerate(self.repo.path.parent.glob(self.repo.path.name+'.before-v*.sqlite')):
            if count>=1000:legacy['complete']=False;legacy['errors'].append('Migration-backup scan limit reached');break
            observed=self._scan(path);legacy['logical_bytes']+=observed['logical_bytes'];legacy['files']+=observed['files']
            if not observed['complete']:legacy['complete']=False;legacy['errors']+=observed['errors']
        categories['migration_backups']=legacy
        errors=[]
        try:
            self._assert_root(self.root);disk=shutil.disk_usage(self.root)
            volume=dict(total_bytes=disk.total,used_bytes=disk.used,free_bytes=disk.free,utilization_percent=round(disk.used/disk.total*100,2) if disk.total else None,
                        observed_at_utc=now(),measurement='observed hosting volume; includes other applications')
        except (OSError,ValueError) as exc:volume=dict(state='unavailable',error=str(exc));errors.append('Volume measurement unavailable')
        try:
            with self.repo.connection() as db:
                db_bytes=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
                image=db.execute('SELECT COUNT(*),COALESCE(SUM(size_bytes),0) FROM images').fetchone()
            estimate=dict(measurement='estimate from DB page count and indexed image byte lengths; does not prove files exist',image_count=image[0],estimated_payload_bytes=db_bytes+image[1],estimated_required_free_bytes=3*(db_bytes+image[1])+self.reserve_bytes)
            jobs=self.repo._rows('SELECT request_id,status,attempt,definition_json,error,updated_at_utc FROM storage_jobs ORDER BY updated_at_utc DESC,request_id DESC LIMIT 20')
            for job in jobs:job['definition']=json.loads(job.pop('definition_json'))
        except Exception:estimate=dict(state='unavailable',measurement='estimate unavailable because database read failed');jobs=[];errors.append('Storage job/database status unavailable')
        partial=errors or any(not item['complete'] for item in categories.values())
        return dict(state='degraded' if partial else 'observed',categories=categories,volume=volume,backup_estimate=estimate,jobs=jobs,errors=errors,
                    capacity_warning=volume.get('utilization_percent',0) is not None and volume.get('utilization_percent',0)>=80,
                    retention=dict(state='unapproved',automatic_deletion=False,policy='Retain all source/history/artifacts. Quotas refuse new work; no cleanup.'),
                    restore_activation_allowed=False)

    def _space(self,required):
        self._assert_root(self.root)
        if shutil.disk_usage(self.root).free<required+self.reserve_bytes:raise OSError('Insufficient free space; no cleanup or deletion performed')

    def _attempt(self,request_id,kind,attempt):
        category='backups' if kind=='backup' else ('restores' if kind=='restore' else 'verification')
        directory=self._safe_artifact(f'{category}/{request_id}/attempt-{attempt}');directory.mkdir(parents=True,exist_ok=False)
        self._write(directory/'ATTEMPT.json',canonical(dict(request_id=request_id,kind=kind,attempt=attempt,state='incomplete_until_durable_receipt',created_at_utc=now())).encode())
        return directory

    @staticmethod
    def _write(path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        sync_directory(path.parent)

    def _build(self,request_id,definition,attempt):
        self._assert_root(self.root);directory=self._attempt(request_id,definition['kind'],attempt)
        deadline=time.monotonic()+self.max_seconds;used=0;allowance=min(self.max_bytes,self.max_total_bytes-self._usage())
        def check(size=0):
            nonlocal used
            used+=size
            if used>allowance:raise OSError('Storage artifact byte quota exceeded; no deletion performed')
            if time.monotonic()>deadline:raise TimeoutError('Storage operation deadline exceeded')
        if definition['kind']=='backup':return self._backup(directory,request_id,attempt,check)
        source=self.job(definition['backup_id'])
        if source['definition']['kind']!='backup' or not source['result'] or 'file' not in source['result']:raise ValueError('Referenced backup has no durable package receipt')
        package=self._safe_artifact(source['result']['file'])
        self._space(package.stat().st_size*3)
        report=self.verify_package(package,directory,expected_sha256=source['result']['sha256'],check=check)
        if definition['kind']=='restore' and report['valid']:
            return self._restore(package,directory,report,definition['backup_id'],check)
        report.update(status='complete' if report['valid'] else 'incomplete',kind=definition['kind'],backup_id=definition['backup_id'],restore_activation_allowed=False)
        encoded=canonical(report).encode();check(len(encoded));self._write(directory/'REPORT.json',encoded);return report

    def _backup(self,directory,request_id,attempt,check):
        with self.repo.connection() as db:
            estimate=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]+db.execute('SELECT COALESCE(SUM(size_bytes),0) FROM images').fetchone()[0]
        self._space(3*estimate);check(estimate)
        snapshot=self.repo.backup(directory/'database.sqlite');SQLiteRepository.validate_snapshot(snapshot)
        with closing(sqlite3.connect(snapshot.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(row) for row in db.execute('SELECT image_id,file_path,timestamp_utc,sha256,size_bytes,width_px,height_px,source FROM images ORDER BY image_id LIMIT ?',(self.max_images+1,))]
            migrations=[dict(row) for row in db.execute('SELECT * FROM migration_history ORDER BY version')]
        if len(rows)>self.max_images:raise ValueError('Backup image count quota exceeded')
        manifest=dict(format='germ-backup-v1',request_id=request_id,attempt=attempt,schema_version=VERSION,software_version=self.version,snapshot_at_utc=now(),
                      timestamp_provenance='SQLite consistent backup completion UTC; image timestamps/provenance from that snapshot',migration_history=migrations,
                      status='complete',members={},images=rows,errors=[],scope='host-only; includes database and indexed JPEGs; source exports/backups are not copied')
        archive=directory/'package.part'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as target:
            check(snapshot.stat().st_size+256);target.write(snapshot,'database.sqlite')
            manifest['members']['database.sqlite']=dict(sha256=self._file_hash(snapshot),size_bytes=snapshot.stat().st_size)
            for row in rows:
                check();name='images/'+safe_member(row['file_path']);row['member']=name
                try:
                    self._assert_root(self.images/row['file_path']);data=self.history_service._image(row)
                    if name.casefold() in {n.casefold() for n in manifest['members']}:raise ValueError('Archive image name collision')
                except (ValueError,OSError) as exc:
                    manifest['errors'].append(dict(image_id=row['image_id'],file_path=row['file_path'],error=type(exc).__name__+': '+str(exc)[:200]));continue
                check(len(data)+256);target.writestr(name,data);manifest['members'][name]=dict(sha256=sha(data),size_bytes=len(data))
            if manifest['errors']:manifest['status']='incomplete'
            encoded=canonical(manifest).encode();check(len(encoded)+1024);target.writestr('manifest.json',encoded)
        sync_file(archive);report=self.verify_package(archive,directory,check=check)
        final=directory/'package.zip'
        if os.name=='nt':os.rename(archive,final)
        else:os.link(archive,final)
        sync_directory(directory)
        result=dict(status='complete' if report['valid'] else 'incomplete',kind='backup',verified=report['valid'],file=final.relative_to(self.root).as_posix(),
                    sha256=self._file_hash(final),size_bytes=final.stat().st_size,report=report,restore_activation_allowed=False)
        encoded=canonical(result).encode();check(len(encoded));self._write(directory/'REPORT.json',encoded);return result

    def verify_package(self,path,directory,*,expected_sha256=None,check=lambda size=0:None):
        report=dict(valid=False,errors=[],verified_at_utc=now(),database_verified=False,images_verified=0)
        try:
            self._assert_root(path)
            if not path.is_file() or path.stat().st_size>self.max_bytes:raise ValueError('Package missing or oversized')
            if expected_sha256 and self._file_hash(path)!=expected_sha256:raise ValueError('Backup archive SHA-256 mismatch')
            with zipfile.ZipFile(path) as package:
                infos=package.infolist()
                if len(infos)>self.max_images+2 or sum(i.file_size for i in infos)>self.max_bytes:raise ValueError('Expanded archive quota exceeded')
                names=[]
                for info in infos:
                    safe_member(info.filename)
                    if info.is_dir() or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise ValueError('Directories, symlinks or encrypted members denied')
                    names.append(info.filename)
                if len(names)!=len(set(n.casefold() for n in names)):raise ValueError('Duplicate/case-colliding archive members')
                if 'manifest.json' not in names or package.getinfo('manifest.json').file_size>8*1024*1024:raise ValueError('Missing/oversized backup manifest')
                manifest=json.loads(package.read('manifest.json'))
                if not isinstance(manifest,dict):raise ValueError('Backup manifest must be an object')
                report['image_errors']=manifest.get('errors',[])
                report['manifest_status']=manifest.get('status')
                if manifest.get('format')!='germ-backup-v1' or manifest.get('schema_version')!=VERSION:raise ValueError('Unsupported backup format or schema')
                utc(manifest['snapshot_at_utc'])
                if not isinstance(manifest.get('software_version'),str) or not manifest['software_version']:raise ValueError('Missing software provenance')
                if manifest.get('status')!='complete' or manifest.get('errors'):raise ValueError('Package is explicitly incomplete')
                if not isinstance(manifest.get('members'),dict) or set(names)!=set(manifest['members'])|{'manifest.json'}:raise ValueError('Package member set inconsistent')
                if 'database.sqlite' not in manifest['members']:raise ValueError('Database member missing')
                for name,meta in manifest['members'].items():
                    check();digest=hashlib.sha256();size=0
                    with package.open(name) as stream:
                        for block in iter(lambda:stream.read(65536),b''):check();digest.update(block);size+=len(block)
                    if digest.hexdigest()!=meta['sha256'] or size!=meta['size_bytes']:raise ValueError('Member checksum/size mismatch: '+name)
                database=directory/('verified-'+uuid.uuid4().hex+'.sqlite')
                self._copy_member(package,'database.sqlite',database,check);SQLiteRepository.validate_snapshot(database)
                report['database_verified']=True
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
                    db.row_factory=sqlite3.Row
                    rows=[dict(r) for r in db.execute('SELECT image_id,file_path,timestamp_utc,sha256,size_bytes,width_px,height_px,source FROM images ORDER BY image_id LIMIT ?',(self.max_images+1,))]
                    migrations=[dict(r) for r in db.execute('SELECT * FROM migration_history ORDER BY version')]
                if len(rows)>self.max_images or migrations!=manifest['migration_history']:raise ValueError('Database/manifest migration or count inconsistency')
                expected=[]
                for row in rows:expected.append(dict(row,member='images/'+safe_member(row['file_path'])))
                if expected!=manifest.get('images'):raise ValueError('Database/image manifest inconsistency')
                if set(manifest['members'])!={'database.sqlite',*[row['member'] for row in expected]}:raise ValueError('Missing/unexpected indexed image files')
                from services.image_validation import inspect_jpeg,MAX_BYTES
                for row in expected:
                    check()
                    if package.getinfo(row['member']).file_size>MAX_BYTES:raise ValueError('Image exceeds decoder limit')
                    data=package.read(row['member']);actual=inspect_jpeg(data)
                    if any(actual[k]!=row[k] for k in actual):raise ValueError('JPEG differs from SQLite metadata')
                    report['images_verified']+=1
                report.update(valid=True,snapshot_at_utc=manifest['snapshot_at_utc'],schema_version=VERSION,software_version=manifest['software_version'],database_file=database.relative_to(self.root).as_posix(),manifest=manifest)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error,zipfile.BadZipFile,RuntimeError) as exc:
            report['errors'].append(type(exc).__name__+': '+str(exc)[:240])
        return report

    def _copy_member(self,package,name,path,check):
        self._assert_root(path);path.parent.mkdir(parents=True,exist_ok=True)
        with package.open(name) as source,path.open('xb') as target:
            for block in iter(lambda:source.read(65536),b''):check(len(block));target.write(block)
            target.flush();os.fsync(target.fileno())
        sync_directory(path.parent)

    def _restore(self,package_path,directory,verification,backup_id,check):
        manifest=verification['manifest'];self._space(sum(m['size_bytes'] for m in manifest['members'].values())*2)
        destination=directory/'offline-restore';destination.mkdir(exist_ok=False)
        # Exclusive files only; no extraction API, no live path supplied by caller.
        with zipfile.ZipFile(package_path) as package:
            for name,meta in manifest['members'].items():
                target=destination/name;self._copy_member(package,name,target,check)
                if self._file_hash(target)!=meta['sha256']:raise ValueError('Restore changed after verification')
        SQLiteRepository.validate_snapshot(destination/'database.sqlite')
        report=dict(status='complete',kind='restore',backup_id=backup_id,verified=True,destination=destination.relative_to(self.root).as_posix(),
                    database_sha256=self._file_hash(destination/'database.sqlite'),images_restored=len(manifest['images']),completed_at_utc=now(),
                    source_snapshot_at_utc=manifest['snapshot_at_utc'],schema_version=VERSION,restore_activation_allowed=False,
                    runtime_attached=False,permissions_restored=False,restart_required=True,
                    recovery_notes=['Offline copy only; no running database/image replacement.',
                                    'Source job receipts and file paths are historical; export/backup archives and orphan/staging images are not included.',
                                    'Runtime adoption requires separate approval and M1/M2/M4 inhibited startup/recovery.'])
        self._write(destination/'RECOVERY_REPORT.json',canonical(report).encode());sync_directory(destination)
        return report

    def download(self,request_id):
        job=self.job(request_id)
        if not job['download_url']:raise ValueError('No durable verified complete backup')
        result=job['result'];path=self._safe_artifact(result['file'])
        if path.stat().st_size>self.max_bytes:raise ValueError('Backup exceeds download quota')
        with path.open('rb') as stream:data=stream.read(self.max_bytes+1)
        if len(data)!=result['size_bytes'] or len(data)>self.max_bytes or sha(data)!=result['sha256']:raise ValueError('Backup file is missing/corrupt')
        return data,result
