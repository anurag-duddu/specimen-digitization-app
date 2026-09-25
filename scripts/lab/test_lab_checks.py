"""Stage checks score what the app recorded. Fixtures come from the real domain models."""

from specimen_digitization.application.domain import (
    Asset,
    Disposition,
    Observation,
    Region,
    Run,
    Scope,
    Specimen,
    Transcript,
)

import lab_checks

SHA = "a" * 64
SUBJECT = "subject_105526321"
ROUTES = ("handwriting-qwen", "handwriting-muse")
SOURCE = {"sha256": SHA, "object_name": f"microscopic-slides/{SUBJECT}.jpeg"}


def reading(route, region="r1", **changes):
    values = dict(
        id=f"o-{region}-{route}",
        region_id=region,
        route_id=route,
        model_id="model-" + route,
        provider="provider-" + route,
        prompt_version="b" * 64,
        input_sha256="c" * 64,
        literal_text="E. slope Mt. McKinley",
        raw_ref="raw-" + route,
        raw_sha256="d" * 64,
        input_tokens=900,
        output_tokens=200,
    )
    return Observation(**(values | changes))


def snapshot(previous=(), **changes):
    region = Region(
        id="r1", asset_id="asset-1", x=0, y=0, width=570, height=590, order=0,
        method="sam3", version="sam3-http-v1",
    )
    observations = [reading(route) for route in ROUTES]
    run = Run(
        id="run-2",
        regions=[region],
        observations=observations,
        transcripts=[
            Transcript(
                region_id="r1",
                observation_ids=[o.id for o in observations],
                alternatives=[],
                resolved=True,
                text="E. slope Mt. McKinley",
                disagreement_ratio=0.0,
                alignment_algorithm="bounded-levenshtein-fraction-v1",
            )
        ],
        segmentation={"model_id": "facebook/sam3", "model_revision": "3c879f39"},
        stage="finalized",
        disposition=Disposition.REVIEW,
        reasons=["mandatory_unresolved:fmnh_ins_number"],
    ).model_copy(update=changes)
    asset = Asset(
        id="asset-1", sha256=SHA, blob_ref=SHA, media_type="image/jpeg",
        size_bytes=123456, width=1780, height=590, filename=SUBJECT + ".jpeg",
        uploader="synthetic-reviewer",
    )
    return Specimen(
        id="specimen-1",
        scope=Scope(organization_id="org", collection_id="collection"),
        asset=asset,
        run=run,
        previous_runs=list(previous),
    ).model_dump(mode="json")


def statuses(evidence, source=SOURCE):
    return {s["stage"]: s["status"] for s in lab_checks.check_stages(evidence, source, SUBJECT)}


def evidence(snap, rows=None, actions=()):
    return {"snapshot": snap, "rows": rows or {}, "actions": list(actions)}


def test_full_sam_run_scores_every_stage_it_can_see():
    result = statuses(evidence(snapshot()))
    assert result["1"] == result["2"] == result["3"] == "passed"
    assert result["5"] == result["8"] == result["9"] == "passed"
    # Nothing on 709ae3c writes normalized rows, a first pass, tool calls or a trace id.
    assert result["4"] == result["6"] == result["7"] == result["trace"] == "not built"


def test_reviewed_region_is_reported_as_a_substitute_not_a_pass():
    blocked = Run(
        id="run-1", stage="processing_blocked",
        blocker="sam3_serving_contract_not_configured_use_reviewed_regions",
    )
    snap = snapshot(
        previous=[blocked], segmentation={}, stage="processing_blocked",
        blocker="external_outcome_unknown", disposition=None, reasons=[],
        attempts={"parse": 1}, completed_steps=["classify", "segment", "adjudicate"],
    )
    result = lab_checks.check_stages(
        evidence(snap, actions=[{"action": "reviewed_region"}]), SOURCE, SUBJECT
    )
    stage = {s["stage"]: s for s in result}
    assert stage["2"]["status"] == "substituted"
    assert "sam3_serving_contract_not_configured_use_reviewed_regions" in stage["2"]["detail"]
    assert "external_outcome_unknown" not in stage["2"]["detail"]  # the later run's own block
    assert stage["8"]["status"] == "blocked"
    assert stage["8"]["detail"].startswith("external_outcome_unknown at ['parse']")


def test_segmentation_is_judged_against_the_lanes_coverage_check():
    # The lab's boxes are ground truth for G15; a miss fails only when the lane's check let it through.
    two_labels = "subject_105526324"  # locality on the right label, notes on the left
    left = Region(
        id="r1", asset_id="asset-1", x=0, y=0, width=570, height=590, order=0,
        method="sam3", version="sam3-http-v1",
    )
    right = left.model_copy(update={"id": "r2", "x": 1110, "width": 670, "order": 1})
    whole = left.model_copy(update={"id": "r3", "width": 1780})
    caught = {"coverage_check": {"outcome": "failed"}, "coverage_confirmed": False}
    let_through = {"coverage_check": {"outcome": "confirmed"}, "coverage_confirmed": True}

    def stage_2(regions, subject, lane=None):
        snap = snapshot(regions=regions)
        snap["run"].update(lane or {})
        result = lab_checks.check_stages(evidence(snap), SOURCE, subject)
        return next(s for s in result if s["stage"] == "2")

    assert stage_2([left, right], two_labels)["status"] == "passed"
    assert stage_2([left], two_labels, caught)["status"] == "passed"
    assert stage_2([left], two_labels, let_through)["status"] == "failed"
    assert stage_2([left], two_labels)["status"] == "not built"  # no coverage check on this commit
    assert stage_2([whole], two_labels, let_through)["status"] == "failed"  # one region, two labels
    assert "not checked" in stage_2([left], "subject_999")["detail"]
    assert lab_checks.label_boxes(two_labels) == [(0.0, 0.34), (0.62, 1.0)]
    assert lab_checks.label_boxes(SUBJECT) == [(0.0, 0.37)]


