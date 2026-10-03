#!/usr/bin/env python3
"""Create the program's allowance ledger for the bound insects collection, once, as the worker.

    ORG_ID=<organization uuid> COLLECTION_ID=<bound insects collection uuid> \
        uv run --frozen python scripts/ops/seed_allowance_ledger.py

The worker reserves every paid step on this document and holds the run while it is missing
(lane_allowance.ProgramLedger: "program_allowance_ledger_unavailable"). The document is:
  kind     worker_cursor (lane_allowance.LEDGER_KIND), in scope (ORG_ID, COLLECTION_ID)
  id       uuid5(NAMESPACE_URL, "processing-lane-allowance:<ORG_ID>/<COLLECTION_ID>")
  payload  {"sensitive": false, "reserved_total_micros": 0}, stored at revision 1 through CreateDocumentV2.
It is read first and created only when absent; an existing ledger is never changed.

ORG_ID is the organization of the worker actor's membership. COLLECTION_ID is the private collection identifier that
SPECIMEN_COLLECTION_BINDINGS_JSON (secret specimen-collection-bindings) binds to the "insects" node, exactly as the
worker reads it (lane.queue -> registry.bound_collections("insects")). Both are canonical lowercase UUIDs; neither is
printed. The worker actor must hold an active membership in that collection; this is checked first.

Identity, as the worker itself: Data Connect is called through the connector's impersonate operations with the
credentials of specimen-worker-runtime (impersonated from the operator's application-default credentials) and the
worker actor's Firebase UID (secret specimen-worker-actor-uid, at its pinned version, held in memory only).
The operator needs: application-default credentials (`gcloud auth application-default login`);
roles/iam.serviceAccountTokenCreator on specimen-worker-runtime; secretAccessor on specimen-worker-actor-uid (the
project owner has it). IMPERSONATE= (empty) uses the operator's own credentials instead, which then need
firebasedataconnect.connectors.impersonateMutation (the project owner has it).

Parameters (environment): ORG_ID, COLLECTION_ID (required), PROJECT (must match runtime_settings), IMPERSONATE
(default the worker identity), DRY_RUN=1.
"""
from __future__ import annotations

import os
import sys
from uuid import UUID

import ops_common as ops

settings = ops.settings
ACTOR_SECRET = "specimen-worker-actor-uid"  # pragma: allowlist secret (secret name, not a value)
SEED = {"sensitive": False, "reserved_total_micros": 0}


def canonical(name: str) -> str:
    value = os.environ.get(name, "")
    try:
        if value == str(UUID(value)):
            return value
    except ValueError:
        pass
    raise SystemExit(f"{name} must be a canonical lowercase UUID")


def ledger_id(organization_id: str, collection_id: str) -> str:
    """The worker's own computation (ProgramLedger.ident), never a copy of it."""
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.lane_allowance import ProgramLedger

    return ProgramLedger(None, Scope(organization_id=organization_id, collection_id=collection_id)).ident


def repository(impersonate: str):
    import google.auth
    from google.auth import impersonated_credentials
    from google.auth.transport.requests import AuthorizedSession
    from specimen_digitization.application.production import SqlConnectRepository, sql_endpoint_from_env

    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials, _ = google.auth.default(scopes=scopes)
    if impersonate:
        credentials = impersonated_credentials.Credentials(
            source_credentials=credentials, target_principal=impersonate, target_scopes=scopes, lifetime=900)
    return SqlConnectRepository(project=settings.PROJECT, session=AuthorizedSession(credentials),
                                **sql_endpoint_from_env(settings.SQL))


def main() -> int:
    project = ops.committed_project()
    organization_id, collection_id = canonical("ORG_ID"), canonical("COLLECTION_ID")
    impersonate = os.environ.get("IMPERSONATE", settings.WORKER_EMAIL)
    ident = ledger_id(organization_id, collection_id)
    from specimen_digitization.application.lane_allowance import LEDGER_KIND

    actor = ops.secret_value(["gcloud", "secrets", "versions", "access",
                              str(settings.SECRET_VERSIONS[ACTOR_SECRET]), f"--secret={ACTOR_SECRET}",
                              f"--project={project}"])
    ops.note(f"ledger {LEDGER_KIND}/{ident} as {impersonate or 'the operator credentials'} and the worker actor")
    ops.note("GetDocumentV2, then CreateDocumentV2 with payload "
             '{"sensitive": false, "reserved_total_micros": 0, "revision": 1} only if absent')
    if ops.dry_run():
        print(ident)
        return 0

    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.production import verified_actor_context
    from specimen_digitization.application.storage import Conflict, Missing

    scope = Scope(organization_id=organization_id, collection_id=collection_id)
    store = repository(impersonate)
    try:
        with verified_actor_context(actor):
            if not any(m["organization_id"] == organization_id and m["collection_id"] == collection_id
                       for m in store.memberships(actor)):
                raise SystemExit("the worker actor has no active membership in ORG_ID / COLLECTION_ID; nothing created")
            try:
                current = store.document(scope, LEDGER_KIND, ident)
                ops.note(f"already present at revision {current.get('revision')}; not changed")
            except Missing:
                try:
                    store.put_document(scope, LEDGER_KIND, ident, dict(SEED), 0)
                    ops.note("created at revision 1")
                except Conflict:
                    store.document(scope, LEDGER_KIND, ident)  # Another writer created it first.
                    ops.note("created concurrently by another writer; not changed")
    except SystemExit:
        raise
    except Exception as error:  # Never echo a response body: it could carry private values.
        raise SystemExit(f"Data Connect call failed: {type(error).__name__}") from None
    print(ident)
    return 0


if __name__ == "__main__":
    sys.exit(main())
