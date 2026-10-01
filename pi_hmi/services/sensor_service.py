"""Current sensor values with explicit provenance and freshness."""

import time
from datetime import datetime, timezone

from dht11_reader import latest_dht
from sensor_reader import latest_data

FRESH_SECONDS = 10


def reading(value, unit, sampled_at, source):
    if value is None or sampled_at is None:
        return {"value": None, "unit": unit, "timestamp_utc": None,
                "state": "unavailable", "source": source}
    age = max(0, time.time() - sampled_at)
    return {"value": value, "unit": unit,
            "timestamp_utc": datetime.fromtimestamp(sampled_at, timezone.utc).isoformat(),
            "age_seconds": round(age),
            "state": "fresh" if age <= FRESH_SECONDS else "stale",
            "source": source}


def current_readings():
    return {
        "air_temperature": reading(latest_dht["temperature"], "°C",
                                   latest_dht["temperature_at"], "Pi DHT11"),
        "humidity": reading(latest_dht["humidity"], "%RH",
                            latest_dht["humidity_at"], "Pi DHT11"),
        "water_temperature": reading(None, "°C", None, "Not installed"),
        "arduino_a0": reading(latest_data["A0"], "raw",
                              latest_data["A0_at"], "Arduino A0"),
    }
