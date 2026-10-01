"""Manual JPEG capture into the SO-5 image tree; SQL metadata is separate."""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

IMAGE_ROOT = Path(os.environ.get("GERM_IMAGE_ROOT", "/var/lib/germ/images"))


def save_manual_capture(frame):
    now = datetime.now(timezone.utc)
    relative = Path(now.strftime("%Y/%m/%d")) / f"manual_{now:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}.jpg"
    target = IMAGE_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(frame)
    return {"file_path": relative.as_posix(), "timestamp_utc": now.isoformat(),
            "sha256": hashlib.sha256(frame).hexdigest(), "capture_reason": "manual",
            "width_px": 640, "height_px": 480}


def latest_local_manual_capture():
    """Keep the last manual JPEG visible across HMI restarts before SQL is wired."""
    try:
        newest = max(IMAGE_ROOT.rglob("manual_*.jpg"),
                     key=lambda path: path.stat().st_mtime, default=None)
        if newest is None:
            return None
        relative = newest.relative_to(IMAGE_ROOT).as_posix()
        timestamp = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
        return {"file_path": relative, "timestamp_utc": timestamp.isoformat(),
                "url": "/captures/" + relative, "indexed": False, "image_id": None}
    except OSError:
        return None
