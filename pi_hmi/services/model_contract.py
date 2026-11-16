"""Versioned local-model contract; fixture review is never plant-model approval."""
from dataclasses import dataclass
import hashlib
import re
from services.sqlite_repository import canonical


@dataclass(frozen=True)
class ModelManifest:
    model_id:str
    version:str
    artifact_sha256:str
    labels:tuple
    width:int
    height:int
    fixture_only:bool=True

    def __post_init__(self):
        if any(not isinstance(v,str) or not 1<=len(v)<=128 for v in (self.model_id,self.version)):raise ValueError('Model identity/version required')
        if not re.fullmatch('[a-f0-9]{64}',self.artifact_sha256):raise ValueError('Artifact SHA-256 required')
        if not isinstance(self.labels,tuple) or not 2<=len(self.labels)<=256 or len(set(self.labels))!=len(self.labels) or any(not isinstance(v,str) or not 1<=len(v)<=80 for v in self.labels):raise ValueError('Unique bounded labels required')
        if any(type(v) is not int or v<1 for v in (self.width,self.height)) or self.width*self.height>1_000_000:raise ValueError('Bounded model input dimensions required')
        if self.fixture_only is not True:raise ValueError('No reviewed production model supplied')

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)!={'schema_version','model_id','version','artifact_sha256','labels','input','fixture_only'} or type(value['schema_version']) is not int or value['schema_version']!=1:raise ValueError('Invalid manifest envelope')
        inputs=value['input']
        if set(inputs)!={'width','height','color_mode','dtype','layout','resize'} or any(inputs[k]!=v for k,v in dict(color_mode='RGB',dtype='uint8',layout='HWC',resize='stretch').items()):raise ValueError('Unsupported model input contract')
        return cls(value['model_id'],value['version'],value['artifact_sha256'],tuple(value['labels']),inputs['width'],inputs['height'],value['fixture_only'])

    def as_dict(self):return dict(schema_version=1,model_id=self.model_id,version=self.version,artifact_sha256=self.artifact_sha256,labels=list(self.labels),input=dict(width=self.width,height=self.height,color_mode='RGB',dtype='uint8',layout='HWC',resize='stretch'),fixture_only=self.fixture_only)

    @property
    def digest(self):return hashlib.sha256(canonical(self.as_dict()).encode()).hexdigest()


@dataclass(frozen=True)
class ClassificationPolicy:
    review_ref:str
    normal_labels:tuple=()
    abnormal_labels:tuple=()

    def __post_init__(self):
        if not isinstance(self.review_ref,str) or not self.review_ref.startswith('synthetic-fixture:'):raise ValueError('Only explicit synthetic fixture classification reviews are supported')
        if not isinstance(self.normal_labels,tuple) or not isinstance(self.abnormal_labels,tuple) or set(self.normal_labels)&set(self.abnormal_labels):raise ValueError('Disjoint reviewed label sets required')

    def as_dict(self):return dict(review_ref=self.review_ref,normal_labels=list(self.normal_labels),abnormal_labels=list(self.abnormal_labels),scope='synthetic-contract-only')
