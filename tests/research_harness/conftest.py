"""The research harness suites run one specialist per lease window unless they ask otherwise.

The e2e suites assert the exact order of model calls and publications, the order
of one role per window (publication order inside a window follows field keys, and
two roles' model calls interleave). Production runs ``role_windows.ROLE_CONCURRENCY``
roles per window; ``test_parallel_roles`` runs that shipped window size end to end
and compares it with this one. A module opts out of the pin with
``SHIPPED_WINDOW = True``.
"""
import pytest

from specimen_digitization.research_harness import role_windows


@pytest.fixture(autouse=True)
def one_role_per_window(request, monkeypatch):
    if not getattr(request.module, "SHIPPED_WINDOW", False):
        monkeypatch.setattr(role_windows, "ROLE_CONCURRENCY", 1)
