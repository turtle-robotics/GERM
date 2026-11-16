"""Opt-in synthetic host launcher. No production install or network exposure."""
import argparse
from pathlib import Path
from werkzeug.serving import make_server
from services.host_lifecycle import HostLifecycle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--create',action='store_true',help='Initialize a new marked synthetic workspace; never adopt/replace an existing DB')
    parser.add_argument('--port',type=int,default=5055)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Use an unprivileged loopback port 1024–65535')
    if args.create:args.workspace.mkdir(parents=True,exist_ok=True)
    import app
    host=HostLifecycle(args.workspace,create=args.create);host.bind(app.app);host.start()
    # GERM_CONTROL_AUTHORIZER stays None: launcher never enables POST controls.
    server=make_server('127.0.0.1',args.port,app.app,threaded=True)
    print('Synthetic host only at http://127.0.0.1:'+str(args.port)+' · no physical devices or POST controls',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();host.stop()

if __name__=='__main__':main()
