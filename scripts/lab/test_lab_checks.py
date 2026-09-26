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

import json

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


def evidence(snap, rows=None, actions=(), requests=0):
    return {"snapshot": snap, "rows": rows or {}, "actions": list(actions),
            "gbif_occurrence_requests": requests}


def coverage(outcome, *reasons):
    """#111's run record (label_coverage.py), not the thread API's view."""
    codes = ["label_coverage_unconfirmed", *reasons] if outcome == "unconfirmed" else []
    return {"coverage_confirmed": outcome == "confirmed", "coverage_check": {
        "version": "label-coverage-v1", "outcome": outcome, "region_count": 2,
        "min_label_regions": 1, "max_label_regions": 3,
        "cross_check": {"concept": "text", "threshold": 0.5, "min_inside_fraction": 0.5,
                        "counted": 1, "uncovered_boxes": []},
        "reason_codes": codes}}


def test_full_sam_run_scores_every_stage_it_can_see():
    snap = snapshot()
    snap["run"].update(coverage("confirmed"))
    result = statuses(evidence(snap))
    assert result["1"] == result["2"] == result["3"] == "passed"
    assert result["5"] == result["9"] == "passed"
    assert result["8"] == "not checked"  # review, as expected for the ten; reasons compared by hand
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
        attempts={"parse": 1}, completed_steps=[
            "pin_dependencies", "classify", "quality_check", "segment",
            "transcribe:r1:handwriting-qwen", "transcribe:r1:handwriting-muse", "adjudicate",
        ],
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
    # A pass needs the lane's own check (G15; #111 writes coverage_check.outcome). The lab's boxes are
    # ground truth, and its "at least half, by a distinct region" is the lab's own measure.
    two_labels = "subject_105526324"  # locality on the right label, notes on the left
    left = Region(
        id="r1", asset_id="asset-1", x=0, y=0, width=570, height=590, order=0,
        method="sam3", version="sam3-http-v1",
    )
    right = left.model_copy(update={"id": "r2", "x": 1110, "width": 670, "order": 1})
    whole = left.model_copy(update={"id": "r3", "width": 1780})

    def stage_2(regions, subject, outcome=None):
        snap = snapshot(regions=regions)
        if outcome:
            snap["run"].update(coverage(outcome, "cross_check_detection_outside_labels"))
        result = lab_checks.check_stages(evidence(snap), SOURCE, subject)
        return next(s for s in result if s["stage"] == "2")

    assert stage_2([left, right], two_labels, "confirmed")["status"] == "passed"  # a covered pass
    assert stage_2([left], two_labels, "confirmed")["status"] == "failed"  # a let-through miss
    assert stage_2([left], two_labels, "unconfirmed")["status"] == "passed"  # a caught miss
    false_alarm = stage_2([left, right], two_labels, "unconfirmed")  # G15 sends it to review anyway
    assert false_alarm["status"] == "not checked" and "false alarm" in false_alarm["detail"]
    assert stage_2([left, right], two_labels)["status"] == "not built"  # no pass without the check
    assert stage_2([whole], two_labels, "confirmed")["status"] == "failed"  # one region, two labels
    assert stage_2([left, right], two_labels, "pending")["status"] == "not checked"  # another outcome
    for outcome in ("confirmed", "unconfirmed"):  # no ground truth outside the ten
        assert stage_2([left], "subject_999", outcome)["status"] == "not checked"
    assert lab_checks.label_boxes(two_labels) == [(0.0, 0.34), (0.62, 1.0)]
    assert lab_checks.label_boxes(SUBJECT) == [(0.0, 0.37)]

def test_stage_8_expects_review_for_the_ten_and_leaves_their_reasons_to_a_person():
    # All ten go to needs human review with reasons (PLAN 8, 879-883); a person compares the reasons.
    for wrong in (Disposition.CLEARED, Disposition.DEFERRED):
        assert statuses(evidence(snapshot(disposition=wrong, reasons=["x"])))["8"] == "failed"
    assert statuses(evidence(snapshot(reasons=[])))["8"] == "failed"  # a review must give reasons
    review = lab_checks.check_stages(evidence(snapshot()), SOURCE, SUBJECT)
    stage = next(s for s in review if s["stage"] == "8")
    assert stage["status"] == "not checked" and "by hand" in stage["detail"]
    cleared = snapshot(disposition=Disposition.CLEARED, reasons=[])
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


