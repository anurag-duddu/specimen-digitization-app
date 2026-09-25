"""The queue decision (HARNESS.md section 16): what the harness resolved clears
(G1), what it could not goes to review with its reasons (G6), a capability
limit defers (QUE-004) and an operational failure blocks (QUE-005)."""

import pytest
from test_field_harness import Blobs, Fakes, model

from specimen_digitization.application.domain import (
    MANDATORY,
    Disposition,
    FieldValue,
    Lookup,
    Observation,
    Profile,
    Region,
    Run,
    Transcript,
)
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.domain import ValueState as V
from specimen_digitization.application.field_harness import FieldPlan, run_harness
from specimen_digitization.application.field_resolution import Reading
from specimen_digitization.application.harness_knowledge import insects
from specimen_digitization.application.harness_ledger import ToolLedger
from specimen_digitization.application.harness_tools import (
    PlaceCandidate,
    SourceCall,
    ToolResult,
)
from specimen_digitization.application.policy import finalize, taxon_lookup
from specimen_digitization.application.taxonomy_tool import Verification

GOOGLE = "google-maps-geocoding"
LABEL = (
    "GUATEMALA: Chimaltenango, Acatenango, San Antonio Nejapa, E. slope Volcan"
    " Fuego, 1200 m, cloud forest, beating, 14-5-48 to 19-5-48, F.G. Werner\n"
    "FMNH INS 0123456 INS\nEpipsocus det. 20.v.1948"
)
# The label's own field literals: every mandatory field but those G41 fills.
STATED = {
    "fmnh_ins_number": "FMNH INS 0123456",
    "collection_code": "INS",
    "country": "GUATEMALA",
    "province_state": "Chimaltenango",
    "county": "Acatenango",
    "city": "San Antonio Nejapa",
    "precise_location": "E. slope Volcan Fuego",
    "elevation_from_m": "1200 m",
    "habitat": "cloud forest",
    "collection_method": "beating",
    "date_visited_from": "14-5-48",
    "date_visited_to": "19-5-48",
    "collectors": "F.G. Werner",
    "verbatim_dts": "14-5-48 to 19-5-48",
    "taxon": "Epipsocus",
    "date_identified": "20.v.1948",
}
LANE = tuple(key for key in MANDATORY if key != "identified_by_irn")  # G16, G42.
PLACES = ("country", "province_state", "county", "city", "precise_location")
PLAN = FieldPlan(
    mandatory=LANE,
    optional=("identified_by_irn",),
    tools={
        "fmnh_ins_number": "catalog_number_validator",
        **dict.fromkeys(PLACES, "geography_lookup"),
        "date_visited_from": "date_parser",
        "date_visited_to": "date_parser",
        "date_identified": "date_parser",
        "taxon": "taxonomy_verifier",
    },
)


class Tools(Fakes):
    """GBIF answers each literal as told (success by default); every admin
    place field matches."""

    def __init__(self, taxa=None):
        super().__init__()
        self.taxa = taxa or {}

    def verify_taxon(self, literal):
        status = self.taxa.get(literal, S.SUCCESS)
        if status == S.SUCCESS:
            return super().verify_taxon(literal)
        self.calls.append(("taxon", literal))
        call = SourceCall(
            source="gbif", query={"name": literal}, retrieved_at="t", outcome=status
        )
        result = ToolResult(
            tool="taxonomy_verifier",
            tool_version="v1",
            outcome=status,
            sub_calls=[call],
        )
        lookup = Lookup(
            provider="gbif",
            adapter_version="v2",
            query={"scientificName": literal},
            status=status,
        )
        return Verification(result, lookup)

    def geocode(self, query):
        fields = {item.field_key: item.literal for item in query.literals}
        self.calls.append(("geocode", fields))
        outcomes = {k: S.SUCCESS for k in fields if k != "precise_location"}
        places = [
            PlaceCandidate(field_key=k, source=GOOGLE, source_record_id=f"place-{k}")
            for k in outcomes
        ]
        call = SourceCall(
            source=GOOGLE,
            query={"address": "x"},
            retrieved_at="t",
            outcome=S.SUCCESS,
            raw_ref="blob",
        )
        return ToolResult(
            tool="geography_lookup",
            tool_version="v1",
            outcome=S.SUCCESS,
            field_outcomes=outcomes,
            places=places,
            sub_calls=[call],
        )


