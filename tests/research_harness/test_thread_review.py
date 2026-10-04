"""What the harness found for a field that waits for a person reaches the thread (W7c, item D3).

Owner, 2026-10-03: a field may stay unresolved because the label lacks it, because public sources
cannot settle it, or because several possibilities remain; all go to Needs human review "with the
candidates and the evidence shown". The thread carried only evidence ids and a question's text.
These tests drive the real GEOLocate adapter over its recorded live responses, store the capture in
real SQLite effects, commit real checkpoints and read the thread back through the real reader.
Offline: no network, no model call, no cost.
"""

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, HumanQuestion, SourceResult, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.persistence import (
    CapturedResult, DurableEffectBroker, ImmutableFileBlobs,
)
from specimen_digitization.research_harness.thread_view import ResearchThread, ResearchThreadReader
from test_geolocate_validator import APO, MCKINLEY, lookup
from test_research_harness_journal import setup

FIXTURE = Path(__file__).parents[1] / "fixtures" / "research_harness" / "http" / "unresolved-thread.json"
LOOSE_APO = {**APO, "latitude": 6.611, "longitude": 125.449, "radius_km": 50}
SYNTHETIC_LOCALITY = "Synthetic locality text"


class Rig:
    """One journal over real SQLite, with the real adapter's captures stored as durable effects."""

    def __init__(self, tmp_path):
        _, self.requests, self.journal, self.settings = setup(tmp_path)
        self.broker = DurableEffectBroker(self.journal.store, ImmutableFileBlobs(tmp_path / "blobs"))
        self.scope = next(iter(self.requests.values())).scope

    def capture(self, result, field_key):
        """Store an adapter result as the durable source effect the engine would have recorded."""
        payload = SourceResult.model_validate(json.loads(result.receipt.result_json)).model_dump(mode="json")
        return self.store_payload(payload, field_key, tag=result.coverage.reason)

    def store_payload(self, payload, field_key, *, tag, operation="source_lookup"):
        async def dispatch(*_):
            return CapturedResult(payload, 0)
        done = asyncio.run(self.broker.execute(
            self.journal.scope, self.journal.lease, f"{operation}:" + digest([str(field_key), tag]),
            {"field": str(field_key), "tag": tag}, 1, dispatch, execution_class="offline",
            field_keys=(str(field_key),)))
        return done.effect_id

    def commit(self, role, resolutions, effect_ids=()):
        asyncio.run(self.journal.commit(self.requests[role], tuple(resolutions), receipt_ids=tuple(effect_ids),
                                        model_settings_digest=self.settings))

    def thread(self):
        return asyncio.run(ResearchThreadReader(self.journal).read(self.scope))

    def field(self, key):
        return next(item for item in self.thread().fields if item.field_key == key)


def apo_ambiguous(rig):
    result = lookup("apo-modern.json", FieldKey.COUNTRY, LOOSE_APO, "Philippines")
    asked = HumanQuestion(field_key=FieldKey.COUNTRY, reason="semantic_ambiguity", coverage=(result.coverage,),
        question="Three places called Mount Apo lie up to 92 km apart. Which one does the label mean?",
        evidence_ids=tuple(item.id for item in result.evidence))
    return result, FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.WAITING_HUMAN, question=asked,
        value=FieldValue(state=ValueState.AMBIGUOUS, literal=SYNTHETIC_LOCALITY),
        reason="Three Mount Apo matches agree on the name and lie far apart")


def mckinley_no_match(rig):
    result = lookup("mckinley-modern.json", FieldKey.PROVINCE_STATE, MCKINLEY, "Davao del Sur")
    asked = HumanQuestion(field_key=FieldKey.PROVINCE_STATE, reason="scoped_absence", coverage=(result.coverage,),
        question="No gazetteer holds Mount McKinley on Mindanao. Which province does the label mean?",
        evidence_ids=tuple(item.id for item in result.evidence))
    return result, FieldResolution(field_key=FieldKey.PROVINCE_STATE, work_state=WorkState.WAITING_HUMAN,
        question=asked, value=FieldValue(state=ValueState.UNRESOLVED, literal=SYNTHETIC_LOCALITY),
        reason="No Mount McKinley on Mindanao in GEOLocate (nine matches elsewhere)")


