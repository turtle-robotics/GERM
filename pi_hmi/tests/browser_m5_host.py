"""Disposable full M5 host harness; stdin is a test-only fault channel."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from werkzeug.serving import make_server
from m1_http_harness import app
from m5_fixtures import media_fixture,scores
from m1_fixtures import feed
from services.control_runtime import install_simulation_gateway
from services.ml_service import MLUnavailable


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        clock,state,actuator,gateway,repo,grow,camera,media,adapter,_,_=media_fixture(Path(directory),outputs=[scores('fixture_normal',.6),scores('fixture_abnormal',.9),scores('fixture_abnormal',.9)])
        install_simulation_gateway(gateway)
        original_read=camera.read
        def advancing_frame():
            with state.lock:clock.advance(.01)
            return original_read()
        camera.read=advancing_frame
        app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
        stop=threading.Event()
        def worker():
            while not stop.is_set():
                with state.lock:clock.advance(.2);feed(gateway)
                media.tick();stop.wait(.2)
        def faults():
            from datetime import timedelta
            for line in sys.stdin:
                command=json.loads(line)
                with state.lock:
                    if command.get('camera')=='unavailable':camera.available=False
                    elif command.get('camera')=='stale':camera.timestamp=(clock.utc()-timedelta(seconds=10)).isoformat()
                    elif command.get('camera')=='ready':camera.available=True;camera.timestamp=None
                    if command.get('model')=='unavailable':media.ml=MLUnavailable()
                    if command.get('clock')=='rollback':clock.advance(-2)
        threading.Thread(target=worker,daemon=True).start()
        threading.Thread(target=faults,daemon=True).start()
        server=make_server('127.0.0.1',0,app.app,threaded=True)
        print(json.dumps({'port':server.server_port,'scope':'SYNTHETIC HOST ONLY'}),flush=True)
        try:server.serve_forever()
        finally:stop.set();server.server_close()
