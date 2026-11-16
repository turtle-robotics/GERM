"""Disposable SQLite + normalized synthetic inputs, never crop recommendations."""
from pathlib import Path
from services.grow_repository import GrowRepository
from services.grow_service import GrowService
from m1_fixtures import fixture,feed

PUMP=dict(target='pump',enabled=True,interval_s=60)
LIGHT=dict(target='lighting',enabled=True,start_utc='00:00',end_utc='01:00',rgb=[10,20,30])


def fresh(clock,gateway):
    for _ in range(2):clock.advance(0.1);feed(gateway)
    gateway.state.complete_startup()


def grow_fixture(root,*,configure=True):
    clock,state,adapter,gateway=fixture(started=False)
    repo=GrowRepository(Path(root)/'grow.sqlite',workspace_root=root,create=True)
    grow=GrowService(gateway,repo)
    fresh(clock,gateway)
    if configure:
        grow.create_cycle('basil','Synthetic cycle',gateway.operator_authority)
        grow.configure([PUMP,LIGHT],gateway.operator_authority)
    adapter.commands.clear()
    return clock,state,adapter,gateway,repo,grow


def workflow(grow,action):
    gateway=grow.gateway
    prepared=gateway.prepare(gateway.intent(action),gateway.operator_authority)
    if not prepared['allowed']:return prepared
    return grow.workflow(action,dict(expected_state_revision=prepared['state_revision'],confirmation_id=prepared.get('confirmation_id')),gateway.operator_authority)
