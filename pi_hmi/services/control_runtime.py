"""Default runtime is deliberately locked; only explicit injected simulation runs.

No environment variable or HTTP body can enable physical control. Production
authentication/network and electrical boundaries need a separately reviewed adapter.
"""
from services.command_service import AdapterResult, CommandGateway
from services.state_service import StateManager


class UnavailableAdapter:
    simulated = False

    def send(self, command):
        return AdapterResult(False, error='Hardware integration is not authorized')


class SimulatedSerialAdapter:
    simulated = True

    def send(self, command):
        import arduino_serial
        ok = arduino_serial._exchange(command)
        return AdapterResult(ok, arduino_serial.reported_state() if ok else None,
                             arduino_serial.last_error() if not ok else None)


_gateway = CommandGateway(StateManager(), UnavailableAdapter())


def get_gateway():
    return _gateway


def install_simulation_gateway(gateway):
    """Trusted host harness/launcher injection, never an HTTP configuration option."""
    if not getattr(gateway.adapter, 'simulated', False):
        raise ValueError('M1 only permits an injected simulated adapter')
    global _gateway
    _gateway = gateway
