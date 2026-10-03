"""The reviewable release templates must still satisfy the real plan validators.

Raw retired origins are pinned and denied by current guards; separately reviewed
synthetic copies bind literal current source hashes. Each template is loaded, its `<OWNER:...>` placeholders are
replaced with syntactically valid dummies, and the result is handed to the same
validation functions the protected workflows call. A template whose keys drift
away from a validator's exact key set fails here, before a release run pays for
the mistake. Nothing in this file contacts a cloud, mints a packet or deploys.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import bootstrap_release
import deploy_data as data
import deploy_runtime as runtime
import mint_release_packet
import release_initialize
import validate_release_packet
from test_data_initialization import catalog_recipient
from test_runtime_release import NOW

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "infra/release"
OWNER_INPUTS = TEMPLATES / "OWNER_INPUTS.md"
PLACEHOLDER = re.compile(r"<OWNER:([a-z0-9_]+)>")
PROJECT_NUMBER = "716045864126"
SOURCE_SHA = "a" * 40
PLAN_TEMPLATES = (
    "data-initialization-inventory.plan.template.json",
    "data-initialize-missing.plan.template.json",
    "data-apply.plan.template.json",
    "data-bootstrap.plan.template.json",
    "runtime-build.plan.template.json",
    "runtime-prepare.plan.template.json",
    "runtime-activate.plan.template.json",
)
ALL_TEMPLATES = PLAN_TEMPLATES + ("evidence-digests.template.json",)


# Frozen raw legacy origins remain unchanged and are refused by the current validator.
# Only synthetic test copies receive this reviewed, literal current source set.
RETIRED_DATA_TEMPLATE_SHA256 = {'data-apply.plan.template.json': '53bb8be429c7d4e562d0519a78b8d7da53ffcd544ae8acaf57cc36443ebf5ef1',
 'data-bootstrap.plan.template.json': '5ab1ded821d4afc9a7d3a529d27e46d242b9d16e0e5301b615a03435eea449da',
 'data-initialize-missing.plan.template.json': 'b18bf7bf21fc0737ff705e4beb4e586aac80ab0ff50f6c53bc9c6591061fc1ff'}
CURRENT_DATA_SOURCE_FILES = {'dataconnect/connector/artifacts.gql': '4d4da17483f84409419323b44441dfde83719c337d48386e2bc451fb7dee3040',
 'dataconnect/connector/auxiliary.gql': '859dec52ba7f4212da4728ab77634766115914a4c66d10df92d662be9c825114',
 'dataconnect/connector/checksum.gql': '4717f7368643b67d1ac4300ed3a02b1679580e7ba63cb81c6f0eb080bc271633',
 'dataconnect/connector/connector.yaml': '112dd6af54062562a6c76b7034b46a54635e13fdcc6b5441e738a3f0e3596ebe',
 'dataconnect/connector/history_restore.gql': 'b10726add6208ac4ff5484788404150d6751133a70f8a00ddfa528972dcaa365',
 'dataconnect/connector/operations.gql': '65ac18159fbed968f058e86df1f7e62b6a6274da40e7a8639ac78efb1d221264',
 'dataconnect/connector/paging.gql': 'e1b9a90c5989cb602aaccddd2f19994b73aa0965cc5b28bea5282d59ced5b4bb',
 'dataconnect/connector/projection.gql': '00f887b0e9064f94418d7426e414106ba81362d0e992b7bfd066545ec7817da9',
 'dataconnect/connector/readiness.gql': 'ae5f7aedbb5c971894fd3a7e2726406bc2463b781a79d833deea5891ac56bfd9',
 'dataconnect/connector/research_binding_v2.gql': '42fb9f0b04d19a6bf24dfce6c93f6ad81cc2da4854bb9afef5c9ac04abab7505',
 'dataconnect/connector/research_harness.gql': 'e55b3694001f138029457d28f422e242da2dfe0f51af9631edb5c1d10b34e79f',
 'dataconnect/connector/research_materialization_inputs_v2.gql': 'fcd991a489dadaa7e5ce512daa6bf0dd518bdc53ae1c23444c223e2c29a777ee',
 'dataconnect/connector/research_publication_v2.gql': '6ad9839de972b81a17f59fb348b83e094f039d39e1b3dc3f51d0ec626801372e',
 'dataconnect/connector/scheduling.gql': 'c12e53ae48fa342deaa2479c4aeca0298b1caf7e2288550d81ec9796f38c51ef',
 'dataconnect/connector/search.gql': '4d344d2acfcc0566719268acff25472975c6136977aa31fde2c8ada29983d681',
 'dataconnect/connector/sensitivity.gql': '521774b8dcef9e0c0c1c43481ae19ad808aafbe08b32c3111e2287313cf1db1f',
 'dataconnect/dataconnect.yaml': '8355ece3fb4b1bebf920c05f2cb358229877cca9d0a0abc6e8cdc0da2756423a',
 'dataconnect/schema/canonical_value_lineage_v2.gql': '7725944af2cdb89289f1876ddd9607ef3edc286302c8af4bc3bfb821ee4b1a78',
 'dataconnect/schema/legacy_import_proof_v1.gql': '753b929178c0b630abbd9f76e01d350f5bcecaa3fcab426774d815c76812b4d5',
 'dataconnect/schema/research_harness.gql': '2195ac06e3584e2b35a324d184a34df221fc0c1374740aabba6b9b87e82b9507',
 'dataconnect/schema/research_publication_v2.gql': 'f5c279f7088cda20d29aa46a0d7f80f85a44fd52dd7cd319f44b97b4ed588766',
 'dataconnect/schema/schema.gql': '26d291d0d229dc4da957477e431e25e0afbb34f5fcb5e9463b389b34f114ca2c',
 'dataconnect/schema/search.gql': 'a7ff0616ed6045d958f7a35eccffbe51671d395fa43a695ccdca7892e724b32a',
 'dataconnect/sql/checksum-audit.sql': '4ba591e82873c5d829c07267447e792b01f32675575fa00bb2b0b3657c27301c',
 'dataconnect/sql/drop-specimen-unique-1.sql': 'c4fcf4484d43f1021952bc4abfb88307a3af4da66f879996e06043835f9ffb65',
 'dataconnect/sql/paging-indexes.sql': '1fd9ab5a7d9048fc19c6edbaa0bc5081eca632f7b7961e06c5e7e7f714d85480',
 'dataconnect/sql/search-indexes.sql': '4d9366222bc073273b2d5f9b3706c429bf5ddd15497229fdc994246110f0e88d',
 'storage.rules': '8d8bf2202a428894aaa46278bfc68c33dce0fd405e547b952a408e930d380893'}


# The frozen initialization origins remain evidence of their reviewed bytes.
# Only synthetic load() copies receive these literal current source pins.
RETIRED_INITIALIZATION_TEMPLATE_SHA256 = {
    'data-initialization-inventory.plan.template.json': '389f82d69d46bede7689cfa4b22fd5f020bef41ba309dcce80be1cc9f8f09639',
    'data-initialize-missing.plan.template.json': 'b18bf7bf21fc0737ff705e4beb4e586aac80ab0ff50f6c53bc9c6591061fc1ff',
}
CURRENT_INITIALIZATION_FILES = {
    'scripts/ci/release_initialize.py':
        'sha256:732a743bff742a7a6d94583ad090711824ee7ed5077b063dd20127f962e30321'.removeprefix('sha256:'),
    'scripts/ci/release_initialize.mjs': '64e9512840a66687158c1d1b3e477a720385a68f8334e02e3a5a845296eb076f',
    'scripts/ci/initialize_database.sql': 'a48409621264c6918b9f2bddb01366df022a01d4d149aca5768a8fc3f0d2a52b',
    'scripts/ci/initialize_catalog.sql': 'd7262f8fc62d823e0a27ad602035c4cd144b003cfb7efadfadc506c03e5083dd',
    'scripts/ci/initialize_postconditions.sql': '8a57dbd6ab3cd999c63371d76d96a420743e167fa1ce820ae378d2387e122c2d',
    'scripts/ci/release_catalog_envelope.py': '59bb843ee485eedd1b0e627886c468349a6be76d00049031619ba025af9b3c1d',
}
RETIRED_INITIALIZER_SOURCE_FILES = {
    # Exact pre-repair public source digest retained by both frozen origins.
    'scripts/ci/release_initialize.py': 'af118d73ce6a7a6cfc9e49cd44f3287534cc8e711a078ce390097c1272fd1b79',
}


def load_raw(name):
    raw = (TEMPLATES / name).read_bytes()
    if name in RETIRED_DATA_TEMPLATE_SHA256:
        assert hashlib.sha256(raw).hexdigest() == RETIRED_DATA_TEMPLATE_SHA256[name]
    if name in RETIRED_INITIALIZATION_TEMPLATE_SHA256:
        assert hashlib.sha256(raw).hexdigest() == RETIRED_INITIALIZATION_TEMPLATE_SHA256[name]
    return json.loads(raw)


def load(name):
    value = load_raw(name)
    if name in RETIRED_DATA_TEMPLATE_SHA256:
        value["source_files"] = dict(CURRENT_DATA_SOURCE_FILES)
    if name == "data-initialization-inventory.plan.template.json":
        value["initialization_files"] = dict(CURRENT_INITIALIZATION_FILES)
    elif name == "data-initialize-missing.plan.template.json":
        value["initialization"]["files"] = dict(CURRENT_INITIALIZATION_FILES)
    return value


def placeholders(value):
    return set(PLACEHOLDER.findall(json.dumps(value)))


def fill(value, table):
    """Replace each exact `<OWNER:name>` string; an undocumented name fails."""
    if isinstance(value, dict):
        return {key: fill(item, table) for key, item in value.items()}
    if isinstance(value, list):
        return [fill(item, table) for item in value]
    if isinstance(value, str):
        match = PLACEHOLDER.fullmatch(value)
        if match:
            assert match.group(1) in table, f"no dummy for placeholder {value}"
            return table[match.group(1)]
        assert not PLACEHOLDER.search(value), f"placeholder embedded in a larger string: {value}"
    return value


def secret_version(name):
    return f"projects/specimen-digitization/secrets/{name}/versions/1"


# ------------------------------------------------------------------- dummies ---


def common_dummies():
    recipient = catalog_recipient()
    return {
        "source_sha": SOURCE_SHA,
        "authorization_sha256": "1" * 64,
        "independent_review_sha256": "2" * 64,
        "pilot_manifest_sha256": "b" * 64,
        "pool_id": "github-actions",
        "sql_settings_version": "17",
        "storage_ruleset_name": "projects/specimen-digitization/rulesets/0000-1111-2222",
        "catalog_recipient_public_key_pem": recipient["public_key_pem"],
        "catalog_recipient_public_key_sha256": recipient["public_key_sha256"],
        "data_ready_receipt_sha256": "c" * 64,
        "data_ready_run_id": 1234567890,
        "data_ready_run_attempt": 1,
        "data_ready_source_sha": "d" * 40,
    }


def recovery_dummies():
    """One consistent two-hour recovery window inside one authorization packet."""
    return {
        "restore_clone_tier": "db-f1-micro",
        "source_disk_gb": 10,
        "source_database_version": "POSTGRES_18",
        "recovery_expires_at_unix": NOW + 7000,
        "clone_allowance_baseline_sha256": "e" * 64,
        "clone_allowance_iam_sha256": "f" * 64,
        "clone_allowance_issued_at_unix": NOW - 20,
        "clone_allowance_expires_at_unix": NOW + 7100,
        "backup_retention_expires_at_unix": NOW + 100000,
        "backup_max_chargeable_bytes": 10 * 1024 ** 3,
    }


def recovery_packet():
    return {
        "source_sha": SOURCE_SHA,
        "source_tree_sha": "9" * 40,
        "authorization_sha256": "1" * 64,
        "independent_review": {"report_sha256": "2" * 64},
        "identity": {"project_number": PROJECT_NUMBER, "pool_id": "github-actions"},
        "pilot": {"manifest_sha256": "b" * 64},
        "release_run_id": 1234567890,
        "release_run_attempt": 1,
        "issued_at_unix": NOW - 10,
        "expires_at_unix": NOW + 7100,
    }


def runtime_packet():
    return {
        "source_sha": SOURCE_SHA,
        "identity": {"project_number": PROJECT_NUMBER},
        "pilot": {"manifest_sha256": "b" * 64},
        "authorization_sha256": "1" * 64,
        "issued_at_unix": NOW,
        "expires_at_unix": NOW + 4000,
        "budget": {"version": "shared-release-reservations/v2",
                   "approval_sha256": runtime.APPROVAL_SHA256,
                   "reservations": [{"category": "provider", "ceiling_micros": 10000},
                                    {"category": "sam", "ceiling_micros": 10000}]},
    }


def runtime_dummies():
    return {
        **common_dummies(),
        "readiness_object": "application/sha256/" + "a" * 64,
        "readiness_object_generation": "1757980800",
        "worker_launch_secret_version": secret_version("pilot-launch"),
        "pilot_manifest_secret_version": secret_version("pilot-manifest"),
        "worker_launch_sha256": "2" * 64,
        "ready_manifest_sha256": "3" * 64,
        "sam_expires_at_unix": NOW + 2200,
        "sam_checkpoint_sha256": "4" * 64,
        "sam_checkpoint_prefix": "application/sha256/" + "4" * 64 + "/sam3-cache",
    }


def bootstrap_identity():
    return {
        "requested_uid": "release-owner-uid-0000000000",
        "requested_email": "release.owner@example.invalid",
        "organization_id": "00000000-0000-4000-8000-000000000064",
        "organization_name": "Example Organization",
    }


def reviewed_tree():
    return (ROOT / bootstrap_release._prepared.TREE_PATH).read_bytes()


def hierarchy_collections():
    """One deterministic synthetic UUID per reviewed key, in reviewed order."""
    entries = bootstrap_release._prepared.tree_entries(reviewed_tree())
    return [{"key": entry["key"], "id": f"00000000-0000-4000-8000-0000000{index:05x}",
             "name": entry["name"], "parent": entry["parent"]}
            for index, entry in enumerate(entries, start=1)]


def prepared_hierarchy():
    scope = bootstrap_identity()
    record = {"uid": scope["requested_uid"], "email": scope["requested_email"],
              "emailVerified": True, "disabled": False}
    return bootstrap_release._prepared.prepare_first_scope_hierarchy(
        auth_record=record, collections=hierarchy_collections(), admin_collection_key="insects",
        tree=reviewed_tree(), **scope)


# --------------------------------------------------------- documentation gate ---


def documented_inputs():
    rows = re.findall(r"^\| `([a-z0-9_]+)` \|", OWNER_INPUTS.read_text(), re.MULTILINE)
    assert len(rows) == len(set(rows)), "the owner inputs table repeats a placeholder"
    return set(rows)


def test_every_placeholder_is_documented_and_every_documented_row_is_used():
    used = set()
    for name in ALL_TEMPLATES:
        used |= placeholders(load(name))
    documented = documented_inputs()
    assert used - documented == set(), "undocumented placeholders"
    assert documented - used == set(), "the owner inputs table documents unused placeholders"


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_templates_are_objects_whose_placeholders_all_have_the_exact_shape(name):
    raw = (TEMPLATES / name).read_text()
    value = json.loads(raw)
    assert isinstance(value, dict) and raw.endswith("\n")
    for found in re.findall(r"<OWNER:[^>]*>", raw):
        assert PLACEHOLDER.fullmatch(found), f"malformed placeholder {found}"


# --------------------------------------------------------------- committed bytes ---


def test_committed_fingerprints_and_fixed_identities_have_not_drifted():
    """Pinned raw origins stay immutable; fixture copies bind this exact reviewed current SDL."""
    assert data.source_fingerprints() == CURRENT_DATA_SOURCE_FILES
    inventory = load("data-initialization-inventory.plan.template.json")
    initialize = load("data-initialize-missing.plan.template.json")
    apply_plan = load("data-apply.plan.template.json")
    bootstrap = load("data-bootstrap.plan.template.json")
    assert inventory["initialization_files"] == release_initialize.fingerprints()
    assert initialize["initialization"]["files"] == release_initialize.fingerprints()
    for plan in (initialize, apply_plan, bootstrap):
        assert plan["source_files"] == data.source_fingerprints()
    init = initialize["initialization"]
    assert init["permissions"] == sorted(release_initialize.PERMISSIONS)
    assert init["disposal_permissions"] == sorted(
        "cloudsql.users." + action for action in ("get", "list", "update", "delete"))
    assert init["service_agent"] == release_initialize.AGENT
    assert init["identity"]["project_number"] == PROJECT_NUMBER
    placeholder = initialize["schema_placeholder"]
    assert placeholder["name"] == data.PREFIX + "/schemas/main"
    assert placeholder["datasources"][0]["postgresql"]["cloudSql"]["instance"].endswith(
        "/instances/" + data.SOURCE)
    assert initialize["recovery"]["clone"] == apply_plan["recovery"]["clone"] == data.CLONE
    for plan in (initialize, apply_plan):
        allowance = plan["recovery"]["allowance"]
        assert allowance["bucket"] == "specimen-digitization.firebasestorage.app"
        assert allowance["object"] == "application/release-control/first-production-restore.json"


def test_runtime_templates_keep_the_committed_runtime_identities():
    for name in ("runtime-build.plan.template.json", "runtime-prepare.plan.template.json",
                 "runtime-activate.plan.template.json"):
        plan = load(name)
        environment = plan["api"]["environment"]
        assert set(environment) == runtime.API_ENV
        assert environment["SPECIMEN_FIREBASE_PROJECT_NUMBER"] == PROJECT_NUMBER
        assert environment["SPECIMEN_CORS_ORIGINS"].split(",") == [
            "https://specimen-digitization.web.app", "https://specimen-digitization.firebaseapp.com"]
        if plan["sam"] is not None:
            assert plan["sam"]["audience"] == f"https://specimen-sam-{PROJECT_NUMBER}.us-east4.run.app"
            assert plan["worker"]["timing_version"] == runtime.TIMING_VERSION
    activate = load("runtime-activate.plan.template.json")
    trace = activate["activation"]["worker_trace"]
    assert trace["approval_sha256"] == runtime.TRACE_APPROVAL_SHA256
    assert trace["version"] == "worker-trace/v2"
    evidence = load("evidence-digests.template.json")
    assert evidence["sam_model"]["revision"] == runtime.SAM3_MODEL.revision
    assert evidence["sam_model"]["repository"] == runtime.SAM3_MODEL.repo_id


# --------------------------------------------------------------------- data ---


def test_data_initialization_inventory_template_validates():
    plan = fill(load("data-initialization-inventory.plan.template.json"), common_dummies())
    assert data.validate_plan(plan, {"source_sha": SOURCE_SHA}) is plan


def initialize_missing_plan():
    table = {**common_dummies(), **recovery_dummies(),
             "native_source_catalog_sha256": "7" * 64,
             "conditional_binding_sha256": "8" * 64,
             "disposal_binding_sha256": "9" * 64,
             "data_initialize_wif_provider": (
                 f"projects/{PROJECT_NUMBER}/locations/global/workloadIdentityPools/"
                 "github-actions/providers/specimen-data-initialize"),
             "schema_placeholder_etag": "observed-schema-etag",
             "schema_placeholder_uid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
             "schema_placeholder_create_time": "2026-09-08T12:00:00Z",
             "schema_placeholder_update_time": "2026-09-08T12:00:01Z"}
    return fill(load("data-initialize-missing.plan.template.json"), table)


def test_data_initialize_missing_template_validates():
    plan = initialize_missing_plan()
    assert data.validate_plan(plan, recovery_packet(), now=NOW) is plan
    assert plan["schema_mode"] == "initialize_missing" and plan["bootstrap"] is None
    schema, connector = data.data_bodies(plan)
    assert "schemaMigration" not in schema["datasources"][0]["postgresql"]
    assert connector["name"].endswith("/connectors/specimen-server")


def test_data_initialize_missing_template_also_validates_without_a_placeholder():
    """DATABASE_INITIALIZATION.md allows actual schema absence instead."""
    plan = initialize_missing_plan()
    plan.pop("schema_placeholder")
    plan["schema_etag"] = None
    assert data.validate_plan(plan, recovery_packet(), now=NOW) is plan


def apply_plan():
    table = {**common_dummies(), **recovery_dummies(),
             "schema_etag": "observed-schema-etag", "connector_etag": "observed-connector-etag"}
    return fill(load("data-apply.plan.template.json"), table)


def test_data_apply_template_validates():
    plan = apply_plan()
    assert data.validate_plan(plan, recovery_packet(), now=NOW) is plan
    schema, _ = data.data_bodies(plan)
    assert schema["datasources"][0]["postgresql"]["schemaValidation"] == "COMPATIBLE"


def test_data_apply_template_also_validates_in_initialize_empty_mode():
    plan = apply_plan()
    plan.update(schema_mode="initialize_empty", schema_etag=None, connector_etag=None)
    assert data.validate_plan(plan, recovery_packet(), now=NOW) is plan
    schema, _ = data.data_bodies(plan)
    assert schema["datasources"][0]["postgresql"]["schemaMigration"] == "MIGRATE_COMPATIBLE"


def bootstrap_plan():
    expected = prepared_hierarchy()
    scope = bootstrap_identity()
    table = {**common_dummies(),
             "admin_uid": scope["requested_uid"], "admin_email": scope["requested_email"],
             "org_uuid": scope["organization_id"],
             "organization_name": scope["organization_name"],
             **{"uuid_" + entry["key"].replace("-", "_"): entry["id"] for entry in hierarchy_collections()},
             "bootstrap_auth_record_sha256": expected["auth_record_sha256"],
             "bootstrap_artifact_sha256": expected["artifact_sha256"]}
    return fill(load("data-bootstrap.plan.template.json"), table), expected


def test_data_bootstrap_template_validates():
    plan, _ = bootstrap_plan()
    assert data.validate_plan(plan, {"source_sha": SOURCE_SHA}) is plan
    assert plan["bootstrap"]["sha256"] == plan["bootstrap"]["payload"]["artifact_sha256"]


def test_bootstrap_payload_is_byte_identical_to_the_preparer_output():
    """bootstrap_release.validate_prepared regenerates and compares these bytes."""
    plan, expected = bootstrap_plan()
    payload = plan["bootstrap"]["payload"]
    assert bootstrap_release.canonical(payload) == bootstrap_release.canonical(expected)
    assert bootstrap_release.validate_prepared(payload, expected["artifact_sha256"]) == expected


def test_bootstrap_template_creates_the_whole_reviewed_tree_with_private_ids():
    """The owner's minted identifiers stay placeholders; the names are reviewed."""
    payload = load("data-bootstrap.plan.template.json")["bootstrap"]["payload"]
    entries = bootstrap_release._prepared.tree_entries(reviewed_tree())
    assert payload["schema_version"] == "first-scope-hierarchy-bootstrap/v1"
    assert payload["hierarchy"]["admin_collection_key"] == "insects"
    assert payload["hierarchy"]["tree_path"] == bootstrap_release._prepared.TREE_PATH
    assert [(row["key"], row["name"], row["parent"]) for row in payload["hierarchy"]["collections"]] == [
        (entry["key"], entry["name"], entry["parent"]) for entry in entries]
    minted = {row["id"] for row in payload["hierarchy"]["collections"]}
    assert len(minted) == len(entries) and all(PLACEHOLDER.fullmatch(value) for value in minted)
    assert payload["request"]["variables"]["collectionId"] == "<OWNER:uuid_insects>"


