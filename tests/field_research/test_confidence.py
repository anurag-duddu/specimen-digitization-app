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


# ---- rule 1: the readers' recorded verbatims differ and the image alone backs the value ---------

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
    run = run_of({"f": value(first, verbatims=(first, second))}, findings=[cleared("f")])
    assert (review(run) == [f"marked:f:{LABEL}:readers_differ"]) is marked


def test_readers_differ_needs_two_recorded_verbatims_and_an_image_only_backing():
    one = run_of({"f": value("24-VII-1916", verbatims=("24-VII-1916",))}, findings=[cleared("f")])
    assert review(one) == []
    no_clear = run_of({"f": value("24-VII-1916", verbatims=("24-VII-1916", "24-VI-1916"))})
    assert review(no_clear) == []
    decided = run_of({"f": value("Kunduz", verbatims=("Kunduz", "Kundus"), evidence_relations={"e": "decides"})},
        findings=[cleared("f")])
    assert review(decided) == []
    place = run_of({"province_state": value("Kunduz", verbatims=("Kunduz", "Kundus"), authority_id="tgn:1",
        key="province_state")}, findings=[cleared("province_state")])
    assert review(place) == []


# ---- rule 2 and recomputation ----------------------------------------------------------------------

def from_and_to(**more):
    return run_of({"date_visited_from": value("5-VII-1940", verbatims=("5-VII-1940", "5-VI-1940"), **more),
        "date_visited_to": derived("date_visited_from", "1940-07-05")}, findings=[cleared("date_visited_from")])


def test_a_value_derived_from_a_marked_one_is_marked_with_it():
    """105526355."""
    assert review(from_and_to()) == ["marked:date_visited_from:L1:readers_differ",
        "marked:date_visited_to:L1:follows_marked"]


def test_marks_are_recomputed_not_accumulated():
    """Codex round 2, 3: a person confirms the From; its mark goes, and refinalize's recomputation takes
    the derived To's follows_marked away with it. A second review drops what no longer holds."""
    run = from_and_to()
    review(run)
    confidence.forget(run, {"date_visited_from"})
    confidence.settle_after_decision(run)
    assert marked_reasons(run) == []
    again = from_and_to()
    review(again)
    again.fields["date_visited_from"].verbatim_by_observation = {"o1A": "5-VI-1940", "o1B": "5-VI-1940"}
    assert review(again) == []


# ---- persons ------------------------------------------------------------------------------------

@pytest.mark.parametrize("record", [
    {"human_review_field_locks": {"city": {"selection_id": "s1"}}},     # a locked research selection
    {"location_reassessment": {"protected": ["city"]}},                  # Codex round 2, 2: reassessment
])
def test_no_mark_lands_on_a_field_a_person_holds(record):
    """Codex round 2, 2: a person selected City "Shidler"; reassessment protects it."""
    fields = {"city": value("Kunduz", excerpt="27 km. north of Kunduz", key="city")}
    assert review(run_of(fields)) == ["marked:city:L1:distance_origin"]
    assert review(run_of(fields, dependencies=record)) == []


def test_no_mark_lands_on_a_carried_or_person_transcribed_field():
    fields = {"city": value("Kunduz", excerpt="27 km. north of Kunduz", key="city")}
    run = run_of(fields)
    confidence.review(run, readings=READINGS, human={"city"}, date_rules=RULES)
    assert marked_reasons(run) == []
    person = (Reading("1A", LABEL, "o1A", "decided_transcript", "label text", person_decided=True), READINGS[1])
    assert review(run_of(fields), person) == []


def test_the_pass_never_changes_a_reason_or_any_other_part_of_a_field():
    """Codex round 2, 1: a mark is a finding only."""
    run = run_of({"date_visited_from": value("5-VII-1940", verbatims=("5-VII-1940", "5-VI-1940"), reason="Read."),
        "date_visited_to": derived("date_visited_from", "1940-07-05")}, findings=[cleared("date_visited_from")])
    before = {key: item.model_copy(deep=True) for key, item in run.fields.items()}
    review(run)
    confidence.forget(run, {"date_visited_from"})
    confidence.settle_after_decision(run)
    assert run.fields == before


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


# ---- rule 4: conventions -------------------------------------------------------------------------

@pytest.mark.parametrize(("excerpt", "literal", "marked"), [
    ("27 km. north of Kunduz", "Kunduz", True),          # 105527218
    ("14.5 km NNW Puerto Octay", "Puerto Octay", True),
    ("Shidler, Osage Co,", "Shidler,", False),           # 105526631: the distance is on the line before: not marked
    ("12 mi. N of Shidler and 3 mi. S of Fairfax", "Fairfax", True),
    ("Kunduz, 27 km. north", "Kunduz", False),
])
def test_a_place_after_a_distance_in_its_own_label_row_is_marked(excerpt, literal, marked):
    found, rows = value(literal, excerpt=excerpt, key="city")
    run = run_of({"city": (found, rows)})
    assert confidence.distance_origin(run, "city", found) is marked


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
    assert confidence.WHYS == ("readers_differ", "follows_marked", "extent", "distance_origin", "not_collection_code",
        "not_verbatim_date")


# ---- the guard ----------------------------------------------------------------------------------

def test_an_exception_inside_the_pass_leaves_the_run_exactly_as_without_it(monkeypatch):
    """Codex round 1, 2: the pass never fails research. Raised at the start, in a rule, and after a
    finding has been added."""
    without = from_and_to()

    def boom(*args, **kwargs):
        raise RuntimeError("forced")

    for target in ("person_holds", "readers_differ", "_follow"):
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
