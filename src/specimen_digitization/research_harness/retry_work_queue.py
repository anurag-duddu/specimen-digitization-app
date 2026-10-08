"""Schedule an admitted field retry without a canonical save or new job."""
from uuid import UUID

from specimen_digitization.application.production import actor_uid
from .contracts import digest
from .discovery_v2 import CanonicalReadBindingV2
from .persistence import ResearchStore, SqlConnectStateBackend, StaleWork

ROLES = {"operator", "reviewer", "manager", "admin"}
# Existing jobs:run has a ten-second timeout; allow the same bounded interval
# for its known receipt's state write. This is read-only grace, never a send.
START_RECEIPT_ATTEMPTS = 21
START_RECEIPT_INTERVAL_SECONDS = 1.0


def queued_retry_command(binding, principal, specimen, *, consuming=False):
    """Select only an exact current undelivered command from native discovery."""
    if not isinstance(binding, CanonicalReadBindingV2):
        raise StaleWork("research_retry_binding_unproved")
    bound = binding.durability_scope(principal)
    if (actor_uid.get() != principal.user_id or principal.role not in ROLES
        or specimen.scope != principal.scope or specimen.id != bound.specimen_id
        or specimen.asset.sensitive is not False or specimen.asset.sha256 != binding.source_sha256
        or specimen.run.id != str(binding.canonical.canonical_run_id)
        or specimen.version != binding.canonical.record_revision
        or specimen.run.stage in {"paused", "cancelled", "finalized"}
        or specimen.run.human_approved or specimen.run.blocker == "external_outcome_unknown"):
        raise StaleWork("research_retry_queue_binding_changed")
    bundle = binding.read_bundle
    if (bundle.halted or bundle.paused or bundle.hold_reasons
        or bundle.job.get("lease") and bundle.job["lease"]["expires_at"] > bundle.server_time
        or any(effect.get("status") in {"reserved", "sending", "held_unknown"}
            or effect.get("actual_micro_usd") is None for effect in bundle.effects.values())):
        raise StaleWork("research_retry_queue_custody_unavailable")
    commands = []
    for event in bundle.outbox.values():
        command = event.get("command", {})
        if (event.get("kind") == "research_field_retry" and event.get("delivered") is False
            and command.get("status") in {"queued", "running"}
            and command.get("scope") == bound.identity()):
            field = bundle.job["fields"].get(command.get("field_key"), {})
            if (command.get("kind") != "retry_field" or command.get("expected_generation") != bound.generation
                or command.get("binding_digest") != binding.runtime_binding_digest
                or field.get("locked") is not False or command.get("field_key") in binding.research_locks):
                raise StaleWork("research_retry_queue_command_changed")
            if (command.get("dispatch_status") in {"unknown", "sending"}
                or consuming and command.get("execution_class") == "live" and command.get("dispatch_status") != "requested"):
                raise StaleWork("research_retry_dispatch_custody_unavailable")
            commands.append(command)
    return min(commands, key=lambda item: (item["created_at"], item["id"])) if commands else None


def _variables(repository, principal, binding, specimen):
    bound = binding.durability_scope(principal)
    if (actor_uid.get() != principal.user_id or principal.role not in ROLES
        or specimen.scope != principal.scope or specimen.id != bound.specimen_id
        or specimen.version != binding.canonical.record_revision
        or specimen.run.id != str(binding.canonical.canonical_run_id)
        or specimen.asset.sensitive is not False):
        raise StaleWork("research_retry_queue_binding_changed")
    info = repository.version_info(principal.scope, specimen.id, specimen.version)
    if (info.get("revision") != specimen.version or info.get("run_id") != specimen.run.id
        or info.get("sha256") != binding.canonical.snapshot_sha256):
        raise StaleWork("research_retry_queue_snapshot_unproved")
    return dict(repository.variables(principal.scope), specimenId=specimen.id,
        recordRevision=specimen.version, canonicalRunId=specimen.run.id,
        snapshotSha256=info["sha256"], programKey=binding.program_key, jobKey=bound.key,
        generation=bound.generation, bindingDigest=binding.runtime_binding_digest)


def _readback(data, root, specimen, *, scheduled):
    row = data.get("read", {}).get("specimen")
    try:
        run_id = str(UUID(row.get("activeRunId", ""))) if isinstance(row, dict) else None
    except (ValueError, TypeError, AttributeError):
        run_id = None
    if (type(data.get(root)) is not int or data[root] != 1 or not isinstance(row, dict)
        or type(row.get("revision")) is not int or row["revision"] != specimen.version
        or run_id != specimen.run.id
        or scheduled and (row.get("state") != "retry_scheduled" or row.get("workAvailableAt") is None)
        or not scheduled and (row.get("state") not in {"completed", "processing_blocked", "retry_scheduled"}
            or (row.get("workAvailableAt") is not None) != (row.get("state") == "retry_scheduled"))):
        raise StaleWork("research_retry_queue_write_unproved")


