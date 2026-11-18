"""Main's approval tests (test_approval_and_research.py) run again with the fields' second opinion on:
the derived marks on (USES_SECOND_OPINION, tests/conftest.py) and the step mounted on every workflow,
answering with an opinion that agrees with every value it is asked about. Every assertion is main's,
unchanged: an approval is the person's (the G51 ruling: no second-opinion code once a person
approved), and a record the opinion agrees with clears as on main. test_approval_and_research.py itself
runs them with the step off."""

from __future__ import annotations

import pytest
from test_approval_and_research import *  # noqa: F403 - the same tests, collected again here

from specimen_digitization.application.workflow import Workflow
from specimen_digitization.field_research import second_opinion as so

USES_SECOND_OPINION = True


@pytest.fixture(autouse=True)
def an_agreeing_second_opinion(monkeypatch):
    def agree(run, **kwargs):
        fields = {key: {"compared": so.shown(value), "value": so.shown(value), "evidence": "", "verdict": so.AGREES_VERDICT}
            for key in so.JUDGED if so._settled(value := run.fields.get(key))}
        return so.Result(so.OBTAINED, fields=fields, answer={}, labels={}, requests=1, spent=0)

    monkeypatch.setattr(Workflow, "second_opinion", so.SecondOpinionStep(model_factory=lambda: None))
    monkeypatch.setattr(so, "obtain", agree)
    yield