def test_editing_the_reviewed_tree_without_reminting_fails_here():
    """The template pins the committed tree's digest, not a placeholder."""
    payload = load("data-bootstrap.plan.template.json")["bootstrap"]["payload"]
    committed = hashlib.sha256(reviewed_tree()).hexdigest()
    assert payload["hierarchy"]["tree_sha256"] == committed
    assert bootstrap_release.reviewed_tree(payload["hierarchy"]) == reviewed_tree()


# ------------------------------------------------------------------ runtime ---


def test_runtime_build_template_validates():
    plan = fill(load("runtime-build.plan.template.json"), runtime_dummies())
    assert runtime.validate_plan(plan, runtime_packet(), now=NOW) is plan
    assert plan["worker"] is None and plan["sam"] is None


def prepare_plan():
    return fill(load("runtime-prepare.plan.template.json"), runtime_dummies())


def test_runtime_prepare_template_validates_and_bounds_every_resource():
    plan = prepare_plan()
    packet = runtime_packet()
    assert runtime.validate_plan(plan, packet, now=NOW) is plan
    images = {role: f"{runtime.REGISTRY}/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    bodies = runtime.resource_bodies(plan, packet, images, "123", "1", now=NOW)
    assert bodies["api"]["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": 2}
    assert bodies["sam"]["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": 1}
    assert bodies["worker"]["template"]["template"]["maxRetries"] == 0
    assert "runExecutionToken" not in bodies["worker"]


def test_runtime_prepare_template_validates_as_the_first_api_only_preparation():
    plan = prepare_plan()
    plan["worker"] = plan["sam"] = None
    packet = runtime_packet()
    assert runtime.validate_plan(plan, packet, now=NOW) is plan
    images = {role: f"{runtime.REGISTRY}/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    assert set(runtime.resource_bodies(plan, packet, images, "123", "1", now=NOW)) == {"api"}


def activate_plan(monkeypatch):
    """Reuse the existing synthetic cohort so the real contracts are exercised."""
    from test_approved_runtime_timing import approved_activation
    fixture, packet = approved_activation(monkeypatch)
    packet["identity"]["project_number"] = PROJECT_NUMBER
    activation = fixture["activation"]
    template = load("runtime-activate.plan.template.json")
    scope_hash = template["activation"]["human_review_authorization_sha256"]
    monkeypatch.setenv("RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256", scope_hash)
    table = {
        **runtime_dummies(),
        "pilot_manifest_sha256": packet["pilot"]["manifest_sha256"],
        "ready_manifest_sha256": fixture["worker"]["manifest_sha256"],
        "worker_launch_sha256": fixture["worker"]["launch_sha256"],
        "sam_expires_at_unix": fixture["sam"]["expires_at_unix"],
        "sam_checkpoint_sha256": fixture["sam"]["checkpoint_sha256"],
        "sam_checkpoint_prefix": fixture["sam"]["checkpoint_prefix"],
        "ready_manifest_bytes": activation["manifest_bytes"],
        "worker_launch_bytes": activation["launch_bytes"],
        "collection_profile_bytes": activation["profile_bytes"],
        "collection_profile_secret_version": activation["profile_secret"],
        "hf_secret_version": activation["hf_secret"],
        "worker_actor_uid": activation["actor_uid"],
        "prepared_receipt_run_id": 1234567890,
        "prepared_receipt_run_attempt": 1,
        "prepared_receipt_sha256": "a" * 64,
        "api_service_etag": "observed-api-etag",
        "api_previous_revision": "specimen-api-aaaaaaaaaaaa-123-1",
        "trace_project_id": "specimen-digitization",
        "worker_logfire_token_secret_version": runtime.TRACE_WRITER_PARENT + "/versions/1",
        "trace_identity_receipt_sha256": "b" * 64,
    }
    return fill(template, table), packet


def test_runtime_activate_template_validates_against_the_real_contracts(monkeypatch):
    plan, packet = activate_plan(monkeypatch)
    assert runtime.validate_plan(plan, packet, now=NOW) is plan
    manifest, launch, profile = runtime.validate_activation_inputs(plan, packet, now=NOW)
    assert len(manifest.specimens) == 10 and launch.evidence_only and profile.state == "draft"


def test_runtime_activate_template_produces_one_bounded_worker_execution(monkeypatch):
    plan, packet = activate_plan(monkeypatch)
    images = {role: f"{runtime.REGISTRY}/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    bodies = runtime.resource_bodies(plan, packet, images, "123", "1", now=NOW)
    worker = runtime.activation_worker(bodies["worker"], plan, packet, now=NOW)
    assert worker["runExecutionToken"] == "pilot-" + packet["pilot"]["manifest_sha256"][:24]
    assert worker["template"]["template"]["maxRetries"] == 0
    environment = {item["name"]: item for item in worker["template"]["template"]["containers"][0]["env"]}
    assert environment["LOGFIRE_TOKEN"] == runtime.env_secret(
        "LOGFIRE_TOKEN", plan["activation"]["worker_trace"]["token_secret"])
    assert "HF_TOKEN" in environment and "value" not in environment["HF_TOKEN"]
    sam = {item["name"]: item.get("value") for item in bodies["sam"]["template"]["containers"][0]["env"]}
    assert sam["HF_HUB_OFFLINE"] == "1" and "HF_TOKEN" not in sam


# -------------------------------------------------------- readiness evidence ---


def evidence_table():
    return {
        **{f"{role}_image_reference":
           f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64
           for role in ("api", "worker", "sam")},
        **{f"{role}_image_provenance_sha256": "7" * 64 for role in ("api", "worker", "sam")},
        "sam_artifacts_sha256": "1" * 64, "sam_config_sha256": "2" * 64,
        "deployed_schema_sha256": "3" * 64, "deployed_connector_sha256": "4" * 64,
        "deployed_storage_rules_sha256": "5" * 64,
        "backup_restore_evidence_sha256": "6" * 64,
        "data_ready_receipt_sha256": "c" * 64,
        "contract_approval_sha256": "8" * 64,
        "bootstrap_artifact_sha256": "9" * 64,
        "budget_approval_sha256": "a" * 64,
        "provider_data_approval_sha256": "b" * 64,
        "public_config_sha256": "d" * 64, "rollback_sha256": "e" * 64,
    }


def candidate_from(evidence):
    run = "https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/1234567890"
    checks = {name: {"source_sha": SOURCE_SHA, "conclusion": "success", "run_url": run}
              for name in validate_release_packet.CHECKS}
    inputs = mint_release_packet.Inputs(
        plane="runtime", release_run_id=1234567890, release_run_attempt=1,
        plan_path=None, authorization_path=None, review_report_path=None,
        ledger_path=None, cost_review_path=None, reviewer_session="reviewer",
        project_number=PROJECT_NUMBER, pool_id="github-actions",
        pilot_manifest_sha256="b" * 64, candidate_evidence=evidence)
    return mint_release_packet.build_candidate(SOURCE_SHA, checks, inputs)


def test_evidence_digests_template_yields_a_complete_public_candidate():
    evidence = fill(load("evidence-digests.template.json"), evidence_table())
    candidate = candidate_from(evidence)
    assert validate_release_packet.validate(
        candidate, require_ready=True, expected_source_sha=SOURCE_SHA) == []


def test_evidence_template_guidance_block_changes_nothing_it_produces():
    """Only this file may carry `_template`; the plan validators use exact keys."""
    evidence = fill(load("evidence-digests.template.json"), evidence_table())
    assert set(evidence["_template"]) == {"purpose", "consumed_by", "notes"}
    stripped = {key: value for key, value in evidence.items() if key != "_template"}
    assert candidate_from(evidence) == candidate_from(stripped)
    for name in PLAN_TEMPLATES:
        assert "_template" not in load(name), f"{name} would fail its exact key set"


def test_an_incomplete_evidence_file_is_reported_as_a_named_gap():
    evidence = fill(load("evidence-digests.template.json"), evidence_table())
    evidence["approvals"]["budget_sha256"] = None
    assert "budget_sha256" in validate_release_packet.validate(candidate_from(evidence))


# ------------------------------------------------------------- no secrets ---


def allowed_digests():
    return (set(CURRENT_DATA_SOURCE_FILES.values())
            # Historical public source hashes are explained by exact pinned raw origins.
            | {value for name in RETIRED_DATA_TEMPLATE_SHA256
               for value in load_raw(name)["source_files"].values()}
            | set(RETIRED_INITIALIZER_SOURCE_FILES.values())
            | set(release_initialize.fingerprints().values())
            # The bootstrap template pins the reviewed collection tree's digest.
            | {hashlib.sha256(reviewed_tree()).hexdigest()}
            | {runtime.TRACE_APPROVAL_SHA256,
               "5c460d9ca7acc86ee0407584732d0cf1e27b1bc685a968f8094ce7ca133dfc15"})  # pragma: allowlist secret (approval digest)


SECRET_SHAPES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{10,}"),
    re.compile(r"\b(?:ghp|gho|ghs|ghu)_[0-9A-Za-z]{10,}"),
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{10,}"),
    re.compile(r"\bhf_[0-9A-Za-z]{10,}"),
    re.compile(r"\bsk-[0-9A-Za-z]{16,}"),
    re.compile(r'"(?:password|passwd|secret_value|token_value|private_key)"\s*:'),
)


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_no_template_carries_anything_shaped_like_a_credential(name):
    raw = (TEMPLATES / name).read_text()
    for shape in SECRET_SHAPES:
        assert not shape.search(raw), f"{name} contains something shaped like a credential"
    # Secret Manager references are resource names, never values, and no template
    # may pin a concrete version: the owner supplies each one through a placeholder.
    assert not re.search(r'"projects/[^"]*/secrets/[^"]*"', raw), f"{name} pins a secret version"
    allowed = allowed_digests()
    for digest in re.findall(r"\b[0-9a-f]{64}\b", raw):
        assert digest in allowed, f"{name} carries an unexplained 64-hex literal"
    for sha in re.findall(r"\b[0-9a-f]{40}\b", raw):
        assert sha == runtime.SAM3_MODEL.revision, f"{name} carries an unexplained 40-hex literal"


# ----------------------------------------------------------------- drift ---


@pytest.mark.parametrize("name,validate", [
    ("data-initialization-inventory.plan.template.json",
     lambda plan: data.validate_plan(plan, {"source_sha": SOURCE_SHA})),
    ("data-initialize-missing.plan.template.json",
     lambda plan: data.validate_plan(plan, recovery_packet(), now=NOW)),
    ("data-apply.plan.template.json",
     lambda plan: data.validate_plan(plan, recovery_packet(), now=NOW)),
    ("data-bootstrap.plan.template.json",
     lambda plan: data.validate_plan(plan, {"source_sha": SOURCE_SHA})),
    ("runtime-build.plan.template.json",
     lambda plan: runtime.validate_plan(plan, runtime_packet(), now=NOW)),
    ("runtime-prepare.plan.template.json",
     lambda plan: runtime.validate_plan(plan, runtime_packet(), now=NOW)),
])
@pytest.mark.parametrize("drift", ["extra", "missing"])
def test_a_drifting_template_key_set_fails_closed(name, validate, drift):
    builders = {
        "data-initialization-inventory.plan.template.json":
            lambda: fill(load(name), common_dummies()),
        "data-initialize-missing.plan.template.json": initialize_missing_plan,
        "data-apply.plan.template.json": apply_plan,
        "data-bootstrap.plan.template.json": lambda: bootstrap_plan()[0],
        "runtime-build.plan.template.json": lambda: fill(load(name), runtime_dummies()),
        "runtime-prepare.plan.template.json": prepare_plan,
    }
    plan = builders[name]()
    validate(copy.deepcopy(plan))
    if drift == "extra":
        plan["unreviewed_extra_key"] = True
    else:
        plan.pop("source_sha")
    with pytest.raises((ValueError, KeyError)):
        validate(plan)


def test_a_drifting_activation_key_set_fails_closed(monkeypatch):
    plan, packet = activate_plan(monkeypatch)
    runtime.validate_plan(copy.deepcopy(plan), packet, now=NOW)
    plan["activation"]["unreviewed_extra_key"] = True
    with pytest.raises(ValueError, match="activation"):
        runtime.validate_plan(plan, packet, now=NOW)


@pytest.mark.parametrize("name", sorted(RETIRED_DATA_TEMPLATE_SHA256))
def test_retired_raw_data_templates_are_refused_by_current_source_guards(name):
    """No historical template is silently qualified for an active G11 release."""
    builders = {
        "data-initialize-missing.plan.template.json": initialize_missing_plan,
        "data-apply.plan.template.json": apply_plan,
        "data-bootstrap.plan.template.json": lambda: bootstrap_plan()[0],
    }
    value = builders[name]()
    value["source_files"] = load_raw(name)["source_files"]
    packet = {"source_sha": SOURCE_SHA} if name == "data-bootstrap.plan.template.json" else recovery_packet()
    with pytest.raises(ValueError, match="source fingerprints changed|compatible current data source required"):
        data.validate_plan(value, packet, now=NOW)


@pytest.mark.parametrize("name", sorted(RETIRED_INITIALIZATION_TEMPLATE_SHA256))
def test_raw_initialization_pins_are_refused_by_current_source_guards(name):
    """Raw initialization pins remain ineligible through the real source validators."""
    if name == "data-initialization-inventory.plan.template.json":
        value = fill(load_raw(name), common_dummies())
        with pytest.raises(ValueError, match="catalog source changed"):
            data.validate_plan(value, {"source_sha": SOURCE_SHA})
    else:
        value = initialize_missing_plan()
        value["initialization"]["files"] = load_raw(name)["initialization"]["files"]
        with pytest.raises(ValueError, match="initialization source bytes changed"):
            data.validate_plan(value, recovery_packet(), now=NOW)


def test_frozen_initializer_source_digests_explain_raw_origins_without_becoming_current():
    for name in RETIRED_INITIALIZATION_TEMPLATE_SHA256:
        raw = load_raw(name)
        pins = raw["initialization_files"] if "initialization_files" in raw else raw["initialization"]["files"]
        for path, digest in RETIRED_INITIALIZER_SOURCE_FILES.items():
            assert pins[path] == digest
            assert CURRENT_INITIALIZATION_FILES[path] != digest
