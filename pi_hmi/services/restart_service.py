"""Durable restart checkpoint coordinator; never restores permission or hardware."""
import threading


def durable_fields(state):
    return dict(profile=state.profile,maintenance=state.maintenance,estop_latched=state.estop_latched)


class RestartCoordinator:
    def __init__(self,state,repository):
        self.state,self.repository=state,repository
        self.lock=threading.Lock()
        self.generation=0
        with state.lock:
            state.persistence_enabled=True
            state.persistence_status='loading'
            state.restart_required=True
            state.startup_complete=False
            state.controller=None
            state.controller_at=None
            state.validator.samples.clear()
            state.validator.good.clear()
            state.validator.previous.clear()
            state.validator.failures.clear()
            state.last_command=None
            state.requested_states={name:None for name in state.requested_states}
        try:
            row=repository.load_restart_state()
            with state.lock:
                if row:
                    self.generation=row['generation']
                    state.profile=row['profile']
                    state.maintenance=row['maintenance']
                    state.estop_latched=row['estop_latched']
                state.persisted_fields=durable_fields(state) if row else None
                state.persistence_status='ready' if row else 'dirty'
                state.recovery_verified=bool(row)
                state.emit('restart_recovery',dict(recovered=bool(row),restart_required=True,generation=self.generation,**durable_fields(state)))
        except Exception as exc:
            with state.lock:
                state.maintenance=True
                state.profile=None
                state.persistence_status='error'
                state.emit('restart_recovery_failed',{'error':type(exc).__name__,'restart_required':True})

    def checkpoint(self):
        # Never called under state.lock. A slow writer cannot block safe-stop dispatch.
        with self.lock:
            for _ in range(4):
                with self.state.lock:
                    fields=durable_fields(self.state)
                    if fields==self.state.persisted_fields and self.state.persistence_status=='ready':return True
                try:
                    generation=self.repository.save_restart_state(fields,self.generation)
                except Exception as exc:
                    with self.state.lock:
                        self.state.persistence_status='error'
                        self.state.restart_required=True
                        self.state.emit('restart_checkpoint_failed',{'error':type(exc).__name__})
                    return False
                self.generation=generation
                with self.state.lock:
                    self.state.persisted_fields=fields
                    self.state.persistence_status='ready' if fields==durable_fields(self.state) else 'dirty'
                    self.state.emit('restart_checkpoint',{'generation':generation,'durable':True})
                    if self.state.persistence_status=='ready':return True
            return False


def attach_restart_store(gateway,repository):
    coordinator=RestartCoordinator(gateway.state,repository)
    gateway.restart_store=coordinator
    return coordinator