def test_a_gbif_occurrence_request_in_any_record_of_any_run_fails_while_d4_is_off():
    # D4 is held: its occurrence check is off and sends nothing (PLAN 2, coordinator rulings). PLAN 4.8's
    # table lists GBIF for species match (G23) and the held occurrence search; only real occurrence-request
    # shapes fail here. GADM and any other GBIF call have their own test below.
    def stage_7(key, value, requests=0, previous=False, blobs=()):
        snap = snapshot()
        (snap.setdefault("previous_runs", []).append(snapshot()["run"] | {"id": "run-1", key: value})
         if previous else snap["run"].__setitem__(key, value))
        ev = evidence(snap, requests=requests) | {"d4_blob_hits": list(blobs)}
        return next(s for s in lab_checks.check_stages(ev, SOURCE, SUBJECT) if s["stage"] == "7")

    real = [
        ("evidence", [{"locator": "https://API.GBIF.ORG/v1/%6Fccurrence/search?q=x"}]),
        ("tool_calls", [{"call_key": "k1", "tool": "gbif_occurrence_search"}]),
        # main's shapes: an authority result names its source, and evidence has a host-less locator.
        ("authority_results", {"authority:0:geography_lookup": {
            "tool_id": "geography_lookup", "field_key": "country", "source_id": "gbif_occurrence",
            "status": "success", "blob_ref": "b", "sha256": "0" * 64}}),
        ("evidence", [{"kind": "authority", "source": "gbif", "locator": "/v1/occurrence/search",
                       "excerpt": "", "raw_ref": "r", "digest": "d"}]),
        ("evidence", [{"source": "gbif", "locator": "/v1/./occurrence/search"}]),
        # a client removes every dot segment, however many (#83 round 1)
        ("evidence", [{"source": "gbif", "locator": "/v1/././occurrence/search"}]),
        ("evidence", [{"source": "gbif", "locator": "/v1/x/../occurrence/search"}]),
        # #84 round 1: merged slashes, a ".." above the root that must not eat the host, a trailing host dot
        ("evidence", [{"source": "gbif", "locator": "/v1//occurrence/12345"}]),
        *(("evidence", [{"kind": "authority", "source": "web", "locator": "https://api.gbif.org" + path}])
          for path in ("/../v1/occurrence/search", "./v1/occurrence/search", "/v2/%2e%2e/%2e%2e/v1/occurrence")),
        ("authority_results", {"k": {"context_json": '{"museum_published": true}'}}),
        ("authority_results", {"k": {"signals": {"occurrence": "supports"}}}),
        ("tool_calls", [{"tool": "occurrence_search", "source": "gbif", "arguments": {"q": "x"}}]),
        ("tool_calls", [{"tool": "taxonomy_verifier", "source": "gbif", "arguments": {"recordedBy": "x"}}]),
        ("lookups", [{"provider": "gbif", "adapter_version": "occurrence-v1", "query": {"catalogNumber": "1"}}]),
        ("authority_results", {"k": {"museum_published": True}}),
    ]
    for key, value in real:
        assert stage_7(key, value)["status"] == "failed", (key, value)
    assert stage_7(*real[1], previous=True)["status"] == "failed"
    assert stage_7("lookups", [], requests=1)["status"] == "failed"  # the runner's request count
    assert stage_7("lookups", [], blobs=["receipts/c1.json"])["status"] == "failed"  # a receipt's blob
    sent_nothing = [
        ("evidence", [{"locator": "https://bionomia.net/occurrence/123"}]),
        ("tool_calls", [{"tool": "taxonomy_verifier", "source": "gbif", "arguments": {"name": "Epipsocus"},
                         "result": {"candidates": [{"numOccurrences": 12}]}}]),
        ("lookups", [{"provider": "gbif", "adapter_version": "species-match-v2.1", "status": "success",
                      "query": {"name": "x"}}]),
        ("evidence", [{"kind": "authority", "source": "gbif", "locator": "/v2/species/match"}]),
        ("authority_results", {"k": {"museum_published": False, "signals": {"occurrence": None}}}),
        ("tool_calls", [{"tool": "occurrence_search", "source": "gbif", "outcome": "policy_blocked"}]),
        ("transcripts", [{"region_id": "r1", "observation_ids": [], "alternatives": [], "resolved": True,
                          "text": "Rare occurrence at light"}]),
    ]
    for key, value in sent_nothing:
        assert stage_7(key, value)["status"] != "failed", (key, value)
    absent = stage_7("lookups", [], requests=None)
    assert absent["status"] == "not checked" and "hook" in absent["detail"]


