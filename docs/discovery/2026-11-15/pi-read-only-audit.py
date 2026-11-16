import json, hashlib, pathlib, urllib.request, urllib.error, subprocess, os
root=pathlib.Path('/home/germ/hmi_flask')
files={}
for p in sorted(root.rglob('*')):
    if any(x in ('venv','.git','__pycache__') for x in p.relative_to(root).parts): continue
    if p.is_file() and p.suffix in ('.py','.ino','.html','.js','.css'):
        files[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
routes={}
for route in ('/','/plant','/trends','/controls','/alerts','/maintenance','/settings','/sensor','/camera.jpg','/api/trends','/api/alerts','/api/experiments','/api/captures'):
    try:
        with urllib.request.urlopen('http://127.0.0.1:5000'+route,timeout=10) as response:
            body=response.read()
            routes[route]={'status':response.status,'bytes':len(body)}
            if route.startswith('/api/') or route=='/sensor': routes[route]['body']=json.loads(body)
    except urllib.error.HTTPError as e: routes[route]={'status':e.code}
    except Exception as e: routes[route]={'error':str(e)}
print(json.dumps({'source_root':str(root),'files_sha256':files,'routes':routes,'storage':{p:{'exists':pathlib.Path(p).exists(),'writable_by_ssh_user':os.access(p,os.W_OK)} for p in ('/var/lib/germ','/var/lib/germ/images','/var/lib/germ/germ.db','/var/lib/germ/models','/var/lib/germ/exports','/etc/germ','/var/log/germ')},'groups':subprocess.run(['id'],capture_output=True,text=True).stdout},indent=2))