def answer(by_reading):
    return {
        "literals": [
            {"field_key": key, "reading": name, "literal": literal}
            for name, fields in by_reading.items()
            for key, literal in fields.items()
        ]
    }


def observation(observation_id, route, text):
    return Observation(
        id=observation_id,
        region_id="r1",
        route_id=route,
        model_id=route + "-model",
        provider="deepinfra",
        prompt_version="p1",
        input_sha256="0" * 64,
        literal_text=text,
        raw_ref="blob-" + observation_id,
        raw_sha256="1" * 64,
    )


def lane_run(by_reading=None, *, texts=None, decided=True, tools=None) -> Run:
    """A lane run whose fields are a real harness outcome on one label read by
    two readers: the first pass decided Muse's reading unless `decided` is
    False, and the harness gets both (G40)."""
    texts = texts or {"o-muse": LABEL, "o-qwen": LABEL}
    role = "decided_transcript" if decided else "raw_reading"
    readings = [
        Reading("r1", "o-muse", role, texts["o-muse"]),
        Reading("r1", "o-qwen", "raw_reading", texts["o-qwen"]),
    ]
    tools = tools or Tools()
    outcome = run_harness(
        model(answer(by_reading or {"1A": STATED})),
        "You are the field harness.",
        plan=PLAN,
        readings=readings,
        notes={},
        ledger=(ledger := ToolLedger(tools.tools(), asset_id="asset-1")),
        asset_id="asset-1",
        blobs=Blobs(),
        timeout_seconds=30,
    )
    assert ledger.records  # The harness ran its tools.
    return Run(
        profile=Profile(
            mandatory_fields=LANE,
            harness_route="harness-test",
            policy_version="insects-clearance-v2",  # As the lane's profile names it.
        ),
        profile_snapshot={
            "harness_knowledge": {"id": "insects", "version": insects.KNOWLEDGE_VERSION}
        },
        regions=[
            Region(
                id="r1",
                asset_id="asset-1",
                x=0,
                y=0,
                width=10,
                height=10,
                order=0,
                method="sam3",
                version="v1",
            )
        ],
        observations=[
            observation("o-muse", "handwriting-muse", texts["o-muse"]),
            observation("o-qwen", "handwriting-qwen", texts["o-qwen"]),
        ],
        transcripts=[
            Transcript(
                region_id="r1",
                text=texts["o-muse"] if decided else None,
                observation_ids=["o-muse", "o-qwen"],
                alternatives=[],
                resolved=decided,
            )
        ],
        coverage_confirmed=True,
        fields=outcome.fields,
        evidence=outcome.evidence,
        findings=outcome.findings,
        tool_calls=outcome.tool_calls,
        lookups=outcome.lookups,
        blocker=outcome.blocker,
        harness_failure=outcome.failure,
    )


def decided(run: Run) -> Run:
    finalize(run)
    return run


def test_what_the_harness_resolved_clears():
    # G1: "When I say something that harness was able to resolve is cleared it
    # is cleared." G41 fills the elevations the label leaves out.
    run = decided(lane_run())

    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert run.disposition_summary == "Cleared under insects-clearance-v2."
    assert run.fields["elevation_to_ft"].layer == "derived"


def test_no_data_for_a_mandatory_field_goes_to_review_with_its_reason():
    run = decided(lane_run({"1A": {k: v for k, v in STATED.items() if k != "habitat"}}))

    assert run.disposition == Disposition.REVIEW
    assert run.reasons == ["mandatory_unresolved:habitat"]
    assert run.disposition_summary == (
        "Needs human review under insects-clearance-v2: mandatory_unresolved."
    )


def test_no_data_for_an_optional_field_still_clears():
    # G16: identified_by_irn is recorded as not resolved and never blocks.
    run = decided(lane_run())

    assert run.fields["identified_by_irn"] == FieldValue()
    assert run.disposition == Disposition.CLEARED


def test_a_failed_coverage_check_goes_to_review():
    run = lane_run()
    run.coverage_confirmed = False  # G15's automatic check failed.

    assert decided(run).reasons == ["label_coverage_unconfirmed"]


