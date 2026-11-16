"""Trusted in-process application injection for host tests only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m1_fixtures import fixture
from services.control_runtime import install_simulation_gateway
import app


def client_fixture(*, firmware_reviewed=False):
    clock, state, adapter, gateway = fixture(firmware_reviewed=firmware_reviewed)
    install_simulation_gateway(gateway)
    app.app.config.update(TESTING=True, GERM_SIMULATION=True, GERM_CONTROL_AUTHORIZER=lambda request: True)
    headers = {'X-GERM-Token': app.control_token}
    return app, app.app.test_client(), headers, clock, state, adapter, gateway


def confirmation(client, headers, action, payload=None):
    response = client.post('/api/confirmations', json={'action': action, 'payload': payload or {}}, headers=headers)
    result = response.get_json()
    return {key: result[key] for key in ('confirmation_id', 'state_revision') if key in result}
