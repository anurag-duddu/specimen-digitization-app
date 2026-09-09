"""Fixed first-database phase. Only deploy_data's protected workflow invokes it."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from release_admission import digest, exact_keys, integer, private_bytes, require, strict_json
from release_context import PROJECT, REPOSITORY
from release_diagnostics import node_failure, stage

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "specimen-digitization-instance"
CLONE = "specimen-digitization-restore-20260908-r1"
DATABASE = "specimen-digitization-database"
INITIALIZER_SQL = "specimen-data-initialize@specimen-digitization.iam"
MAINTENANCE = "specimen-data-release@specimen-digitization.iam"
AGENT = "service-716045864126@gcp-sa-firebasedataconnect.iam"
ROLES = {f"firebase{role}_{DATABASE}_public" for role in ("owner", "reader", "writer")}
PERMISSIONS = {"cloudsql.instances.get", "cloudsql.instances.connect", "cloudsql.instances.login",
               "cloudsql.databases.create", "cloudsql.databases.get", "cloudsql.databases.list",
               "cloudsql.users.create", "cloudsql.users.get", "cloudsql.users.list",
               "cloudsql.users.update", "cloudsql.users.delete"}
FILES = ("scripts/ci/release_initialize.py", "scripts/ci/release_initialize.mjs",
         "scripts/ci/initialize_database.sql", "scripts/ci/initialize_catalog.sql",
         "scripts/ci/initialize_postconditions.sql", "scripts/ci/release_catalog_envelope.py")


def fingerprints():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_catalog_recipient(recipient):
    from release_catalog_envelope import validate_public_key
    exact_keys(recipient, {"public_key_pem", "public_key_sha256"}, "controlled catalog recipient")
    require(isinstance(recipient["public_key_pem"], str) and len(recipient["public_key_pem"]) <= 4096,
            "bounded coordinator public key required")
    validate_public_key(recipient["public_key_pem"].encode(), recipient["public_key_sha256"])
    return recipient


def catalog_provenance(packet):
    return {"repository": REPOSITORY, "source_sha": packet["source_sha"],
            "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"]}


def validate_plan(plan, packet):
    validate_catalog_recipient(plan["catalog_recipient"])
    init = exact_keys(plan["initialization"], {"files", "catalog_sha256", "authority_sha256", "review_sha256",
        "privilege_window_seconds", "identity", "permissions", "conditional_binding_sha256", "service_agent",
        "disposal_permissions", "disposal_binding_sha256"}, "initialization")
    require(plan["schema_mode"] == "initialize_missing" and plan["schema_etag"] is None
            and plan["connector_etag"] is None and plan["bootstrap"] is None,
            "first initialization cannot adopt existing schema or bootstrap")
    require(plan["recovery"]["recipe"]["source_version"] == "POSTGRES_18", "only qualified PostgreSQL18 initialization")
    require(init["files"] == fingerprints(), "initialization source bytes changed")
    for key in ("catalog_sha256", "authority_sha256", "review_sha256", "conditional_binding_sha256", "disposal_binding_sha256"):
        digest(init[key], key)
    require(init["disposal_permissions"] == sorted("cloudsql.users." + action for action in ("get", "list", "update", "delete")),
            "ordinary disposal must have only reviewed user read/revoke/delete capabilities")
    require(init["authority_sha256"] == packet["authorization_sha256"]
            and init["review_sha256"] == packet["independent_review"]["report_sha256"], "temporary privilege lacks exact authority/review")
    integer(init["privilege_window_seconds"], 120, 600, "post-restore privilege window")
    require(init["permissions"] == sorted(PERMISSIONS), "initializer capability must be exact; no IAM policy or source capacity writes")
    identity = exact_keys(init["identity"], {"project_number", "pool_id", "provider"}, "initializer identity")
    require(identity["project_number"] == packet["identity"]["project_number"] == "716045864126"
            and init["service_agent"] == AGENT, "unobserved project/service-agent identity")
    require(isinstance(identity["pool_id"], str) and identity["pool_id"] == packet["identity"].get("pool_id", identity["pool_id"])
            and identity["provider"] == f"projects/{identity['project_number']}/locations/global/workloadIdentityPools/{identity['pool_id']}/providers/specimen-data-initialize",
            "initializer provider must be separately pinned")
    return plan


def once(directory, name, effect, *, context=None):
    """An owned intent survives every ambiguous write. Never replay an intent."""
    require(name.replace("-", "").isalnum(), "invalid fixed operation name")
    target = directory / f"{name}.json"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise ValueError("operation intent exists; reconcile without replay") from None
    intent = {"operation": name, "outcome": "unknown", "submitted_at_unix": int(time.time()), **(context or {})}
    with os.fdopen(fd, "w") as handle:
        json.dump(intent, handle)
        handle.flush(); os.fsync(handle.fileno())
    result = effect()
    target.write_text(json.dumps({**intent, "outcome": "observed", "result": result}, sort_keys=True))
    return result


def user_request(instance, action):
    require(instance in (SOURCE, CLONE), "unowned initialization target")
    resource = f"projects/{PROJECT}/instances/{instance}/users"
    if action == "create":
        return "POST", resource, {"body": {"name": INITIALIZER_SQL, "type": "CLOUD_IAM_SERVICE_ACCOUNT",
                                           "databaseRoles": ["cloudsqlsuperuser"]}}
    if action == "revoke":
        return "PUT", resource, {"params": {"name": INITIALIZER_SQL, "revokeExistingRoles": "true"}, "body": {}}
    require(action == "delete", "unknown user action")
    return "DELETE", resource, {"params": {"name": INITIALIZER_SQL}}


def recovery_receipt(packet, plan, native, now):
    return {"version": "data-initialization-recovery/v1", "source_sha": packet["source_sha"],
            "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"],
            "plan_sha256": sha(plan), "native_restore_verified": native["native_restore_verified"],
            "native_recovery": native, "catalog_sha256": plan["initialization"]["catalog_sha256"],
            "initialization_files": plan["initialization"]["files"], "parity_at_unix": int(now),
            "privilege_deadline_unix": min(int(now) + plan["initialization"]["privilege_window_seconds"],
                                           packet["expires_at_unix"], plan["recovery"]["expires_at_unix"]),
            "data_ready": False, "release_accepted": False}


def validate_recovery_receipt(receipt, packet, plan, *, now=None, cleanup=False):
    require(receipt.get("version") == "data-initialization-recovery/v1"
            and receipt.get("source_sha") == packet["source_sha"]
            and receipt.get("run_id") == packet["release_run_id"]
            and receipt.get("run_attempt") == packet["release_run_attempt"]
            and receipt.get("plan_sha256") == sha(plan)
            and receipt.get("native_restore_verified") is True
            and receipt.get("catalog_sha256") == plan["initialization"]["catalog_sha256"]
            and receipt.get("initialization_files") == fingerprints(), "stale or incomplete native restoration proof")
    native = exact_keys(receipt["native_recovery"], {"clone", "source", "source_sha", "backup_id", "run_id", "run_attempt",
        "create_operation", "expires_at_unix", "create_time", "restore_operation", "native_restore_verified", "inventory_sha256"}
        | ({"backup_retention"} if "backup_retention" in plan["recovery"] else set()), "native restoration")
    require(native["clone"] == CLONE and native["source"] == SOURCE and native["source_sha"] == packet["source_sha"]
            and native["run_id"] == packet["release_run_id"] and native["run_attempt"] == packet["release_run_attempt"]
            and native["native_restore_verified"] is True and native["inventory_sha256"] == receipt["catalog_sha256"]
            and native["expires_at_unix"] == plan["recovery"]["expires_at_unix"], "native restore ownership or catalog binding differs")
    if "backup_retention" in plan["recovery"]:
        from release_backup import validate_proof
        validate_proof(native["backup_retention"], plan["recovery"]["backup_retention"], native["backup_id"], packet)
    now = time.time() if now is None else now
    start, end = receipt.get("parity_at_unix"), receipt.get("privilege_deadline_unix")
    integer(start, packet["issued_at_unix"], packet["expires_at_unix"], "native parity time")
    integer(end, start + 1, min(start + plan["initialization"]["privilege_window_seconds"],
                              packet["expires_at_unix"], plan["recovery"]["expires_at_unix"]), "privilege deadline")
    require(cleanup or start <= now < end, "post-restore privilege window expired")
    return receipt


def qualify_then_source(initialize, cleanup, source_recheck):
    for instance in (CLONE, SOURCE):
        if instance == SOURCE:
            source_recheck()
        try:
            initialize(instance)
        finally:
            cleanup(instance)


@stage("catalog.native-preflight")
def native(directory, instance, mode, *, files, deadline, expected_catalog=None, expected_postconditions=None,
           recipient=None, provenance=None):
    require(instance in (SOURCE, CLONE) and mode in {"inspect", "absence", "capability", "initialize", "clean", "post",
            "disposal-check", "disposal-absent"}, "unnamed native operation")
    require(files == fingerprints(), "consumed native source differs from reviewed bytes")
    target = directory / f"{instance}-{mode}.json"
    env = dict(os.environ, INITIALIZATION_FILES=json.dumps(files), INITIALIZATION_DEADLINE=str(deadline))
    env.pop("INITIALIZATION_EXPECTED_POST", None)
    if expected_postconditions is not None:
        env["INITIALIZATION_EXPECTED_POST"] = json.dumps(expected_postconditions)
    private_catalog = mode in {"inspect", "absence", "capability"}
    if private_catalog:
        validate_catalog_recipient(recipient)
    evidence = None
    try:
        with stage("catalog.native-execute"):
            result = subprocess.run(["node", "scripts/ci/release_initialize.mjs", mode, instance, str(target)],
                                    cwd=ROOT, env=env, capture_output=True, timeout=max(1, min(90, deadline - time.time())))
            raw = private_bytes(target) if target.exists() else None
    finally:
        # Native checks can leave observations before they fail. Encrypt those
        # exact bytes too; upload selectors never include this plaintext path.
        if private_catalog and target.exists():
            with stage("catalog.encryption"):
                from release_catalog_envelope import encrypt_catalog
                raw = private_bytes(target)
                envelope = encrypt_catalog(raw, recipient["public_key_pem"].encode(),
                    public_key_sha256=recipient["public_key_sha256"], provenance=provenance)
                encrypted = directory / f"{instance}-{mode}.encrypted.json"
                encrypted.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n")
                encrypted.chmod(0o600)
                evidence = {"file": encrypted.name, "sha256": hashlib.sha256(private_bytes(encrypted)).hexdigest()}
                target.unlink()
    if result.returncode != 0:
        raise node_failure(getattr(result, "stderr", None))
    with stage("catalog.native-result"):
        require(raw is not None, "native initialization did not retain evidence")
        value = strict_json(raw)
        require(value.get("instance") == instance and value.get("mode") == mode and value.get("files") == files,
                "native initialization result provenance mismatch")
        if expected_catalog is not None:
            require(sha(value["catalog"]) == expected_catalog, "native catalog differs from reviewed source/restore")
        if private_catalog:
            require(value.get("qualified") is True, "native catalog not qualified")
            value["catalog_evidence"] = evidence
        return value


def inspect_catalog(google, plan, directory, output):
    with stage("catalog.recipient"):
        validate_catalog_recipient(plan["catalog_recipient"])
    with stage("catalog.metadata-request"):
        source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    with stage("catalog.metadata-identity"):
        require(source.get("region") == "us-east4" and source.get("databaseVersion") == "POSTGRES_18"
                and source.get("settings", {}).get("settingsVersion") == plan["database_etag"], "catalog target changed")
    observed = native(directory, SOURCE, "inspect", files=plan["initialization_files"], deadline=google.packet["expires_at_unix"],
                      recipient=plan["catalog_recipient"], provenance=catalog_provenance(google.packet))
    with stage("catalog.receipt"):
        output.write_text(json.dumps({"version": "data-initialization-inventory/v1",
            "source_sha": google.packet["source_sha"], "run_id": google.packet["release_run_id"],
            "run_attempt": google.packet["release_run_attempt"], "files": plan["initialization_files"],
            "catalog_sha256": sha(observed["catalog"]), "catalog_evidence": observed["catalog_evidence"],
            "native_client_sessions": observed["native_client_sessions"],
            "data_ready": False, "release_accepted": False}, sort_keys=True) + "\n")


def prepare_recovery(google, plan, directory, output):
    """The ordinary identity proves actual postgres parity before initializer OIDC."""
    import deploy_data as data
    source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    require(source.get("settings", {}).get("settingsVersion") == plan["database_etag"], "source revision changed")
    expiry = min(google.packet["expires_at_unix"], plan["recovery"]["expires_at_unix"])
    require(time.time() + 1800 < expiry, "insufficient single-clone recovery window")
    for resource in ("services/specimen-api", "jobs/specimen-worker"):
        require(google.request("run", "GET", f"projects/{PROJECT}/locations/us-east4/{resource}", missing=True) is None,
                "runtime writers exist; no guessed maintenance switch")
    require(google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True) is None, "never adopt an existing clone")
    require(not any(o.get("operationType") == "CREATE" and o.get("targetId") == CLONE for o in
                    data.list_sql(google, f"projects/{PROJECT}/operations", instance=CLONE, maxResults=100)), "single clone allowance already used")
    body = data.clone_body(source, plan["recovery"]["recipe"], google.packet["release_run_id"],
                          run_attempt=google.packet["release_run_attempt"], source_sha=google.packet["source_sha"])
    files, catalog = plan["initialization"]["files"], plan["initialization"]["catalog_sha256"]
    private_evidence = {"recipient": plan["catalog_recipient"], "provenance": catalog_provenance(google.packet)}
    native(directory, SOURCE, "absence", files=files, deadline=expiry, expected_catalog=catalog, **private_evidence)
    backup_args = {"retention": plan["recovery"]["backup_retention"], "source": source} if "backup_retention" in plan["recovery"] else {}
    backup_id = data.ensure_backup(google, plan["recovery"]["backup_id"], directory, **backup_args)
    backup = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}/backupRuns/{backup_id}")
    require(0 <= time.time() - data.stamp(backup.get("endTime")) <= 7200, "stale or unobserved source backup checkpoint")
    from release_backup import attach_proof
    backup_proof = {"backup_id": backup_id}
    attach_proof(backup_proof, plan, google.packet, directory)
    operation = once(directory, "clone-create", lambda: google.request("sql", "POST", f"projects/{PROJECT}/instances", body=body))
    creation = {"clone": CLONE, "source": SOURCE, "source_sha": google.packet["source_sha"], "backup_id": backup_id,
                "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
                "create_operation": operation["name"], "expires_at_unix": plan["recovery"]["expires_at_unix"]}
    creation.update(backup_proof)
    receipt_path = directory / "native-recovery.json"
    receipt_path.write_text(json.dumps(creation)); receipt_path.chmod(0o600)
    data.wait_sql(google, operation, maximum_seconds=900)
    clone = observe(lambda: google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True), bool, expiry)
    creation["create_time"] = clone["createTime"]
    data.validate_clone_ownership(clone, creation, google.packet["release_run_id"])
    receipt_path.write_text(json.dumps(creation))
    operation = once(directory, "clone-restore", lambda: google.request("sql", "POST", f"projects/{PROJECT}/instances/{CLONE}/restoreBackup",
        body={"restoreBackupContext": {"backupRunId": backup_id, "instanceId": SOURCE, "project": PROJECT}}))
    creation["restore_operation"] = operation["name"]
    receipt_path.write_text(json.dumps(creation))
    data.wait_sql(google, operation, maximum_seconds=900)
    native(directory, CLONE, "absence", files=files, deadline=expiry, expected_catalog=catalog, **private_evidence)
    native(directory, SOURCE, "absence", files=files, deadline=expiry, expected_catalog=catalog, **private_evidence)
    creation.update(native_restore_verified=True, inventory_sha256=catalog)
    receipt_path.write_text(json.dumps(creation))
    output.write_text(json.dumps(recovery_receipt(google.packet, plan, creation, time.time()), sort_keys=True) + "\n")


def observe(read, matches, deadline):
    """Only read propagation; a write is never part of this bounded retry."""
    stop = min(time.time() + 30, deadline)
    while True:
        require(time.time() < stop, "native read deadline reached")
        value = read()
        require(time.time() < stop, "native observation arrived after the original deadline")
        if matches(value):
            return value
        require(time.time() + 2 < stop, "native propagation not observed; retained operation must be reconciled")
        time.sleep(2)


def operation_proof(operation, instance, kind, recovery):
    import re
    from deploy_data import stamp
    require(isinstance(operation, dict) and re.fullmatch(r"[A-Za-z0-9_-]+", operation.get("name", ""))
            and operation.get("targetId") == instance and operation.get("targetProject") == PROJECT
            and operation.get("operationType") == kind
            and operation.get("user") == INITIALIZER_SQL + ".gserviceaccount.com"
            and recovery["parity_at_unix"] <= stamp(operation.get("insertTime")) < recovery["privilege_deadline_unix"],
            "native initializer operation identity or timing mismatch")
    return operation


def validate_request(api, method, resource, body, params):
    """The initializer transport cannot mutate IAM, backup, capacity or app data."""
    require(api == "sql", "initializer has no other Google API effects")
    for instance in (SOURCE, CLONE):
        prefix = f"projects/{PROJECT}/instances/{instance}"
        if method == "GET" and resource in (prefix, prefix + "/users", prefix + "/databases", prefix + "/databases/" + DATABASE):
            require(body is None and (params is None or resource.endswith('/users') and set(params) <= {"pageToken"}), "unexpected initializer read parameters")
            return
        for action in ("create", "revoke", "delete"):
            m, r, args = user_request(instance, action)
            if (method, resource, body, params) == (m, r, args.get("body"), args.get("params")):
                return
        if method == "POST" and resource == prefix + "/databases":
            require(body == {"project": PROJECT, "instance": instance, "name": DATABASE} and params is None,
                    "only the fixed absent application database may be created")
            return
    import re
    if method == "GET" and resource == f"projects/{PROJECT}/operations":
        require(body is None and isinstance(params, dict) and set(params) <= {"instance", "maxResults", "pageToken"}
                and params.get("instance") in (SOURCE, CLONE) and params.get("maxResults") == 100
                and ("pageToken" not in params or isinstance(params["pageToken"], str) and 0 < len(params["pageToken"]) <= 4096),
                "initializer history must be completely paginated for a named target only")
        return
    require(method == "GET" and re.fullmatch(rf"projects/{PROJECT}/operations/[A-Za-z0-9_-]+", resource)
            and body is None and params is None, "unnamed initializer request rejected")


def prepare_initializer_intents(google, plan, directory, recovery):
    """Publish both absent-target intents before either privileged create."""
    import deploy_data as data
    validate_recovery_receipt(recovery, google.packet, plan)
    require(time.time() + 120 < recovery["privilege_deadline_unix"], "insufficient intent publication window")
    google.sql_read_deadline = recovery["privilege_deadline_unix"]
    for instance in (CLONE, SOURCE):
        records = data.list_sql(google, f"projects/{PROJECT}/instances/{instance}/users")
        require(not any(row.get("name") == INITIALIZER_SQL for row in records), "preexisting initializer cannot be adopted")
        require(google.request("sql", "GET", f"projects/{PROJECT}/instances/{instance}/databases/{DATABASE}", missing=True) is None,
                "application database exists before published initialization intent")
        require(time.time() < recovery["privilege_deadline_unix"], "absence observation arrived too late")
        name = "initializer-create-" + instance
        journal = {"version": "initializer-create-intent/v1", "operation": name, "outcome": "prepared",
            "source_sha": google.packet["source_sha"], "run_id": google.packet["release_run_id"],
            "run_attempt": google.packet["release_run_attempt"], "initial_absence_observed": True,
            "absence_at_unix": int(time.time()), "not_before_unix": int(time.time()),
            "privilege_deadline_unix": recovery["privilege_deadline_unix"], "recovery_sha256": sha(recovery)}
        fd = os.open(directory / (name + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(journal, handle, sort_keys=True); handle.flush(); os.fsync(handle.fileno())


def validate_creation_intent(journal, instance, packet, recovery):
    exact_keys(journal, {"version", "operation", "outcome", "source_sha", "run_id", "run_attempt",
        "initial_absence_observed", "absence_at_unix", "not_before_unix", "privilege_deadline_unix", "recovery_sha256"}, "published creation intent")
    require(journal["version"] == "initializer-create-intent/v1" and journal["outcome"] == "prepared"
        and journal["operation"] == "initializer-create-" + instance
        and journal["source_sha"] == packet["source_sha"] and journal["run_id"] == packet["release_run_id"]
        and journal["run_attempt"] == packet["release_run_attempt"] and journal["initial_absence_observed"] is True
        and journal["privilege_deadline_unix"] == recovery["privilege_deadline_unix"]
        and journal["recovery_sha256"] == sha(recovery), "signed original absence/create intent differs")
    integer(journal["absence_at_unix"], recovery["parity_at_unix"], recovery["privilege_deadline_unix"] - 1, "original absence")
    integer(journal["not_before_unix"], journal["absence_at_unix"], recovery["privilege_deadline_unix"] - 1, "original create window")
    return journal


def initialize_targets(google, plan, directory, recovery, output, *, prepared_intents):
    import deploy_data as data
    validate_recovery_receipt(recovery, google.packet, plan)
    deadline = recovery["privilege_deadline_unix"]
    google.initialization_deadline = deadline
    google.sql_read_deadline = deadline
    require(time.time() + 120 < deadline, "insufficient initialization and revocation window")
    clone = google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}")
    data.validate_clone_ownership(clone, recovery["native_recovery"], google.packet["release_run_id"])
    results, created = {}, {}
    files = plan["initialization"]["files"]
    require(set(prepared_intents) == {SOURCE, CLONE}, "both published creation intents must precede all effects")
    for instance, journal in prepared_intents.items():
        validate_creation_intent(journal, instance, google.packet, recovery)

    def guarded():
        require(time.time() + 60 < deadline, "no new effects within the reserved cleanup minute")

    def users(instance):
        return data.list_sql(google, f"projects/{PROJECT}/instances/{instance}/users")

    def own_user(instance):
        matching = [u for u in users(instance) if u.get("name") == INITIALIZER_SQL]
        require(len(matching) <= 1, "ambiguous initializer SQL principal")
        return matching[0] if matching else None

    def effect(instance, action):
        if action in {"revoke", "delete"}:
            return google.cleanup_initializer(instance, action)
        method, resource, args = user_request(instance, action)
        return google.request("sql", method, resource, **args)

    def initialize(instance):
        guarded()
        require(own_user(instance) is None, "preexisting initializer SQL principal must never be adopted")
        require(google.request("sql", "GET", f"projects/{PROJECT}/instances/{instance}/databases/{DATABASE}", missing=True) is None,
                "application database exists; missing phase cannot resume an unknown write")
        journal = prepared_intents[instance]
        require(journal["not_before_unix"] <= time.time(), "published create window not yet open")
        operation = once(directory, "initializer-create-effect-" + instance, lambda: effect(instance, "create"),
                         context={"published_intent_sha256": sha(journal)})
        operation_proof(operation, instance, "CREATE_USER", recovery)
        # Once a native creation response exists, retain it for cleanup even if polling fails.
        created[instance] = operation
        data.wait_sql(google, operation, maximum_seconds=max(1, deadline - time.time() - 60))
        user = observe(lambda: own_user(instance), lambda u: u is not None, deadline)
        require(user.get("type") == "CLOUD_IAM_SERVICE_ACCOUNT" and user.get("databaseRoles") == ["cloudsqlsuperuser"],
                "native initializer identity or assigned role differs")
        native(directory, instance, "capability", files=files, deadline=deadline,
               expected_catalog=plan["initialization"]["catalog_sha256"], recipient=plan["catalog_recipient"],
               provenance=catalog_provenance(google.packet))
        guarded()
        operation = once(directory, "database-create-" + instance, lambda: google.request("sql", "POST",
            f"projects/{PROJECT}/instances/{instance}/databases", body={"project": PROJECT,"instance": instance,"name": DATABASE}))
        operation_proof(operation, instance, "CREATE_DATABASE", recovery)
        data.wait_sql(google, operation, maximum_seconds=max(1, deadline-time.time()-60))
        database = observe(lambda: google.request("sql", "GET", f"projects/{PROJECT}/instances/{instance}/databases/{DATABASE}", missing=True),
                           lambda value: value is not None, deadline)
        require(database.get("name") == DATABASE and database.get("instance") == instance
                and database.get("project") == PROJECT, "created database target differs")
        result = once(directory, "roles-create-" + instance,
                      lambda: native(directory, instance, "initialize", files=files, deadline=deadline,
                          expected_postconditions=results[CLONE]["native"]["postconditions"] if instance == SOURCE else None))
        results[instance] = {"database_operation": operation, "database": database, "native": result}

    def cleanup_owned(instance, state):
        # Never remove a principal without a retained native creation response.
        # Pending CREATE_USER is already an effect; read-only observation does
        # not extend its original privilege deadline or replay its creation.
        data.wait_sql(google, created[instance], maximum_seconds=60)
        user = own_user(instance)
        require(user and user.get("type") == "CLOUD_IAM_SERVICE_ACCOUNT", "owned initializer identity disappeared or changed")
        prove_current_initializer_ownership(google, instance, prepared_intents[instance], recovery, created[instance], deadline)
        operation = once(directory, "initializer-revoke-" + instance, lambda: effect(instance, "revoke"))
        operation_proof(operation, instance, "UPDATE_USER", recovery)
        state["step"] = "observe_role_revocation"
        data.wait_sql(google, operation, maximum_seconds=max(1, deadline-time.time()))
        observe(lambda: own_user(instance), lambda u: u is not None and u.get("databaseRoles", []) == [], deadline)
        state["api_roles_empty"] = True
        state["step"] = "verify_native_privilege_removal"
        native(directory, instance, "clean", files=files, deadline=deadline)
        state["native_removal_verified"] = True
        state["step"] = "delete_owned_principal"
        prove_current_initializer_ownership(google, instance, prepared_intents[instance], recovery, created[instance], deadline,
                                            {operation["name"]: operation})
        operation = once(directory, "initializer-delete-" + instance, lambda: effect(instance, "delete"))
        operation_proof(operation, instance, "DELETE_USER", recovery)
        data.wait_sql(google, operation, maximum_seconds=max(1, deadline-time.time()))
        observe(lambda: own_user(instance), lambda u: u is None, deadline)
        state["principal_deleted"] = True
        require(time.time() < deadline, "initializer cleanup exceeded its admitted privilege window")
        if instance in results:
            results[instance]["initializer_deleted"] = True
            results[instance]["cleanup_at_unix"] = int(time.time())

    def cleanup(instance):
        intent_path = directory / ("initializer-create-effect-" + instance + ".json")
        if instance not in created and not intent_path.exists():
            return  # No CREATE_USER intent was ever issued on this target.
        state = {"version": "initializer-cleanup/v1", "source_sha": google.packet["source_sha"],
                 "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
                 "instance": instance, "privilege_deadline_unix": deadline, "outcome": "blocked",
                 "requires_reconciliation": True, "api_roles_empty": False,
                 "native_removal_verified": False, "principal_deleted": False,
                 "step": "reconcile_native_creation", "create_intent_sha256": hashlib.sha256(private_bytes(intent_path)).hexdigest()}
        state_path = directory / ("initializer-cleanup-state-" + instance + ".json")
        try:
            if instance not in created:
                # A timeout or rejected ownership proof cannot authorize deletion
                # of a subsequently observed, possibly unrelated SQL principal.
                state["native_principal_observed"] = own_user(instance) is not None
                state["reason"] = "CREATE_USER ownership unconfirmed; never adopt or replay"
                return
            cleanup_owned(instance, state)
            state.update(outcome="complete", requires_reconciliation=False)
        except BaseException as error:
            state["failure_class"] = type(error).__name__
            raise
        finally:
            state["observed_at_unix"] = int(time.time())
            state["deadline_exceeded"] = time.time() >= deadline
            state_path.write_text(json.dumps(state, sort_keys=True)); state_path.chmod(0o600)

    def recheck():
        guarded()
        require(results.get(CLONE, {}).get("initializer_deleted") is True, "source needs completed clone privilege cleanup")
        source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
        require(source.get("settings", {}).get("settingsVersion") == plan["database_etag"], "source changed after clone qualification")

    qualify_then_source(initialize, cleanup, recheck)
    output.write_text(json.dumps({"version": "data-initialized/v1", "source_sha": google.packet["source_sha"],
        "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
        "plan_sha256": sha(plan), "recovery": recovery, "targets": results,
        "initialized": True, "data_ready": False, "release_accepted": False}, sort_keys=True) + "\n")


def verified_handoff(path, packet, plan, *, initialized=False):
    from deploy_runtime import verified_receipt_bytes
    expected = os.environ.get("INITIALIZATION_RECEIPT_SHA256", "")
    digest(expected, "previous protected-job receipt")
    raw = verified_receipt_bytes(path, expected, packet["source_sha"], "data-release.yml")
    value = strict_json(raw)
    if not initialized:
        return validate_recovery_receipt(value, packet, plan)
    require(value.get("version") == "data-initialized/v1" and value.get("initialized") is True
            and value.get("source_sha") == packet["source_sha"]
            and value.get("run_id") == packet["release_run_id"] and value.get("run_attempt") == packet["release_run_attempt"]
            and value.get("plan_sha256") == sha(plan), "stale initialization result")
    recovery = validate_recovery_receipt(value["recovery"], packet, plan, cleanup=True)
    require(set(value["targets"]) == {SOURCE, CLONE}, "both named targets require initialization proof")
    for instance, target in value["targets"].items():
        require(target.get("initializer_deleted") is True
                and type(target.get("cleanup_at_unix")) is int
                and recovery["parity_at_unix"] <= target["cleanup_at_unix"] < recovery["privilege_deadline_unix"]
                and target["native"].get("instance") == instance and target["native"].get("files") == fingerprints(),
                "native initialization or bounded privilege cleanup unconfirmed")
    return value


def require_protected_initializer_environment(plan):
    from release_admission import gh_json
    from release_context import REPOSITORY
    environment = gh_json(f"repos/{REPOSITORY}/environments/data-initialization-production")
    require(environment.get("deployment_branch_policy") == {"protected_branches": False, "custom_branch_policies": True},
            "initializer environment must have a verified custom main-only policy before OIDC")
    policies = gh_json(f"repos/{REPOSITORY}/environments/data-initialization-production/deployment-branch-policies")
    require(policies.get("total_count") == 1 and len(policies.get("branch_policies", [])) == 1
            and policies["branch_policies"][0].get("name") == "main"
            and policies["branch_policies"][0].get("type") == "branch", "default or broader initializer environment rejected")


def verified_disposal_inputs(packet, recovery_path, journal_directory):
    """Original signed attempt, without renewed initialization or paid authority."""
    from deploy_runtime import verified_receipt_bytes
    def signed(path):
        raw = path.read_bytes()
        return strict_json(verified_receipt_bytes(path, hashlib.sha256(raw).hexdigest(), packet["source_sha"], "data-release.yml"))
    recovery = signed(recovery_path)
    require(recovery.get("version") == "data-initialization-recovery/v1"
            and recovery.get("source_sha") == packet["source_sha"]
            and recovery.get("run_id") == packet["release_run_id"]
            and recovery.get("run_attempt") == packet["release_run_attempt"]
            and recovery.get("initialization_files") == fingerprints()
            and recovery.get("native_restore_verified") is True, "disposal requires original signed native parity")
    integer(recovery["parity_at_unix"], packet["issued_at_unix"], packet["expires_at_unix"], "original parity")
    integer(recovery["privilege_deadline_unix"], recovery["parity_at_unix"] + 1,
            min(recovery["parity_at_unix"] + 600, packet["expires_at_unix"]), "original privilege deadline")
    journals = {}
    for instance in (SOURCE, CLONE):
        path = journal_directory / ("initializer-create-" + instance + ".json")
        if path.exists():
            journals[instance] = signed(path)
    return recovery, journals


def prove_current_initializer_ownership(google, instance, journal, recovery, creation, deadline, acknowledged_updates=None):
    import deploy_data as data
    acknowledged_updates = acknowledged_updates or {}
    # Operations do not identify the affected SQL username. Any
    # intervening create/delete on this instance makes the current
    # same-named principal's lineage ambiguous, regardless of actor.
    lifecycle = data.list_sql(google, f"projects/{PROJECT}/operations", instance=instance, maxResults=100)
    original_seen = 0
    keys = ("name", "targetId", "targetProject", "operationType", "user", "insertTime")
    for candidate in lifecycle:
        if candidate.get("operationType") not in {"CREATE_USER", "DELETE_USER", "UPDATE_USER"}:
            continue
        inserted = data.stamp(candidate.get("insertTime"))
        if inserted < journal["absence_at_unix"]:
            continue
        require(candidate.get("targetId") == instance and candidate.get("targetProject") == PROJECT
                and inserted <= time.time(), "untrusted native user lifecycle scope or time")
        if candidate.get("name") == creation["name"]:
            require(all(candidate.get(key) == creation.get(key) for key in keys), "original creation provenance changed")
            require(candidate.get("status") == "DONE" and "error" not in candidate, "original creation no longer confirmed complete")
            original_seen += 1
            continue
        require(candidate.get("operationType") == "UPDATE_USER", "intervening create/delete makes current SQL principal ownership ambiguous")
        acknowledged = acknowledged_updates.get(candidate.get("name"))
        require(acknowledged is not None and all(candidate.get(key) == acknowledged.get(key) for key in keys),
                "user update lacks exact retained request/response proof; current ownership is ambiguous")
        require(candidate.get("status") == "DONE" and "error" not in candidate,
                "unfinished user update requires reconciliation")
    require(original_seen == 1 and time.time() < deadline, "current ownership continuity unconfirmed")


def dispose_initializer_target(google, instance, recovery, journals, directory):
    """Only ordinary data identity: reconcile a signed intent, revoke, then dispose.

    A new bounded disposal clock cannot qualify initialization or extend its
    privilege window. Uncertain ownership is never converted into permission.
    """
    import deploy_data as data
    require(google.plane == "data" and instance in (SOURCE, CLONE), "ordinary named disposal only")
    started, deadline = time.time(), time.time() + 180
    state = {"version": "initializer-disposal/v1", "source_sha": google.packet["source_sha"],
        "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
        "instance": instance, "privilege_deadline_unix": recovery["privilege_deadline_unix"],
        "outcome": "blocked", "principal_absence_verified": False, "release_accepted": False}
    path = directory / ("initializer-disposal-" + instance + ".json")
    previous_deadline = getattr(google, "sql_read_deadline", None)
    google.sql_read_deadline = deadline
    def users():
        records = data.list_sql(google, f"projects/{PROJECT}/instances/{instance}/users")
        matching = [value for value in records if value.get("name") == INITIALIZER_SQL]
        require(len(matching) <= 1, "ambiguous temporary SQL principal")
        require(time.time() < deadline, "disposal observation exceeded its own fixed deadline")
        return matching[0] if matching else None
    def check(mode):
        return native(directory, instance, mode, files=fingerprints(), deadline=deadline)
    def poll(operation):
        import re
        identity = {key: operation.get(key) for key in ("name", "targetId", "targetProject", "operationType", "user", "insertTime")}
        require(isinstance(identity["name"], str) and re.fullmatch(r"[A-Za-z0-9_-]+", identity["name"]), "invalid disposal operation")
        while operation.get("status") != "DONE":
            require(time.time() + 5 < deadline, "disposal operation timed out")
            time.sleep(5)
            operation = google.request("sql", "GET", f"projects/{PROJECT}/operations/{identity['name']}")
            require(all(operation.get(key) == value for key, value in identity.items()), "disposal operation provenance drift")
        require(time.time() < deadline and "error" not in operation, "disposal operation failed or arrived late")
        return operation
    try:
        user = users()
        if user is None:
            check("disposal-absent")
        else:
            journal = validate_creation_intent(journals.get(instance, {}), instance, google.packet, recovery)
            require(user.get("type") == "CLOUD_IAM_SERVICE_ACCOUNT", "SQL principal type differs from owned intent")
            operations = data.list_sql(google, f"projects/{PROJECT}/operations", instance=instance, maxResults=100)
            candidates = []
            for operation in operations:
                if operation.get("operationType") != "CREATE_USER" or operation.get("user") != INITIALIZER_SQL + ".gserviceaccount.com":
                    continue
                stamp = data.stamp(operation.get("insertTime"))
                if journal["not_before_unix"] <= stamp < recovery["privilege_deadline_unix"]:
                    operation_proof(operation, instance, "CREATE_USER", recovery)
                    candidates.append(operation)
            require(len(candidates) == 1, "native creation ownership is missing or ambiguous; no adoption")
            creation = candidates[0]
            poll(creation)
            state["creation_operation"] = creation["name"]
            acknowledged_updates = {}


            for action in ("revoke", "delete"):
                prove_current_initializer_ownership(google, instance, journal, recovery, creation, deadline, acknowledged_updates)
                operation = once(directory, "disposal-" + action + "-" + instance,
                                 lambda: google.dispose_initializer(instance, action))
                require(operation.get("targetId") == instance and operation.get("targetProject") == PROJECT
                    and operation.get("operationType") == ("UPDATE_USER" if action == "revoke" else "DELETE_USER")
                    and operation.get("user") == MAINTENANCE + ".gserviceaccount.com"
                    and started <= data.stamp(operation.get("insertTime")) < deadline, "native ordinary disposal identity differs")
                poll(operation)
                if action == "revoke":
                    acknowledged_updates[operation["name"]] = operation
                    observe(users, lambda value: value is not None and value.get("databaseRoles", []) == [], deadline)
                    check("disposal-check")
                else:
                    observe(users, lambda value: value is None, deadline)
                    check("disposal-absent")
        state.update(outcome="complete", principal_absence_verified=True)
        return state
    except BaseException as error:
        state["failure_class"] = type(error).__name__
        raise
    finally:
        google.sql_read_deadline = previous_deadline
        state["observed_at_unix"] = int(time.time())
        state["privilege_deadline_exceeded"] = time.time() >= recovery["privilege_deadline_unix"]
        path.write_text(json.dumps(state, sort_keys=True)); path.chmod(0o600)