def test_several_possibilities_reach_the_thread_with_each_candidate_and_its_receipt(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = apo_ambiguous(rig)
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [rig.capture(result, FieldKey.COUNTRY)])
    review = rig.field(FieldKey.COUNTRY).review
    assert review is not None
    assert review.question_reason == "semantic_ambiguity"
    assert review.reason == waiting.reason
    assert [item.authority_id for item in review.candidates] == [
        "geolocate:a863d52e6ff08fe2", "geolocate:a71cd5741681e8fa", "geolocate:3e5a153ca95eedd5"]
    assert [item.rank for item in review.candidates] == [1, 2, 3]
    [evidence] = review.evidence
    assert {item.evidence_id for item in review.candidates} == {evidence.evidence_id}
    assert {item.source_id for item in review.candidates} == {"geolocate"}
    assert (evidence.source_id, evidence.kind, evidence.outcome) == ("geolocate", "qualified_source", "ambiguous")
    assert evidence.note == "ambiguous: GEOLocate is ambiguous for 'Philippines': agreeing matches lie up to 92 km apart"
    # What was asked of the source is the interpretation's place text, not the label's own words.
    assert evidence.searched_text == "Mount Apo" and evidence.quote is None
    assert (review.evidence_not_shown, review.candidates_not_shown) == (0, 0)
    assert [(item.label, item.details, item.distance_km) for item in review.candidates] == [
        ("MOUNT APO", ("CENTRAL MINDANAO",), 46), ("MOUNT APO", ("RPP3",), 46), ("MOUNT APO", ("COTABATO",), 46)]


def test_public_sources_that_cannot_settle_it_show_the_receipt_and_no_invented_candidates(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = mckinley_no_match(rig)
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [rig.capture(result, FieldKey.PROVINCE_STATE)])
    review = rig.field(FieldKey.PROVINCE_STATE).review
    assert review.question_reason == "scoped_absence"
    assert review.candidates == ()
    [evidence] = review.evidence
    assert evidence.outcome == "no_match"
    assert "none is 'Mount McKinley' within 40 km" in evidence.note
    assert review.evidence_not_shown == 0


def test_a_field_waiting_for_policy_or_a_source_shows_the_reason_without_a_question(tmp_path):
    rig = Rig(tmp_path)
    rig.commit(SpecialistRole.COLLECTION, [
        FieldResolution(field_key=FieldKey.HABITAT, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(state=ValueState.NOT_PRESENT), reason="The label names no habitat"),
        FieldResolution(field_key=FieldKey.COLLECTION_METHOD, work_state=WorkState.WAITING_POLICY,
            value=FieldValue(state=ValueState.UNRESOLVED), reason="Two readings of the method differ"),
    ])
    habitat, method = rig.field(FieldKey.HABITAT), rig.field(FieldKey.COLLECTION_METHOD)
    assert habitat.review.question_reason is None and habitat.review.reason == "The label names no habitat"
    assert method.review.reason == "Two readings of the method differ"
    assert habitat.review.evidence == habitat.review.candidates == ()
    assert habitat.actions == () and method.actions == ()


def test_only_fields_that_wait_carry_a_review(tmp_path):
    rig = Rig(tmp_path)
    resolved = FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="Guatemala"), evidence_ids=("e1",), reason="accepted")
    failed = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.OPERATIONAL_FAILED,
        value=FieldValue(), reason="specialist_operational_failure")
    rig.commit(SpecialistRole.GEOGRAPHY, [resolved, failed])
    reviews = {item.field_key: item.review for item in rig.thread().fields}
    assert all(review is None for review in reviews.values())


def test_a_cited_evidence_id_the_journal_cannot_resolve_is_counted_never_invented(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = apo_ambiguous(rig)
    cited = waiting.question.evidence_ids + ("native-evidence-the-journal-does-not-hold",)
    waiting = waiting.model_copy(update={"question": waiting.question.model_copy(update={"evidence_ids": cited})})
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [rig.capture(result, FieldKey.COUNTRY)])
    review = rig.field(FieldKey.COUNTRY).review
    assert len(review.evidence) == 1 and review.evidence_not_shown == 1
    assert "native-evidence-the-journal-does-not-hold" not in review.model_dump_json()


def test_the_review_reads_only_the_fields_own_source_lookups_never_model_or_neighbor_captures(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = apo_ambiguous(rig)
    model_effect = rig.store_payload({"secret": "PRIVATE_CAPTURE_CANARY"}, FieldKey.COUNTRY, tag="m", operation="model")
    neighbor_result, _ = mckinley_no_match(rig)
    neighbor_effect = rig.capture(neighbor_result, FieldKey.PROVINCE_STATE)
    own_effect = rig.capture(result, FieldKey.COUNTRY)
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [model_effect, neighbor_effect, own_effect])
    review = rig.field(FieldKey.COUNTRY).review
    assert [item.outcome for item in review.evidence] == ["ambiguous"]
    assert len(review.candidates) == 3
    assert "PRIVATE_CAPTURE_CANARY" not in rig.thread().model_dump_json()
    assert "McKinley" not in review.model_dump_json()


