"""The slide pilot profile as configuration (docs/execution/golive/LANE.md, T4)."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import runtime_config
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    CollectionProfileRegistry,
    DateRules,
    published_registry,
)
from specimen_digitization.application.collection_runtime import classify_and_select
from specimen_digitization.application.domain import (
    MANDATORY,
    FieldValue,
    Principal,
    Profile,
    Region,
    Run,
    Scope,
)
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.review_risk import (
    RiskPolicy,
    RiskPolicyReference,
)
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters, crop_bytes

from test_api_runtime import config_env
from test_lane_trigger import RecordingDispatcher, intake, specimen_with

REPOSITORY = Path(__file__).resolve().parents[1]
COLLECTION_UUID = "00000000-0000-4000-8000-0000000000c1"
SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
USER = "lane-reviewer"
FIELD_TOOLS = {
    "taxon": ("taxonomy_verifier",),
    "country": ("geography_lookup",),
    "province_state": ("geography_lookup",),
    "county": ("geography_lookup",),
    "city": ("geography_lookup",),
    "precise_location": ("geography_lookup",),
    "fmnh_ins_number": ("catalog_number_validator",),
    "date_visited_from": ("date_parser",),
    "date_visited_to": ("date_parser",),
    "date_identified": ("date_parser",),
}


def pilot():
    return published_registry().resolve("insects").profile


def test_the_published_tree_is_the_reviewed_tree():
    reviewed = json.loads(
        (REPOSITORY / "infra/reference/fieldmuseum-collection-tree.json").read_text()
    )["collections"]
    assert {
        (node.id, node.parent_id, node.name) for node in published_registry().nodes
    } == {(c["key"], c["parent"], c["name"]) for c in reviewed}


def test_the_slide_pilot_profile_carries_the_specified_settings():
    profile = pilot()
    assert (profile.id, profile.version, profile.state) == (
        "zoology_insects_slides",
        "1.0.0",
        "active",
    )
    assert profile.collection_id == "insects" and not profile.synthetic
    assert profile.model_routes == ("handwriting-qwen", "handwriting-muse")
    assert profile.mandatory_fields == tuple(
        key for key in MANDATORY if key != "identified_by_irn"
    )
    assert profile.optional_fields == ("identified_by_irn",)
    assert {
        "elevation_from_m",
        "elevation_to_m",
        "elevation_from_ft",
        "elevation_to_ft",
    } <= set(profile.mandatory_fields)
    assert profile.field_tools == FIELD_TOOLS
    assert set(profile.tools) == {tool for tools in FIELD_TOOLS.values() for tool in tools}
    assert "identified_by_irn" not in profile.field_tools
    assert profile.segmentation_settings.prompt == "label"
    assert profile.clearance_policy == "insects-clearance-v1"
    assert profile.first_pass_route is None and profile.harness_route is None
    assert not profile.institutional_policy_approved
    assert not profile.semantics_confirmed
    allowance = profile.processing
    assert allowance.run_cost_limit_micros == 500_000
    assert allowance.stage_cost_micros.cost_micros == {
        "segment": 15_000,
        "transcribe:handwriting-qwen": 20_000,
        "transcribe:handwriting-muse": 20_000,
        "parse": 20_000,
    }
    assert (allowance.max_tokens, allowance.max_external_calls) == (480_000, 96)
    assert profile.date_rules == DateRules(
        version="date-rules-v1", two_digit_year_century=1900
    )


@pytest.mark.parametrize("century", [1950, 0, -100, 10000])
def test_date_rules_name_a_whole_century(century):
    with pytest.raises(ValueError):
        DateRules(version="date-rules-v1", two_digit_year_century=century)


def test_the_pilot_references_the_existing_uncalibrated_risk_policy():
    reference = pilot().scoring_policy_ref
    default = RiskPolicy()
    assert (reference.id, reference.version, reference.digest) == (
        default.id,
        default.version,
        default.sha256,
    )
    assert default.calibration_dataset_version is None and not default.synthetic
    resolution = published_risk_registry().resolve(
        RiskPolicyReference.model_validate(reference.model_dump()),
        allow_synthetic=False,
    )
    assert resolution.status == "resolved", resolution.reason


def test_resolution_walks_up_to_the_nearest_mapped_collection():
    published = published_registry()
    assert published.resolve("zoology").reason == "missing_mapping"
    assert published.resolve("mammals").reason == "missing_mapping"
    assert published.resolve("nowhere").reason == "unknown_collection"
    extended = CollectionProfileRegistry(
        version=published.version,
        nodes=published.nodes
        + (CollectionNode(id="psocodea", parent_id="insects", name="Psocodea"),),
        profiles=published.profiles,
        mappings=published.mappings,
    )
    inherited = extended.resolve("psocodea")
    assert inherited.status == "selected"
    assert inherited.profile.id == "zoology_insects_slides"


def test_bindings_translate_private_identifiers_and_stay_private():
    bound = published_registry({COLLECTION_UUID: "insects"})
    assert bound.resolve(COLLECTION_UUID).profile.id == "zoology_insects_slides"
    assert bound.resolve("insects").profile.id == "zoology_insects_slides"
    assert COLLECTION_UUID not in json.dumps(bound.model_dump(mode="json"))
    assert COLLECTION_UUID not in bound.model_dump_json()
    with pytest.raises(ValueError):
        published_registry({COLLECTION_UUID: "no-such-collection"})


def test_classify_gives_the_run_every_field_with_its_group(tmp_path):
    run = Run(
        profile=Profile(synthetic=False),
        classification_selection={
            "collection_id": "insects",
            "actor_id": USER,
            "reason": "Intake collection",
        },
    )
    specimen = specimen_with(run)
    blobs = LocalBlobs(tmp_path / "blobs")
    issue = classify_and_select(
        specimen, published_registry(), None, blobs, published_risk_registry()
    )
    assert issue is None
    assert set(specimen.run.fields) == set(MANDATORY)
    assert specimen.run.field_groups == {
        key: "optional" if key == "identified_by_irn" else "mandatory"
        for key in MANDATORY
    }
    assert "identified_by_irn" not in specimen.run.profile.mandatory_fields


def test_runs_without_optional_fields_serialize_as_before():
    assert "field_groups" not in Run().model_dump()


def test_collection_bindings_configuration():
    env = config_env()
    assert runtime_config.RuntimeConfig.from_env(env).collection_bindings == ()
    bound = runtime_config.RuntimeConfig.from_env(
        dict(env, SPECIMEN_COLLECTION_BINDINGS_JSON=json.dumps({COLLECTION_UUID: "insects"}))
    )
    assert bound.collection_bindings == ((COLLECTION_UUID, "insects"),)
    for value in ("not json", "[]", json.dumps({COLLECTION_UUID: 3}), json.dumps({"": "insects"})):
        with pytest.raises(ValueError):
            runtime_config.RuntimeConfig.from_env(
                dict(env, SPECIMEN_COLLECTION_BINDINGS_JSON=value)
            )


class ProductionLikeAdapters(SyntheticAdapters):
    """Readers that read their region crop, as ProductionAdapters' readers do."""

    def segment(self, specimen):
        return [
            Region(
                asset_id=specimen.asset.id,
                x=0,
                y=0,
                width=specimen.asset.width,
                height=specimen.asset.height,
                order=0,
                method="lab_fixture_region",
                version="1",
            )
        ]

    def transcribe(self, specimen, region, route):
        observation = super().transcribe(specimen, region, route)
        crop = crop_bytes(self.blobs, specimen, region)
        return observation.model_copy(
            update={"input_sha256": hashlib.sha256(crop).hexdigest()}
        )