def test_stage_8_fails_a_pilot_slide_that_clears():
    # All ten go to needs human review (PLAN 8, G42): a clear is a wrong run for them, not for others.
    cleared = snapshot(disposition=Disposition.CLEARED, reasons=[])
    assert statuses(evidence(cleared))["8"] == "failed"
    other = lab_checks.check_stages(evidence(cleared), SOURCE, "subject_999")
    assert next(s for s in other if s["stage"] == "8")["status"] == "passed"


def test_a_blocked_run_names_its_next_step_and_a_scheduled_retry_is_blocked():
    budget = snapshot(
        stage="processing_blocked", blocker="approved_cost_budget_unavailable", disposition=None,
        reasons=[], observations=[], transcripts=[], attempts={},
        completed_steps=["pin_dependencies", "classify", "quality_check", "segment"],
    )
    stage = {s["stage"]: s for s in lab_checks.check_stages(evidence(budget), SOURCE, SUBJECT)}
    assert stage["8"]["status"] == "blocked"
    assert "transcribe:r1:handwriting-qwen" in stage["8"]["detail"]  # the app's own next step
    waiting = snapshot(stage="retry_scheduled", blocker="provider_rate_limited", disposition=None, reasons=[])
    assert statuses(evidence(waiting))["8"] == "blocked"


def test_two_readings_of_one_route_on_one_region_fail_stage_3():
    doubled = snapshot(observations=[reading(r) for r in ROUTES] + [reading("handwriting-qwen", id="o-2")])
    assert statuses(evidence(doubled))["3"] == "failed"


def test_a_gbif_occurrence_request_fails_the_run_while_d4_is_off():
    # D4 is held: its occurrence check is off and sends nothing (PLAN 2, coordinator rulings).
    snap = snapshot()
    snap["run"]["tool_calls"] = [{"call_key": "k1", "tool": "gbif_occurrence_search", "source": "gbif"}]
    assert statuses(evidence(snap))["7"] == "failed"


def test_stage_4_is_not_built_only_without_run_rows_and_never_passes_an_empty_set():
    other_run = {"pipeline_run": [{"id": "another-run", "specimen_id": "specimen-1"}]}
    assert statuses(evidence(snapshot(), {"specimen_snapshot": [{"id": "x"}]}))["4"] == "not built"
    assert statuses(evidence(snapshot(), other_run))["4"] == "failed"  # readings, but no run row
    unread = snapshot(observations=[], transcripts=[], stage="processing_blocked", blocker="x",
                      disposition=None, reasons=[])
    assert statuses(evidence(unread, other_run))["4"] == "blocked"


def test_a_missing_route_fails_stage_3_and_a_block_is_reported_as_blocked():
    one = snapshot(observations=[reading("handwriting-qwen")])
    assert statuses(evidence(one))["3"] == "failed"
    stuck = snapshot(
        observations=[], transcripts=[], stage="processing_blocked",
        blocker="external_outcome_unknown", disposition=None, reasons=[],
    )
    result = statuses(evidence(stuck))
    assert result["3"] == result["8"] == "blocked"


def test_linkage_and_image_identity_are_checked():
    foreign = snapshot(observations=[reading(r, region="elsewhere") for r in ROUTES])
    assert statuses(evidence(foreign))["9"] == "failed"
    assert statuses(evidence(snapshot()), {"sha256": "e" * 64})["1"] == "failed"


def test_disagreement_needs_the_named_metric_on_every_region():
    unscored = snapshot(
        transcripts=[
            Transcript(region_id="r1", observation_ids=[], alternatives=[], resolved=False)
        ]
    )
    assert statuses(evidence(unscored))["5"] == "failed"


def test_normalized_rows_keyed_to_specimen_and_run_pass_stage_4():
    # S5's contract: readings are model_observation rows with independent = true, sharing the
    # snapshot's observation ids and linked to the specimen only through pipeline_run.
    first_pass = {"id": "fp-r1", "run_id": "run-2", "independent": False}
    rows = {
        "pipeline_run": [{"id": "run-2", "specimen_id": "specimen-1"}],
        "model_observation": [
            {"id": f"o-r1-{route}", "run_id": "run-2", "independent": True} for route in ROUTES
        ] + [first_pass],
    }
    assert statuses(evidence(snapshot(), rows))["4"] == "passed"
    rows["model_observation"][0]["run_id"] = "another-run"
    assert statuses(evidence(snapshot(), rows))["4"] == "failed"
    rows["model_observation"][0]["run_id"] = "run-2"
    rows["pipeline_run"][0]["specimen_id"] = "another-specimen"
    assert statuses(evidence(snapshot(), rows))["4"] == "failed"


def test_verdict_separates_errors_failures_and_incomplete_runs():
    passed = [{"status": "passed"}]
    assert lab_checks.verdict(passed, passed) == "pass"
    assert lab_checks.verdict(passed, []) == "incomplete"  # no stages scored is not a pass
    assert lab_checks.verdict(passed, [{"status": "not built"}]) == "incomplete"
    assert lab_checks.verdict(passed, [{"status": "failed"}]) == "fail"
    assert lab_checks.verdict([{"status": "failed"}], passed) == "error"
