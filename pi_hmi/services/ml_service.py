"""SO-1/SO-6 ML boundary. The ML team owns model loading and inference.

The camera owner must pass an image ID/path to analyze_image. Return an
inference linked to that image, with UTC time, class, confidence and version.
"""


class MLUnavailable:
    status = "not_configured"

    def __init__(self,error=None):
        self.error=error
        self.status='error' if error else 'not_configured'

    def snapshot(self):return dict(state=self.status,latest_result=None,model=None,error=self.error)

    def get_latest_result(self):
        return None

    def get_model_info(self):
        return None

    def analyze_image(self, image_id, image_path=None, **context):
        raise RuntimeError("ML service is not configured")


ml_service = MLUnavailable()