def test_a_harness_failure_goes_to_review_with_its_code():
    run = lane_run()
    run.harness_failure = "harness_usage_limit"  # G6: it decided no field.
    run.fields = {key: FieldValue() for key in run.fields}

    reasons = decided(run).reasons
    assert run.disposition == Disposition.REVIEW
    assert reasons[0] == "harness_failure:harness_usage_limit"
    assert "mandatory_unresolved:taxon" in reasons


def test_a_capability_limit_defers():
    run = lane_run()
    run.capability_reason = "unsupported_script"  # QUE-004.
    run.retry_eligibility = "newer_model_family"
    run.completed_steps.append("capability_attempts_exhausted")

    assert decided(run).disposition == Disposition.DEFERRED
    assert run.disposition_summary == (
        "Deferred under insects-clearance-v2: unsupported_script."
    )


def test_an_operational_lookup_blocks_unless_a_retry_recovered_it():
    # QUE-005: the lookup the taxon rests on, the latest of its request.
    run = lane_run()
    failed = Lookup(
        provider="gbif",
        adapter_version="v2",
        query={"scientificName": "Epipsocus"},
        status=S.RATE_LIMITED,
    )
    run.lookups.insert(0, failed)  # An earlier attempt, recovered.
    assert decided(run).disposition == Disposition.CLEARED

    run.lookups.append(failed.model_copy(update={"id": "later"}))
    assert decided(run).stage == "processing_blocked"
    assert (run.disposition, run.disposition_summary) == (None, None)
    assert run.reasons == ["lookup_operational_failure"]


def test_a_derived_value_counts_only_with_its_record():
    # #124: a derived value names its inputs, its rule and apply_derivations;
    # without that record, or asserted by the model, it does not count.
    run = lane_run()
    rule = next(
        e
        for e, relation in run.fields["elevation_to_m"].evidence_relations.items()
        if relation == "decides"
    )
    run.evidence = [
        item.model_copy(update={"raw_ref": None}) if item.id == rule else item
        for item in run.evidence
    ]
    run.fields["elevation_to_ft"] = FieldValue(
        state=V.SUPPORTED, layer="derived", parsed="9999", derived_from=["x"]
    )

    reasons = decided(run).reasons
    assert "mandatory_unresolved:elevation_to_m" in reasons
    assert "mandatory_unresolved:elevation_to_ft" in reasons
    assert "elevation_invalid:m" in reasons


@pytest.mark.parametrize(
    ("literal", "cleared"),
    [
        ("20.v.1948", True),
        ("V.1948", True),  # G24: a date clears at the precision written.
        ("20.v.1948?", False),  # An uncertain date keeps the date gate.
    ],
)
def test_the_date_gate_reads_the_parsed_date(literal, cleared):
    label = LABEL.replace("20.v.1948", literal)
    fields = STATED | {"date_identified": literal}

    run = decided(lane_run({"1A": fields}, texts={"o-muse": label, "o-qwen": label}))

    assert (run.disposition == Disposition.CLEARED) is cleared
    if not cleared:
        assert "date_precision_requires_review" in run.reasons


def test_g19_readers_who_differ_clear_when_their_lookups_agree():
    # The first pass picked no reading; the taxon lookups settle one usage.
    qwen = LABEL.replace("Epipsocus", "Epipsocvs")
    tools = Tools()
    by_reading = {"1A": STATED, "1B": STATED | {"taxon": "Epipsocvs"}}

    run = decided(
        lane_run(
            by_reading,
            texts={"o-muse": LABEL, "o-qwen": qwen},
            decided=False,
            tools=tools,
        )
    )

    taxon = run.fields["taxon"]
    assert taxon.verbatim_by_observation == {
        "o-muse": "Epipsocus",
        "o-qwen": "Epipsocvs",
    }
    assert len([c for c in tools.calls if c[0] == "taxon"]) == 2  # Two lookups.
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert [f.reason_code for f in run.findings] == ["spelling_disagreement"]


def test_g19_a_field_left_with_conflicting_readings_goes_to_review():
    qwen = LABEL.replace("cloud forest", "cloud-forest")
    by_reading = {"1A": STATED, "1B": STATED | {"habitat": "cloud-forest"}}

    run = decided(
        lane_run(by_reading, texts={"o-muse": LABEL, "o-qwen": qwen}, decided=False)
    )

    assert run.reasons == [
        "unresolved_transcription:r1",
        "mandatory_unresolved:habitat",
    ]


