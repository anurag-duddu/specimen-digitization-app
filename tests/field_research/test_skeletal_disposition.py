"""Plan WP K1 (docs/execution/autonomy/PLAN.md): the skeletal record.

The owner typed on 2026-11-18 (coordinator session f9614090): "Where there is no field related data on the lable,
nothing to do, it will get cleared. Not all fields are mandatory right. As long as the mandatory ones are filled it
should be cleared. Lets make skeletal records mandatory (decide if not already decided), full set (remaining
optional)". The coordinator's decision for this build (the coordinator's words, not the owner's): the mandatory
(skeletal) set is the catalogue number, `fmnh_ins_number`; every other field is optional.

What is tested here:
- the published profile makes only the catalogue number mandatory;
- step.split_reasons: every kind of reason scientific_reasons and finalize_fields give, as holding the record or as
  an optional field's doubt (run.open_reasons);
- through the rig on the published profile: a label with only the catalogue number clears; the same fields, states,
  values, findings and reasons as under the profile with every field mandatory, the reasons only split between
  run.reasons and run.open_reasons; what still holds (the catalogue number, a label it is drawn from, a label no
  field is drawn from, a field research could not finish, a person's pending approval, coverage);
- the ordinary path (policy.finalize) splits the same way, and the extraction request asks for the same fields.
"""

from __future__ import annotations

import pytest
from test_step import (
    LABEL,
    SMITH_OR_SMYTH,
    SMYTH,
    TEXT,
    TODAY,
    Scripted,
    answering,
    build_rig,
    every_field,
    failing,
    field_mechanics_profile,
    resolved,
    settle,
)

from specimen_digitization.application import policy
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Disposition,
    Evidence,
    FieldValue,
    Observation,
    Region,
    Run,
    RunFinding,
    ValueState,
)
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldOutcome

LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")
CATALOGUE = "fmnh_ins_number"


def published():
    return published_registry().profiles[0]


# ---- the profile -------------------------------------------------------------------------------

def test_the_published_profile_makes_only_the_catalogue_number_mandatory():
    profile = published()
    assert profile.mandatory_fields == (CATALOGUE,)
    # The 19 other fields, in the order the mandatory set had them, then the determiner's IRN, as before.
    assert profile.optional_fields == (*field_mechanics_profile().mandatory_fields[1:], "identified_by_irn")
    assert len(profile.optional_fields) == 19 and (profile.id, profile.version) == ("zoology_insects_slides", "1.0.0")


def test_the_extraction_is_asked_for_the_same_fields_as_before(tmp_path):
    """harness.extract_with_agent's request lists policy.checked_fields: every field a label writes, the same
    list in the same order as the mandatory set it listed before the change."""
    rig = build_rig(tmp_path, profile=published())
    assert policy.checked_fields(rig.specimen.run) == field_mechanics_profile().mandatory_fields


# ---- split_reasons -------------------------------------------------------------------------------

def a_run():
    """Two labels: L1, from which the catalogue number and the country are drawn; L2, from which the habitat is
    drawn; and L3, from which no field is drawn."""
    regions = [Region(id=name, asset_id="a", x=0, y=0, width=1, height=1, order=i, method="fixture", version="1")
        for i, name in enumerate(("L1", "L2", "L3"))]
    fields = {key: FieldValue() for key in published().mandatory_fields + published().optional_fields}
    fields[CATALOGUE] = FieldValue(state=ValueState.SUPPORTED, literal="FMNH-INS 0010001", source_region_id="L1")
    fields["country"] = FieldValue(state=ValueState.SUPPORTED, literal="United States", source_region_id="L1")
    fields["habitat"] = FieldValue(state=ValueState.SUPPORTED, literal="grassland", source_region_id="L2")
    return Run(regions=regions, fields=fields)