def test_the_review_is_bounded_in_count_and_in_text(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = apo_ambiguous(rig)
    payload = SourceResult.model_validate(json.loads(result.receipt.result_json)).model_dump(mode="json")
    template = json.loads(payload["candidate_json"][0])
    crowd = [json.dumps({**template, "authority_id": f"geolocate:{index:016x}", "rank": index + 1,
                         "match_name": "ST " + "X" * 1500}) for index in range(12)]
    payload["candidate_json"] = crowd
    payload["coverage"]["reason"] = "ambiguous: " + "why " * 400
    waiting = waiting.model_copy(update={"reason": "because " * 300})
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [rig.store_payload(payload, FieldKey.COUNTRY, tag="crowd")])
    review = rig.field(FieldKey.COUNTRY).review
    assert len(review.candidates) == 8 and review.candidates_not_shown == 4
    assert all(len(item.label) <= 240 for item in review.candidates)
    assert all(len(item.evidence_id or "") <= 240 for item in review.candidates)
    assert len(review.reason) <= 600 and review.reason.endswith(chr(0x2026))
    assert len(review.evidence[0].note) <= 240
    assert len(review.model_dump_json()) < 8000


def test_a_malformed_capture_degrades_to_the_reason_and_never_breaks_the_thread(tmp_path):
    rig = Rig(tmp_path)
    _, waiting = apo_ambiguous(rig)
    broken = rig.store_payload({"candidate_json": "not a list", "status": 7}, FieldKey.COUNTRY, tag="broken")
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [broken])
    thread = rig.thread()
    review = next(item for item in thread.fields if item.field_key == FieldKey.COUNTRY).review
    assert review.reason == waiting.reason and review.question_reason == "semantic_ambiguity"
    assert review.evidence == review.candidates == ()
    assert len(thread.fields) == 20


def test_an_unrelated_source_lookup_effect_is_ignored_when_the_checkpoint_does_not_cite_it(tmp_path):
    rig = Rig(tmp_path)
    result, waiting = apo_ambiguous(rig)
    rig.capture(result, FieldKey.COUNTRY)
    rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [])
    review = rig.field(FieldKey.COUNTRY).review
    assert review.evidence == review.candidates == ()
    assert review.evidence_not_shown == 1


def fixture_rig(tmp_path):
    rig = Rig(tmp_path)
    ambiguous, country = apo_ambiguous(rig)
    unmatched, location = mckinley_no_match(rig)
    rig.commit(SpecialistRole.GEOGRAPHY, [country, location],
               [rig.capture(ambiguous, FieldKey.COUNTRY), rig.capture(unmatched, FieldKey.PROVINCE_STATE)])
    rig.commit(SpecialistRole.COLLECTION, [
        FieldResolution(field_key=FieldKey.HABITAT, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(state=ValueState.NOT_PRESENT), reason="The label names no habitat."),
        FieldResolution(field_key=FieldKey.COLLECTION_METHOD, work_state=WorkState.WAITING_POLICY,
            value=FieldValue(state=ValueState.UNRESOLVED, literal="synthetic method text"),
            reason="Two readings of the collection method differ and no approved rule chooses between them."),
    ])
    return rig


def digests_as_placeholders(body):
    """Every 64-hex digest becomes a low-entropy placeholder, numbered by first appearance.

    The thread carries real digests (profile, prompts, evidence ids); a fixture holding them trips
    the secret scanners as high-entropy strings. Placeholders keep the cross-references (one digest,
    one placeholder) and still satisfy the contract's digest pattern.
    """
    seen = {}

    def replace(match):
        return seen.setdefault(match[0], f"{len(seen) + 1:02x}" * 32)

    return json.loads(re.sub(r"[a-f0-9]{64}", replace, json.dumps(body)))


def test_the_committed_unresolved_thread_fixture_is_what_the_real_reader_produces(tmp_path):
    """The Flutter tests decode this file, so a drift between reader and fixture fails here first.

    Run with SPECIMEN_WRITE_THREAD_FIXTURE=1 to rewrite it. Only the fields carrying a review are
    compared: digests of pinned prompts elsewhere in the thread change whenever a prompt does.
    """
    thread = fixture_rig(tmp_path).thread()
    produced = digests_as_placeholders(thread.model_dump(mode="json") | {"effects": [], "trace_ids": []})
    if os.environ.get("SPECIMEN_WRITE_THREAD_FIXTURE") == "1":
        FIXTURE.write_text(json.dumps(produced, indent=2, sort_keys=False, ensure_ascii=False) + "\n")
    committed = json.loads(FIXTURE.read_text())
    ResearchThread.model_validate(committed)
    reviews = lambda body: {item["field_key"]: item["review"] for item in body["fields"] if item["review"]}  # noqa: E731
    assert set(reviews(committed)) == {"country", "province_state", "habitat", "collection_method"}
    assert reviews(digests_as_placeholders(committed)) == reviews(produced)
    assert [item["field_key"] for item in committed["fields"]] == [item["field_key"] for item in produced["fields"]]
    assert all(len(set(digest)) <= 2 for digest in re.findall(r"[a-f0-9]{64}", FIXTURE.read_text()))


@pytest.mark.parametrize("name", ["FieldReview", "ReviewCandidate", "ReviewEvidence"])
def test_the_review_models_forbid_unknown_keys(name):
    assert ResearchThread.model_json_schema()["$defs"][name]["additionalProperties"] is False
