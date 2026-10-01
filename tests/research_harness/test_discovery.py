"""Scoped native discovery never creates journal, lease, budget or model effects."""

from copy import deepcopy

import pytest

from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.production import actor_uid, verified_actor_context
from specimen_digitization.research_harness.canonical_binding import (
    BindingUnavailable, CanonicalBindingSnapshot, CanonicalResearchBinding,
)
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.discovery import ResearchDiscovery, ScopedCanonicalReadStore
from specimen_digitization.research_harness.persistence import HeldUnknown, StaleWork

ORG = "11111111-1111-4111-8111-111111111111"
COLLECTION = "22222222-2222-4222-8222-222222222222"
SPECIMEN = "33333333-3333-4333-8333-333333333333"
VERSION = "44444444-4444-4444-8444-444444444444"
RUN = "55555555-5555-4555-8555-555555555555"


def fixture():
    principal = Principal(user_id="verified-viewer", role="viewer",
                          scope=Scope(organization_id=ORG, collection_id=COLLECTION))
    pins = {"input_digest": "a" * 64, "profile": {"fixture": True}}
    canonical = {"organization_id": ORG, "collection_id": COLLECTION, "specimen_id": SPECIMEN,
                 "record_revision": 7, "record_version_id": VERSION, "canonical_run_id": RUN,
                 "host_record_version_id": RUN + ":7", "snapshot_sha256": "9" * 64, "sensitive": True}
    identity = {"organization_id": ORG, "collection_id": COLLECTION,
                "specimen_id": SPECIMEN, "job_id": "opaque-journal-job"}
    job = {"identity": identity, "generation": 2, "sensitive": True, "pins": pins,
           "binding_digest": digest(pins), "record_revision": 7, "paused": False,
           "history": [], "dependencies": {}, "trace_context": None, "fields": {
               str(k): {"locked": False, "revision": 0, "checkpoint": None, "reuse": None} for k in FieldKey}}
    version_tuple = {key: canonical[key] for key in ("record_revision", "record_version_id",
        "canonical_run_id", "host_record_version_id", "snapshot_sha256")}
    row = {"binding_id": "66666666-6666-4666-8666-666666666666", "active": True,
           "registration_revision": 1, "base_canonical": deepcopy(version_tuple),
           "current_canonical": deepcopy(version_tuple), "job_id": identity["job_id"],
           "job_key": digest(identity), "generation": 2,
           "input_digest": pins["input_digest"], "profile_digest": digest(pins["profile"]),
           "runtime_binding_digest": digest(pins), "program_key": "existing-program",
           "policy_digest": "c" * 64, "source_sha256": "e" * 64,
           "canonical_profile_digest": "f" * 64, "semantic_mapping_digest": "d" * 64,
           "field_mapping": {str(k): str(k) for k in FieldKey},
           "human_locks": {str(k): k == FieldKey.TAXON for k in FieldKey},
           "publication_transition": None, "job": deepcopy(job), "read_bundle": {
               "state_revision": 3, "observed_at": "2026-10-01T00:00:00Z", "job": deepcopy(job),
               "effects": {}, "outbox": {}, "halted": False,
               "hold_reasons": ["legacy_live_import_not_confirmed"]}}
    row["semantic_mapping"] = {"field_mapping": deepcopy(row["field_mapping"]),
        "journal_budget_policy_digest": "b" * 64, "research_policy_origin": "fixture-owner-reviewed"}
    row["semantic_mapping_digest"] = digest(row["semantic_mapping"])
    row["journal_budget_policy_digest"] = "b" * 64
    row["journal_budget_policy_origin"] = "verified_owner_registration_not_SQL_recomputed"
    row["research_policy_origin"] = "fixture-owner-reviewed"
    row["read_bundle"].pop("observed_at")
    row["read_bundle"].update(server_time=100.0, job_key=row["job_key"], paused=False)
    return principal, row