HOLDS = [
    "label_coverage_unconfirmed",
    "identifier_format",
    f"evidence_missing:{CATALOGUE}",
    f"evidence_does_not_support_value:{CATALOGUE}",
    f"raw_reading_grounding_unproved:{CATALOGUE}",
    f"pixel_lineage_missing:{CATALOGUE}",
    "raw_provenance_missing:L1",           # the catalogue number is drawn from L1
    "field_research_given_up",
    f"mandatory_unresolved:{CATALOGUE}",
    f"unsupported_parsed:{CATALOGUE}",
    f"marked:{CATALOGUE}:L1:text_only",
    "preserved_human_decision:habitat",
    "human_approval_required",
    "location_reassessment_unconfirmed:city",
    "lookup_operational_failure:country",
    "unresolved_transcription:L1",          # the catalogue number is drawn from L1
    "independent_observations_missing:L1",
    "evidence_lineage_invalid:e1",          # the ordinary path's
    "institutional_policy_unapproved",
    "a_code_this_rule_does_not_know:habitat",
]
OPEN = [
    "mandatory_unresolved:habitat",
    "mandatory_unresolved:taxon",
    "unsupported_parsed:country",
    "unsupported_normalized:country",
    "unsupported_authority_id:taxon",
    "identified_by_irn_identity_unproved",
    "taxonomy_unresolved",
    "taxonomy_lookup_missing",
    "elevation_invalid:m",
    "elevation_range:ft",
    "elevation_units_conflict:from",
    "date_precision_requires_review",
    "date_order",
    "marked:habitat:L2:text_only",
    "marked:country:L1:conflict",
    "marked:taxon:L2:parts_on_labels",
    "marked:county:L2:place_within_settled_places",
    "unresolved_transcription:L2",          # only the habitat, optional, is drawn from L2
    "independent_observations_missing:L2",
    "unresolved_transcription:L3",          # no field is drawn from L3
    "independent_observations_missing:L3",
    "raw_provenance_missing:L2",
    "raw_provenance_missing:L3",
    "evidence_missing:habitat",
    "evidence_does_not_support_value:habitat",
    "raw_reading_grounding_unproved:habitat",
    "pixel_lineage_missing:habitat",
    "research_incomplete:taxon",
]


@pytest.mark.parametrize("reason", HOLDS)
def test_a_reason_that_is_not_an_optional_fields_doubt_holds_the_record(reason):
    assert field_step.split_reasons(a_run(), [reason], mandatory=(CATALOGUE,)) == ([reason], [])


@pytest.mark.parametrize("reason", OPEN)
def test_an_optional_fields_doubt_does_not_hold_the_record(reason):
    assert field_step.split_reasons(a_run(), [reason], mandatory=(CATALOGUE,)) == ([], [reason])


@pytest.mark.parametrize("reason", OPEN)
def test_every_field_doubt_holds_where_its_field_is_mandatory(reason):
    """Under the profile with every field mandatory, as before 2026-11-18, the same reasons hold, but for the
    determiner's IRN (optional there too) and a label no field is drawn from (L3: nothing of it is in the
    record)."""
    every = field_mechanics_profile().mandatory_fields
    holds, open_ = field_step.split_reasons(a_run(), [reason], mandatory=every)
    opened = reason == "identified_by_irn_identity_unproved" or reason.endswith(":L3")
    assert (holds, open_) == (([], [reason]) if opened else ([reason], []))


def test_a_label_whose_first_pass_was_given_up_is_a_label_like_the_others():
    """The coordinator's ruling of 2026-11-18: a given-up label holds only where the catalogue number is drawn
    from it and the slide's code does not confirm it."""
    from specimen_digitization.application.first_pass import GIVEN_UP

    run = a_run()
    for label in ("L1", "L2"):
        run.findings.append(RunFinding(rule_id=GIVEN_UP, rule_version="1", severity="warning",
            reason_code=f"first_pass_given_up:{label}:model_rate_limited"))
    assert {"L1", "L2"} <= field_step.given_up_regions(run)
    reasons = ["unresolved_transcription:L1", "unresolved_transcription:L2"]
    assert field_step.split_reasons(run, reasons, mandatory=(CATALOGUE,)) == (reasons[:1], reasons[1:])
    with_the_code(run)
    assert field_step.split_reasons(run, reasons, mandatory=(CATALOGUE,)) == ([], reasons)


