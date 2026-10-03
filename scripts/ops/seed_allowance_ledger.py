#!/usr/bin/env python3
"""Create the program's allowance ledger for the bound insects collection, once, as the worker actor.

    ORG_ID=<organization uuid> uv run --frozen python scripts/ops/seed_allowance_ledger.py

The worker reserves every paid step on this document and holds the run while it is missing
(lane_allowance.ProgramLedger: "program_allowance_ledger_unavailable"). The document is:
  kind     worker_cursor (lane_allowance.LEDGER_KIND), in scope (ORG_ID, the ledger collection)
  id       uuid5(NAMESPACE_URL, "processing-lane-allowance:<ORG_ID>/<ledger collection>")
  payload  {"sensitive": false, "reserved_total_micros": 0}, stored at revision 1 through CreateDocumentV2.
It is read first and created only when absent; an existing ledger is never changed.

ORG_ID is the organization of the worker actor's membership. The ledger collection is read, not supplied: the one
private collection identifier that secret specimen-collection-bindings (at its pinned version) binds to the program
allowance's ledger node ("insects"), found as lane.queue finds it (runtime_config.collection_bindings, then
registry.bound_collections). Both are canonical lowercase UUIDs; neither is printed. The worker actor must hold an
active membership in that collection with a role CreateDocumentV2 accepts (operator, reviewer, manager or admin);
this is checked first.

Identity: Data Connect is called through the connector's impersonate operations as the worker actor's Firebase UID
(secret specimen-worker-actor-uid, at its pinned version, held in memory only). The UID is used exactly as stored,
as the worker's drain_settings reads it; a value with surrounding whitespace or a control character is refused.
By default the calls carry the operator's own application-default credentials, which need
firebasedataconnect.connectors.impersonateMutation (the project owner has it) and a quota project in the ADC file
(`gcloud auth application-default set-quota-project specimen-digitization`).
IMPERSONATE=<service account email> is opt-in: it impersonates that account from the operator's credentials, which
needs roles/iam.serviceAccountTokenCreator on it. roles/owner does not include iam.serviceAccounts.getAccessToken,
and iam.py grants no token creator.

The operator needs the gcloud CLI signed in (it reads both secrets; secretAccessor, which the project owner has) and
application-default credentials (`gcloud auth application-default login`, read through google.auth.default).

Parameters (environment): ORG_ID (required), PROJECT (must match runtime_settings), IMPERSONATE (default empty: the
operator's own credentials), DRY_RUN=1.
"""
from __future__ import annotations

import os
import sys
from uuid import UUID

import ops_common as ops

settings = ops.settings
ACTOR_SECRET = "specimen-worker-actor-uid"  # pragma: allowlist secret (secret name, not a value)
BINDINGS_SECRET = "specimen-collection-bindings"  # pragma: allowlist secret (secret name, not a value)
SEED = {"sensitive": False, "reserved_total_micros": 0}


def canonical(name: str, value: str | None = None) -> str:
    value = os.environ.get(name, "") if value is None else value
    try:
        if value == str(UUID(value)):
            return value
    except ValueError:
        pass
    raise SystemExit(f"{name} must be a canonical lowercase UUID")


def ledger_collection(raw_bindings: str) -> str:
    """The one collection bound to the program allowance's ledger node, found as lane.queue finds it."""
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.application.runtime_config import collection_bindings

    try:
        registry = published_registry(
            dict(collection_bindings({"SPECIMEN_COLLECTION_BINDINGS_JSON": raw_bindings})))
    except ValueError:  # The message could carry the private identifiers.
        raise SystemExit(f"{BINDINGS_SECRET} is not a valid bindings object; its value is withheld") from None
    nodes = {profile.processing.program_allowance.ledger_collection for profile in registry.profiles
             if profile.processing and profile.processing.program_allowance}
    if len(nodes) != 1:
        raise SystemExit("the published profiles name no single program allowance ledger node")
    [node] = nodes
    ledgers = registry.bound_collections(node)
    if len(ledgers) != 1:
        raise SystemExit(f"{BINDINGS_SECRET} must bind exactly one collection to {node!r}; it binds {len(ledgers)}")
    return canonical("the bound ledger collection", ledgers[0])


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
    organization_id = canonical("ORG_ID")
    impersonate = os.environ.get("IMPERSONATE", "")
    from specimen_digitization.application.lane_allowance import LEDGER_KIND
    from specimen_digitization.application.lane_worker import LANE_ROLES, exact_uid

    actor = ops.secret_value(["gcloud", "secrets", "versions", "access",
                              str(settings.SECRET_VERSIONS[ACTOR_SECRET]), f"--secret={ACTOR_SECRET}",
                              f"--project={project}"], exact=True)
    bindings = ops.secret_value(["gcloud", "secrets", "versions", "access",
                                 str(settings.SECRET_VERSIONS[BINDINGS_SECRET]), f"--secret={BINDINGS_SECRET}",
                                 f"--project={project}"])
    ops.note(f"ledger {LEDGER_KIND} in ORG_ID and the collection {BINDINGS_SECRET} binds to the ledger node, as "
             f"{impersonate or 'the operator credentials'} and the worker actor")
    ops.note("GetDocumentV2, then CreateDocumentV2 with payload "
             '{"sensitive": false, "reserved_total_micros": 0, "revision": 1} only if absent')
    if ops.dry_run():
        return 0
    if not exact_uid(actor):  # The worker's own rule; its value is never printed.
        raise SystemExit(f"{ACTOR_SECRET} must hold the exact Firebase UID, with no surrounding whitespace or "
                         "control character: the worker reads it unstripped; nothing created")
    collection_id = ledger_collection(bindings)
    ident = ledger_id(organization_id, collection_id)

    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.production import verified_actor_context
    from specimen_digitization.application.storage import Conflict, Missing

    scope = Scope(organization_id=organization_id, collection_id=collection_id)
    store = repository(impersonate)
    try:
        with verified_actor_context(actor):
            roles = {m["role"] for m in store.memberships(actor)
                     if m["organization_id"] == organization_id and m["collection_id"] == collection_id}
            if not roles:
                raise SystemExit("the worker actor has no active membership in ORG_ID and the bound ledger "
                                 "collection; nothing created")
            if not roles & LANE_ROLES:
                raise SystemExit("the worker actor's membership there has no role CreateDocumentV2 accepts "
                                 f"({', '.join(sorted(LANE_ROLES))}); nothing created")
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
