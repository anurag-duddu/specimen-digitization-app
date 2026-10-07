"""Evidence from a RAW reading through the production composer: an undecided label whose readers agree.

test_organiser_raw_reading_evidence pins the graph builder and the contract; this module runs the same shape
through the production composer with the real validator and the real publication, as
test_organiser_handover_composer does for the decided label. Label 0 is decided by the first pass (as there). Label
1 is a label the first pass never decided (two readers that differ on one line, a first-pass decision that selects
neither: ``resolved`` false, both readings raw, the shape of specimens 1, 4, 6 and 9). The ordinary extractor here is
the real ``apply_candidates`` fed scripted candidates that name a reading (1A, 2A, 2B ...): not a model. The
specialist is the same overlay as in the decided-label module (it reads the v5 hand-over sentences out of its pinned
text). It proves what the real validators and publication accept and refuse; it does not show that a real model
follows the text (the canary does).
"""
from __future__ import annotations

import hashlib
import json

import pytest

import production_e2e_support as support
import test_organiser_handover_composer as base
import test_unkeyed_label_review as review
from specimen_digitization.application.domain import Observation, Region
from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters, Workflow
from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole
from specimen_digitization.research_harness.persistence import DurabilityScope, ImmutableFileBlobs, SqliteStateBackend

from production_e2e_support import (
    COLLECTION, ORG, WORKER, FakeDataConnect, GenerationBlobs, research_state, specimen_before_adjudication,
    worker_principal,
)

DECIDED_LABEL = "Chicago, Cook County\nIllinois, United States\ngrassland margin"
# Label 1: both readers print the catalog number, the collector and the method; they differ on the last line.
READER_A = "FMNH INS\n0010001\nSynthetic Collector\nlight trap\nGamma 11"
READER_B = "FMNH INS\n0010001\nSynthetic Collector\nlight trap\nGamma 17"

# (field, reading name, literal, quote): the scripted extraction call. "1A" is label 0's decided reading; "2A" and
# "2B" are label 1's two raw readings (no decided transcript, so both are raw).
ANSWERS = (
    ("habitat", "1A", "grassland margin", "grassland margin"),
    ("fmnh_ins_number", "2A", "0010001", "0010001"), ("fmnh_ins_number", "2B", "0010001", "0010001"),
    ("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
    ("collectors", "2B", "Synthetic Collector", "Synthetic Collector"),
    ("collection_method", "2A", "light trap", "light trap"), ("collection_method", "2B", "light trap", "light trap"),
    # The readers differ on this one: no value is chosen, no assembly exists.
    ("collection_code", "2A", "Gamma 11", "Gamma 11"), ("collection_code", "2B", "Gamma 17", "Gamma 17"),
)
RESOLVED = ("fmnh_ins_number", "collectors", "collection_method")


class Adapters(SyntheticAdapters):
    """The ordinary extract step with scripted candidates through the real apply_candidates (hidden from the step's
    first ``hasattr`` so it is not metered as a billable external step, as the decided-label module does)."""

    def __init__(self, blobs, text, answers):
        super().__init__(blobs, text)
        self.answers, self._seen = answers, 0

    def __getattr__(self, name):
        if name != "extract":
            raise AttributeError(name)
        self._seen += 1
        if self._seen < 2:
            raise AttributeError(name)
        return self._extract

    def _extract(self, specimen):
        candidates = [ExtractionCandidate(field_key=key, reading=reading, literal=literal, source_excerpt=quote)
            for key, reading, literal, quote in self.answers]
        raw = json.dumps({"scripted_extraction": True}).encode()
        apply_candidates(specimen.run, specimen.asset.id, ExtractionOutput(candidates=candidates),
            self.blobs.put(raw), hashlib.sha256(raw).hexdigest())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


from test_organiser_handover_composer import refusals  # noqa: E402,F401  (the fixture: the publication's refusals)


def make_rig(tmp_path, monkeypatch, answers=ANSWERS, reader_b=READER_B):
    monkeypatch.setattr(support, "LABEL_TEXT", DECIDED_LABEL)
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {WORKER: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}]}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, Adapters(blobs, DECIDED_LABEL, answers))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    specimen = specimen_before_adjudication(blobs, first_pass=True)
    run, first = specimen.run, specimen.run.regions[0]
    region = Region(asset_id=specimen.asset.id, x=0, y=0, width=first.width, height=first.height, order=1,
        method="synthetic_fixture_region", version="1", crop_ref=first.crop_ref)
    run.regions.append(region)
    readings = []
    for route, text in zip(run.profile.routes, (READER_A, reader_b)):
        raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
        reading = Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
            provider="synthetic", prompt_version=hashlib.sha256(("prompt:" + route).encode()).hexdigest(),
            input_sha256=run.observations[0].input_sha256, input_asset_id=specimen.asset.id,
            input_crop_ref=region.crop_ref, literal_text=text, raw_ref=blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest())
        run.observations.append(reading)
        readings.append(reading)
    run.completed_steps += [f"transcribe:{region.id}:{route}" for route in run.profile.routes]
    # The first pass declined to choose between the two readings of label 1: its decision selects neither.
    decision = synthetic_decision(blobs, region, readings)
    run.first_pass_decisions.append(decision.model_copy(update={"selected_observation_id": None,
        "differences": [item.model_copy(update={"verdict": "uncertain"}) for item in decision.differences]}))
    run.completed_steps.append(f"first_pass:{region.id}")
    created = repository.create(principal, specimen, "e2e-intake", "e2e-intake")
    rig = type("Rig", (), dict(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
        principal=principal, specimen_id=created.id, research_blobs=ImmutableFileBlobs(tmp_path / "research"),
        model_calls=[], source_urls=[]))
    return rig, token