def test_a_gadm_call_fails_against_plan_4_8_and_other_gbif_calls_are_reported():
    # Coordinator ruling (2026-09-25): PLAN 4.8 does not use GADM, not even as a measurement, so a GADM call
    # fails on that ground; it is not an occurrence request (D4). Reporting any other GBIF call is the lab's
    # own choice: PLAN 4.8's only GBIF rows are species match (G23) and the held occurrence search.
    def stage_7(key, value):
        snap = snapshot()
        snap["run"][key] = value
        return next(s for s in lab_checks.check_stages(evidence(snap), SOURCE, SUBJECT) if s["stage"] == "7")

    for key, value in (
        ("lookups", [{"provider": "gbif_gadm", "adapter_version": "gbif-gadm-1", "status": "success"}]),
        ("tool_calls", [{"tool": "geography_lookup", "source": "gbif_gadm", "arguments": {"q": "Davao"}}]),
    ):
        stage = stage_7(key, value)
        assert stage["status"] == "failed" and "GADM is not used (PLAN 4.8)" in stage["detail"], key
    other = stage_7("tool_calls", [{"tool": "dataset_lookup", "source": "gbif", "arguments": {"q": "x"}}])
    assert other["status"] != "failed" and "outside PLAN 4.8" in other["detail"]
    # with no tool-call record, the reported call is the stage's whole finding (#83 round 1)
    alone = stage_7("lookups", [{"provider": "gbif", "adapter_version": "dataset-v1", "status": "success"}])
    assert alone["status"] == "not checked" and "outside PLAN 4.8" in alone["detail"], alone
    assert "0 tool calls" not in alone["detail"], alone


def test_134s_species_match_evidence_is_not_reported_outside_plan_4_8():
    # #134 (harness_ledger.py) records a GBIF species match's evidence as source "gbif" with the locator
    # "usage/<key>", or with no locator when the lookup failed; its tool call names the evidence it wrote.
    snap = snapshot()
    snap["run"]["tool_calls"] = [{"call_key": "k1", "tool": "taxonomy_verifier", "source": "gbif",
                                  "outcome": "failed", "evidence_id": "ev-2"}]
    snap["run"]["evidence"] = [
        {"id": "ev-1", "kind": "lookup", "source": "gbif", "locator": "usage/5143893", "excerpt": "gbif success"},
        {"id": "ev-2", "kind": "lookup", "source": "gbif", "locator": None, "excerpt": "gbif failed"},
    ]
    stage = next(s for s in lab_checks.check_stages(evidence(snap), SOURCE, SUBJECT) if s["stage"] == "7")
    assert stage["status"] == "not checked" and "outside PLAN 4.8" not in stage["detail"], stage

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


def test_tracing_reads_the_runs_trace_id():
    assert statuses(evidence(snapshot()))["trace"] == "not built"
    traced = snapshot()
    traced["run"]["trace_id"] = "0af7651916cd43dd8448eb211c80319c"
    assert statuses(evidence(traced))["trace"] == "not checked"  # needs a Logfire read token


def test_a_block_without_a_blocker_shows_its_reasons_and_stage_1_prints_no_hash():
    snap = snapshot(stage="processing_blocked", blocker=None, disposition=None, observations=[],
                    reasons=["label_coverage_unconfirmed"])
    stage = {s["stage"]: s for s in lab_checks.check_stages(evidence(snap), SOURCE, SUBJECT)}
    assert stage["3"]["status"] == "blocked"
    assert stage["3"]["detail"].startswith("['label_coverage_unconfirmed'] at")  # reasons stand in
    assert SHA[:12] not in stage["1"]["detail"]


def test_a_receipt_blob_names_the_occurrence_api_after_a_root_dot_segment():
    # #84 round 1: the dot-segment rule ate the host, so this blob read as "https://v1/occurrence/...".
    assert lab_checks.occurrence_blob('{"url": "https://api.gbif.org/../v1/occurrence/search"}')
    assert not lab_checks.occurrence_blob('{"url": "https://api.gbif.org/../v2/species/match"}')


FORMS = ("/%2E%2E/v1/occurrence/search", "/v1//occurrence/12345", "//v1/occurrence/search",
         "/v2/%2e%2e/%2e%2e/v1/occurrence/search", "/%3F/../v1/occurrence/search", "/v1/%20/../occurrence/search",
         "/v1;x/occurrence/search",
         # #84 round 3: a client resolves ".." before a server drops ";" or merges slashes
         "/v1/occurrence/;x/../search", "/v1/occurrence/;/../search", "/v1/occurrence//../search",
         "/v1/%5C/../occurrence/search")


