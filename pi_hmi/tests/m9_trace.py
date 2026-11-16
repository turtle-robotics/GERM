"""Bounded instrumentation for disposable test processes only; no HTTP controls."""
from collections import deque
from contextlib import contextmanager
import json,os,threading,time
from pathlib import Path
from flask import g,request
from services.sqlite_repository import SQLiteRepository

def install_trace(host,application):
    target=Path(os.environ['GERM_M9_TRACE']);target.parent.mkdir(parents=True,exist_ok=True)
    lock=threading.Lock();records=deque(maxlen=2048);started=time.perf_counter();sequence=0
    def flush():
        while True:
            time.sleep(.25)
            with lock:snapshot=list(records)
            # Instrumentation must never serialize/write a trace inside a SQLite transaction.
            stage=target.with_suffix('.stage');stage.write_text(json.dumps(snapshot),encoding='utf-8');os.replace(stage,target)
    threading.Thread(target=flush,daemon=True,name='m9-test-trace-writer').start()
    def record(kind,**values):
        nonlocal sequence
        with lock:
            sequence+=1;records.append(dict(sequence=sequence,elapsed_s=time.perf_counter()-started,thread=threading.current_thread().name,kind=kind,**values))
    original=SQLiteRepository.connection
    @contextmanager
    def connection(repo):
        begin=time.perf_counter()
        try:
            with original(repo) as db:
                db.set_trace_callback(lambda sql:record('sqlite',operation=sql.split()[0] if sql.split() else '',repository_state=repo.status))
                yield db
        except Exception as exc:record('sqlite_error',error=type(exc).__name__,message=str(exc)[:180],sqlite_errorcode=getattr(exc,'sqlite_errorcode',None),repository_state=repo.status);raise
        finally:record('sqlite_connection',duration_s=time.perf_counter()-begin,repository_state=repo.status)
    SQLiteRepository.connection=connection
    @application.before_request
    def begin():g.m9_started=time.perf_counter()
    @application.after_request
    def end(response):
        payload=response.get_json(silent=True) if response.is_json else None
        grow=(payload or {}).get('grow',{})
        record('http',method=request.method,path=request.path,status=response.status_code,duration_s=time.perf_counter()-getattr(g,'m9_started',time.perf_counter()),
               grow_state=grow.get('state'),cycle_status=(grow.get('cycle') or {}).get('status'),lifecycle=host.status,
               worker_alive=bool(host.worker and host.worker.is_alive()),heartbeat=host.heartbeat,repository_state=host.repo.status if host.repo else None,
               lifecycle_error=host.error,logging_evidence=host.grow.persistence.last_tick_evidence if host.grow else None,
               response_reasons=(payload or {}).get('reason_codes'),current_state_revision=host.gateway.state.revision)
        return response
    record('trace_started',limit=2048,scope='synthetic host fixture only')
    return record
