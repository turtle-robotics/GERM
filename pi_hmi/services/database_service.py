"""SO-2/SO-3/SO-5 repository boundary for the database team.

Replace `repository` with an implementation of these methods. The HMI never
opens SQLite itself. Timestamps are UTC ISO-8601 strings, sensor units come
from the `sensors` table, and image paths are relative to /var/lib/germ/images.
"""


class DatabaseUnavailable:
    status = "not_configured"

    def get_latest_sensor_values(self):
        return {}

    def get_sensor_history(self, sensor, start_time, end_time, experiment_id=None):
        return []

    def get_active_alerts(self):
        return []

    def get_alert_history(self, limit=50):
        return []

    def acknowledge_alert(self, alert_id):
        return False

    def get_experiments(self):
        return []

    def get_experiment_data(self, experiment_id):
        return None

    def get_recent_images(self, limit=12):
        return []

    def record_image(self, image):
        return None

    def record_actuator_event(self, event):
        return False

    def log_sensor_reading(self, reading):
        return False

    def log_event(self, event):
        return False


repository = DatabaseUnavailable()
