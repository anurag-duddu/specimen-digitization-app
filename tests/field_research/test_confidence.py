"""Confident or flagged (field_research/confidence.py, lane Q1 of the autonomy program).

The rules read only what the run recorded about a field (its literal, the readers' verbatims for it,
its label rows, the organiser's candidates for it, the settlement's finding, its derivation sources),
compare exactly, and do not mark where what they need is not recorded. The cases are the stored runs'
(`~/specimen-golive/runs/`, the 100 truth slides) and the review findings of Codex rounds 1 and 2 on
PR #454, each with its outcome under these rules: several are now "not marked", stated in the test.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState
from specimen_digitization.field_research import confidence
from specimen_digitization.field_research.contracts import Candidate, Reading
from specimen_digitization.field_research.step import marked_reasons

RULES = published_registry().profiles[0].date_rules
LABEL = "L1"
READINGS = tuple(Reading(name, LABEL, f"o{name}", "raw_reading", "label text") for name in ("1A", "1B"))


def value(literal, *, layer="settled", verbatims=(), excerpt=None, key="f", **more):
    """A settled value; `verbatims` the readers' recorded verbatims (1A's, 1B's); `excerpt` its label row's."""
    rows = [Evidence(id=f"row-{key}", kind="literal", region_id=LABEL, source="field_research", locator=None,
        excerpt=excerpt)] if excerpt is not None else []
    return FieldValue(state=ValueState.SUPPORTED, literal=literal, layer=layer, source_region_id=LABEL,
        verbatim_by_observation={f"o1{chr(65 + i)}": text for i, text in enumerate(verbatims)},
        evidence_ids=[row.id for row in rows], **more), rows


def cleared(key):
    return RunFinding(rule_id="field_settlement", rule_version="v", severity="info", field_key=key,
        reason_code=f"cleared:{key}:{LABEL}")


def run_of(fields, *, findings=(), dependencies=None):
    """fields: {key: (FieldValue, rows)}."""
    return SimpleNamespace(fields={key: item[0] for key, item in fields.items()},
        evidence=[row for item in fields.values() for row in item[1]], findings=list(findings),
        dependencies=dependencies or {})


def review(run, readings=READINGS):
    confidence.review(run, readings=readings, date_rules=RULES)
    return sorted(marked_reasons(run))


def derived(source, parsed):
    return FieldValue(state=ValueState.SUPPORTED, parsed=parsed, layer="derived", derived_from=[source]), []


# ---- rule 1: the recorded verbatims differ and only the image can have cleared the value ---------

@pytest.mark.parametrize(("first", "second", "marked"), [
    ("24-VII-1916", "24-VI-1916", True),          # 105526392
    ("-80 m", "80 m", True),                      # Codex round 2, 4: a sign
    ("1.5 km N", "15 km N", True),                # Codex round 1, 3: a decimal point
    ("80-90 m", "8090 m", True),                  # Codex round 2, 4: a hyphen between numbers
    ("28- III -1974", "28- III-1974", True),      # spacing inside: marked too (exact comparison)
    ("J. Smith", "J. Smyth", True),               # Codex round 1, 4: the collector's own verbatims
    ("J. Smith", "J. Smith", False),              # Codex round 2, 5: the determiner line plays no part
    ("Shrubs ", "Shrubs", False),                 # outer white space only
])
def test_readers_differ_compares_the_recorded_verbatims_exactly(first, second, marked):
    run = run_of({"collectors": value(first, verbatims=(first, second), key="collectors")},
        findings=[cleared("collectors")])
    assert (review(run) == ["marked:collectors:L1:readers_differ"]) is marked


def test_readers_differ_reads_only_the_fields_no_source_checks():
    """Codex round 3, 3: a locality, a place or a taxon may be cleared by a source ("York" against "Yrok",
    TGN confirming York): this rule never marks them. The dates, elevations and catalogue number have
    checks but no source, so only the image clears them."""
    assert confidence.IMAGE_ONLY_FIELDS == {"date_visited_from", "date_visited_to", "date_identified",
        "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft", "fmnh_ins_number",
        "collectors", "collection_code", "habitat", "collection_method", "verbatim_dts"}
    for key in ("precise_location", "city", "province_state", "country", "county", "taxon"):
        run = run_of({key: value("York", verbatims=("York", "Yrok"), key=key)}, findings=[cleared(key)])
        assert review(run) == [], key


def test_readers_differ_needs_two_recorded_verbatims_a_clearing_and_no_deciding_row():
    one = run_of({"collectors": value("J. Smith", verbatims=("J. Smith",), key="collectors")},
        findings=[cleared("collectors")])
    assert review(one) == []
    no_clear = run_of({"collectors": value("J. Smith", verbatims=("J. Smith", "J. Smyth"), key="collectors")})
    assert review(no_clear) == []
    code = run_of({"fmnh_ins_number": value("4486518", verbatims=("4486518", "4486618"), key="fmnh_ins_number",
        evidence_relations={"code": "decides"})}, findings=[cleared("fmnh_ins_number")])
    assert review(code) == []


# ---- rule 2, decisions and research passes ----------------------------------------------------------

def from_and_to(**more):
    return run_of({"date_visited_from": value("5-VII-1940", verbatims=("5-VII-1940", "5-VI-1940"), **more),
        "date_visited_to": derived("date_visited_from", "1940-07-05")}, findings=[cleared("date_visited_from")])


def test_a_value_derived_from_a_marked_one_is_marked_with_it():
    """105526355."""
    assert review(from_and_to()) == ["marked:date_visited_from:L1:readers_differ",
        "marked:date_visited_to:L1:follows_marked"]


def test_a_decision_drops_the_field_s_marks_and_its_dependents_follows_marked_and_recomputes_nothing():
    """Codex round 3, 1a: a person confirms the derived To while its From is still marked: To's mark goes
    and nothing puts it back. A person confirms the From: its mark and To's follows_marked go."""
    run = from_and_to()
    review(run)
    confidence.forget(run, "date_visited_to")
    assert marked_reasons(run) == ["marked:date_visited_from:L1:readers_differ"]
    run = from_and_to()
    review(run)
    confidence.forget(run, "date_visited_from")
    assert marked_reasons(run) == []


