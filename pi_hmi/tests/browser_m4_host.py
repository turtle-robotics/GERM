"""Disposable M4 browser harness: synthetic inputs, temporary database, loopback."""
import json
from pathlib import Path
import tempfile
import threading
from werkzeug.serving import make_server
from m1_http_harness import client_fixture
from services.grow_repository import GrowRepository
from services.grow_service import GrowService
from m4_fixtures import fresh


if __name__=='__main__':
    application,_,_,clock,state,adapter,gateway=client_fixture()
    with tempfile.TemporaryDirectory() as directory:
        repo=GrowRepository(Path(directory)/'browser.sqlite',workspace_root=directory,create=True)
        grow=GrowService(gateway,repo)
        fresh(clock,gateway)
        # Finish the deterministic fixture's startup event backlog before the UI
        # positive path races it. Runtime storage refusals/timeouts stay unchanged.
        assert grow.persistence.tick(), 'Synthetic startup persistence did not become durable'
        stop=threading.Event()
        def worker():
            while not stop.is_set():grow.tick();stop.wait(0.2)
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        server=make_server('127.0.0.1',0,application.app,threaded=True)
        print(json.dumps({'port':server.server_port,'scope':'SYNTHETIC HOST ONLY'}),flush=True)
        try:server.serve_forever()
        finally:stop.set();thread.join(3);server.server_close()