@pytest.fixture
def rig(tmp_path, monkeypatch):
    made, token = make_rig(tmp_path, monkeypatch)
    yield made
    actor_uid.reset(token)


def run(rig, factory):
    return base.run(rig, factory)


def published(rig):
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    return [row["causal_proof"]["changed_field"] for row in receipts]


# ---------------------------------------------------------------------------- the premise
def test_the_second_label_is_undecided_and_the_graph_grounds_the_agreeing_fields_on_the_raw_reading(rig):
    parsed = base.to_plan(review.compose(rig, review.specialist_factory([]), review.transport([])), rig)
    run_ = parsed.run
    assert [(t.resolved, t.selected_observation_id is None) for t in run_.transcripts] == [(True, False), (False, True)]
    assert {value.state for key, value in run_.fields.items() if key == "collection_code"} == {"ambiguous"}
    assert run_.fields["collectors"].state == "supported"
    from specimen_digitization.research_harness.contracts import ResearchScope
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id=rig.specimen_id, job_id="job",
        generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    fragments, events, assemblies, _, _, found = NativeGenerationRequestFactory._build_graph(parsed, scope)
    grounded = {str(item.field_key): item for item in found if item.status == "grounded"}
    assert set(grounded) == {"fmnh_ins_number", "collectors", "collection_method", "habitat"}
    undecided = run_.regions[1].id
    assert {key for key, item in grounded.items() if item.region_id == undecided} == set(RESOLVED)
    assert {row.input_source for row in fragments if row.id in {item.fragment_id for item in grounded.values()
        if item.region_id == undecided}} == {"raw_reading"}
    assert {str(row.field_key) for row in assemblies} == set(grounded)
    # The readers differ on the collection code: located, one per reader, no assembly.
    code = [item for item in found if item.field_key == FieldKey.COLLECTION_CODE]
    assert len(code) == 2 and {item.status for item in code} == {"located"}
    assert {item.reason for item in code} == {"readings_differ_no_value_chosen"}


# ---------------------------------------------------------------------------- publication through the real chain
def test_a_value_both_raw_readers_state_publishes_with_evidence_from_both_readers(rig, refusals):
    decisions = []
    parsed, specimen, hold = run(rig, base.hand_over(review.specialist_factory(rig.model_calls), decisions=decisions))
    assert refusals == [], f"a publication was refused: {refusals}"
    assert hold is None, hold
    assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
    assert sorted(decisions) == [("collection_method", "resolved"), ("collectors", "resolved"),
        ("fmnh_ins_number", "resolved"), ("habitat", "rejected")]
    assert set(RESOLVED) <= set(published(rig)) and "collection_code" not in published(rig)
    fields = specimen.run.fields
    assert (fields["fmnh_ins_number"].literal, fields["collectors"].literal, fields["collection_method"].literal) == (
        "0010001", "Synthetic Collector", "light trap")
    for key in RESOLVED:
        assert fields[key].state == "supported" and fields[key].evidence_relations
        # Evidence from both readers: two native rows, each a quote of one reader's own reading.
        quotes = [row for row in specimen.run.evidence if row.id in fields[key].evidence_ids]
        assert len(quotes) == 2 and {tuple(row.observation_ids) for row in quotes} == {
            (reading.id,) for reading in specimen.run.observations if reading.region_id == specimen.run.regions[1].id}
    # The lineage of each published value names the RAW reading it was read from, never the decided transcript.
    sources = {row["researchFieldKey"]: row["readingSources"]
        for row in rig.fake.tables["canonical_value_lineage_v2"].values() if row["readingSources"]}
    assert set(RESOLVED) <= set(sources)
    assert all(item["inputSource"] == "raw_reading" for key in RESOLVED for item in sources[key])
    _, state = research_state(rig.fake, rig.specimen_id)
    job = list(state["jobs"].values())[0]
    assert {key: job["fields"][key]["work_state"] for key in (*RESOLVED, "collection_code", "habitat")} == {
        "fmnh_ins_number": "resolved", "collectors": "resolved", "collection_method": "resolved",
        "collection_code": "waiting_policy", "habitat": "waiting_policy"}
    held = {reason.split(":", 1)[1] for reason in specimen.run.reasons if reason.startswith("mandatory_unresolved:")}
    assert {"collection_code", "habitat"} <= held and not held & set(RESOLVED)
    # NOTE (not asserted either way): the policy adds unresolved_transcription:<region> for a label with no decided
    # transcript only when no field is "drawn" from it or a terminal drawn field is unsupported
    # (canonical_materialization_v2._scientific_reasons). Once the organiser's rows cite the label (#262) the field is
    # drawn from it, with or without this change; the record still holds the held fields' own reasons, as above.
    assert not [reason for reason in specimen.run.reasons if reason.startswith(("research_work:", "canonical_"))]
    assert not rig.fake.duplicates


