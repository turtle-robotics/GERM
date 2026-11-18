"""SO-1/SO-6 ML boundary. The ML team owns model loading and inference.

The camera owner must pass an image ID/path to analyze_image. Return an
inference linked to that image, with UTC time, class, confidence and version.
"""


class MLUnavailable:
    status = "not_configured"

    def get_latest_result(self):
        return None

    def get_model_info(self):
        return None

    def analyze_image(self, image_id, image_path):
        raise RuntimeError("ML service is not configured")


ml_service = MLUnavailable()
