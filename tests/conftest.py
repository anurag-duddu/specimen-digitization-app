"""Own the caller context for each test without clearing production scopes."""

import logging
import sys

import pytest

from specimen_digitization.application.production import actor_uid

# Loggers that production entry points (or the libraries they start) reconfigure.
_PROCESS_LOGGERS = ("huggingface_hub", "uvicorn", "uvicorn.error", "uvicorn.access")


def _remove_process_handler(root):
    # The handler can only exist once its module has been imported, so a checkout
    # without the module has nothing to remove.
    module = sys.modules.get("specimen_digitization.process_logging")
    if module is None:
        return
    for handler in list(root.handlers):
        if handler.get_name() == module.HANDLER_NAME:
            root.removeHandler(handler)


@pytest.fixture(autouse=True)
def owned_test_actor_context():
    # Legacy adapter fixtures bind an actor for direct repository calls. Their
    # state belongs to this test; the next test inherits its own exact caller.
    # Preserve the prior value and bound/unbound state with the returned token.
    token = actor_uid.set(actor_uid.get())
    try:
        yield
    finally:
        actor_uid.reset(token)


@pytest.fixture(autouse=True)
def owned_process_logging():
    # cli.main() and worker.main() install the process logging handler on the
    # root logger, and uvicorn applies its own logging config. In a single-process
    # run that state would outlive the test that caused it, so every test starts
    # and ends without it. Only the handler this repository installs is removed:
    # pytest's own capture handlers on the root logger are left alone.
    root = logging.getLogger()
    level = root.level
    kept = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            logging.getLogger(name).level,
        )
        for name in _PROCESS_LOGGERS
    }
    _remove_process_handler(root)
    try:
        yield
    finally:
        _remove_process_handler(root)
        root.setLevel(level)
        for name, (handlers, propagate, logger_level) in kept.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.propagate = propagate
            logger.setLevel(logger_level)


# The recovery fixtures whose every save is checked for an unknown-outcome kind
# left on a step that has ended (workflow.end_step; HARNESS.md section 3).
_KIND_CHECKED_MODULES = frozenset({
    "test_extraction_recovery",
    "test_first_pass_stuck_recovery",
    "test_first_pass_transient_recovery",
    "test_first_pass_given_up",
    "test_rate_limit_refusal",
    "test_reader_failures_recoverable",
    "test_reconcile_unknown_outcome",
    "test_lane_drain",
    "test_lane_routes",
    "test_pending_processing_restart",
    "test_camera_intake_worker_journey",
    "test_step_outcome",
    "test_step_failure_logging",
})


@pytest.fixture(autouse=True)
def no_kind_outlives_its_step(request, monkeypatch):
    """A step that has ended cannot have an unresolved unknown outcome: no save
    in the recovery fixtures may keep a kind for a completed step.

    Its limits: it sees only saves through SQLiteRepository (not the SQL Connect
    repository or a test's own stub), only in the modules listed above, and only
    the states those fixtures reach; it checks completed steps, not a kind left
    on a step that has not ended (the per-attempt rules cover those)."""
    if request.module.__name__.rpartition(".")[2] not in _KIND_CHECKED_MODULES:
        yield
        return
    from specimen_digitization.application.storage import SQLiteRepository

    save = SQLiteRepository.save

    def checked(self, principal, specimen, *args, **kwargs):
        run = specimen.run
        kinds = run.dependencies.get("unknown_outcome_kinds", {})
        ended = [key for key in kinds if key.rpartition(":")[0] in run.completed_steps]
        assert not ended, f"unknown-outcome kinds left on ended steps: {ended}"
        return save(self, principal, specimen, *args, **kwargs)

    monkeypatch.setattr(SQLiteRepository, "save", checked)
    yield
