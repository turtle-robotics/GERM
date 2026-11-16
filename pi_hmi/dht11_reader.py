import time

# GPIO4 (physical pin 7)
dhtDevice = None  # device initialization is allowed only in an explicit simulation launcher

latest_dht = {
    "temperature": None,
    "humidity": None,
    "temperature_at": None,
    "humidity_at": None,
}


def read_dht():
    """
    Continuously reads the DHT11 sensor.
    Run this in a daemon thread.
    """
    global latest_dht, dhtDevice
    if dhtDevice is None:
        # Never initialize GPIO from import or default application startup.
        return
    while True:
        try:
            temperature = dhtDevice.temperature
            humidity = dhtDevice.humidity
            if temperature is not None:
                latest_dht["temperature"] = temperature
                latest_dht["temperature_at"] = time.time()
            if humidity is not None:
                latest_dht["humidity"] = humidity
                latest_dht["humidity_at"] = time.time()
        except RuntimeError:
            # DHT sensors randomly fail readings — this is normal
            pass
        time.sleep(2)
