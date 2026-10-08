"""Synthetic dates through the real composer, checkpoint and automatic writer.

The readings and FunctionModel answers are scripted; Data Connect is the local
fake and geography uses recorded fixture bytes. These tests exercise native
validation/publication without HTTP, a source-provider call, paid processing,
human Save, or live specimen acceptance.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
import test_organiser_handover_composer as composer
import test_unkeyed_label_review as review
from specimen_digitization.application.field_harness import labelled
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.organiser import extraction_readings
from specimen_digitization.application.production import actor_uid
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import EventKind, FieldKey, SpecialistRole, WorkState


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the synthetic temporal composer test performs no HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


class _EveryReaderExtractor(composer.ExtractorAdapters):
    """Keep the helper's unmetered synthetic extraction seam, store real locators.

    The existing helper stores only the selected reader's proposal. Date event
    qualification needs every reader's independently quoted counterpart, so
    these scripted proposals pass through the real apply_candidates boundary.
    """

    def _extract(self, specimen):
        names = labelled(extraction_readings(specimen.run))
        proposals = []
        for key, literal, region_index in self.stored:
            region_id = specimen.run.regions[region_index].id
            for name, reading in names.items():
                if reading.region_id != region_id:
                    continue
                quote = next(line for line in reading.text.splitlines() if line.partition(": ")[2] == literal)
                proposals.append(ExtractionCandidate(field_key=key, reading=name,
                    literal=literal, source_excerpt=quote))
        output = ExtractionOutput(candidates=proposals)
        raw = output.model_dump_json().encode()
        apply_candidates(specimen.run, specimen.asset.id, output,
            self.blobs.put(raw), hashlib.sha256(raw).hexdigest())


def _temporal_factory(rig, seen):
    base = review.specialist_factory(rig.model_calls)

    def factory(request, binding):
        if request.role != SpecialistRole.TEMPORAL:
            return base(request, binding)
        seen.append(request)
        collecting = [event for event in request.events if event.kind == EventKind.COLLECTING
            and event.status == "accepted" and any(assembly.event_id == event.id
                and assembly.field_key == FieldKey.DATE_VISITED_FROM for assembly in request.assemblies)]
        assert len(collecting) == 1
        arguments = {"field_key": "date_visited_from", "event_id": collecting[0].id}

        def respond(messages, info):
            turn = 1 + sum(isinstance(message, ModelResponse) for message in messages)
            rig.model_calls.append((str(request.role), turn))
            assert not [part for message in messages for part in message.parts
                if isinstance(part, RetryPromptPart)], "the exact utility output should pass without correction"
            if turn == 1:
                return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                    "tool_id": "settle_temporal", "arguments": arguments},
                    tool_call_id="synthetic-temporal-settlement")], usage=support.USAGE)
            assert turn == 2
            [result] = [part.content for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart) and part.tool_name == "invoke_utility"]
            rows = json.loads(result.candidate_json[0])["resolutions"]
            assert {row["field_key"] for row in rows} == {"date_visited_from", "date_visited_to"}
            resolutions = [row for row in rows if FieldKey(row["field_key"]) in request.field_keys]
            resolutions.append(review.abstention(FieldKey.DATE_IDENTIFIED, WorkState.WAITING_POLICY,
                "no written determination event").model_dump(mode="json"))
            output = SpecialistOutput.model_validate({"role": request.role, "resolutions": resolutions})
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="synthetic-temporal-output")], usage=support.USAGE)

        return FunctionModel(respond)

    return factory


@pytest.mark.parametrize("linked", (False, True, "repeated-year"),
    ids=("complete-written-date", "explicit-linked-date-year", "exact-repeated-year-roles"))
def test_collecting_date_publishes_from_and_derived_to_without_human_save(tmp_path, monkeypatch, linked):
    """Real composed offline publication; scripted science is not live acceptance."""
    locality = "Chicago, Cook County\nIllinois, United States\ngrassland margin"
    if linked == "repeated-year":
        texts = (locality, "Collecting event: trip7\nDate: 1946-09-14\nYear: 1946")
        stored = (("date_visited_from", "1946-09-14", 1), ("date_visited_from", "1946", 1))
        expected = "1946-09-14"
    elif linked:
        texts = (locality, "Collecting event: trip7\nDay and month: IV-24",
                 "Collecting event: trip7\nYear: 1946")
        stored = (("date_visited_from", "IV-24", 1), ("date_visited_from", "1946", 2))
        expected = "1946-04-24"
    else:
        texts = (locality, "Collected: IX-14-46")
        stored = (("date_visited_from", "IX-14-46", 1),)
        expected = "1946-09-14"
    rig, token = composer.build_rig(tmp_path, monkeypatch, stored=(), texts=texts)
    rig.ordinary.adapters = _EveryReaderExtractor(rig.ordinary.blobs, locality, stored)
    seen = []
    try:
        parsed, specimen, hold = composer.run(rig, _temporal_factory(rig, seen))
    finally:
        actor_uid.reset(token)

    assert hold is None, hold
    assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
    fields = specimen.run.fields
    assert fields["date_visited_from"].state == fields["date_visited_to"].state == "supported"
    assert fields["date_visited_from"].normalized == fields["date_visited_to"].normalized == expected
    assert fields["date_visited_from"].precision == fields["date_visited_to"].precision == "day"
    assert fields["date_visited_from"].layer == "settled" and fields["date_visited_to"].layer == "derived"
    assert fields["date_visited_to"].literal is None
    assert fields["date_identified"].state != "supported"
    assert fields["date_visited_from"].evidence_relations and fields["date_visited_to"].evidence_relations
    assert set(fields["date_visited_from"].evidence_relations.values()) == {"supports"}
    assert set(fields["date_visited_to"].evidence_relations.values()) == {"supports"}

    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    published = [row["causal_proof"]["changed_field"] for row in receipts]
    assert published.index("date_visited_from") < published.index("date_visited_to")
    assert rig.fake.audit_events and {row["action"] for row in rig.fake.audit_events.values()} == {
        "research_publication"}
    lineages = {row["researchFieldKey"]: row for row in
        rig.fake.tables["canonical_value_lineage_v2"].values() if row["researchFieldKey"].startswith("date_")}
    end = lineages["date_visited_to"]
    assert end["layer"] == "derived" and end["derivation"]["rule_id"] == "G44"
    [dependency] = end["consumedDependencies"]
    assert dependency["researchFieldKey"] == "date_visited_from"
    assert dependency["dependencyResolutionDigest"] == lineages["date_visited_from"]["resolutionDigest"]
    assert end["precision"] == "day" and end["scientificSourceDigest"]
    assert not rig.fake.duplicates
    assert [turn for role, turn in rig.model_calls if role == SpecialistRole.TEMPORAL.value] == [1, 2]
    if linked:
        [request] = seen
        accepted = [event for event in request.events if event.status == "accepted"
            and event.validator_version == "explicit-temporal-event-link/v1"]
        assert len(accepted) == 1
        parts = [item for item in request.fragments if item.id in accepted[0].fragment_ids]
        assert {item.literal for item in parts} == ({"1946-09-14", "1946"}
            if linked == "repeated-year" else {"IV-24", "1946"})
        assert len({item.region_id for item in parts}) == (1 if linked == "repeated-year" else 2)
        assert parsed.run.fields["date_visited_from"].state == "ambiguous"
