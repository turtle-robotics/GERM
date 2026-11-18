from arduino_serial import send


def send_fan(action):
    """
    action = 'on'  → FAN_ON
    action = 'off' → FAN_OFF
    action = '128' → FAN_SPEED:128   (0-255)
    """
    if action == 'on':
        return send("FAN_ON")
    elif action == 'off':
        return send("FAN_OFF")
    else:
        try:
            speed = int(action)
            speed = max(0, min(255, speed))
            return send(f"FAN_SPEED:{speed}")
        except ValueError:
            print(f"[FAN] Unknown action: {action}")
            return False