def test_a_research_pass_recomputes_only_the_fields_it_researched_or_derived():
    """As step.build_tasks leaves a settled field unresearched on a retry, the pass leaves its marks, or
    their absence, as they are; on a field it researched it drops and recomputes them."""
    run = from_and_to()
    review(run)
    confidence.forget(run, "date_visited_from")
    confidence.review(run, readings=READINGS, date_rules=RULES, researched={"habitat"})
    assert marked_reasons(run) == []
    run.fields["date_visited_from"].verbatim_by_observation = {"o1A": "5-VI-1940", "o1B": "5-VI-1940"}
    run.findings.append(RunFinding(rule_id=confidence.RULE, rule_version="v", severity="warning",
        field_key="date_visited_from", reason_code="marked:date_visited_from:L1:readers_differ"))
    confidence.review(run, readings=READINGS, date_rules=RULES, researched={"date_visited_from"})
    assert marked_reasons(run) == []


# ---- persons ------------------------------------------------------------------------------------

def held_run(**more):
    return run_of({"collectors": value("J. Smith", verbatims=("J. Smith", "J. Smyth"), key="collectors",
        excerpt="J. Smith")}, findings=[cleared("collectors")], **more)


@pytest.mark.parametrize("record", [
    {"human_review_field_locks": {"collectors": {"selection_id": "s1"}}},  # a locked research selection
    {"location_reassessment": {"protected": ["collectors"]}},             # Codex round 2, 2: reassessment
])
def test_no_mark_lands_on_a_field_a_person_holds(record):
    assert review(held_run()) == ["marked:collectors:L1:readers_differ"]
    assert review(held_run(dependencies=record)) == []


def test_no_mark_lands_on_a_carried_or_person_transcribed_field():
    run = held_run()
    confidence.review(run, readings=READINGS, human={"collectors"}, date_rules=RULES)
    assert marked_reasons(run) == []
    person = (Reading("1A", LABEL, "o1A", "decided_transcript", "label text", person_decided=True), READINGS[1])
    assert review(held_run(), person) == []


def test_the_pass_never_changes_a_field():
    """Codex round 2, 1: a mark is a finding only."""
    run = from_and_to(reason="Read.")
    before = {key: item.model_copy(deep=True) for key, item in run.fields.items()}
    review(run)
    confidence.forget(run, "date_visited_from")
    assert run.fields == before


