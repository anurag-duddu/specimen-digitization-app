"""Every test of tests/field_research runs twice: with test_step.PATH "old", then "units".

test_step.make_specimen gives the runs it builds that first-pass path (Run.first_pass_path),
so every test that builds its run with test_step.build_rig, directly or through a helper,
runs on each path (docs/execution/units/PLAN.md, WP 1.3: "tests/field_research green on
both paths"). A test that builds its readings or its run another way runs the same both
times. A test whose assertion differs by path takes this fixture's value by its name."""

from __future__ import annotations

import pytest
import test_step


@pytest.fixture(autouse=True, params=["old", "units"])
def first_pass_path(request, monkeypatch):
    monkeypatch.setattr(test_step, "PATH", request.param)
    return request.param
