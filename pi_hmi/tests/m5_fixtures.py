"""Explicit synthetic media/model fixtures; no plant model or accuracy claim."""
import hashlib
from pathlib import Path
import uuid
from m1_fixtures import fixture
from m4_fixtures import fresh
from services.grow_service import GrowService
from services.media_repository import MediaRepository
from services.camera_adapter import CameraOwner
from services.model_contract import ModelManifest,ClassificationPolicy
from services.local_ml_service import LocalMLService
from services.media_runtime import MediaRuntime
from sim.media_fakes import SyntheticCamera,SyntheticInference


def media_fixture(root,*,reviewed=True,timeout_s=1,outputs=None,model=True):
    root=Path(root)
    clock,state,actuator,gateway=fixture(started=False)
    repo=MediaRepository(root/'germ.sqlite',workspace_root=root,create=True)
    grow=GrowService(gateway,repo);fresh(clock,gateway)
    grow.create_cycle('basil','Synthetic media experiment',gateway.operator_authority)
    experiment=state.experiment_id
    repo._write('INSERT INTO plants(experiment_id,position,species) VALUES(?,1,?)',(experiment,'synthetic fixture plant'))
    adapter=SyntheticCamera(clock.utc)
    owner=CameraOwner(adapter,utc_now=clock.utc)
    artifact=root/'fixture-contract.txt';artifact.write_bytes(b'SYNTHETIC CONTRACT ADAPTER; NOT PLANT MODEL WEIGHTS\n')
    manifest=ModelManifest('synthetic-contract','fixture-1',hashlib.sha256(artifact.read_bytes()).hexdigest(),('fixture_normal','fixture_abnormal'),32,24)
    policy=ClassificationPolicy('synthetic-fixture:classification-v1',('fixture_normal',),('fixture_abnormal',)) if reviewed else None
    inference=SyntheticInference(outputs)
    factory=lambda captures:LocalMLService(captures,inference,manifest,artifact,policy=policy,timeout_s=timeout_s)
    media=MediaRuntime(gateway,repo,owner,root/'images',factory if model else None)
    actuator.commands.clear()
    return clock,state,actuator,gateway,repo,grow,adapter,media,inference,manifest,artifact


def capture(media,clock,*,plant_id=None):
    clock.advance(0.1)
    return media.captures.capture(str(uuid.uuid4()),plant_id=plant_id)['image']


def scores(label,confidence=0.9):
    other='fixture_normal' if label=='fixture_abnormal' else 'fixture_abnormal'
    return dict(label=label,scores={label:confidence,other:1-confidence})