class BindingReader:
    def __init__(self, row):
        self.row = row
        self.rows = None
        self.calls = []
        self.change_on_second_read = False
        self.denied = False

    def current_research_binding(self, scope, specimen_id):
        self.calls.append(actor_uid.get())
        if self.denied:
            raise PermissionError("fresh sensitive access denied")
        row = deepcopy(self.row)
        if self.change_on_second_read and len(self.calls) > 1:
            row["current_canonical"]["host_record_version_id"] = "changed-current-pointer"
            row["base_canonical"] = deepcopy(row["current_canonical"])
        return CanonicalBindingSnapshot.model_validate({
            "canonical": {"organization_id": ORG, "collection_id": COLLECTION,
                          "specimen_id": SPECIMEN, "sensitive": True, **row["current_canonical"]},
            "active_registration_count": len(self.rows) if self.rows is not None else 1,
            "registrations": self.rows if self.rows is not None else [row],
            "snapshot": {"snapshot": {"fixture": "private"}, "sha256": row["current_canonical"]["snapshot_sha256"],
                "revision": row["current_canonical"]["record_revision"], "contractVersion": "fixture-source"},
            "projection": [],
        })

    def store(self, binding):
        return ScopedCanonicalReadStore(binding, verified_actor=actor_uid.get())


def bound_registration(row, principal):
    return BindingReader(row).current_research_binding(principal.scope, SPECIMEN).current(
        organization_id=ORG, collection_id=COLLECTION, specimen_id=SPECIMEN)


@pytest.mark.asyncio
async def test_viewer_discovery_reads_only_coherent_registered_scope():
    principal, row = fixture()
    original = deepcopy(row)
    repository = BindingReader(row)
    discovery = ResearchDiscovery(repository, store_factory=repository.store)
    with verified_actor_context(principal.user_id):
        result = await discovery.discover(principal, SPECIMEN)
        assert await discovery.retry_available(principal, result.scope, FieldKey.TAXON) is False
    assert result.scope.job_id == "opaque-journal-job"
    assert result.scope.input_digest == row["input_digest"] != row["source_sha256"]
    assert result.human_locked_fields == (FieldKey.TAXON,)
    assert result.capabilities.model_dump() == {"read": True, "retry": False, "review": False}
    assert result.retry_blocked_reason == "retry_admission_uninstalled"
    assert row == original
    assert all(uid == principal.user_id for uid in repository.calls)
    assert actor_uid.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [[], "duplicate"])
async def test_missing_or_ambiguous_mapping_is_unavailable(rows):
    principal, row = fixture()
    repository = BindingReader(row)
    repository.rows = [row, deepcopy(row)] if rows == "duplicate" else rows
    discovery = ResearchDiscovery(repository, store_factory=repository.store)
    with verified_actor_context(principal.user_id), pytest.raises(BindingUnavailable):
        await discovery.discover(principal, SPECIMEN)


@pytest.mark.asyncio
async def test_pointer_move_during_read_rejects_result():
    principal, row = fixture()
    repository = BindingReader(row)
    repository.change_on_second_read = True
    with verified_actor_context(principal.user_id), pytest.raises(StaleWork):
        await ResearchDiscovery(repository, store_factory=repository.store).discover(principal, SPECIMEN)


@pytest.mark.asyncio
async def test_current_revoked_sensitive_access_stays_permission_denial():
    principal, row = fixture()
    repository = BindingReader(row)
    repository.denied = True
    with verified_actor_context(principal.user_id), pytest.raises(PermissionError):
        await ResearchDiscovery(repository, store_factory=repository.store).discover(principal, SPECIMEN)


@pytest.mark.asyncio
async def test_uninstalled_native_operation_is_unavailable_not_created():
    principal, _ = fixture()
    with verified_actor_context(principal.user_id), pytest.raises(BindingUnavailable):
        await ResearchDiscovery(None, store_factory=None).discover(principal, SPECIMEN)


@pytest.mark.asyncio
@pytest.mark.parametrize("held_state", ["halted", "paused", "unknown_effect"])
async def test_unknown_budget_or_sent_effect_does_not_authorize_retry(held_state):
    principal, row = fixture()
    principal = principal.model_copy(update={"role": "operator"})
    if held_state == "halted":
        row["read_bundle"]["halted"] = True
    elif held_state == "paused":
        row["job"]["paused"] = row["read_bundle"]["job"]["paused"] = True
        row["read_bundle"]["paused"] = True
    else:
        row["read_bundle"]["effects"]["sent"] = {
            "job_key": row["job_key"], "scope": {**row["job"]["identity"], "generation": 2},
            "status": "held_unknown", "actual_micro_usd": None,
            "binding_digest": row["runtime_binding_digest"]}
    repository = BindingReader(row)
    discovery = ResearchDiscovery(repository, store_factory=repository.store)
    with verified_actor_context(principal.user_id):
        assert await discovery.retry_available(principal,
            bound_registration(row, principal).research_scope(), FieldKey.COUNTRY) is False