def test_a_label_language_rule_is_a_label_doubt():
    run = a_run()
    run.label_language_handling = {"labels": [{"region_id": "L1", "reasons": ["language_conflicting"]},
        {"region_id": "L2", "reasons": ["language_conflicting"]}]}
    reasons = ["language_conflicting:L1", "language_conflicting:L2"]
    assert field_step.split_reasons(run, reasons, mandatory=(CATALOGUE,)) == (reasons[:1], reasons[1:])


def test_a_label_is_drawn_from_by_a_reading_or_a_cited_row_too():
    run = a_run()
    run.observations.append(Observation(id="o3", region_id="L3", route_id="r", model_id="m", provider="p",
        prompt_version="v", input_sha256="0" * 64, input_asset_id="a", input_crop_ref="c", literal_text="x",
        raw_ref="r", raw_sha256="0" * 64))
    run.evidence.append(Evidence(id="e3", kind="literal", region_id="L3", asset_id="a", excerpt="x", source="label",
        locator="L3"))
    run.fields["city"] = FieldValue(state=ValueState.SUPPORTED, literal="x", verbatim_by_observation={"o3": "x"})
    assert field_step.label_fields(run, "L3") == {"city"}
    run.fields["city"] = FieldValue(state=ValueState.SUPPORTED, literal="x", evidence_ids=["e3"])
    run.fields[CATALOGUE] = FieldValue(state=ValueState.SUPPORTED, literal="1", evidence_ids=["e3"])
    assert field_step.label_fields(run, "L3") == {"city", CATALOGUE}
    assert field_step.split_reasons(run, ["unresolved_transcription:L3"], mandatory=(CATALOGUE,))[0]


def with_the_code(run, payload="0010001", *, decides=True):
    """The slide's QR code stored on L1 (barcode.evidence_row's shape), deciding the catalogue number as
    catalogue_code.settle's rule 1 leaves it, or not."""
    from specimen_digitization.application import barcode

    row = Evidence(kind=barcode.KIND, asset_id="a", region_id="L1", source=barcode.SOURCE, locator=barcode.LOCATOR,
        excerpt=barcode.EXCERPT.format(field=CATALOGUE, payload=payload, decoder="zxing-cpp", version="3.1.1",
            rung="whole"))
    run.evidence.append(row)
    value = run.fields[CATALOGUE]
    run.fields[CATALOGUE] = value.model_copy(update={"layer": "settled", **({"evidence_ids": [row.id],
        "evidence_relations": {row.id: "decides"}} if decides else {})})
    return run


def test_a_label_whose_catalogue_number_the_slide_code_confirms_holds_only_for_its_other_fields():
    """105526522 in the stored runs: the code confirms the number; the readers of its label differ, and the label
    also gives the collection code (optional). The number is the code's, read from the image, so the readers'
    doubt touches only the optional field."""
    run = with_the_code(a_run())
    assert field_step.code_confirmed(run) == {CATALOGUE}
    assert field_step.split_reasons(run, ["unresolved_transcription:L1"], mandatory=(CATALOGUE,)) == (
        [], ["unresolved_transcription:L1"])
    assert field_step.split_reasons(run, ["independent_observations_missing:L1"], mandatory=(CATALOGUE,)) == (
        [], ["independent_observations_missing:L1"])


def same_specimen_new_run(run):
    """The run's labels as a second run of the same specimen draws them: new ids, the same image."""
    regions = [region.model_copy(update={"id": "N" + region.id}) for region in run.regions]
    fields = {key: value.model_copy(update={"source_region_id": "N" + value.source_region_id}
        if value.source_region_id else {}) for key, value in run.fields.items()}
    return run.model_copy(update={"regions": regions, "fields": fields})


