"""A disposable subprocess intentionally killed by the M9 test; no devices."""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.host_lifecycle import HostLifecycle
from services.sqlite_repository import canonical
root=Path(sys.argv[1]);host=HostLifecycle(root,create=True);assert host.start(background=False)['state']=='running'
host.grow.create_cycle('basil','Retained across deliberate test-process death',host.gateway.operator_authority)
request=str(uuid.uuid4());stamp=host.gateway.state.utc_now().isoformat()
definition=canonical(host.history.definition({}))
host.repo._write("INSERT INTO export_jobs VALUES(?,?,'running',1,?,?,NULL,NULL)",(request,definition,stamp,stamp))
stage=root/'exports'/'interrupted-fixture.part';stage.write_bytes(b'SYNTHETIC INCOMPLETE; NEVER A COMPLETE EXPORT')
print(json.dumps(dict(request_id=request)),flush=True)
while True:time.sleep(.1)
