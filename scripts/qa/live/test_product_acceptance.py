"""Red-first release journey and shared budget regressions; fixtures only."""

import copy

import pytest

from acceptance import CASES, InvalidEvidence, evaluate, skeleton
from test_acceptance import CANDIDATE, MANIFEST_SHA, claimed_live_report, manifest, budget


JOURNEYS = (
    "UI-SIGN-IN",
    "UI-INTAKE",
    "UI-PROCESSING",
    "UI-IMAGE-REGIONS",
    "UI-LITERAL-UNCERTAINTY",
    "UI-SAVE-REOPEN",
    "UI-SEARCH-QUEUE",
    "UI-PROVENANCE-HISTORY",
    "UI-DENIAL-RECOVERY",
    "UI-NO-SYNTHETIC-FALLBACK",
)

def test_each_product_journey_is_required_and_starts_not_run():
    report = skeleton(CANDIDATE, MANIFEST_SHA)
    rows = {row["case_id"]: row for row in report["results"]}
    assert set(JOURNEYS) <= set(CASES)
    assert all(rows[case]["status"] == "not_run" for case in JOURNEYS)
    assert report["budget"] == {}


def test_generic_browser_pass_cannot_replace_individual_journeys(tmp_path):
    report = claimed_live_report(tmp_path)
    report["results"] = [row for row in report["results"] if row["case_id"] not in JOURNEYS]
    with pytest.raises(InvalidEvidence, match="Missing acceptance"):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)


def test_missing_shared_budget_blocks_otherwise_complete_evidence(tmp_path):
    report = claimed_live_report(tmp_path)
    report.pop("budget", None)
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert "COHORT-BUDGET" in result["pending"]
    assert not result["release_accepted"]


@pytest.mark.parametrize("case", JOURNEYS[1:8])
def test_data_journeys_require_all_ten_even_if_one_fails(tmp_path, case):
    report = claimed_live_report(tmp_path)
    row = next((row for row in report["results"] if row["case_id"] == case), None)
    assert row is not None, "Dedicated journey case is absent"
    row["specimen_ids"].pop()
    with pytest.raises(InvalidEvidence, match="Full ten"):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.update(total_limit_microusd=5_000_001),
        lambda b: b.update(daily_limit_microusd=5_000_001),
        lambda b: b.update(scope="per_session"),
        lambda b: b.update(manifest_sha256="e" * 64),
        lambda b: b.update(currency="EUR"),
        lambda b: b["categories"].pop("network"),
        lambda b: b["categories"]["restore"].update(reconciled=False),
        lambda b: b["categories"]["build"].update(artifacts=[]),
        lambda b: b["entries"][0].update(amount_microusd=True),
        lambda b: b["entries"][0].update(amount_microusd=-1),
        lambda b: b["entries"][0].update(amount_microusd=float("nan")),
        lambda b: b["entries"][0].update(state="skipped"),
        lambda b: b["entries"][0].update(day_utc="2026-02-30"),
        lambda b: b["entries"].append(copy.deepcopy(b["entries"][0])),
        lambda b: b["entries"][1].update(amount_microusd=4_000_001),
        lambda b: b["entries"][1].update(day_utc="2026-09-09", amount_microusd=4_000_001),
        lambda b: b["entries"][1].update(state="unknown", amount_microusd=None),
        lambda b: b["entries"][1].update(state="unknown", amount_microusd=0),
        lambda b: b["categories"].pop("identity"),
        lambda b: b["categories"].pop("secrets"),
        lambda b: b["categories"].pop("telemetry"),
    ],
)
def test_budget_cannot_reset_ignore_liabilities_or_omit_cost_classes(tmp_path, mutation):
    report = claimed_live_report(tmp_path)
    report["budget"] = budget(tmp_path)
    mutation(report["budget"])
    with pytest.raises(InvalidEvidence):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)


def test_daily_cap_and_unknown_effect_remain_reserved(tmp_path):
    report = claimed_live_report(tmp_path)
    report["budget"] = budget(tmp_path)
    report["budget"]["daily_limit_microusd"] = 2_000_000
    with pytest.raises(InvalidEvidence):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    report["budget"]["entries"][1].update(day_utc="2026-09-09", state="unknown")
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert result["budget_exposure_microusd"] == 3_000_000
    assert not result["release_accepted"]


@pytest.mark.parametrize("mode", ["fixture", "emulator", "owner_report"])
def test_fixture_budget_never_completes_live_evidence(tmp_path, mode):
    report = claimed_live_report(tmp_path)
    report["budget"] = budget(tmp_path)
    report["budget"]["mode"] = mode
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert "COHORT-BUDGET" in result["pending"]
