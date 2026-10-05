"""Native G38 scheduling metadata; proposals never rewrite scientific values."""
from uuid import UUID

from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.storage import digest as snapshot_digest
from .contracts import digest
from .persistence import StaleWork


def _variables(repository, principal, specimen, command):
    if (actor_uid.get() != principal.user_id or specimen.scope != principal.scope
            or specimen.asset.sensitive is not False
            or specimen.run.id != command.canonical_run_id
            or specimen.version != command.queued_revision
            or digest(specimen.run.dependencies.get("research_derivation_request")) != digest(command)):
        raise StaleWork("derivation_queue_binding_changed")
    return dict(repository.variables(principal.scope), specimenId=specimen.id,
        queuedRevision=command.queued_revision, canonicalRunId=command.canonical_run_id)


def _readback(data, root, command, *, scheduled):
    if type(data.get(root)) is not int or data[root] != 1:
        raise StaleWork("derivation_queue_write_unproved")
    row = data.get("read", {}).get("specimen")
    try:
        run_id = str(UUID(row.get("activeRunId", ""))) if isinstance(row, dict) else None
    except (ValueError, TypeError, AttributeError):
        run_id = None
    if (not isinstance(row, dict) or type(row.get("revision")) is not int
            or row.get("revision") != command.queued_revision
            or run_id != command.canonical_run_id
            or row.get("state") != ("pending" if scheduled else "completed")
            or ((row.get("workAvailableAt") is not None) != scheduled)):
        raise StaleWork("derivation_queue_readback_unproved")


def schedule_derivation(repository, principal, saved, command):
    from .derivation_contracts import DerivationScheduleReceipt
    command = type(command).model_validate(command.model_dump(mode="json"))
    current = repository.get(principal.scope, saved.id)
    variables = _variables(repository, principal, current, command)
    if snapshot_digest(current.model_dump(mode="json")) != snapshot_digest(saved.model_dump(mode="json")):
        raise StaleWork("derivation_queue_binding_changed")
    info = repository.version_info(principal.scope, saved.id, saved.version)
    if info.get("revision") != saved.version or not isinstance(info.get("sha256"), str):
        raise StaleWork("derivation_queue_snapshot_unproved")
    data = repository.execute("ScheduleResearchDerivationV1",
        dict(variables, queuedSnapshotSha256=info["sha256"]), mutation=True)
    _readback(data, "scheduled", command, scheduled=True)
    return DerivationScheduleReceipt(request_id=command.id,
        queued_revision=command.queued_revision, canonical_run_id=command.canonical_run_id,
        status="scheduled")


def finish_derivation(repository, principal, specimen, command, scope, program_key):
    variables = _variables(repository, principal,
        repository.get(principal.scope, specimen.id), command)
    if (scope.specimen_id != specimen.id
            or scope.organization_id != principal.scope.organization_id
            or scope.collection_id != principal.scope.collection_id
            or scope.actor_uid != principal.user_id):
        raise StaleWork("derivation_queue_binding_changed")
    data = repository.execute("FinishResearchDerivationV1", dict(variables,
        programKey=program_key, jobKey=scope.key, requestId=command.id), mutation=True)
    _readback(data, "finished", command, scheduled=False)
