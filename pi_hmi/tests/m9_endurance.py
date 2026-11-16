"""Accelerated synthetic endurance; never claims real 72-hour/physical acceptance."""
from datetime import timedelta
from collections import deque
import argparse,csv,hashlib,io,json,sqlite3,subprocess,sys,tempfile,time,uuid,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from m5_fixtures import media_fixture,scores
from m1_fixtures import feed
from m4_fixtures import workflow
from services.command_service import dispatch_authorized
from services.history_export import HistoryService,sha
from services.storage_service import StorageService
from services.sqlite_repository import SQLiteRepository

def run(hours=72):
    if type(hours) is not int or not 1<=hours<=72:raise ValueError('Bounded 1–72 synthetic hours')
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='germ-m9-endurance-') as directory:
        root=Path(directory)
        clock,state,adapter,gateway,repo,grow,camera,media,inference,*_=media_fixture(root)
        history=HistoryService(repo,root/'images',root/'exports',software_version='m9-synthetic',max_jobs=6,max_total_bytes=32*1024*1024)
        storage=StorageService(history,root/'storage',software_version='m9-synthetic',max_jobs=6,max_total_bytes=32*1024*1024)
        dispatch=[];send=adapter.send;status_polls=0;adapter.commands=deque(maxlen=1024)
        def audited(command):
            nonlocal status_polls
            allowed=dispatch_authorized('command')
            if command!='STATUS':assert allowed,'Actuation bypassed M1 dispatch'
            if command=='STATUS':status_polls+=1
            else:dispatch.append(dict(command=command,gateway_dispatch=allowed,synthetic_second=clock.value))
            return send(command)
        adapter.send=audited
        try:
            grow.configure([dict(target='pump',enabled=True,interval_s=3600),dict(target='lighting',enabled=True,start_utc='00:00',end_utc='16:00',rgb=[1,2,3])],gateway.operator_authority)
            assert workflow(grow,'start')['accepted']
            base=clock.value;anchor=clock.utc()+timedelta(seconds=3600)
            media.captures.configure_schedule(True,3600,anchor.isoformat())
            repo._write("INSERT OR IGNORE INTO sensors(sensor_id,unit,location,expected_period_s) VALUES('m9_synthetic_temperature','degC','SYNTHETIC 5-minute fixture',300)")
            checks=[];jobs=[];image_ids=[]
            def artifact(service,definition):
                request=str(uuid.uuid4());service.start(request,definition);service.wait();job=service.job(request)
                assert job['status']=='complete',job
                data,result=service.download(request);assert sha(data)==result['sha256']
                with zipfile.ZipFile(io.BytesIO(data)) as package:
                    manifest=json.loads(package.read('manifest.json'))
                    for name,meta in manifest['members'].items():assert sha(package.read(name))==meta['sha256']
                    if 'tables' in manifest:
                        for table,meta in manifest['tables'].items():
                            assert len(list(csv.reader(io.StringIO(package.read(table+'.csv').decode('utf-8')))))-1==meta['rows']
                            assert len(package.read(table+'.jsonl').splitlines())==meta['rows']
                jobs.append(dict(request_id=request,kind=definition.get('kind','export'),sha256=result['sha256'],size_bytes=len(data)))
                return request
            for hour in range(1,hours+1):
                for _ in range(3600):clock.advance(1);feed(gateway)
                results=grow.tick()
                assert grow.armed and not state.restart_required,(hour,state.snapshot()['inhibits'])
                assert results and all(r.get('firmware_confirmed') for r in results),(hour,results)
                image=media.captures.scheduler_tick();assert image and image.get('metadata_committed'),image
                image_id=image['image']['image_id'];image_ids.append(image_id)
                again=media.captures.scheduler_tick();assert again['image']['image_id']==image_id
                inference.outputs=[scores('fixture_abnormal' if hour%12 in (1,2) else 'fixture_normal',.60 if hour%12==0 else .90)]
                result=media.ml.analyze_image(image_id);assert result['committed'],result
                # Explicit batched synthetic records, not measured samples or a 300s wall-clock loop.
                with repo.connection() as db:
                    db.execute('BEGIN')
                    db.executemany("INSERT INTO sensor_readings(sensor_id,experiment_id,timestamp_utc,value,quality_flag) VALUES('m9_synthetic_temperature',?,?,24,'good')",
                      ((state.experiment_id,(clock.utc()-timedelta(minutes=5*i)).isoformat()) for i in range(12)))
                    db.execute('COMMIT')
                media.captures.flush_outbox(gateway.event_pipeline);assert grow.persistence.tick()
                assert repo.integrity_check()
                if hour in {max(1,hours//2),hours}:
                    artifact(history,{'strict_images':True})
                    backup=artifact(storage,{'kind':'backup'})
                    restore=str(uuid.uuid4());storage.start(restore,{'kind':'restore','backup_id':backup});storage.wait();job=storage.job(restore)
                    assert job['status']=='complete',job
                    destination=storage.root/job['result']['destination']
                    assert SQLiteRepository.validate_snapshot(destination/'database.sqlite')
                    assert not job['result']['runtime_attached'] and not job['result']['permissions_restored']
                    jobs.append(dict(request_id=restore,kind='isolated_restore',database_verified=True))
                checks.append(dict(hour=hour,images=len(image_ids),armed=grow.armed,integrity='ok',logging=state.snapshot()['logging']['state']))
            assert len(set(image_ids))==hours
            counts={table:repo._rows('SELECT COUNT(*) AS n FROM '+table)[0]['n'] for table in ('images','ml_inferences','sensor_readings','system_events','actuator_events','schedule_runs')}
            fixture_readings=repo._rows("SELECT COUNT(*) AS n FROM sensor_readings WHERE sensor_id='m9_synthetic_temperature'")[0]['n']
            assert counts['images']==hours and counts['ml_inferences']==hours and fixture_readings==hours*12,(counts,fixture_readings)
            assert repo._rows("SELECT COUNT(*) AS n FROM media_outbox WHERE status!='committed'")[0]['n']==0
            assert repo._rows('SELECT COUNT(*) AS n FROM actuator_events WHERE physically_verified!=0')[0]['n']==0
            assert repo._rows('SELECT COUNT(*) AS n FROM actuator_events WHERE firmware_confirmed=1')[0]['n']>=hours
            assert not repo._rows('PRAGMA foreign_key_check')
            usage=sum(p.stat().st_size for p in root.rglob('*') if p.is_file());files=sum(p.is_file() for p in root.rglob('*'))
            assert usage<64*1024*1024 and files<1000,(usage,files)
            return dict(status='PASS',scope='synthetic accelerated host only',simulated_hours=hours,simulated_seconds=hours*3600,
                        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],text=True).strip(),
                        real_elapsed_seconds=time.perf_counter()-started,schedule_tick_seconds=3600,synthetic_input_tick_seconds=1,sensor_record_interval_seconds=300,
                        physical_endurance_accepted=False,real_72_hour_runtime=False,counts=counts,checkpoints=checks,artifacts=jobs,
                        file_count=files,logical_bytes=usage,artifact_limit_bytes=64*1024*1024,gateway_dispatches=dispatch,status_polls=status_polls,
                        synthetic_sensor_records=fixture_readings,missing_synthetic_records=hours*12-fixture_readings,
                        retention_deletion=False,limitations=['Hourly synthetic pump/light schedule; not agronomic settings','Batched sensor fixtures; not real sensor cadence','Fault/restart campaigns are separate from uninterrupted synthetic run'])
        finally:storage.close();history.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--hours',type=int,default=72);parser.add_argument('--output',type=Path,default=Path('build/m9-endurance/RESULTS.json'));args=parser.parse_args()
    result=run(args.hours);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','simulated_hours','real_elapsed_seconds','counts','logical_bytes')}))