def changed(run, literal):
    value = run.fields[CATALOGUE]
    run.fields[CATALOGUE] = value.model_copy(update={"literal": literal, "parsed": None})
    return run


@pytest.mark.parametrize("case", ["no-code", "marked-differs", "marked-text-only", "stale-relation",
    "changed-by-a-person", "changed-by-research", "another-image", "a-second-run"])
def test_a_catalogue_number_the_code_does_not_confirm_keeps_its_label_s_hold(case):
    """105526487 in the stored runs: the code contradicts the number (barcode_differs), which holds the record
    by itself and keeps its label's reason holding too. Confirmation is recomputed on the run as it is now
    (Codex round 1 on #455), never read from a relation alone: a stale `decides` relation over a decode of
    another number; a value a person or research changed after the code confirmed it; a decode row of another
    image, or one a second run of the specimen does not hold among its labels."""
    run = a_run() if case == "no-code" else with_the_code(a_run(),
        payload="9999999" if case == "stale-relation" else "0010001")
    if case == "changed-by-a-person":
        changed(run, "FMNH-INS 0010002").fields[CATALOGUE].reason = "A person corrected the number."
    elif case == "changed-by-research":
        changed(run, "FMNH-INS 0010011")
    elif case == "another-image":
        run.evidence[-1] = run.evidence[-1].model_copy(update={"asset_id": "another-image"})
    elif case == "a-second-run":
        run = same_specimen_new_run(run)
    if case.startswith("marked"):
        why = "barcode_differs" if case == "marked-differs" else "text_only"
        run.findings.append(RunFinding(rule_id=field_step.SETTLEMENT, rule_version="1", severity="warning",
            field_key=CATALOGUE, reason_code=f"marked:{CATALOGUE}:L1:{why}"))
    assert field_step.code_confirmed(run) == frozenset()
    label = run.regions[0].id
    reasons = [f"unresolved_transcription:{label}", f"marked:{CATALOGUE}:{label}:barcode_differs"]
    assert field_step.split_reasons(run, reasons, mandatory=(CATALOGUE,)) == (reasons, [])


def test_the_code_confirms_a_value_whose_relation_is_gone_but_whose_number_is_the_code_s():
    """Recomputed, not read: the same number with no stored relation is confirmed all the same."""
    assert field_step.code_confirmed(with_the_code(a_run(), decides=False)) == {CATALOGUE}


# ---- a person's pending holds survive every finalize (Codex round 1 on #455) ----------------------

def test_a_pending_approval_survives_research_after_a_retry(tmp_path, monkeypatch):
    """Through the routes: research leaves an optional field unresolved (the record clears); a person's edit
    (here the approval hold the decisions route leaves, set by hand) holds it for approval; Retry puts the
    unresolved field to research again; the research's finalize keeps human_approval_required until a
    person approves. On main the same research dropped it too (finalize_fields recomputes the reasons), but
    there a mandatory field's own reason almost always held the record anyway."""
    from test_approval_and_research import act, queue_in_place, run_to_rest, save_by_hand, unresolved_country
    from test_step import decide, mounted, review_client

    rig = build_rig(tmp_path, profile=published())
    mounted(rig, unresolved_country())
    done = run_to_rest(rig)
    assert done.run.disposition == Disposition.CLEARED and done.run.fields["country"].state == ValueState.UNRESOLVED

    def a_persons_edit(run):
        # What a person's decision records (api.py apply_decision: person_acted) and leaves.
        run.pending_review, run.reasons, run.disposition = [field_step.APPROVAL], [field_step.APPROVAL], \
            Disposition.REVIEW

    save_by_hand(rig, a_persons_edit, "pending-approval")
    client = review_client(rig)
    queue_in_place(monkeypatch)
    from specimen_digitization.application.workflow import FIELD_RESEARCH

    retried = act(client, rig, "retry", "retry-research")
    assert FIELD_RESEARCH not in retried.run.completed_steps
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.fields["country"].state == ValueState.SUPPORTED
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [field_step.APPROVAL])
    approved = decide(client, rig, "approve-after-retry", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)