def test_a_specialist_that_cites_a_reading_that_does_not_hold_the_literal_is_refused(rig, refusals, monkeypatch):
    """A model names the assembly but cites the other label's reading: the Agent refuses it before publication."""
    original = base.from_assembly

    def wrong_reading(request, candidate, rules, *, omit=()):
        resolution = original(request, candidate, rules, omit=omit)
        decided = next(row for row in request.fragments if row.input_source == "decided_transcript")
        value = resolution.value.model_copy(update={"verbatim_by_observation": {decided.observation_id: decided.observation_text},
            "settled_observation_ids": [decided.observation_id]})
        return resolution.model_copy(update={"value": value})
    monkeypatch.setattr(base, "from_assembly", wrong_reading)
    parsed, specimen, hold = run(rig, base.hand_over(review.specialist_factory(rig.model_calls)))
    assert refusals == [] and isinstance(hold, OperationalBlock)
    assert str(hold) == "native_research_operational_hold"
    assert [turn for role, turn in rig.model_calls if role == SpecialistRole.COLLECTION.value] == [1, 2]
    _, state = research_state(rig.fake, rig.specimen_id)
    fields = list(state["jobs"].values())[0]["fields"]
    for key in RESOLVED:
        assert fields[key]["work_state"] == "operational_failed"
        checkpoint = fields[key]["checkpoint"]
        assert checkpoint["payload"]["resolution"]["reason"] == "specialist_operational_failure"
        assert checkpoint["payload"]["resolution"]["value"]["literal"] is None
        assert not checkpoint.get("accepted_output_proof")
    assert not set(RESOLVED) & set(published(rig))


def test_when_the_readers_differ_the_field_is_not_resolved_to_either_reading(rig, refusals):
    """collection_code: reader A prints 'Gamma 11', reader B 'Gamma 17'. A specialist that resolves it anyway (from a
    hint it treats as a value) has no assembly to cite and is refused by the validator: the role fails and the record
    holds. A specialist that does what the text says leaves it waiting_policy and the record goes to review."""
    parsed, specimen, hold = run(rig, base.hand_over(review.specialist_factory(rig.model_calls), resolve_hints=True))
    # No hint exists for it (its rows are located spans, not hints), so the overlay changes nothing: control.
    assert refusals == [] and hold is None
    assert "collection_code" not in published(rig)
    _, state = research_state(rig.fake, rig.specimen_id)
    assert list(state["jobs"].values())[0]["fields"]["collection_code"]["work_state"] == "waiting_policy"
    assert "mandatory_unresolved:collection_code" in specimen.run.reasons
    assert specimen.run.fields["collection_code"].literal is None and specimen.run.fields["collection_code"].state == "ambiguous"


def test_one_reader_silent_gives_no_assembly_and_the_field_stays_for_a_person(tmp_path, monkeypatch, refusals):
    answers = tuple(item for item in ANSWERS if not (item[0] == "collectors" and item[1] == "2B"))
    made, token = make_rig(tmp_path, monkeypatch, answers=answers)
    try:
        parsed, specimen, hold = run(made, base.hand_over(review.specialist_factory(made.model_calls)))
        assert refusals == [] and hold is None
        assert "collectors" not in published(made) and "fmnh_ins_number" in published(made)
        assert specimen.run.fields["collectors"].state == "ambiguous" and specimen.run.fields["collectors"].literal is None
        assert "mandatory_unresolved:collectors" in specimen.run.reasons
    finally:
        actor_uid.reset(token)