def schedule_research_retry(repository, principal, binding, command_id):
    """Prove current admission and make this exact record due, idempotently."""
    specimen = repository.get(principal.scope, binding.canonical.specimen_id)
    queued_retry_command(binding, principal, specimen)
    variables = _variables(repository, principal, binding, specimen)
    bound = binding.durability_scope(principal)
    store = ResearchStore(SqlConnectStateBackend(repository), binding.program_key)
    document = store._read(bound)
    job = store._job(document.state, bound)
    binding.validate_job(job, program_key=store.program_key)
    event = document.state["outbox"].get("retry/" + command_id, {})
    command = event.get("command", {})
    field = job["fields"].get(command.get("field_key"), {})
    checkpoint = field.get("checkpoint") or {}
    if (event.get("kind") != "research_field_retry" or event.get("delivered") is not False
        or command.get("id") != command_id or command.get("scope") != bound.identity()
        or command.get("kind") != "retry_field" or command.get("status") != "queued"
        or command.get("execution_class") != "live" or command.get("created_by") != principal.user_id
        or command.get("expected_generation") != bound.generation
        or command.get("binding_digest") != job["binding_digest"]
        or field.get("locked") is not False or field.get("work_state") != "retry_scheduled"
        or field.get("retry_command_id") != command_id
        or field.get("revision") != command.get("expected_field_revision")
        or digest(checkpoint) != command.get("checkpoint_digest")):
        raise StaleWork("research_retry_queue_command_changed")
    store._source_retry_safety(document.state, bound, job, document.server_time, execution_class="live")
    if checkpoint.get("payload", {}).get("resolution", {}).get("work_state") == "waiting_source":
        if not store._completed_source_failure(document.state, bound, job, command["field_key"]):
            raise StaleWork("research_retry_queue_source_unproved")
    data = repository.execute("ScheduleResearchRetryV1", dict(variables,
        commandId=command_id, stateRevision=document.revision), mutation=True)
    _readback(data, "scheduled", specimen, scheduled=True)
    return {"contract_version": "research-retry-schedule/v1", "command_id": command_id,
        "record_revision": specimen.version, "canonical_run_id": specimen.run.id, "status": "scheduled"}


def finish_research_retry(repository, principal, binding, command_id, outcome):
    """Retire scheduling only after the command and current native progress agree."""
    specimen = repository.get(principal.scope, binding.canonical.specimen_id)
    variables = _variables(repository, principal, binding, specimen)
    bound = binding.durability_scope(principal)
    event = binding.read_bundle.outbox.get("retry/" + command_id, {})
    command = event.get("command", {})
    native = binding.native
    from .native_worker import _current_progress_matches_job
    head = native.causal_chain[-1] if native.causal_chain else None
    if (event.get("kind") != "research_field_retry" or event.get("delivered") is not True
        or command.get("id") != command_id or command.get("scope") != bound.identity()
        or command.get("status") not in {"completed", "blocked"}
        or binding.read_bundle.halted or binding.read_bundle.paused or binding.read_bundle.hold_reasons
        or binding.read_bundle.job.get("lease") is not None
        or outcome.scope != binding.research_scope() or head is None
        or head.receipt_id != native.head_receipt_id or head.resulting != native.canonical
        or str(head.receipt_id) not in outcome.publication_receipt_ids
        or head.progress_receipt.run_stage != specimen.run.stage
        or specimen.run.stage not in {"finalized", "processing_blocked"}
        or not _current_progress_matches_job(native, bound, binding.read_bundle.job)):
        raise StaleWork("research_retry_completion_unproved")
    if command["status"] == "completed":
        ResearchStore._retry_result(binding.read_bundle.job, command, command.get("result_checkpoint_id"))
    if any(effect.get("status") in {"reserved", "sending", "held_unknown"}
        or effect.get("actual_micro_usd") is None for effect in binding.read_bundle.effects.values()):
        raise StaleWork("research_retry_completion_custody_unavailable")
    data = repository.execute("FinishResearchRetryV1", dict(variables,
        commandId=command_id, stateRevision=binding.read_bundle.state_revision,
        fieldWorkDigest=digest(binding.read_bundle.job["fields"]),
        fieldMappingDigest=digest(binding.field_mapping), policyDigest=binding.policy_digest), mutation=True)
    _readback(data, "finished", specimen, scheduled=False)
    return specimen


