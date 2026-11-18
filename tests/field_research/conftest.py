"""Field research tests that are not about the second opinion run without it.

A FieldResearchStep built without a second-opinion model marks every settled value not checked
(field_research/second_opinion.py): that is the product's behaviour, tested in
test_second_opinion.py. The other tests here are about research itself and were written before the
second opinion; for them a step with no second-opinion model leaves the run as research left it,
so their records clear or wait for their own reasons. A test that gives the step a model still runs
the real second_opinion.check.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def without_a_second_opinion(request, monkeypatch):
    if request.module.__name__.rsplit(".", 1)[-1] == "test_second_opinion":
        yield
        return
    from specimen_digitization.field_research import second_opinion

    real = second_opinion.check

    def check(run, **kwargs):
        return real(run, **kwargs) if kwargs.get("model_factory") is not None else None

    monkeypatch.setattr(second_opinion, "check", check)
    yield
