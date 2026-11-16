"""Loopback-only real lifecycle fixture; healthy inputs explicitly synthetic."""
import json
from pathlib import Path
import tempfile
import threading
from werkzeug.serving import make_server
from m1_http_harness import app
from m1_fixtures import fixture,feed
from services.host_lifecycle import HostLifecycle
from sim.media_fakes import SyntheticCamera

def factory():
    clock,state,adapter,gateway=fixture(started=False)
    adapter.synthetic_host_only=True;gateway.fixture_clock=clock;return gateway

class Provider:
    synthetic=True
    def __call__(self,gateway):gateway.fixture_clock.advance(.2);feed(gateway)

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        host=HostLifecycle(directory,create=True,gateway_factory=factory,sensor_provider=Provider())
        host.camera_factory=lambda:SyntheticCamera(host.gateway.state.utc_now)
        host.bind(app.app);host.start(background=False)
        host.grow.create_cycle('basil','M8 synthetic offline cycle',host.gateway.operator_authority)
        host.grow.configure([dict(target='lighting',enabled=True,start_utc='00:00',end_utc='23:59',rgb=[1,2,3])],host.gateway.operator_authority)
        host.stop();host.start(background=True)
        from m9_trace import install_trace
        trace=install_trace(host,app.app)
        app.app.config.update(TESTING=True,GERM_CONTROL_AUTHORIZER=lambda request:True)
        def faults():
            import sys,sqlite3
            for line in sys.stdin:
                data=json.loads(line)
                if data.get('fault')=='database':host.repo._rows=lambda *a,**k:(_ for _ in ()).throw(sqlite3.OperationalError('Injected host DB loss'))
                if data.get('fault')=='camera_stale':
                    from datetime import timedelta
                    host.media.captures.camera.adapter.timestamp=(host.gateway.state.utc_now()-timedelta(seconds=10)).isoformat()
        threading.Thread(target=faults,daemon=True).start()
        server=make_server('127.0.0.1',0,app.app,threaded=True)
        print(json.dumps({'port':server.server_port,'scope':'M8 SYNTHETIC OFFLINE HOST ONLY'}),flush=True)
        try:server.serve_forever()
        finally:server.server_close();host.stop()
