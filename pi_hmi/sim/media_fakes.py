"""Deterministic, visibly synthetic JPEGs and contract-only inference outputs."""
from datetime import datetime,timezone
import io
from PIL import Image,ImageDraw
from services.camera_adapter import Frame


def synthetic_jpeg(width=320,height=180):
    image=Image.new('RGB',(width,height),(20,45,60))
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,width//3,height),fill=(40,120,90))
    draw.rectangle((width//3,0,2*width//3,height),fill=(90,60,140))
    draw.text((8,8),'SYNTHETIC / HOST TEST',fill='white')
    output=io.BytesIO();image.save(output,format='JPEG',quality=90,optimize=False)
    return output.getvalue()


class SyntheticCamera:
    synthetic=True
    def __init__(self,utc_now=lambda:datetime.now(timezone.utc),jpeg=None):
        self.utc_now=utc_now;self.jpeg=jpeg if jpeg is not None else synthetic_jpeg()
        self.sequence=0;self.available=True;self.timestamp=None;self.reads=0
    def read(self):
        if not self.available:
            from services.camera_adapter import CameraUnavailable
            raise CameraUnavailable('Synthetic camera unavailable')
        self.sequence+=1;self.reads+=1
        return Frame(self.jpeg,self.timestamp or self.utc_now().isoformat(),self.sequence)


class SyntheticInference:
    synthetic=True
    def __init__(self,outputs=None):self.outputs=list(outputs or []);self.calls=0
    def infer(self,inputs):
        self.calls+=1
        if len(inputs['pixels'])!=inputs['width']*inputs['height']*3:raise ValueError('Invalid RGB tensor size')
        if self.outputs:return self.outputs.pop(0)
        return dict(label='fixture_normal',scores={'fixture_normal':0.9,'fixture_abnormal':0.1})
