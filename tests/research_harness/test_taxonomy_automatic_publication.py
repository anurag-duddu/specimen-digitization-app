"""Offline automatic taxonomy publication with a genuinely negative alternative.

The production workflow, capture broker, SQLite ledger and native publisher run
against synthetic model/source fixtures and an in-memory connector. This proves
local composition and provenance, not scientific or live production acceptance.
"""

import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import SpecialistRole
from specimen_digitization.research_harness.evidence import validate_resolution
from specimen_digitization.research_harness.persistence import BlobRef
from specimen_digitization.research_harness.source_capture_v2 import SourceRequestEnvelopeV2
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

import production_e2e_support as support
import test_production_e2e as e2e

ALTERNATE_NAME = "Danaus plxxippus"
NEGATIVE_BODY = json.dumps({"usage": None, "classification": [],
    "diagnostics": {"matchType": "NONE", "alternatives": []}, "synonym": False},
    sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture(autouse=True)
def refuse_live_http(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("taxonomy publication regression performs no live HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def taxonomy_model_factory(log):
    """Use the shared scripted specialists; taxonomy also researches reader B."""
    ordinary_factory = support.scripted_model_factory(log, geolocate=True)
    requests = []

    def factory(request, binding):
        if request.role != SpecialistRole.TAXONOMY:
            return ordinary_factory(request, binding)
        requests.append(request)
        literal = support.LABEL_VALUES["taxon"]
        plan = (("gbif", literal), ("gbif", ALTERNATE_NAME),
                ("global_names_verifier", literal), ("catalogue_of_life", literal))

        def respond(messages, info):
            results, attempted = support._results(messages)
            log.append((str(request.role), attempted + 1))
            if attempted < len(plan):
                source, name = plan[attempted]
                return ModelResponse(parts=[ToolCallPart("lookup_source", {"query": {
                    "source_id": source, "field_key": "taxon", "query_text": name}},
                    tool_call_id=f"taxonomy-regression-lookup-{attempted}")], usage=support.USAGE)
            resolution = support._taxon(request, results)
            assert resolution is not None, "the confirmed reader must produce a positive proposal"
            validate_resolution(request, resolution, results)
            output = SpecialistOutput(role=request.role, resolutions=(resolution,))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="taxonomy-regression-output")],
                usage=support.USAGE)

        return FunctionModel(respond)

    factory.requests = requests
    return factory


def alternate_source_transport(log):
    ordinary = support.fixture_source_transport(log)

    async def read(url, policy):
        params = parse_qs(urlsplit(url).query)
        if policy.id == "gbif" and params.get("scientificName") == [ALTERNATE_NAME]:
            assert params["taxonRank"] == ["SPECIES"]
            log.append(url)
            return 200, NEGATIVE_BODY
        return await ordinary.read(url, policy)

    return FixtureSourceTransport(read)


def test_confirmed_raw_reader_and_captured_negative_publish_taxon_without_save(tmp_path, monkeypatch):
    original_specimen = support.specimen_before_adjudication

    def specimen_with_taxon_alternative(blobs, *, first_pass=False):
        specimen = original_specimen(blobs, first_pass=False)
        first, second = specimen.run.observations
        alternate_text = support.LABEL_TEXT.replace(support.LABEL_VALUES["taxon"], ALTERNATE_NAME)
        raw = ("SYNTHETIC FIXTURE alternate-reader\n" + alternate_text).encode()
        second.literal_text = alternate_text
        second.raw_ref = blobs.put(raw)
        second.raw_sha256 = hashlib.sha256(raw).hexdigest()
        region = specimen.run.regions[0]
        decision = synthetic_decision(blobs, region, [first, second])
        specimen.run.first_pass_decisions = [decision.model_copy(update={
            "selected_observation_id": first.id,
            "differences": [item.model_copy(update={"verdict": first.id})
                for item in decision.differences]})]
        specimen.run.completed_steps.append(f"first_pass:{region.id}")
        return specimen

    monkeypatch.setattr(e2e, "specimen_before_adjudication", specimen_with_taxon_alternative)
    with_rig = e2e.build_rig(tmp_path, first_pass=True)
    rig = next(with_rig)
    try:
        model_factory = taxonomy_model_factory(rig.model_calls)
        workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
            environ=e2e.SWITCH_ON, actor_uid=support.WORKER, state_backend=rig.backend,
            model_factory=model_factory, source_transport=alternate_source_transport(rig.source_urls),
            blobs=rig.research_blobs)
        parsed = e2e.first_pass_to_plan(workflow, rig)
        with e2e.supervised():
            published = workflow.step(rig.principal, rig.specimen_id)

        # Automatic native publication occurs in the worker's plan step. No
        # review selection, manual candidate mutation, or user Save is invoked.
        taxon = published.run.fields["taxon"]
        assert taxon.state == "supported" and taxon.normalized == e2e.GBIF_NAME
        taxon_receipts = [row for row in rig.fake.receipts.values()
            if row["causal_proof"]["changed_field"] == "taxon"]
        assert len(taxon_receipts) == 1
        assert taxon_receipts[0]["used_canonical_revision"] == parsed.version
        assert taxon_receipts[0]["resulting_canonical_revision"] == parsed.version + 1
        assert published.run.stage == "finalized"
        assert published.run.disposition == "needs_human_review"
        assert {reason for reason in published.run.reasons if reason.startswith("mandatory_unresolved:")} == {
            "mandatory_unresolved:verbatim_dts"}
        assert not any(reason.startswith("research_work:taxon:") for reason in published.run.reasons)

        # Both independent raw readings survive unchanged in native rows.
        readers = [row for row in rig.fake.tables["model_observation"].values() if row["independent"]]
        assert {row["literalText"] for row in readers} == {support.LABEL_TEXT,
            support.LABEL_TEXT.replace(support.LABEL_VALUES["taxon"], ALTERNATE_NAME)}
        request = model_factory.requests[0]
        assert any(ALTERNATE_NAME in item.observation_text for item in request.fragments)

        # The alternate's actual response bytes, query and original raw input
        # remain in an immutable completed source envelope, not a model claim.
        _, state = support.research_state(rig.fake, rig.specimen_id)
        negative = []
        for effect in state["effects"].values():
            if not effect["operation_key"].startswith("source_capture_v2:"):
                continue
            payload = effect["receipt"]["typed_payload"]
            if payload["coverage"]["source_id"] == "gbif" and payload["status"] == "no_match":
                negative.append(effect)
        assert len(negative) == 1
        effect = negative[0]
        assert effect["status"] == "completed" and effect["execution_class"] == "offline"
        envelope = SourceRequestEnvelopeV2.model_validate_json(rig.research_blobs.get(
            BlobRef(**effect["receipt"]["raw_capture"])))
        assert envelope.query.query_text == ALTERNATE_NAME and envelope.original_request == request
        assert len(envelope.responses) == 1 and envelope.responses[0].status_code == 200
        response_body = rig.research_blobs.get(BlobRef(**envelope.responses[0].body.model_dump()))
        assert response_body == NEGATIVE_BODY
        assert envelope.responses[0].response_fingerprint == hashlib.sha256(NEGATIVE_BODY).hexdigest()
        assert any(ALTERNATE_NAME in item.observation_text for item in envelope.original_request.fragments)
        assert sum(parse_qs(urlsplit(url).query).get("scientificName") == [ALTERNATE_NAME]
            for url in rig.source_urls) == 1
        assert not rig.fake.duplicates
    finally:
        with_rig.close()