def test_emulator_runs_with_production_readers_pass_parse(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    dispatcher = RecordingDispatcher()
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=ProductionLikeAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=dispatcher,
    )
    row = intake(TestClient(app, raise_server_exceptions=False))
    assert row["status"] == "pending"
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    specimen = app.state.workflow.drain(principal, row["specimen_id"])
    assert specimen.run.profile.id == "zoology_insects_slides"
    assert specimen.run.profile.execution.max_tokens == 480_000
    assert specimen.run.profile.execution.max_external_calls == 96
    assert "parse" in specimen.run.completed_steps, specimen.run.blocker
    assert specimen.run.field_groups["identified_by_irn"] == "optional"


def test_production_app_passes_the_published_registries(monkeypatch):
    from types import SimpleNamespace

    import firebase_admin

    from specimen_digitization.application import cli, runtime_auth, runtime_health

    config = runtime_config.RuntimeConfig.from_env(
        dict(
            config_env(),
            SPECIMEN_COLLECTION_BINDINGS_JSON=json.dumps({COLLECTION_UUID: "insects"}),
        )
    )
    captured = {}
    monkeypatch.setattr(runtime_config, "build_provenance", lambda required: {})
    monkeypatch.setattr(
        firebase_admin,
        "get_app",
        lambda name: SimpleNamespace(
            project_id=config.project_number
            if name == "specimen-api-app-check"
            else config.project
        ),
    )
    monkeypatch.setattr(runtime_auth, "firebase_verifier", lambda *_: None)
    monkeypatch.setattr(runtime_health, "install_health", lambda *_, **__: None)
    monkeypatch.setattr(runtime_health, "cloud_probe", lambda *_: None)
    monkeypatch.setattr(runtime_health, "DependencyReadiness", lambda *_: None)
    monkeypatch.setattr(cli, "GcsBlobs", lambda **_: object())
    monkeypatch.setattr(
        cli,
        "SqlConnectRepository",
        lambda **_: SimpleNamespace(memberships=lambda user: []),
    )
    monkeypatch.setattr(cli, "ProductionAdapters", lambda blobs: object())
    monkeypatch.setattr(
        cli, "create_app", lambda **kwargs: captured.update(kwargs) or object()
    )
    cli.production_app(config)
    registry = captured["profile_registry"]
    assert registry.resolve(COLLECTION_UUID).profile.id == "zoology_insects_slides"
    assert captured["risk_registry"].version == published_risk_registry().version


def test_a_regions_correction_keeps_every_field_and_its_group(tmp_path):
    from test_application import HEADERS, PREFIX

    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=ProductionLikeAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    client = TestClient(app, raise_server_exceptions=False)
    row = intake(client)
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    drained = app.state.workflow.drain(principal, row["specimen_id"])
    assert drained.run.field_groups
    response = client.post(
        PREFIX + f"/specimens/{row['specimen_id']}/regions",
        headers=dict(HEADERS, **{"Idempotency-Key": "regions-1"}),
        json={
            "expected_revision": drained.version,
            "base_run_id": drained.run.id,
            "reason": "Reviewer drew the label",
            "regions": [
                {
                    "asset_id": drained.asset.id,
                    "x": 0,
                    "y": 0,
                    "width": drained.asset.width,
                    "height": drained.asset.height,
                    "order": 0,
                    "method": "reviewer_drawn",
                    "version": "1",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    run = SQLiteRepository(tmp_path / "state.sqlite3").get(SCOPE, row["specimen_id"]).run
    assert run.id != drained.run.id
    assert run.field_groups == drained.run.field_groups
    assert set(run.fields) == set(drained.run.field_groups)
    assert all(value == FieldValue() for value in run.fields.values())
