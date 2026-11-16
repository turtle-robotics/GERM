"""Disposable Task 131 browser server; no worker or physical interface."""
import json
from pathlib import Path
import tempfile
from werkzeug.serving import make_server
from m1_http_harness import app
from m5_fixtures import media_fixture,capture
from services.history_export import HistoryService
from services.control_runtime import install_simulation_gateway

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        clock,state,actuator,gateway,repo,_,camera,media,*_=media_fixture(root)
        install_simulation_gateway(gateway)
        repo._write("INSERT INTO sensors(sensor_id,unit,location,expected_period_s) VALUES('history_fixture','°C','Synthetic history',1)")
        with repo.connection() as db:
            db.execute('BEGIN')
            db.executemany("INSERT INTO sensor_readings(sensor_id,experiment_id,timestamp_utc,value,quality_flag) VALUES('history_fixture',?,'2026-11-15T00:00:00Z',?,'good')",((state.experiment_id,i) for i in range(205)))
            db.execute('COMMIT')
        repo._write('UPDATE experiments SET name=?',('<img src=x onerror=alert(1)> basil β',))
        capture(media,clock);missing=capture(media,clock)
        (root/'images'/missing['file_path']).unlink()  # fixture-only missing-file fault
        service=HistoryService(repo,root/'images',root/'exports',software_version='m6-browser-fixture')
        app.app.config.update(TESTING=True,GERM_SIMULATION=True,GERM_CONTROL_AUTHORIZER=lambda request:True,GERM_HISTORY_SERVICE=service)
        server=make_server('127.0.0.1',0,app.app,threaded=True)
        print(json.dumps({'port':server.server_port,'scope':'HOST SYNTHETIC HISTORY ONLY'}),flush=True)
        try:server.serve_forever()
        finally:server.server_close();service.close()