def test_every_pinned_form_counts_in_the_record_and_blob_scans():
    # #84 round 2: each form, with its host (also with a trailing dot) and as a GBIF record's own path, in the
    # record scan and the blob scan. A segment that decodes to "?" or a space must not hide the ".." after it.
    def stage_7(record):
        snap = snapshot()
        snap["run"]["evidence"] = [record]
        return next(s for s in lab_checks.check_stages(evidence(snap), SOURCE, SUBJECT) if s["stage"] == "7")

    for form in FORMS:
        for host in ("https://api.gbif.org", "https://api.gbif.org."):
            url = host + form
            assert stage_7({"kind": "authority", "source": "web", "locator": url})["status"] == "failed", url
            assert lab_checks.occurrence_blob(json.dumps({"url": url})), url
        assert stage_7({"kind": "lookup", "source": "gbif", "locator": form})["status"] == "failed", form
        assert lab_checks.occurrence_blob(json.dumps({"source": "gbif", "locator": form})), form
    for species in ("https://api.gbif.org/v2/%3F/../species/match", "https://api.gbif.org/v2;x/species/match"):
        assert not lab_checks.occurrence_blob(json.dumps({"url": species})), species


def stage_7_of(record):
    snap = snapshot()
    snap["run"]["evidence"] = [record]
    return next(s for s in lab_checks.check_stages(evidence(snap), SOURCE, SUBJECT) if s["stage"] == "7")


def test_a_path_the_client_resolves_to_species_match_is_not_an_occurrence_request():
    # #84 round 3: "occurrence%3F" is one segment to a client, so the two ".." reach /v2/species/match.
    url = "https://api.gbif.org/v1/occurrence%3F/../../v2/species/match"
    assert not lab_checks.occurrence_blob(json.dumps({"url": url}))
    assert stage_7_of({"kind": "authority", "source": "web", "locator": url})["status"] != "failed"
    assert stage_7_of({"kind": "lookup", "source": "gbif", "locator": url})["status"] != "failed"


def test_a_gbif_records_relative_and_network_paths_are_read():
    # #84 round 3: a relative path resolves from the root; "//host/path" is also read as a host and path.
    for locator in ("v1/occurrence/search", "//mirror.example.org/v1/occurrence/search"):
        assert stage_7_of({"kind": "lookup", "source": "gbif", "locator": locator})["status"] == "failed", locator


def test_a_url_encoded_inside_another_is_split_before_each_decoding():
    # #84 round 3: an inner %253F or %2520 hid the ".." one level down when the text was decoded to the end first.
    for text in ("next=https%3A%2F%2Fapi.gbif.org%2F%253F%2F..%2Fv1%2Foccurrence%2Fsearch",
                 "next=https%3A%2F%2Fapi.gbif.org%2Fv1%2F%2520%2F..%2Foccurrence%2Fsearch"):
        assert lab_checks.occurrence_request(text), text
    assert not lab_checks.occurrence_request(
        "next=https%3A%2F%2Fapi.gbif.org%2Fv1%2Foccurrence%253F%2F..%2F..%2Fv2%2Fspecies%2Fmatch")


def test_a_blob_holding_escaped_json_is_read_at_each_level():
    # #84 round 3: the blob's record branch applied only the record test, not the text test to its strings.
    inner = '{"url": "https:\\/\\/api.gbif.org\\/v1\\/occurrence\\/search"}'
    assert lab_checks.occurrence_blob(json.dumps({"context_json": inner}))


def test_a_gbif_records_path_inside_a_value_or_a_key_counts():
    # #84 round 4: round 3 read a value only as one whole path and skipped keys.
    records = [{"kind": "lookup", "source": "gbif", "locator": value}
               for value in ("GET /v1/occurrence/search?catalogNumber=1", "fetched /v1/occurrence/search",
                             "path=/v1/occurrence/search")]
    records.append({"kind": "lookup", "source": "gbif", "result": {"/v1/occurrence/search": "x"}})
    for record in records:
        assert stage_7_of(record)["status"] == "failed", record
        assert lab_checks.occurrence_blob(json.dumps(record)), record


def test_a_record_holding_escaped_json_counts_in_the_record_scan():
    # #84 round 4: json.dumps doubled the escaped slashes, and only the blob scan read strings on their own.
    inner = '{"url": "https:\\/\\/api.gbif.org\\/v1\\/occurrence\\/search"}'
    assert stage_7_of({"kind": "authority", "source": "web", "context_json": inner})["status"] == "failed"


def test_an_empty_port_and_idn_dots_name_api_gbif_org_in_stored_text():
    # #84 round 4: httpx sends each of these to api.gbif.org.
    for host in ("api.gbif.org:", "api\u3002gbif\u3002org", "api\uff0egbif\uff0eorg", "api\uff61gbif\uff61org"):
        url = f"https://{host}/v1/occurrence/search"
        assert lab_checks.occurrence_request(url), url
        assert stage_7_of({"kind": "authority", "source": "web", "locator": url})["status"] == "failed", url


def test_a_double_encoded_path_is_decoded_once_as_the_client_sends_it():
    # #84 round 4: stated, not caught: httpx decodes once, so %252F stays an encoded slash in the path.
    assert not lab_checks.occurrence_request("https://api.gbif.org/v1%252Foccurrence%252Fsearch")