def test_g20_the_taxonomy_gate_reads_the_lookup_that_settled_the_taxon():
    # The decided literal matches nothing; the raw reading's settles it (G20).
    # A later lookup on another literal does not decide the taxon.
    tools = Tools(taxa={"Epipsocvs": S.NO_MATCH})
    label = LABEL.replace("Epipsocus", "Epipsocvs")
    by_reading = {"1A": STATED | {"taxon": "Epipsocvs"}, "1B": STATED}

    run = lane_run(
        by_reading, texts={"o-muse": label, "o-qwen": LABEL}, decided=True, tools=tools
    )
    run.lookups.append(
        Lookup(
            provider="gbif",
            adapter_version="v2",
            query={"scientificName": "Epipsocidae"},
            status=S.NO_MATCH,
        )
    )

    assert taxon_lookup(run).query["scientificName"] == "Epipsocus"
    assert decided(run).disposition == Disposition.CLEARED
    assert run.fields["taxon"].literal == "Epipsocvs"  # G27: the verbatim stays.


def test_the_summary_follows_the_evidence_phase_gate():
    # The phase gate has the last word; a hard finding reopens a cleared run.
    from types import SimpleNamespace

    from specimen_digitization.application.evidence_runtime import apply_phase_gate

    run = decided(lane_run())
    hard = SimpleNamespace(severity="hard", code="phase_check_failed", field_key=None)
    apply_phase_gate(run, SimpleNamespace(applicability="applicable", findings=[hard]))

    assert run.disposition == Disposition.REVIEW
    assert run.disposition_summary == (
        "Needs human review under insects-clearance-v2: phase_check_failed."
    )


def test_the_approval_gates_stay_for_a_run_the_harness_did_not_decide():
    # G1 turns on with the harness route: a synthetic demo, or a run before
    # the switch, keeps the approval gates.
    run = lane_run()
    run.profile = run.profile.model_copy(update={"harness_route": None})

    assert decided(run).reasons == [
        "institutional_policy_unapproved",
        "mandatory_semantics_unconfirmed",
        "human_approval_required",
    ]


def test_a_single_collecting_date_fills_to_derived_and_the_record_clears():
    # G44: "Date Visited To gets the same date, marked as derived from Date
    # Visited From, so the record can clear on it."
    single = {k: v for k, v in STATED.items() if k != "date_visited_to"}

    run = decided(lane_run({"1A": single}))

    to = run.fields["date_visited_to"]
    assert (to.layer, to.parsed, to.precision, to.derived_from) == (
        "derived",
        "1948-05-14",
        "day",
        ["date_visited_from"],
    )
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


@pytest.mark.parametrize(
    ("field", "written"),
    [
        ("collectors", "VI-24-68-7"),  # The real run on 105526328.
        ("collection_code", "IV-29-68-a"),  # The real run on 105526330.
        ("habitat", "♀ legs Sp.#1"),  # The real run on 105526330.
    ],
)
def test_a_value_that_does_not_look_like_its_field_goes_to_review(field, written):
    # G45: in a field no lookup checks, a value that doesn't look like its
    # field's kind goes to review with its own reason.
    label = LABEL + "\n" + written

    run = decided(
        lane_run(
            {"1A": STATED | {field: written}}, texts={"o-muse": label, "o-qwen": label}
        )
    )

    assert run.reasons == [f"value_shape_mismatch:{field}"]


def test_a_preparation_code_in_verbatim_dts_is_a_finding_that_never_routes():
    # PRD 529 leaves verbatim_dts's meaning unconfirmed (G45, the coordinator).
    label = LABEL + "\n10-6-78-la"
    run = lane_run(
        {"1A": STATED | {"verbatim_dts": "10-6-78-la"}},
        texts={"o-muse": label, "o-qwen": label},
    )

    decided(run)
    decided(run)  # Decided again: the finding is not repeated.

    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert [(f.field_key, f.reason_code) for f in run.findings] == [
        ("verbatim_dts", "value_shape_mismatch:verbatim_dts")
    ]
