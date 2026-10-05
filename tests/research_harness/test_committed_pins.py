"""The research job's pins come from committed configuration and installed code."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from specimen_digitization import model_gateway
from specimen_digitization.application.collection_profiles import (
    CollectionProfile as PublishedProfile, published_registry,
)
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES
from specimen_digitization.research_harness import committed_pins, registered_pins, sources
from specimen_digitization.research_harness.committed_pins import (
    MAX_OUTPUT_TOKENS, REQUEST_BOUND, TOKENIZER_PIN, build_committed_pins,
    committed_harness_route, committed_run_cost_limit_micros,
)
from specimen_digitization.research_harness.contracts import ALL_FIELDS, SpecialistRole, digest
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.persistence import (
    MAX_STATE_BYTES, BudgetPolicy, DurabilityScope, HeldUnknown, PinnedRuntime, ResearchStore,
    SqliteStateBackend, canonical,
)
from specimen_digitization.research_harness.production_runtime import committed_job_pins
from specimen_digitization.research_harness.source_readiness import (
    CAPTURE_POLICIES, SOURCE_READINESS,
)

ORG, COLLECTION = "org-synthetic", "collection-synthetic"
TAXONOMY_APIS = ("gbif", "global_names_verifier", "catalogue_of_life")
CANARIES = (Path(sources.__file__).parent / "prompts"
    / "public-source-canaries-2026-09-29.json")


def published():
    return published_registry().resolve("insects").profile


def pins_for(profile=None):
    return build_committed_pins(published() if profile is None else profile,
        organization_id=ORG, collection_id=COLLECTION)


def bindings_of(pins):
    out = {}
    for role in SpecialistRole:
        data = dict(pins["model"][str(role)])
        data.pop("route")
        out[role] = ModelBinding(**data)
    return out


def with_harness_price(**change):
    data = published().model_dump(mode="json")
    data["processing"]["price_list"]["models"]["harness-deepseek"].update(change)
    return PublishedProfile.model_validate(data)


def test_two_builds_are_equal_whether_from_the_snapshot_or_the_profile():
    profile = published()
    first = pins_for(profile)
    assert first == pins_for(profile)
    assert first == pins_for(profile.model_dump(mode="json"))
    assert json.loads(canonical(first)) == first
    assert set(first) == set(PinnedRuntime.__dataclass_fields__) - {"input_digest"}


def test_the_registered_validators_accept_the_pins():
    pins = pins_for()
    registry = registered_pins.registered_registry(pins["sources"])
    overrides = {key: row for key, row in SOURCE_READINESS.items()
        if key in {policy.id for policy in sources.insects_registry().policies}}
    assert registry.digest == sources.insects_registry(qualification_overrides=overrides).digest
    assert registry.digest == pins["sources"]["registry_digest"]
    assert set(registered_pins.registered_capture_policies(pins["sources"], registry)) == (
        set(CAPTURE_POLICIES) & {policy.id for policy in registry.policies})
    bindings = bindings_of(pins)
    assert set(registered_pins.registered_model_prices(pins["sources"], bindings)) == set(SpecialistRole)
    assert set(registered_pins.registered_model_request_guards(pins["sources"], bindings)) == set(SpecialistRole)
    for pin in pins["prompts"].values():
        assert pin["source_registry_digest"] == registry.digest
        assert pin["model_route"] == "harness-deepseek"


def test_a_created_job_holds_the_pins_a_rebuild_produces(tmp_path):
    scope = DurabilityScope(ORG, COLLECTION, "specimen-synthetic", "run-synthetic:r1", 1,
        "worker-synthetic", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite3")
    backend.grant(scope)
    store = ResearchStore(backend, "program-synthetic")
    store.initialize(scope, BudgetPolicy(500_000))
    pins = pins_for()
    store.create_job(scope, PinnedRuntime(input_digest="a" * 64, **pins), [str(key) for key in ALL_FIELDS])
    stored = store.job(scope)["pins"]
    assert stored["input_digest"] == "a" * 64
    assert {key: value for key, value in stored.items() if key != "input_digest"} == pins_for()
    # Creating it again with rebuilt pins replays the same job.
    store.create_job(scope, PinnedRuntime(input_digest="a" * 64, **pins_for()), [str(key) for key in ALL_FIELDS])


def test_qualified_taxonomy_and_geography_sources_are_pinned():
    pins = pins_for()
    registry = registered_pins.registered_registry(pins["sources"])
    geography = {"geolocate", "georeference_history", "georeference_spatial", "tgn", "wikidata", "nga"}
    assert {policy.id for policy in registry.policies if policy.ready} == set(TAXONOMY_APIS) | geography
    assert set(SOURCE_READINESS) == set(TAXONOMY_APIS) | geography
    # Lane G's qualification, read from sources.py so the two cannot drift.
    assert SOURCE_READINESS["geolocate"] == sources.GEOLOCATE_QUALIFICATION
    assert set(sources.GEOLOCATE_QUALIFICATION) == registered_pins._READINESS
    geolocate = registry.get("geolocate")
    assert {key: getattr(geolocate, key) for key in registered_pins._READINESS} == (
        sources.GEOLOCATE_QUALIFICATION)
    assert geolocate.schema_digest == digest(sources.GEOLOCATE_SCHEMA)
    assert geolocate.source_release == sources.GEOLOCATE_RELEASE
    assert CAPTURE_POLICIES["geolocate"] == ("full_response", 1)
    capture = registered_pins.registered_capture_policies(pins["sources"], registry)
    assert capture["geolocate"].kind == "full_response" and capture["geolocate"].maximum_responses == 1
    assert capture["geolocate"].source_policy_digest == digest(geolocate)
    assert {capture[key].kind for key in ("tgn", "wikidata", "nga")} == {"full_response"}
    assert {capture[key].maximum_responses for key in ("tgn", "wikidata", "nga")} == {3}
    assert capture["georeference_history"].kind == "pinned_dataset"
    assert capture["georeference_spatial"].kind == "computed"


def test_readiness_rows_hold_the_committed_canary_schemas_and_a_repository_reference():
    canaries = {row["source_id"]: row for row in json.loads(CANARIES.read_text())["results"]}
    for source_id in TAXONOMY_APIS:
        row = SOURCE_READINESS[source_id]
        assert set(row) == registered_pins._READINESS
        assert row["qualification_state"] == "searched"
        assert row["schema_digest"] == digest(canaries[source_id]["schema_keys"])
        assert row["qualification_receipt"] == (
            "repo:src/specimen_digitization/research_harness/source_readiness.py"
            f"#SOURCE_READINESS.{source_id}")
    assert SOURCE_READINESS["catalogue_of_life"]["source_release"] == (
        canaries["catalogue_of_life"]["resolved_dataset_key"])


def install_smaller_registry(monkeypatch):
    """Installs the source registry minus one row that has a capture policy but
    is not ready (as removing google_maps did); returns the real registry and
    the dropped id. Choosing the row from the live registry keeps this true
    after any later row change."""
    real = sources.insects_registry
    dropped = next(policy.id for policy in reversed(real().policies)
        if policy.id in CAPTURE_POLICIES and policy.id not in SOURCE_READINESS)

    def smaller(*, qualification_overrides=None):
        registry = real(qualification_overrides=qualification_overrides)
        return sources.SourceRegistry([p for p in registry.policies if p.id != dropped])

    monkeypatch.setattr(committed_pins, "insects_registry", smaller)
    monkeypatch.setattr(registered_pins, "insects_registry", smaller)
    return real, dropped


def test_capture_rows_follow_the_installed_registry(monkeypatch):
    real, dropped = install_smaller_registry(monkeypatch)
    pins = pins_for()
    assert dropped not in pins["sources"]["capture_policies"]
    assert dropped not in {row["id"] for row in pins["sources"]["registry_policies"]}
    assert pins["sources"]["registry_digest"] != real().digest


def test_pins_built_on_a_smaller_registry_hold_exactly_the_installed_rows(monkeypatch):
    real, _ = install_smaller_registry(monkeypatch)
    installed = committed_pins.insects_registry()
    assert len(installed.policies) == len(real().policies) - 1
    pins = pins_for()
    assert [row["id"] for row in pins["sources"]["registry_policies"]] == [
        policy.id for policy in installed.policies]
    registry = registered_pins.registered_registry(pins["sources"])
    assert registry.digest == pins["sources"]["registry_digest"]
    assert set(registered_pins.registered_capture_policies(pins["sources"], registry)) == (
        set(CAPTURE_POLICIES) & {policy.id for policy in installed.policies})
    assert set(registered_pins.registered_model_prices(pins["sources"], bindings_of(pins))) == (
        set(SpecialistRole))


def test_a_job_pinned_on_the_old_registry_is_not_reused_after_a_row_is_removed(monkeypatch):
    stale = committed_job_pins(published(), organization_id=ORG, collection_id=COLLECTION,
        input_digest="a" * 64)
    registered_pins.registered_registry(stale["sources"])
    _, dropped = install_smaller_registry(monkeypatch)
    assert dropped in {row["id"] for row in stale["sources"]["registry_policies"]}
    rebuilt = committed_job_pins(published(), organization_id=ORG, collection_id=COLLECTION,
        input_digest="a" * 64)
    # NativeResearchRuntimeFactory.open holds a job whose pins differ from a
    # rebuild, and the registry validator it applies next refuses the old rows.
    assert stale != rebuilt
    assert stale["sources"]["registry_digest"] != rebuilt["sources"]["registry_digest"]
    with pytest.raises(HeldUnknown, match="research_registered_source_policies_missing"):
        registered_pins.registered_registry(stale["sources"])


def test_the_harness_route_is_priced_at_the_cited_list_price():
    profile = published()
    assert profile.harness_route == committed_harness_route(profile) == "harness-deepseek"
    route = HUGGINGFACE_ROUTES["harness-deepseek"]
    assert (route.logical_capability, tuple(route.required_input_modalities)) == ("field_harness", ("text",))
    prices = profile.processing.price_list
    # The pins carry whatever version the published price list has.
    assert prices.version.startswith("pilot-prices-")
    assert {binding["price_version"] for binding in pins_for()["model"].values()} == {prices.version}
    row = prices.models["harness-deepseek"].model_dump(exclude_none=True)
    assert {key: row[key] for key in ("input_micros_per_million", "output_micros_per_million",
        "context_tokens")} == {
        "input_micros_per_million": 200_000,
        "output_micros_per_million": 600_000,
        "context_tokens": 1_048_576,
    }
    source = Path(committed_pins.__file__).read_text()
    cited = re.search(r"USD (\d+\.\d+) / (\d+\.\d+) per 1M input / output tokens", source)
    assert tuple(round(float(value) * 1_000_000) for value in cited.groups()) == (200_000, 600_000)
    assert "https://router.huggingface.co/v1/models" in source
    assert "https://deepinfra.com/deepseek-ai/DeepSeek-V4.1-Flash" in source
    row = pins_for()["sources"]["model_prices"]["specimen_taxonomy"]
    assert (row["route_id"], row["model_id"], row["provider"]) == (
        "harness-deepseek", route.model_id, route.provider)
    assert (row["input_micro_usd_per_million_tokens"], row["output_micro_usd_per_million_tokens"]) == (
        200_000, 600_000)
    assert row["owner_registration_digest"] == profile.digest


def test_one_request_reserves_its_worst_case_within_the_run_allowance():
    pins = pins_for()
    row = pins["sources"]["model_prices"]["specimen_geography"]
    model = pins["model"]["specimen_geography"]
    liability = -(-(row["max_input_tokens"] * 200_000 + MAX_OUTPUT_TOKENS * 600_000) // 1_000_000)
    assert model["reservation_micro_usd"] == liability == 212_173
    assert liability <= committed_run_cost_limit_micros(published()) == 1_000_000
    assert row["max_input_tokens"] == 1_048_576
    assert pins["settings"] == {"max_tokens": MAX_OUTPUT_TOKENS} and model["max_tokens"] == MAX_OUTPUT_TOKENS


def test_the_request_bound_admits_the_largest_geography_request():
    bound = pins_for()["sources"]["model_request_bounds"]["specimen_geography"]
    assert bound["maximum_serialized_bytes"] == REQUEST_BOUND["maximum_serialized_bytes"] >= 72 * 1024
    assert bound["tokenizer_source_sha256"] == TOKENIZER_PIN["tokenizer_json_sha256"] == (
        "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b")  # pragma: allowlist secret (pinned digest)
    assert bound["chat_template_source_sha256"] == TOKENIZER_PIN["chat_template_jinja_sha256"] == (
        "d959d804d5101b79a49b6ff1bf3c54cd5affa9a5a78c503d925f3090040b31c3")  # pragma: allowlist secret (pinned digest)
    assert TOKENIZER_PIN["hf_commit"] == "2cba9e42aa026125f3ed06c6d98c1db82f7ca027"  # pragma: allowlist secret (pinned commit id)


def test_the_gateway_digest_is_read_from_the_installed_file(tmp_path, monkeypatch):
    installed = Path(model_gateway.__file__).read_bytes()
    bound = pins_for()["sources"]["model_request_bounds"]["specimen_temporal"]
    assert bound["gateway_source_sha256"] == hashlib.sha256(installed).hexdigest()
    changed = tmp_path / "model_gateway.py"
    changed.write_bytes(installed + b"\n")
    monkeypatch.setattr(model_gateway, "__file__", str(changed))
    rebuilt = pins_for()["sources"]["model_request_bounds"]["specimen_temporal"]
    assert rebuilt["gateway_source_sha256"] == hashlib.sha256(installed + b"\n").hexdigest()


def test_a_price_change_changes_the_pins():
    before, after = pins_for(), pins_for(with_harness_price(input_micros_per_million=210_000))
    assert before != after
    assert after["sources"]["model_prices"]["specimen_taxonomy"]["input_micro_usd_per_million_tokens"] == 210_000
    assert after["model"]["specimen_taxonomy"]["reservation_micro_usd"] > 107_725


def test_a_profile_without_a_registered_harness_route_has_no_pins():
    data = published().model_dump(mode="json")
    del data["harness_route"]
    assert committed_harness_route(data) is None
    with pytest.raises(ValueError, match="research_committed_harness_route_unavailable"):
        pins_for(data)
    # A priced route that is not a text-only harness route is not one either.
    assert committed_harness_route(dict(data, harness_route="first-pass-glm")) is None
    assert committed_harness_route({}) is None


def test_the_pins_fit_one_state_document_per_run_with_room_to_spare():
    assert len(canonical(pins_for())) < MAX_STATE_BYTES // 8


def test_twenty_publications_of_a_full_run_fit_one_state_document(tmp_path):
    # One research state document per run: all 20 fields of a run built from
    # the committed pins must be publishable before the document is full.
    scope = DurabilityScope(ORG, COLLECTION, "specimen-synthetic", "run-synthetic-r1", 1,
        "worker-synthetic", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite3")
    backend.grant(scope)
    store = ResearchStore(backend, "program-synthetic")
    store.initialize(scope, BudgetPolicy(500_000))
    fields = [str(key) for key in ALL_FIELDS]
    assert len(fields) == 20
    store.create_job(scope, PinnedRuntime(input_digest="a" * 64, **pins_for()), fields)
    lease = store.claim(scope, "worker-synthetic", ttl_seconds=300)
    # Each checkpoint about the size of a typed resolution in the e2e run.
    for field in fields:
        store.checkpoint(scope, lease, field, {"resolution": {"field_key": field,
            "work_state": "resolved", "note": "x" * 4000}}, expected_revision=0)
    for field in fields:
        guard = store.prepare_publication(scope, lease, field, expected_field_revision=1,
            expected_record_revision=0)
        assert "pins" not in guard
        store.validate_publication(scope, guard)
    size = len(canonical(backend.load(scope, "program-synthetic").state))
    assert size < MAX_STATE_BYTES // 2, size


def test_pins_hold_the_live_thirteen_row_registry_without_google_maps():
    # registered_pins.registered_registry requires exactly the installed rows;
    # after G34/G38 the eight original rows gain three gazetteers and two
    # locally computed sources; Google Maps remains excluded.
    installed = [policy.id for policy in sources.insects_registry().policies]
    pins = pins_for()
    ids = [row["id"] for row in pins["sources"]["registry_policies"]]
    assert ids == installed and len(ids) == 13
    assert "google_maps" not in ids and "google_maps" not in pins["sources"]["capture_policies"]
    registered_pins.registered_registry(pins["sources"])