def park_research_retry(repository, principal, binding, command_id, outcome):
    """Stop due work for a known terminal failure without claiming a fresh save."""
    specimen = repository.get(principal.scope, binding.canonical.specimen_id)
    variables = _variables(repository, principal, binding, specimen)
    bound = binding.durability_scope(principal)
    event = binding.read_bundle.outbox.get("retry/" + command_id, {})
    command = event.get("command", {})
    bundle = binding.read_bundle
    if (outcome.scope != binding.research_scope() or outcome.status != "blocked"
        or outcome.reason_code not in {"research_retry_not_completed", "final_research_progress_requires_native_publication"}
        or specimen.run.stage != "processing_blocked" or specimen.run.disposition is not None
        or event.get("kind") != "research_field_retry" or event.get("delivered") is not True
        or command.get("id") != command_id or command.get("scope") != bound.identity()
        or command.get("binding_digest") != binding.runtime_binding_digest
        or command.get("status") not in {"completed", "blocked"}
        or bundle.paused or bundle.job.get("lease") is not None
        or any(effect.get("status") in {"reserved", "sending", "held_unknown"}
            or effect.get("actual_micro_usd") is None for effect in bundle.effects.values())):
        raise StaleWork("research_retry_parking_unproved")
    if command["status"] == "completed":
        checkpoint = ResearchStore._retry_result(bundle.job, command, command.get("result_checkpoint_id"))
        proof = checkpoint.get("accepted_output_proof") or {}
        from .contracts import FieldResolution, FieldKey, WorkState
        from specimen_digitization.application.domain import FieldValue
        from .output_admission import is_validation_failure
        resolution = FieldResolution.model_validate(checkpoint["payload"]["resolution"])
        # The journal attaches the request's settled context pins even to a
        # bare failure. They describe consumed input; they do not supply a value.
        without_context = resolution.model_copy(update={"dependencies": ()})
        bare_failure = without_context == FieldResolution(field_key=FieldKey(command["field_key"]),
            work_state=WorkState.OPERATIONAL_FAILED, value=FieldValue(), reason="specialist_operational_failure")
        validation_failure = is_validation_failure(without_context)
        if bare_failure or validation_failure:
            if (checkpoint.get("dependencies") != {str(pin.field_key): pin.revision for pin in resolution.dependencies}
                or checkpoint.get("dependency_digests") != {str(pin.field_key): pin.digest for pin in resolution.dependencies}):
                raise StaleWork("research_retry_parking_dependency_unproved")
            from .native_materialization_inputs_v2 import _current_checkpoint
            for pin in resolution.dependencies:
                current, pair = _current_checkpoint(bundle.job, str(pin.field_key), binding.research_scope())
                source = pair["original"] if pair is not None else {}
                source_proof = source.get("accepted_output_proof") or {}
                if (current is None or bundle.job["fields"][str(pin.field_key)]["locked"]
                    or current.revision != pin.revision or digest(current.resolution) != pin.digest
                    or current.resolution.work_state != WorkState.RESOLVED
                    or source_proof.get("contract_version") != "research-accepted-checkpoints/v1"
                    or digest(source["payload"]) not in source_proof.get("checkpoint_payload_digests", ())):
                    raise StaleWork("research_retry_parking_dependency_unproved")
        if not (bare_failure or validation_failure) and (
            resolution.work_state not in {WorkState.WAITING_SOURCE, WorkState.WAITING_POLICY}
            or proof.get("contract_version") != "research-accepted-checkpoints/v1"
            or digest(checkpoint["payload"]) not in proof.get("checkpoint_payload_digests", ())):
            raise StaleWork("research_retry_parking_result_unproved")
    elif command.get("blocked_reason") not in {"retry_worker_failed", "retry_checkpoint_missing"}:
        raise StaleWork("research_retry_parking_result_unproved")
    store = ResearchStore(SqlConnectStateBackend(repository), binding.program_key)
    document = store._read(bound)
    binding.validate_job(store._job(document.state, bound), program_key=store.program_key)
    if (document.revision != bundle.state_revision
        or any(item.get("kind") == "canonical_publication_required" and item.get("delivered") is False
            and item.get("guard", {}).get("scope") == bound.identity()
            for item in document.state["outbox"].values())):
        raise StaleWork("research_retry_parking_publication_unproved")
    data = repository.execute("ParkResearchRetryV1", dict(variables,
        commandId=command_id, stateRevision=bundle.state_revision), mutation=True)
    _readback(data, "parked", specimen, scheduled=False)
    return specimen