def test_a_location_reassessment_left_unconfirmed_survives_a_recheck_until_approval(tmp_path):
    from specimen_digitization.application.standing_holds import note_pending, replace_reassessment

    _, run = settled_under(tmp_path, everything_settles, published())
    # What FieldResearchStep._retained_reassessment records.
    note_pending(run, "location_reassessment_unconfirmed:city")
    run.reasons = ["snapshot_limit_exceeded"]  # a blocker replaced the list: the hold is derived anyway
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["location_reassessment_unconfirmed:city"])
    # The reassessment that settles it records what it still leaves unconfirmed itself.
    replace_reassessment(run, [])
    field_step.finalize_fields(run, None, (), today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    note_pending(run, "location_reassessment_unconfirmed:city")
    run.human_approved = True
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


def test_the_summary_counts_an_optional_fields_doubt_for_its_field(tmp_path):
    """Codex round 1 on #455: the server's per-field counts read both lists, as they read reason_codes
    before; the record's reason_codes and disposition read the holding reasons alone."""
    from specimen_digitization.application.api import summary
    from specimen_digitization.application.review_summary import project_fields, review_summary

    rig, run = settled_under(tmp_path, taxon_and_habitat_lacking, published())
    assert run.disposition == Disposition.CLEARED and run.reasons == []
    listed = summary(rig.specimen, "reviewer")
    assert listed["reason_codes"] == [] and listed["open_reason_codes"] == run.open_reasons
    fields = project_fields({key: value.model_dump(mode="json") for key, value in run.fields.items()})
    assert listed["review_summary"] == review_summary(fields, run.open_reasons)
    assert listed["review_summary"]["review"] > review_summary(fields, [])["review"]


def test_open_reasons_are_left_out_of_a_stored_run_while_empty():
    """Additive: a run with none keeps its stored bytes (domain.Run.open_reasons)."""
    run = Run()
    assert "open_reasons" not in run.model_dump(mode="json")
    run.open_reasons = ["taxonomy_unresolved"]
    assert run.model_dump(mode="json")["open_reasons"] == ["taxonomy_unresolved"]
    assert Run.model_validate(run.model_dump(mode="json")).open_reasons == ["taxonomy_unresolved"]


# ---- through the rig: the published profile against every field mandatory ----------------------

def only_the_catalogue_number():
    text = f"{CATALOGUE}: {LABEL[CATALOGUE]}"
    candidates = [(CATALOGUE, name, LABEL[CATALOGUE], text) for name in ("1A", "1B")]
    script = Scripted({key: answering(LACKS) for key in LABEL if key != CATALOGUE} | {
        "collectors": answering(LACKS)})
    return text, None, candidates, script


def readers_differ_on_the_collectors():
    """test_review_rules' Smith/Smyth label: the collectors' expert settles 1A's text, the readers disagree."""
    return TEXT, SMYTH, every_field(*SMITH_OR_SMYTH), Scripted({
        "collectors": answering(resolved("J. Smith", reading="1A"))})


def everything_settles():
    return TEXT, None, every_field(), Scripted()


def taxon_and_habitat_lacking():
    return TEXT, None, every_field(), Scripted({"taxon": answering(LACKS), "habitat": answering(LACKS)})


def catalogue_number_lacking():
    return TEXT, None, every_field(), Scripted({CATALOGUE: answering(LACKS)})


def country_too_large():
    """The country's research stops: its request is too large to send (a failure, not a doubt)."""
    return TEXT, None, every_field(), Scripted({"country": failing("input_too_large")})


def country_fallback():
    async def script(task, readings, tools):
        return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", explanation="Exhausted."),
            fallback=True, model_calls=3)
    return TEXT, None, every_field(), Scripted({"country": script})


