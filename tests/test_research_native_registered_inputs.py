"""Registered admission pins and actual ordinary parsing provenance (UNRUN)."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import (
    Asset, Observation, ReaderHandoff, Region, Run, Scope, Specimen, Transcript,
)
from specimen_digitization.application.workflow import Workflow
from specimen_digitization.research_harness.contracts import FieldKey, ResearchScope, digest
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.persistence import HeldUnknown, StaleWork
from specimen_digitization.research_harness.registered_pins import (
    RegisteredModelPriceV1, RegisteredTextRequestBoundV1,
    registered_registry, registered_model_prices, registered_model_request_guards,
)
from specimen_digitization.research_harness.sources import insects_registry


def source_pins():
    registry = insects_registry()
    return {"registry_digest":registry.digest,
        "registry_policies":[policy.model_dump(mode="json") for policy in registry.policies]}


def test_registered_registry_preserves_actual_owner_allowlist():
    pins = source_pins()
    assert registered_registry(pins).digest == pins["registry_digest"]
    changed = deepcopy(pins)
    changed["registry_policies"][0]["allowed_hosts"].append("foreign.example")
    with pytest.raises(StaleWork, match="capability_expanded"):
        registered_registry(changed)
    with pytest.raises(HeldUnknown, match="policies_missing"):
        registered_registry({"registry_digest":pins["registry_digest"]})


def price_pins(binding):
    # Explicit fixture rates; no current provider-price claim or live authority.
    return {"model_prices":{"collection":{
        "contract_version":"registered-model-price/v1", "currency":"USD",
        "route_id":binding.route_id, "model_id":binding.model_id, "provider":binding.provider,
        "price_version":binding.price_version, "input_micro_usd_per_million_tokens":1_000,
        "output_micro_usd_per_million_tokens":2_000, "max_input_tokens":100_000,
        "owner_registration_digest":"a"*64, "owner_registration_origin":"offline-fixture",
        "rate_source_sha256":"b"*64}}}


def test_actual_cost_requires_known_usage_and_covers_reservation():
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra",128,1_000,"fixture-price-v1")
    pins = price_pins(binding)
    cost = registered_model_prices(pins,{"collection":binding})["collection"]
    assert cost(SimpleNamespace(usage=SimpleNamespace(input_tokens=1_000,output_tokens=1_000))) == 3
    assert cost(SimpleNamespace(usage=SimpleNamespace(input_tokens=0,output_tokens=0))) is None
    assert cost(SimpleNamespace(usage=SimpleNamespace())) is None
    # Cache reads never discount the full reported input at the registered list rate.
    for cached in (1, 1_000):
        assert cost(SimpleNamespace(usage=SimpleNamespace(
            input_tokens=1_000,output_tokens=1_000,cache_read_tokens=cached))) == 3
    # Actual usage above the registered input bound and reservation counts in full.
    assert cost(SimpleNamespace(usage=SimpleNamespace(
        input_tokens=2_000_000,output_tokens=1_000))) == 2_002 > binding.reservation_micro_usd
    changed = deepcopy(pins)
    changed["model_prices"]["collection"]["input_micro_usd_per_million_tokens"] = True
    with pytest.raises(HeldUnknown, match="unqualified"):
        registered_model_prices(changed,{"collection":binding})
    small = ModelBinding(binding.route_id,binding.model_id,binding.provider,128,1,binding.price_version)
    with pytest.raises(HeldUnknown, match="below_registered_liability"):
        registered_model_prices(pins,{"collection":small})


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("invalid", [None, 0, -1, True, 1.0, "1"])
def test_actual_cost_keeps_invalid_or_missing_token_usage_unknown(field, invalid):
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra",128,1_000,"fixture-price-v1")
    cost = registered_model_prices(price_pins(binding),{"collection":binding})["collection"]
    usage = {"input_tokens":1_000, "output_tokens":1_000, field:invalid}
    assert cost(SimpleNamespace(usage=SimpleNamespace(**usage))) is None
    del usage[field]
    assert cost(SimpleNamespace(usage=SimpleNamespace(**usage))) is None


@pytest.mark.parametrize("modality", ["cache_write_tokens", "audio_tokens"])
def test_actual_cost_keeps_unpriced_billed_modalities_unknown(modality):
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra",128,1_000,"fixture-price-v1")
    cost = registered_model_prices(price_pins(binding),{"collection":binding})["collection"]
    usage = {"input_tokens":1_000, "output_tokens":1_000, modality:1}
    assert cost(SimpleNamespace(usage=SimpleNamespace(**usage))) is None


def request_bound(binding):
    from specimen_digitization import model_gateway
    from specimen_digitization.research_harness.package_qualification import SERIALIZATION_VERSION
    return {"contract_version":"registered-text-request-bound/v1",
        "route_id":binding.route_id,"model_id":binding.model_id,"provider":binding.provider,
        "price_version":binding.price_version,"serialization_version":SERIALIZATION_VERSION,
        "gateway_source_sha256":hashlib.sha256(Path(model_gateway.__file__).read_bytes()).hexdigest(),
        "tokenizer_source_sha256":"c"*64,"chat_template_source_sha256":"d"*64,
        "bound_source_sha256":"e"*64,"owner_registration_digest":"a"*64,
        "owner_registration_origin":"offline-fixture","maximum_serialized_bytes":2_000,
        "tokens_per_utf8_byte_upper_bound":2,"fixed_overhead_tokens":50}


def test_literal_input_bound_rejects_missing_authority_oversize_and_multimodal():
    binding = ModelBinding("harness-deepseek","deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra",128,1_000,"fixture-price-v1")
    pins = price_pins(binding)
    with pytest.raises(HeldUnknown,match="bound_missing"):
        registered_model_request_guards(pins,{"collection":binding})
    raw = request_bound(binding)
    price = RegisteredModelPriceV1.from_registered(binding,pins["model_prices"]["collection"])
    guard = RegisteredTextRequestBoundV1.from_registered(binding,price,raw)
    text = [{"kind":"request","parts":[{"part_kind":"user-prompt","content":"Kenya"}]}]
    assert guard.validate(text,{},{} )["bound_digest"] == digest(guard.__dict__)
    with pytest.raises(HeldUnknown,match="bound_exceeded"):
        guard.validate([{ "parts":[{"part_kind":"user-prompt","content":"x"*2_000}]}],{}, {})
    with pytest.raises(HeldUnknown,match="modality_unqualified"):
        guard.validate([{ "parts":[{"part_kind":"user-prompt","content":[{"url":"https://example.invalid/image"}]}]}],{}, {})
    for update in ({"maximum_serialized_bytes":True},{"gateway_source_sha256":"f"*64},
        {"maximum_serialized_bytes":60_000},{"owner_registration_digest":"b"*64}):
        with pytest.raises(HeldUnknown,match="unqualified"):
            RegisteredTextRequestBoundV1.from_registered(binding,price,{**raw,**update})


def test_previous_package_serialization_cannot_authorize_new_provider_requests():
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 1_000, "fixture-price-v1")
    pins = price_pins(binding)
    pins["model_request_bounds"] = {"collection": {**request_bound(binding),
        "serialization_version": "pydantic-ai-2.51.0+harness-0.36.0/v1"}}
    with pytest.raises(HeldUnknown, match="bound_unqualified"):
        registered_model_request_guards(pins, {"collection": binding})


def parsed_specimen():
    asset = Asset(sha256="a"*64,blob_ref="a"*64+":1",media_type="image/jpeg",
        size_bytes=10,width=100,height=100,filename="fixture.jpeg",uploader="fixture",sensitive=False)
    region = Region(asset_id=asset.id,x=0,y=0,width=100,height=100,order=0,method="fixture",version="fixture")
    reading = Observation(region_id=region.id,route_id="handwriting-qwen",model_id="fixture-model",
        provider="fixture",prompt_version="b"*64,input_sha256="c"*64,input_asset_id=asset.id,
        literal_text="country: Kenya",raw_ref="fixture-response",raw_sha256="d"*64)
    transcript = Transcript(region_id=region.id,text=reading.literal_text,observation_ids=[reading.id],
        alternatives=[reading.literal_text],resolved=True,decision_kind="identical_readings",
        selected_observation_id=reading.id,handoffs=[ReaderHandoff(observation_id=reading.id,
            role="decided_transcript",handed_text=reading.literal_text)])
    specimen = Specimen(scope=Scope(organization_id="org",collection_id="collection"),asset=asset,
        run=Run(regions=[region],observations=[reading],transcripts=[transcript]))
    Workflow.parse(specimen.run,asset.id)
    scope = ResearchScope(organization_id="org",collection_id="collection",specimen_id=specimen.id,
        job_id="opaque-fixture-job",generation=1,input_digest="e"*64,profile_digest="f"*64,sensitive=False)
    return specimen,scope


def test_initial_graph_uses_actual_ordinary_evidence_identity_and_full_handoff():
    specimen,scope = parsed_specimen()
    fragments,events,assemblies,evidence,_ = NativeGenerationRequestFactory._graph(specimen,scope)
    actual = specimen.run.evidence[0]
    assert evidence[0].id == actual.id
    assert evidence[0].publisher_assertion_id == digest(actual.model_dump(mode="json"))
    assert len(fragments) == len(events) == len(assemblies) == 1
    assert fragments[0].literal == "Kenya" and fragments[0].input_source == "decided_transcript"
    assert assemblies[0].field_key == FieldKey.COUNTRY
    assert assemblies[0].evidence_ids == (actual.id,)
    changed = specimen.model_copy(deep=True)
    changed.run.transcripts[0].handoffs[0].handed_text = "altered"
    with pytest.raises(StaleWork, match="handoff_literal_unproved"):
        NativeGenerationRequestFactory._graph(changed,scope)


def test_absent_native_evidence_never_creates_label_authority():
    specimen,scope = parsed_specimen()
    specimen.run.evidence.clear()
    fragments,events,assemblies,evidence,_ = NativeGenerationRequestFactory._graph(specimen,scope)
    assert len(fragments) == 1
    assert not events and not assemblies and not evidence


def test_official_tagged_memory_text_is_admitted_under_same_byte_liability_bound():
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, TextContent, UserPromptPart
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash", "deepinfra",128,1_000,"fixture-price-v1")
    pins = price_pins(binding)
    price = RegisteredModelPriceV1.from_registered(binding,pins["model_prices"]["collection"])
    guard = RegisteredTextRequestBoundV1.from_registered(binding,price,request_bound(binding))
    messages = ModelMessagesTypeAdapter.dump_python([ModelRequest([UserPromptPart([
        TextContent("Reviewed procedure context", metadata="harness-memory-scope-marker")])])],mode="json")
    assert guard.validate(messages,{}, {})["bound_digest"] == digest(guard.__dict__)
    messages[0]["parts"][0]["content"][0]["metadata"] = "x" * 2_000
    with pytest.raises(HeldUnknown,match="bound_exceeded"):
        guard.validate(messages,{}, {})


@pytest.mark.parametrize("chunk", [{"kind":"binary","content":"not text"},
    {"kind":"text-content","content":"text","url":"https://example.invalid/image"},
    {"kind":"text-content","content":{"text":"not a literal"}}])
def test_tagged_text_does_not_admit_binary_url_or_forged_modalities(chunk):
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash", "deepinfra",128,1_000,"fixture-price-v1")
    pins = price_pins(binding)
    price = RegisteredModelPriceV1.from_registered(binding,pins["model_prices"]["collection"])
    guard = RegisteredTextRequestBoundV1.from_registered(binding,price,request_bound(binding))
    with pytest.raises(HeldUnknown,match="modality_unqualified"):
        guard.validate([{"parts":[{"part_kind":"user-prompt","content":[chunk]}]}],{}, {})
