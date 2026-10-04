"""The research harness suites run the shipped window size, except the modules that name one role per window.

Production runs ``role_windows.ROLE_CONCURRENCY`` roles per lease window, so a test of the
production composer runs that, by default. Two kinds of assertion are specific to one role per
window and cannot hold at two: the exact order of model calls (two roles' calls interleave) and the
hold code of a held model effect (one role per window stops at once with
research_worker_custody_requires_reconciliation; with two, the partner finishes and the publication
pass then refuses it with native_publication_requires_reconciliation). Modules asserting those are
listed here (``test_unkeyed_label_review`` is PR 252's) or set ``ONE_ROLE_PER_WINDOW = True``.
"""
import pytest

from specimen_digitization.research_harness import role_windows

ONE_ROLE_PER_WINDOW = frozenset({"test_production_e2e", "test_unkeyed_label_review"})


@pytest.fixture(autouse=True)
def window_size_of_the_module(request, monkeypatch):
    if request.module.__name__ in ONE_ROLE_PER_WINDOW or getattr(request.module, "ONE_ROLE_PER_WINDOW", False):
        monkeypatch.setattr(role_windows, "ROLE_CONCURRENCY", 1)