SCENARIOS = {
    "everything-settles": (everything_settles, Disposition.CLEARED),
    "only-the-catalogue-number": (only_the_catalogue_number, Disposition.CLEARED),
    "taxon-and-habitat-lacking": (taxon_and_habitat_lacking, Disposition.CLEARED),
    # The label the catalogue number is drawn from holds when its readers differ, whatever field they differ on.
    "readers-differ-on-the-catalogue-label": (readers_differ_on_the_collectors, Disposition.REVIEW),
    "catalogue-number-lacking": (catalogue_number_lacking, Disposition.REVIEW),
    # The coordinator's ruling of 2026-11-18: an optional field research could not finish is that field's
    # doubt; the field stays open with its reason.
    "country-request-too-large": (country_too_large, Disposition.CLEARED),
    "country-expert-fell-back": (country_fallback, Disposition.CLEARED),
}


def settled_under(tmp_path, scenario, profile):
    text, other, candidates, script = scenario()
    rig = build_rig(tmp_path, text, other, candidates=candidates, profile=profile)
    settle(rig, script)
    return rig, rig.specimen.run


LAYERS = ("state", "literal", "parsed", "normalized", "authority_id", "layer", "reason", "precision", "derived_from")


def named(run, text):
    """The text with each label's id as its place in the run (two rigs make different ids)."""
    for i, region in enumerate(run.regions):
        text = text.replace(region.id, f"L{i + 1}")
    return text


def comparable(run):
    """Each field's value and wording and each finding, with the ids two rigs draw differently left out."""
    return ({key: {layer: getattr(value, layer) for layer in LAYERS} for key, value in run.fields.items()},
        [(f.rule_id, f.severity, f.field_key, named(run, f.reason_code), len(f.evidence_ids)) for f in run.findings])


def reasons(run, which):
    return {named(run, reason) for reason in which}


@pytest.mark.parametrize(("name", "expected"), [(name, d) for name, (_, d) in SCENARIOS.items()], ids=list(SCENARIOS))
def test_the_published_profile_changes_only_which_reasons_hold(tmp_path, name, expected):
    """Every field's state, value, layer, evidence and reason text, and every finding (marks included), are the
    same under the published profile as under the profile with every field mandatory; the reasons are the same
    set, split between those that hold and the optional fields' doubts, with research_incomplete added for an
    optional field research could not finish. The record clears exactly when no reason holds."""
    scenario = SCENARIOS[name][0]
    _, every = settled_under(tmp_path / "every", scenario, field_mechanics_profile())
    _, skeletal = settled_under(tmp_path / "skeletal", scenario, published())
    assert comparable(skeletal) == comparable(every)
    holding, open_ = reasons(skeletal, skeletal.reasons), reasons(skeletal, skeletal.open_reasons)
    # Added beside the reasons: an optional field research could not finish; a field an open label doubt
    # reaches (step.label_attention).
    incomplete = {r for r in open_ if r.startswith((field_step.INCOMPLETE + ":", field_step.LABEL_UNSETTLED + ":"))}
    assert holding | open_ - incomplete == reasons(every, every.reasons)
    assert not holding & open_
    assert skeletal.disposition == expected == (Disposition.CLEARED if not skeletal.reasons else Disposition.REVIEW)
    assert every.disposition == (Disposition.CLEARED if name == "everything-settles" else Disposition.REVIEW)