def test_scoped_snapshot_refuses_all_mutations_and_contains_no_global_ledger():
    principal, row = fixture()
    binding = bound_registration(row, principal)
    before = deepcopy(row)
    with verified_actor_context(principal.user_id):
        store = ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
        document = store._read(binding.durability_scope(principal))
        assert set(document.state["jobs"]) == {row["job_key"]}
        assert "budget_policy" not in document.state and "budget_totals" not in document.state
        with pytest.raises(PermissionError):
            store.initialize(binding.durability_scope(principal), None)
        with pytest.raises(PermissionError):
            store.claim(binding.durability_scope(principal), "worker")
        with pytest.raises(HeldUnknown):
            store.budget(binding.durability_scope(principal))
    assert row == before


@pytest.mark.parametrize("missing", ["read_bundle", "effects", "outbox"])
def test_missing_scoped_source_bundle_cannot_be_filled_with_defaults(missing):
    principal, row = fixture()
    if missing == "read_bundle":
        row[missing] = None
        binding = bound_registration(row, principal)
        with verified_actor_context(principal.user_id), pytest.raises(BindingUnavailable):
            ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
    else:
        from pydantic import ValidationError
        del row["read_bundle"][missing]
        with pytest.raises(ValidationError):
            CanonicalResearchBinding.model_validate(row)



@pytest.mark.asyncio
async def test_clear_native_dynamic_holds_do_not_install_live_retry_authority():
    principal, row = fixture()
    row["read_bundle"]["hold_reasons"] = []
    repository = BindingReader(row)
    discovery = ResearchDiscovery(repository, store_factory=repository.store)
    with verified_actor_context(principal.user_id):
        result = await discovery.discover(principal, SPECIMEN)
    assert result.capabilities.retry is False
    assert result.retry_blocked_reason == "retry_admission_uninstalled"
    assert row["read_bundle"]["hold_reasons"] == []



def retry_thread_fixture(status="queued", *, generation=1):
    """Synthetic checkpoint load, real scoped-store and ThreadReader outbox path."""
    from specimen_digitization.application.domain import FieldValue
    from specimen_digitization.research_harness.contracts import FieldCheckpoint, FieldResolution, ResearchScope, WorkState

    principal, row = fixture()
    row["generation"] = row["job"]["generation"] = generation
    scope = ResearchScope(**row["job"]["identity"], generation=generation,
        input_digest=row["input_digest"], profile_digest=row["profile_digest"], sensitive=True)
    checkpoint = FieldCheckpoint(scope=scope, field_key=FieldKey.COUNTRY, revision=1,
        resolution=FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.OPERATIONAL_FAILED,
            value=FieldValue(reason="Synthetic operational failure"), reason="Synthetic operational failure"),
        prompt_digest="1" * 64, model_settings_digest="2" * 64, source_registry_digest="3" * 64)
    native_checkpoint = {"id": digest("synthetic-native-checkpoint"), "payload": checkpoint.model_dump(mode="json"),
        "receipt_ids": [], "dependencies": {}, "dependency_digests": {}}
    command_id = digest({"synthetic_retry": status, "generation": generation})
    row["job"]["fields"]["country"].update(revision=1, checkpoint=native_checkpoint,
        retry_command_id=command_id if status in {"queued", "running"} else None)
    row["read_bundle"]["job"] = deepcopy(row["job"])
    row["read_bundle"]["outbox"]["retry/" + command_id] = {"kind": "research_field_retry",
        "delivered": status in {"blocked", "completed"}, "command": {
            "id": command_id, "kind": "retry_field", "status": status,
            "scope": {**row["job"]["identity"], "generation": generation},
            "field_key": "country", "expected_generation": generation, "expected_field_revision": 1,
            "checkpoint_digest": digest(native_checkpoint), "binding_digest": row["runtime_binding_digest"]}}
    return principal, row, checkpoint, command_id


class RetryJournalFixture:
    # Only checkpoint delivery is synthetic; scoped outbox reads are production code.
    def __init__(self, binding, store, checkpoint, principal):
        self.scope = binding.durability_scope(principal)
        self.store = store
        self.checkpoint = checkpoint

    async def load(self, scope):
        assert scope == self.checkpoint.scope
        return (self.checkpoint,)

    async def retry_eligible(self, scope, key):
        return False  # No fixture installs retry admission or budget authority.


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected,blocker", [
    ("queued", "retry_scheduled", None), ("running", "researching", None),
    ("blocked", "operational_failed", "research_retry_blocked")])
