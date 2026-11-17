"""Decode bounded JPEGs; dimensions/hash describe bytes, not camera claims."""
import hashlib
import io
import warnings
from PIL import Image

MAX_BYTES=8*1024*1024
MAX_PIXELS=4_000_000


def inspect_jpeg(data):
    if not isinstance(data,bytes) or not 4<=len(data)<=MAX_BYTES or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('A complete bounded JPEG is required')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data),formats=['JPEG']) as image:
            width,height=image.size
            if width<=0 or height<=0 or width*height>MAX_PIXELS:raise ValueError('Image dimensions exceed host policy')
            image.verify()
        with Image.open(io.BytesIO(data),formats=['JPEG']) as image:image.load()
    return dict(width_px=width,height_px=height,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
