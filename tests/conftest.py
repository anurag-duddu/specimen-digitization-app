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
        )
        for name in _PROCESS_LOGGERS
    }
    _remove_process_handler(root)
    try:
        yield
    finally:
        _remove_process_handler(root)
        root.setLevel(level)
        for name, (handlers, propagate) in kept.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.propagate = propagate