def test_a_label_with_only_the_catalogue_number_clears_with_every_other_field_blank(tmp_path):
    """The owner's "Where there is no field related data on the lable, nothing to do, it will get cleared": PR #451's
    no_specimen_value guard held this record; it is removed."""
    _, run = settled_under(tmp_path, only_the_catalogue_number, published())
    assert (run.disposition, run.reasons, run.stage) == (Disposition.CLEARED, [], "finalized")
    assert run.fields[CATALOGUE].state == ValueState.SUPPORTED
    assert all(value.state != ValueState.SUPPORTED for key, value in run.fields.items() if key != CATALOGUE)
    assert "no_specimen_value" not in run.reasons + run.open_reasons
    # What is open is kept: the taxon's doubt among them.
    assert {"taxonomy_unresolved", "mandatory_unresolved:taxon"} <= set(run.open_reasons)


def test_an_optional_field_research_could_not_finish_stays_open_with_its_reason(tmp_path):
    """The coordinator's ruling of 2026-11-18: an optional field's failure or fallback is that field's doubt. The
    field stays unresolved with a reason a reviewer reads; the reason is kept through refinalize."""
    _, run = settled_under(tmp_path, country_too_large, published())
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert {"research_incomplete:country", "mandatory_unresolved:country"} <= set(run.open_reasons)
    assert run.fields["country"].state == ValueState.UNRESOLVED
    assert run.fields["country"].reason == field_step.FIELD_REASONS["input_too_large"]
    field_step.refinalize(run, today=TODAY)
    assert run.disposition == Disposition.CLEARED and "research_incomplete:country" in run.open_reasons


def test_research_given_up_for_the_run_holds_through_refinalize_until_a_person_approves(tmp_path):
    """FieldResearchStep.give_up: every field it would research fails as run_limit. That is the run not
    finishing, not a field's doubt: field_research_given_up holds, also on a record whose catalogue number an
    earlier attempt settled."""
    _, run = settled_under(tmp_path, everything_settles, published())
    assert run.disposition == Disposition.CLEARED
    # The give-up records its finding and finalizes: every field it would research (all but the catalogue
    # number, settled earlier) fails as run_limit (FieldResearchStep.give_up).
    run.findings.append(RunFinding(rule_id=field_step.GIVEN_UP, rule_version=field_step.GIVEN_UP_RULES,
        severity="warning", reason_code=f"{field_step.GIVEN_UP}:token_budget_exhausted"))
    field_step.finalize_fields(run, None, [FieldOutcome(key, None, failure="run_limit")
        for key in published().optional_fields if key != "identified_by_irn"], today=TODAY)
    assert run.fields[CATALOGUE].state == ValueState.SUPPORTED
    assert field_step.GIVEN_UP in run.reasons and run.disposition == Disposition.REVIEW
    run.reasons = ["snapshot_limit_exceeded"]  # a blocker replaced the list: the hold is derived anyway
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [field_step.GIVEN_UP])
    run.human_approved = True
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


def test_a_person_s_decision_and_coverage_still_hold_a_record_whose_optional_fields_are_open(tmp_path):
    _, run = settled_under(tmp_path, taxon_and_habitat_lacking, published())
    assert run.disposition == Disposition.CLEARED
    from specimen_digitization.application.standing_holds import person_acted

    person_acted(run)  # what the decisions route records where a person's decision enters
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [field_step.APPROVAL])
    run.human_approved = True
    run.coverage_confirmed = False
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["label_coverage_unconfirmed"])


# ---- the ordinary path ----------------------------------------------------------------------------

def test_the_ordinary_path_splits_the_same_way(tmp_path):
    """policy.finalize: the optional fields' doubts go to open_reasons, every other reason still holds (its
    institutional approval and human approval among them); every field a label writes is still checked."""
    _, run = settled_under(tmp_path, taxon_and_habitat_lacking, published())
    every = policy.evaluate(run)
    policy.finalize(run)
    assert set(run.reasons) | set(run.open_reasons) == set(every)
    assert {"mandatory_unresolved:taxon", "mandatory_unresolved:habitat"} <= set(run.open_reasons)
    assert {"human_approval_required", "institutional_policy_unapproved"} <= set(run.reasons)
    assert run.disposition == Disposition.REVIEW
