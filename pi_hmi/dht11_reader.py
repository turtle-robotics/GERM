import time
import board
import adafruit_dht

# GPIO4 (physical pin 7)
dhtDevice = adafruit_dht.DHT11(board.D4)

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
    global latest_dht
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
