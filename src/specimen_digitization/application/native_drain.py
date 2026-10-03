"""The drain's research harness mount.

The drain CLI calls compose_registered_native_drain only when
SPECIMEN_RESEARCH_HARNESS is on. It mounts the production research workflow
over the ordinary chain: a run whose profile names a harness route is
researched at its plan step, and every other step stays ordinary. The live
authority is rebuilt at each research open from the switch, the worker actor's
fresh membership and the run's profile.
"""
from __future__ import annotations

import os

from .workflow import OperationalBlock
from .worker_deadline import current_deadline
from ..research_harness.enablement import research_harness_enabled
from ..research_harness.workflow_bridge import compose_production_research_workflow


class RegisteredNativeDrainWorkflow:
    """The drain's mount: research over the ordinary chain, each step supervised.

    The drain steps every run inside its worker deadline. A step outside one is
    refused before any read or paid effect.
    """
    def __init__(self, workflow):
        self.workflow = workflow

    def __getattr__(self, name):
        return getattr(self.workflow, name)

    def step(self, principal, specimen_id):
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        return self.workflow.step(principal, specimen_id)


def compose_registered_native_drain(ordinary, *, repository, environ=None, actor_uid=None):
    """The ordinary workflow while the switch is off, else the research mount.

    ``environ`` defaults to the process environment. ``actor_uid`` defaults to
    the verified actor context the drain sets from its settings.
    """
    environ = os.environ if environ is None else environ
    if not research_harness_enabled(environ):
        return ordinary
    return RegisteredNativeDrainWorkflow(compose_production_research_workflow(ordinary,
        repository=repository, environ=environ, actor_uid=actor_uid))