async def test_real_scoped_outbox_path_overlays_only_exact_current_retry(status, expected, blocker):
    from specimen_digitization.research_harness.thread_view import ResearchThreadReader

    principal, row, checkpoint, _ = retry_thread_fixture(status)
    original = deepcopy(row)
    binding = bound_registration(row, principal)
    with verified_actor_context(principal.user_id):
        store = ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
        thread = await ResearchThreadReader(RetryJournalFixture(binding, store, checkpoint, principal)).read(
            binding.research_scope())
    field = next(field for field in thread.fields if field.field_key == FieldKey.COUNTRY)
    assert str(field.work_state) == expected
    assert field.blocker_code == blocker
    assert field.checkpoint == checkpoint
    assert thread.effects == ()
    assert row == original and actor_uid.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "running", "blocked"])
@pytest.mark.parametrize("fault", ["bool", "float", "string", "extra", "missing", "generation_mismatch"])
async def test_malformed_late_command_scope_is_denied_before_actual_outbox_overlay(status, fault):
    from specimen_digitization.research_harness.thread_view import ResearchThreadReader

    principal, row, checkpoint, command_id = retry_thread_fixture(status)
    binding = bound_registration(row, principal)
    # Simulate corrupted/mutated native Any after its initial typed validation.
    command = binding.read_bundle.outbox["retry/" + command_id]["command"]
    if fault in {"bool", "float", "string"}:
        command["scope"]["generation"] = {"bool": True, "float": 1.0, "string": "1"}[fault]
    elif fault == "extra":
        command["scope"]["actor_uid"] = "extra"
    elif fault == "missing":
        del command["scope"]["job_id"]
    else:
        command["scope"]["generation"] = 2
    with verified_actor_context(principal.user_id), pytest.raises(BindingUnavailable):
        store = ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
        await ResearchThreadReader(RetryJournalFixture(binding, store, checkpoint, principal)).read(
            binding.research_scope())
    assert actor_uid.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["blocked", "completed"])
async def test_real_outbox_read_retains_terminal_history_without_current_overlay(status):
    from specimen_digitization.research_harness.thread_view import ResearchThreadReader

    principal, row, checkpoint, command_id = retry_thread_fixture(status, generation=2)
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    row["job"]["history"] = [{"scope": old_scope, "generation": 1,
        "pins": old_pins, "binding_digest": old_binding}]
    row["read_bundle"]["job"] = deepcopy(row["job"])
    command = row["read_bundle"]["outbox"]["retry/" + command_id]["command"]
    command.update(scope=old_scope, expected_generation=1, binding_digest=old_binding)
    original = deepcopy(row)
    binding = bound_registration(row, principal)
    with verified_actor_context(principal.user_id):
        store = ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
        thread = await ResearchThreadReader(RetryJournalFixture(binding, store, checkpoint, principal)).read(
            binding.research_scope())
    field = next(field for field in thread.fields if field.field_key == FieldKey.COUNTRY)
    assert str(field.work_state) == "operational_failed"
    assert field.blocker_code == "research_operational_failure"
    assert field.checkpoint.scope.generation == 2
    assert field.actions == () and thread.effects == ()
    assert row == original and actor_uid.get() is None


@pytest.mark.asyncio
async def test_historical_command_marker_cannot_claim_the_current_field():
    from specimen_digitization.research_harness.thread_view import ResearchThreadReader

    principal, row, checkpoint, command_id = retry_thread_fixture("blocked", generation=2)
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    row["job"]["history"] = [{"scope": old_scope, "generation": 1,
        "pins": old_pins, "binding_digest": old_binding}]
    row["job"]["fields"]["country"]["retry_command_id"] = command_id
    row["read_bundle"]["job"] = deepcopy(row["job"])
    row["read_bundle"]["outbox"]["retry/" + command_id]["command"].update(
        scope=old_scope, expected_generation=1, binding_digest=old_binding)
    binding = bound_registration(row, principal)
    with verified_actor_context(principal.user_id), pytest.raises(StaleWork):
        store = ScopedCanonicalReadStore(binding, verified_actor=principal.user_id)
        await ResearchThreadReader(RetryJournalFixture(binding, store, checkpoint, principal)).read(
            binding.research_scope())
    assert actor_uid.get() is None
