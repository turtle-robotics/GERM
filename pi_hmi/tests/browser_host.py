"""Disposable loopback-only synthetic server for browser checks. Never production."""
import json
from werkzeug.serving import make_server
from m1_http_harness import client_fixture

if __name__ == '__main__':
    application, *_ = client_fixture()
    server = make_server('127.0.0.1', 0, application.app, threaded=True)
    print(json.dumps({'port': server.server_port, 'scope': 'SYNTHETIC HOST ONLY'}), flush=True)
    server.serve_forever()
