"""Own the caller context for each test without clearing production scopes."""

import pytest

from specimen_digitization.application.production import actor_uid


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
