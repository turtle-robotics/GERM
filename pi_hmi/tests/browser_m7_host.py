"""Disposable storage HMI server. Stdin only injects owned synthetic faults."""
import json
from pathlib import Path
import shutil
import tempfile
import threading
from werkzeug.serving import make_server
from m1_http_harness import app
from m5_fixtures import media_fixture,capture
from services.control_runtime import install_simulation_gateway
from services.history_export import HistoryService
from services.storage_service import StorageService

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);clock,state,actuator,gateway,repo,_,camera,media,*_=media_fixture(root)
        install_simulation_gateway(gateway);image=capture(media,clock)
        history=HistoryService(repo,root/'images',root/'exports',software_version='m7-browser-fixture')
        storage=StorageService(history,root/'storage',software_version='m7-browser-fixture')
        app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True,GERM_HISTORY_SERVICE=history,GERM_STORAGE_SERVICE=storage)
        def faults():
            import sys
            for line in sys.stdin:
                data=json.loads(line)
                if data.get('fault')=='disk_full':storage._space=lambda required:(_ for _ in ()).throw(OSError('Injected insufficient free space; no deletion'))
                if data.get('fault')=='missing_image':(root/'images'/image['file_path']).unlink()
        threading.Thread(target=faults,daemon=True).start()
        server=make_server('127.0.0.1',0,app.app,threaded=True)
        print(json.dumps({'port':server.server_port,'scope':'SYNTHETIC HOST STORAGE ONLY'}),flush=True)
        try:server.serve_forever()
        finally:server.server_close();storage.close();history.close()
