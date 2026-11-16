"""Current sensor values with explicit provenance and freshness."""

import time
import math
from datetime import datetime, timezone

from dht11_reader import latest_dht
from sensor_reader import latest_data

FRESH_SECONDS = 10


def reading(value, unit, sampled_at, source):
    invalid = (value is not None and (type(value) not in (int, float) or not math.isfinite(value)))
    invalid_time = (sampled_at is not None and (type(sampled_at) not in (int, float) or not math.isfinite(sampled_at)))
    if value is None or sampled_at is None or invalid or invalid_time or sampled_at > time.time():
        return {"value": None, "unit": unit, "timestamp_utc": None,
                "state": "unavailable", "source": source, "quality_flag": "invalid" if invalid or invalid_time or (sampled_at is not None and sampled_at > time.time()) else "missing",
                "fault_reason": "invalid_or_future_sample" if invalid or invalid_time or (sampled_at is not None and sampled_at > time.time()) else "missing"}
    age = max(0, time.time() - sampled_at)
    try:
        timestamp = datetime.fromtimestamp(sampled_at, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return {"value": None, "unit": unit, "timestamp_utc": None, "state": "unavailable",
                "quality_flag": "invalid", "fault_reason": "invalid_timestamp", "source": source}
    return {"value": value, "unit": unit,
            "timestamp_utc": timestamp,
            "age_seconds": round(age),
            "state": "fresh" if age <= FRESH_SECONDS else "stale",
            "quality_flag": "suspect" if age <= FRESH_SECONDS else "stale",
            "fault_reason": "unreviewed_context_only" if age <= FRESH_SECONDS else "stale",
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
