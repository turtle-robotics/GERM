"""No I/O adapter: only synthetic STATUS/OFF acknowledgements, never real devices."""
from services.command_service import AdapterResult,CommandGateway
from services.state_service import StateManager
from collections import deque

class OfflineAdapter:
    simulated=True
    synthetic_host_only=True
    def __init__(self):self.commands=deque(maxlen=1024)  # Bounded transient diagnostics; durable history stays in M3.
    def send(self,command):
        self.commands.append(command)
        if command not in ('STATUS','STOP','PUMP_OFF','FAN_OFF','FAN_SPEED:0','LED_OFF','LED:0,0,0,0','MODE:normal'):
            return AdapterResult(False,error='Offline host adapter does not emulate energizing commands')
        return AdapterResult(True,dict(protocol=2,id=0,pump=False,fan=False,fan_speed=0,rgb=[0,0,0],lighting_mode='normal'))

def offline_gateway():
    return CommandGateway(StateManager(),OfflineAdapter(),safe_commands=('STOP',),firmware_reviewed=False)