def test_a_reassessment_computes_no_mark_and_drops_the_marks_of_a_value_it_replaces(tmp_path, monkeypatch):
    """Codex round 3, 2: a City's mark does not survive its replacement by the reassessment."""
    from test_location_reassessment import execute, old_location_run

    rig = old_location_run(tmp_path)
    region = rig.specimen.run.regions[0].id
    rig.specimen.run.findings.append(RunFinding(rule_id=confidence.RULE, rule_version="v", severity="warning",
        field_key="city", reason_code=f"marked:city:{region}:readers_differ"))
    before, done, *_ = execute(rig, monkeypatch)
    assert done.run.fields["city"] != before.fields["city"]
    assert not [finding for finding in done.run.findings if finding.rule_id == confidence.RULE]


# ---- rule 3: the organiser's agreed candidate is longer ----------------------------------------

def candidates(*pairs):
    return [Candidate(reading, literal, literal, f"c{n}") for n, (reading, literal) in enumerate(pairs)]


@pytest.mark.parametrize(("pairs", "literal", "marked"), [
    ((("1A", "ex Peromyscus leucopus"), ("1B", "ex Peromyscus  leucopus")), "ex Peromyscus", True),   # 105526617
    ((("1A", "ex Peromyscus leucopus"), ("1B", "ex Peromyscus leucopas")), "ex Peromyscus", False),   # not agreed
    ((("1A", "ex Peromyscus leucopus"),), "ex Peromyscus", False),                                    # one reader
    ((("1A", "Meriones"), ("1B", "Meriones")), "Meriones", False),        # Codex round 2, 6: "Meriones\nCHILE"
    ((("1A", "Forest"), ("1B", "Forest")), "Forest", False),              # Codex round 2, 5: the City's unit
    ((("1A", "ex Peromyscus leucopus"), ("1B", "ex Peromyscus leucopus")), "ex Peromyscus leucopus\nShidler",
        False),                                                          # Codex round 1, 5: now not marked
])
def test_extent_marks_only_a_literal_inside_the_readers_agreed_candidate(pairs, literal, marked):
    found, _ = value(literal)
    assert confidence.extent("habitat", found, candidates(*pairs), READINGS) is marked


# ---- rules 4 and 5: conventions ------------------------------------------------------------------

def test_a_town_after_a_distance_is_no_longer_marked():
    """Codex round 3, 4: the distance rule is removed ("York" inside "Yorktown"); it waits for a rule on
    recorded spans."""
    fields = {"city": value("York", excerpt="27 km north of Yorktown; collected in York", key="city")}
    assert review(run_of(fields)) == []
    assert not hasattr(confidence, "distance_origin")


@pytest.mark.parametrize(("literal", "flagged"), [
    ("LEWIS COLLECTION", False), ("LEWIS\nCOLLECTION", False), ("FM SUB.563", True), ("FMA 8 SUB. 664", True),
    ("RMT 1149", True), ("1X-17-66-1", True),
])
def test_only_the_ruled_heading_is_a_collection_code(literal, flagged):
    assert confidence.not_collection_code("collection_code", value(literal, layer="verbatim")[0]) is flagged


@pytest.mark.parametrize(("literal", "flagged"), [
    ("1X-14-46", True),               # an exact day, a digit one for the I (105526325)
    ("3 sept. '46", True),
    ("1916 IV-29-68-4", True),        # Codex on PR #453: a slide code as one of its words
    ("IX-3-66-10", True),
    ("17.Mar.1934 10:30", False),     # Codex on PR #453: an exact date with a clock time: now not marked
    ("VI.'41", False), ("XI.'46", False), ("1916", False), ("III.87", False), ("Nov, Dec 1955", False),
    ("XII-1970 I-1971", False), ("July-Aug. 1950", False),
])
def test_verbatim_dts_reads_only_its_own_literal(literal, flagged):
    assert confidence.not_verbatim_date("verbatim_dts", value(literal, layer="verbatim")[0], RULES) is flagged


def test_the_identification_date_plays_no_part():
    """Codex round 2, 7 and round 1, 8: the same month as Date Identified marks nothing."""
    run = run_of({"date_identified": value("XI.'46"), "verbatim_dts": value("XI.'46", layer="verbatim")})
    assert review(run) == []


def test_every_why_has_a_plain_code():
    assert confidence.WHYS == ("readers_differ", "follows_marked", "extent", "not_collection_code", "not_verbatim_date")


# ---- the guard ----------------------------------------------------------------------------------

