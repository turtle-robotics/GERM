from arduino_serial import send


def send_led(r, g, b, w):
    """
    Send RGBW colour values to the Arduino.
    Clamps every channel to 0-255.
    Protocol:  LED:r,g,b,w
    """
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    w = max(0, min(255, int(w)))

    # all zero → explicit OFF
    if r == 0 and g == 0 and b == 0 and w == 0:
        return send("LED_OFF")

    return send(f"LED:{r},{g},{b},{w}")
