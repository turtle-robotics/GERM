"""Inventory host HTTP/read boundaries and actuator call sites without I/O adapters."""
import ast,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[2]

def inventory():
    from m1_http_harness import app
    routes=[]
    for rule in app.app.url_map.iter_rules():
        for method in sorted(rule.methods-{'HEAD','OPTIONS'}):
            routes.append(dict(path=str(rule),method=method,endpoint=rule.endpoint,
                boundary='global restricted POST + endpoint validation; production denied' if method=='POST' else 'no identity authentication; read privacy gate unresolved',
                production_access_approved=False))
    sites=[]
    for p in sorted((ROOT/'pi_hmi').rglob('*.py')):
        if any(part in ('tests','sim','.venv','venv','__pycache__') for part in p.relative_to(ROOT/'pi_hmi').parts):continue
        tree=ast.parse(p.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                name=ast.unparse(node.func)
                if name.endswith(('adapter.send','adapter.firmware_update','arduino_serial._exchange','ser.write')):
                    sites.append(dict(path=p.relative_to(ROOT).as_posix(),line=node.lineno,call=name))
    return dict(scope='host source/route inventory, not penetration or physical safety certification',routes=sorted(routes,key=lambda r:(r['path'],r['method'])),
      low_level_call_sites=sites,unchanged_gateway_source_sha256={p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in
      ('pi_hmi/services/command_service.py','pi_hmi/services/state_service.py','pi_hmi/services/control_runtime.py','pi_hmi/arduino_serial.py','pi_hmi/firmware_service.py')},
      gaps=['Anonymous HTTP reads/downloads','No production authentication/roles/Origin/Host policy','No global HTTP rate/concurrency limit','Trusted Python/filesystem not sandboxed','Physical safety and target resource limits unverified'])

if __name__=='__main__':
    target=ROOT/'docs/phase0/M9_HTTP_GATEWAY_AUDIT.json';target.write_text(json.dumps(inventory(),indent=2)+'\n',encoding='utf-8');print('Recorded HTTP methods and low-level gateway call-site inventory')