def test_an_exception_inside_the_pass_leaves_the_run_exactly_as_without_it(monkeypatch):
    """Codex round 1, 2: the pass never fails research. Raised at the start, in a rule, and after a
    finding has been added."""
    without = from_and_to()

    def boom(*args, **kwargs):
        raise RuntimeError("forced")

    for target in ("person_holds", "readers_differ", "_marked_fields"):
        with monkeypatch.context() as patch:
            patch.setattr(confidence, target, boom)
            run = from_and_to()
            confidence.guarded(run, confidence.review, readings=READINGS, date_rules=RULES)
            assert run.fields == without.fields and run.findings == without.findings, target
    with monkeypatch.context() as patch:
        made = []

        def late(**kwargs):
            if made:
                raise RuntimeError("forced")
            made.append(kwargs)
            return RunFinding(**kwargs)

        patch.setattr(confidence, "RunFinding", late)
        run = from_and_to()
        confidence.guarded(run, confidence.review, readings=READINGS, date_rules=RULES)
        assert run.fields == without.fields and run.findings == without.findings


# ---- a person's decision, through the decision endpoint ------------------------------------------

def test_a_person_confirming_a_marked_value_unchanged_takes_the_mark_off_and_the_audit_matches(tmp_path):
    """Codex rounds 1 and 2, 1: readers "Shrubs" and "Shurbs", the image naming 1A's; research marks the
    habitat readers_differ. A reviewer confirms it by submitting the existing FieldValue unchanged: the
    mark goes, the saved field equals the decision's `after` exactly (the comparison
    human_field_carry.prepare makes before a reprocess), and the approval's refinalize adds nothing."""
    from test_settlement_rule import HABITATS, naming
    from test_step import TEXT, Scripted, answering, build_rig, decide, mounted, reasons_for, resolved, review_client

    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=HABITATS)
    naming(rig, 0)
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "naming", "naming")
    mounted(rig, Scripted({"habitat": answering(resolved("Shrubs", reading="1A"))}))
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    region = done.regions[0].id
    assert reasons_for(done, "habitat") == [f"marked:habitat:{region}:readers_differ"]
    client = review_client(rig)
    habitat = done.fields["habitat"]
    after = habitat.model_dump(mode="json", exclude={"evidence_ids"})
    decided = decide(client, rig, "field-habitat", "field", target_id="habitat", after=after,
        evidence_ids=list(habitat.evidence_ids))
    assert decided.fields["habitat"] == FieldValue.model_validate(dict(after, evidence_ids=habitat.evidence_ids))
    assert reasons_for(decided, "habitat") == []
    approved = decide(client, rig, "approve-habitat", "approve")
    assert reasons_for(approved, "habitat") == []
    assert approved.fields["habitat"] == decided.fields["habitat"]


def test_an_ordinary_retry_after_a_person_confirms_a_marked_field_leaves_it_unmarked(tmp_path, monkeypatch):
    """Codex round 3, 1b: a person confirms Habitat "Shrubs" (readers "Shrubs", "Shurbs"), the Country is
    unresolved, an ordinary Retry researches again with no carry. As on main, where the retry researches
    only the unsettled fields (step.build_tasks) and leaves the confirmed one and its marks as they are,
    the pass recomputes only what the retry researched: Habitat stays unmarked."""
    from test_settlement_rule import HABITATS, naming
    from test_step import (
        LABEL as STEP_LABEL, ORG, TEXT, FieldAnswer, Scripted, answering, build_rig, decide, mounted, reasons_for,
        resolved, review_client,
    )

    from specimen_digitization.application import api as app_api

    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=HABITATS)
    naming(rig, 0)
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "naming", "naming")
    unresolved = answering(FieldAnswer(outcome="sources_cannot_resolve", literal=STEP_LABEL["country"],
        reading_names=["1A"], explanation="Cannot settle."))
    mounted(rig, Scripted({"habitat": answering(resolved("Shrubs", reading="1A")), "country": unresolved}))
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert reasons_for(done, "habitat") == [f"marked:habitat:{done.regions[0].id}:readers_differ"]
    client = review_client(rig)
    habitat = done.fields["habitat"]
    decide(client, rig, "field-habitat", "field", target_id="habitat",
        after=habitat.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(habitat.evidence_ids))
    monkeypatch.setattr(app_api, "queue", lambda specimen, registry, actor: setattr(specimen.run, "stage", "pending"))
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": "retry"},
        json={"expected_revision": current.version, "action": "retry", "reason": "Retry."})
    assert response.status_code == 200, response.text
    second = Scripted({"habitat": answering(resolved("Shrubs", reading="1A")), "country": unresolved})
    mounted(rig, second)
    again = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert "habitat" not in second.calls and "country" in second.calls
    assert reasons_for(again, "habitat") == []
    assert again.fields["habitat"] == habitat
