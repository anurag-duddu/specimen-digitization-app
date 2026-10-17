"""Explicit-only contracts for the live, seeded, disposable SQL Connect engine.

Select this file inside test-postgres.sh's engine lifetime. Missing opt-in,
loopback host, engine or canonical seed is a failure, never a skipped contract.
Admin GraphQL observes real rows; every application write uses the real adapter.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import requests

from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from specimen_digitization.application.demo import fixture as synthetic_image
from specimen_digitization.application.domain import Asset, Principal, Run, Scope, Specimen
from specimen_digitization.application.lane import run_status
from specimen_digitization.application.production import (
    SqlConnectRepository,
    actor_uid,
    sql_emulator_host,
    verified_actor_context,
)
from specimen_digitization.application.storage import Conflict, LocalBlobs, digest, work_available_at


OWNER = "synthetic-reviewer"
TABLE_FIELDS = {
    "specimens": "organizationId collectionId id revision state disposition activeRunId workAvailableAt sourceChecksum sensitive createdBy createdAt updatedAt",
    "specimenSnapshots": "organizationId collectionId specimenId revision contractVersion snapshot sha256 createdAt",
    "requestReceipts": "organizationId collectionId actorUid operation idempotencyKey requestSha256 specimenId revision createdAt",
    "auditEvents": "organizationId collectionId id specimenId actorUid action revision requestSha256 createdAt",
    "outboxEvents": "organizationId collectionId id specimenId aggregateRevision eventType deduplicationKey payloadReferences createdAt",
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _uuid(value):
    return UUID(value).hex


def _scope_key(scope):
    return f'organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}"'


def _where(scope):
    return f'organizationId:{{eq:"{scope.organization_id}"}},collectionId:{{eq:"{scope.collection_id}"}}'


def _ok(reply, label):
    status, body = reply
    assert status == 200, f"{label}: HTTP {status}: {body}"
    assert not body.get("errors") and not body.get("code"), f"{label}: {body}"
    assert isinstance(body.get("data"), dict), f"{label}: missing data: {body}"
    return body["data"]


def _denied(reply, operation, label, *, member=None, client=None):
    """Require an access failure at the intended check, with no protected data."""
    results = {
        "GetSpecimen": {"specimen", "specimenSnapshots"},
        "GetSnapshot": {"specimen", "specimenSnapshot"},
        "ListSpecimens": {"specimens"},
        "ListSpecimenPage": {"specimens"},  # paging.gql: adapter list uses the keyset page.
        "GetReceipt": {"requestReceipt"},
        "CreateSpecimenV3": {"specimen_insert", "specimenSnapshot_insert", "requestReceipt_insert",
                             "outboxEvent_insert", "auditEvent_insert"},
        "SaveSpecimenV3": {"specimen_updateMany", "specimenSnapshot_insert", "requestReceipt_insert",
                           "outboxEvent_insert", "auditEvent_insert"},
    }
    assert operation in results, f"{label}: unrecognized refusal operation: {operation}"
    assert client in {None, "authenticated", "anonymous"}, client
    mutation = operation in {"CreateSpecimenV3", "SaveSpecimenV3"}
    if client:
        assert mutation and member is None, f"{label}: client refusal must isolate V3 NO_ACCESS"
    else:
        assert member in {"organizationMember", "collectionMember"}, f"{label}: expected membership check required"
    status, body = reply
    assert status in ({200, 401, 403} if client else {200}), f"{label}: transport failure: {reply}"
    assert isinstance(body, dict), f"{label}: malformed error envelope: {body}"
    data = body.get("data")
    assert data is None or isinstance(data, dict), f"{label}: malformed response data: {data}"
    # Read operations also select membership metadata; V3's queries are @redact.
    metadata = {"organizationMember", "collectionMember"} if not mutation else set()
    for field, value in (data or {}).items():
        assert field in results[operation] | metadata, f"{label}: unexpected response data: {field}={value}"
        if field in results[operation]:
            assert value is None or (isinstance(value, list) and not value), (
                f"{label}: protected response data from {operation}.{field}: {value}"
            )
        elif value is not None:
            fields = {"active"} if field == "organizationMember" else {"active", "role", "canViewSensitive"}
            if operation == "ListSpecimenPage" and field == "collectionMember":
                fields = {"active", "canViewSensitive"}  # paging.gql selects no role.
            assert isinstance(value, dict) and value.keys() <= fields, f"{label}: unexpected membership data: {value}"
            for name, item in value.items():
                assert (isinstance(item, str) if name == "role" else type(item) is bool), (
                    f"{label}: malformed membership data: {value}"
                )
    # Registration, SQL execution and internal errors are never denial evidence,
    # even if mixed with a permission error in the same GraphQL response.
    assert not re.search(
        r"cannot query|unknown (?:operation|field|argument|type)|not defined|"
        r"syntax error|validation error|invalid value|was not provided|not published|"
        r"already.exists|duplicate key|unique constraint|internal|sqlstate|constraint violation",
        _json(body), re.I,
    ), f"{label}: did not reach a registered authorization check: {body}"
    codes = {"PERMISSION_DENIED", "UNAUTHENTICATED"} if client == "anonymous" else {"PERMISSION_DENIED"}
    errors = body.get("errors")
    if errors is not None:
        assert isinstance(errors, list) and errors, f"{label}: unexpectedly authorized: {reply}"
        assert not body.get("code") and not body.get("error"), f"{label}: mixed error envelopes: {body}"
        # checksum.gql's query @redact collapses a child's failed @check to
        # ['query'] on the wire (round-3 local probe). A wrapper path alone
        # cannot identify which check refused: require that detail below.
        redacted = mutation and not client and isinstance(errors[0], dict) and errors[0].get("path") == ["query"]
        expected_path = ["query"] if redacted else (["query", member] if mutation else [member])
        for index, error in enumerate(errors):
            assert isinstance(error, dict) and isinstance(error.get("message"), str) and error["message"], (
                f"{label}: malformed GraphQL error: {error}"
            )
            extensions = error.get("extensions")
            path = error.get("path")
            if not client and isinstance(extensions, dict) and extensions.get("code") == "ABORTED":
                # The engine aborts dependent fields after a membership @check.
                # Production reads errors[0], which must remain a real denial.
                assert index > 0, f"{label}: cascade cannot establish denial: {error}"
                assert error == {
                    "message": "(aborted)", "locations": [], "path": path,
                    "extensions": {"file": "", "code": "ABORTED", "debugDetails": "", "resource": "",
                                   "warningLevel": "WARNING_LEVEL_UNKNOWN", "workarounds": []},
                }, f"{label}: unexpected abort envelope: {error}"
                cascade_paths = [[field] for field in results[operation] | metadata]
                if mutation:
                    cascade_paths += [["query"], ["query", "organizationMember"], ["query", "collectionMember"]]
                    if operation == "SaveSpecimenV3":
                        cascade_paths += [["current"], ["current", "specimen"]]
                assert path != expected_path and path in cascade_paths, (
                    f"{label}: cascade must be at another field of {operation}: {error}"
                )
                continue
            assert (isinstance(extensions, dict) and isinstance(extensions.get("code"), str)
                    and extensions["code"] in codes), (
                f"{label}: expected {'/'.join(sorted(codes))}, got {error}"
            )
            if client:
                assert path in (None, [], [operation]), f"{label}: client failed a field check, not NO_ACCESS: {error}"
            else:
                assert path == expected_path, f"{label}: expected membership check at {expected_path}, got {error}"
                if redacted:
                    details = extensions.get("debugDetails")
                    assert isinstance(details, str), f"{label}: redacted denial must identify its membership check: {error}"
                    checks = tuple(re.findall(r"Check Requirement Evaluated: Every\(path: ([^,\s]+),", details))
                    # Source order is organizationMember, collectionMember;
                    # either can fail alone, or both can fail in that order.
                    allowed = {(f"query.{member}",)}
                    if member == "organizationMember":
                        allowed.add(("query.organizationMember", "query.collectionMember"))
                    assert checks in allowed, f"{label}: wrong redacted membership check: {error}"
    else:
        # HTTP status alone proves nothing. Accept only a structured client auth
        # status (gRPC code or Google REST error), never a generic 401/403 page.
        assert client and status in {401, 403}, f"{label}: missing authorization error: {reply}"
        error = body.get("error", body)
        assert isinstance(error, dict) and isinstance(error.get("message"), str) and error["message"], (
            f"{label}: malformed client auth error: {body}"
        )
        grpc_codes = {7, 16} if client == "anonymous" else {7}
        assert type(error.get("code")) is int and (
            (error["code"] in grpc_codes and "status" not in error)
            or (error["code"] == status and isinstance(error.get("status"), str) and error["status"] in codes)
        ), (
            f"{label}: expected structured client authorization failure: {body}"
        )


_HOSTED_DENIAL_CASES = (
    "foreign_actor", "foreign_organization", "foreign_collection", "revoked_organization",
)


def _hosted_denial_fragment(case):
    """Replay the recorded cascade with the established primary denial.

    I10-V2/hosted-evidence.json, pilot 38980318610: complete ABORTED errors
    at log lines 240/346/452/545; first-error codes at 249/355/461/554.
    Full replies were truncated. The primary message and unprinted reply
    fields use minimal synthetic values; the primary code/path were
    established by the adapter log and prior assertions.
    This is a minimal fragment replay, not a complete recorded HTTP reply.
    """
    organization_denied = case in {"foreign_organization", "revoked_organization"}
    member = "organizationMember" if organization_denied else "collectionMember"
    cascade = "collectionMember" if organization_denied else "specimen"
    return member, (200, {
        "data": {"collectionMember": None,
                 "organizationMember": None if organization_denied else {"active": True},
                 "specimen": None, "specimenSnapshots": None},
        "errors": [
            {"message": "membership denied (synthetic message)", "path": [member],
             "extensions": {"code": "PERMISSION_DENIED"}},
            {"message": "(aborted)", "locations": [], "path": [cascade],
             "extensions": {"file": "", "code": "ABORTED", "debugDetails": "", "resource": "",
                            "warningLevel": "WARNING_LEVEL_UNKNOWN", "workarounds": []}},
        ],
        "extensions": None,
    })


@pytest.mark.parametrize("case", _HOSTED_DENIAL_CASES)
def test_denial_oracle_hosted_fragment(case):
    member, reply = _hosted_denial_fragment(case)
    _denied(reply, "GetSpecimen", case, member=member)


@pytest.mark.parametrize("case", _HOSTED_DENIAL_CASES)
@pytest.mark.parametrize("fault", (
    "aborted_only", "aborted_first", "first_code", "first_path", "later_denial_path",
    "other_code", "message", "locations", "missing_locations", "foreign_path",
    "same_path", "nested_path", "other_operation_field", "file", "debugDetails",
    "resource", "warningLevel", "workarounds", "extra_extension", "missing_extension",
    "extra_error_field", "data_object", "data_list", "authorized", "authorized_empty",
))
def test_denial_oracle_rejects_invalid_fragment(case, fault):
    member, reply = _hosted_denial_fragment(case)
    body = reply[1]
    first, cascade = body["errors"]
    if fault == "aborted_only":
        body["errors"] = [cascade]
    elif fault == "aborted_first":
        body["errors"] = [cascade, first]
    elif fault == "first_code":
        first["extensions"]["code"] = "UNAUTHENTICATED"
    elif fault == "first_path":
        first["path"] = ["collectionMember" if member == "organizationMember" else "organizationMember"]
    elif fault == "later_denial_path":
        cascade["extensions"]["code"] = "PERMISSION_DENIED"
    elif fault == "other_code":
        cascade["extensions"]["code"] = "UNAVAILABLE"
    elif fault == "message":
        cascade["message"] = "aborted"
    elif fault == "locations":
        cascade["locations"] = [{"line": 1, "column": 1}]
    elif fault == "missing_locations":
        del cascade["locations"]
    elif fault == "foreign_path":
        cascade["path"] = ["foreignField"]
    elif fault == "same_path":
        cascade["path"] = [member]
    elif fault == "nested_path":
        cascade["path"] = ["specimen", "foreignField"]
    elif fault == "other_operation_field":
        cascade["path"] = ["specimens"]
    elif fault in {"file", "debugDetails", "resource", "warningLevel"}:
        cascade["extensions"][fault] = "different"
    elif fault == "workarounds":
        cascade["extensions"]["workarounds"] = ["retry"]
    elif fault == "extra_extension":
        cascade["extensions"]["other"] = ""
    elif fault == "missing_extension":
        del cascade["extensions"]["file"]
    elif fault == "extra_error_field":
        cascade["other"] = ""
    elif fault == "data_object":
        body["data"]["specimen"] = {"id": "protected"}
    elif fault == "data_list":
        body["data"]["specimenSnapshots"] = [{"snapshot": "protected"}]
    elif fault == "authorized":
        body["errors"] = []
        body["data"]["specimen"] = {"id": "protected"}
    elif fault == "authorized_empty":
        body["errors"] = []
    else:
        raise AssertionError(f"Unknown refusal fault: {fault}")
    with pytest.raises(AssertionError):
        _denied(reply, "GetSpecimen", f"{case}: {fault}", member=member)


@pytest.mark.parametrize("operation,member,path", (
    ("GetSpecimen", "collectionMember", ("specimenSnapshots",)),
    ("GetSnapshot", "organizationMember", ("specimenSnapshot",)),
    ("ListSpecimens", "organizationMember", ("specimens",)),
    ("GetReceipt", "organizationMember", ("requestReceipt",)),
    ("CreateSpecimenV3", "organizationMember", ("query", "collectionMember")),
    ("CreateSpecimenV3", "collectionMember", ("specimen_insert",)),
    ("SaveSpecimenV3", "organizationMember", ("current", "specimen")),
    ("SaveSpecimenV3", "collectionMember", ("specimen_updateMany",)),
))
def test_denial_oracle_operation_cascade(operation, member, path):
    # Synthetic coverage of the same rule for the other registered operations.
    _, reply = _hosted_denial_fragment("foreign_actor")
    body = reply[1]
    body["data"] = None
    primary = ["query", member] if operation.endswith("V3") else [member]
    body["errors"][0]["path"] = primary
    body["errors"][1]["path"] = list(path)
    # Repeated permitted denials remain before the cascade.
    body["errors"].insert(1, {"message": "membership denied", "path": list(primary),
                              "extensions": {"code": "PERMISSION_DENIED"}})
    _denied(reply, operation, "synthetic operation cascade", member=member)


@pytest.mark.parametrize("client,code", (
    ("authenticated", "PERMISSION_DENIED"), ("anonymous", "PERMISSION_DENIED"),
    ("anonymous", "UNAUTHENTICATED"),
))
def test_denial_oracle_client_boundary(client, code):
    _, reply = _hosted_denial_fragment("foreign_actor")
    body = reply[1]
    body["data"] = None
    body["errors"][0]["path"] = ["CreateSpecimenV3"]
    body["errors"][0]["extensions"]["code"] = code
    cascade = body["errors"].pop()
    _denied(reply, "CreateSpecimenV3", "client denial", client=client)
    body["errors"].append(cascade)
    with pytest.raises(AssertionError):
        _denied(reply, "CreateSpecimenV3", "client must not accept field cascade", client=client)


@pytest.mark.parametrize("member", ("organizationMember", "collectionMember"))
@pytest.mark.parametrize("fault", (None, "data", "path", "first_code", "other_field", "metadata"))
def test_denial_oracle_page_replay(member, fault):
    # paging.gql: ListSpecimenPage selects specimens plus active/canViewSensitive
    # membership metadata. These replies are synthetic, not engine evidence.
    _, reply = _hosted_denial_fragment("foreign_actor")
    body = reply[1]
    body["data"] = {"organizationMember": None, "collectionMember": None, "specimens": None}
    body["errors"][0]["path"] = [member]
    body["errors"][1]["path"] = ["specimens"]
    if fault == "data":
        body["data"]["specimens"] = [{"id": "protected"}]
    elif fault == "path":
        body["errors"][0]["path"] = ["specimens"]
    elif fault == "first_code":
        body["errors"][0]["extensions"]["code"] = "UNAUTHENTICATED"
    elif fault == "other_field":
        body["errors"][1]["path"] = ["specimenSnapshots"]
    elif fault == "metadata":
        body["data"]["collectionMember"] = {"role": "reviewer"}
    if fault is None:
        _denied(reply, "ListSpecimenPage", "page refusal replay", member=member)
    else:
        with pytest.raises(AssertionError):
            _denied(reply, "ListSpecimenPage", f"page refusal replay: {fault}", member=member)


@pytest.mark.parametrize("operation", ("NotAConnectorOperation", "Memberships"))
def test_denial_oracle_rejects_unregistered_refusal(operation):
    # Memberships has actor/active filters but no membership @check; success
    # there cannot substitute for a scope refusal on ListSpecimenPage.
    member, reply = _hosted_denial_fragment("foreign_actor")
    with pytest.raises(AssertionError, match="unrecognized refusal operation"):
        _denied(reply, operation, "unregistered refusal replay", member=member)


@pytest.mark.parametrize("member", ("organizationMember", "collectionMember"))
@pytest.mark.parametrize("fault", (
    None, "foreign_organization", "foreign_collection", "inactive", "duplicate", "missing_row",
    "extra_field", "missing_table", "protected_data", "member_denial", "member_actor",
    "malformed_active", "malformed_sensitive",
    "target_grant", "page_data", "page_path", "page_code", "missing_page", "unknown_operation",
))
def test_denial_oracle_adapter_list_replay(member, fault):
    # Synthetic admin expectations and wire replies, never an engine substitute.
    scope = Scope(organization_id="10000000-0000-4000-8000-000000000001",
                  collection_id="10000000-0000-4000-8000-000000000002")
    own_org, own_collection = "20000000000040008000000000000001", "20000000000040008000000000000002"
    uid = "synthetic-replay-actor"
    expected = {
        "organizationMembers": [{"organizationId": own_org, "active": True}],
        "collectionMembers": [{"organizationId": own_org, "collectionId": own_collection,
                               "active": True, "role": "reviewer", "canViewSensitive": True}],
    }
    # Organization revocation leaves the actor's active collection row; collection
    # revocation leaves the active organization row. Neither grants scoped access.
    if member == "organizationMember":
        expected["collectionMembers"].append({
            "organizationId": _uuid(scope.organization_id), "collectionId": _uuid(scope.collection_id),
            "active": True, "role": "reviewer", "canViewSensitive": True,
        })
    else:
        expected["organizationMembers"].append({"organizationId": _uuid(scope.organization_id), "active": True})
    data = json.loads(_json(expected))
    memberships = {"operationName": "Memberships", "variables": {"actorUid": uid}}
    membership_body = {"data": data, "errors": []}
    _, page_reply = _hosted_denial_fragment("foreign_actor")
    page_reply[1]["data"] = {"specimens": None}
    page_reply[1]["errors"][0]["path"] = [member]
    page_reply[1]["errors"][1]["path"] = ["specimens"]
    page = {"operationName": "ListSpecimenPage", "variables": _base(scope, uid)}
    attempts = [(memberships, (200, membership_body)), (page, page_reply)]
    if fault in {"foreign_organization", "foreign_collection"}:
        table = "organizationMembers" if fault == "foreign_organization" else "collectionMembers"
        data[table].append({**data[table][0], "organizationId": "30000000000040008000000000000001"})
    elif fault == "inactive":
        data["collectionMembers"][0]["active"] = False
    elif fault == "duplicate":
        data["collectionMembers"].append(dict(data["collectionMembers"][0]))
    elif fault == "missing_row":
        data["collectionMembers"].pop()
    elif fault == "extra_field":
        data["collectionMembers"][0]["uid"] = "another-actor"
    elif fault == "missing_table":
        del data["organizationMembers"]
    elif fault == "protected_data":
        data["specimens"] = [{"id": "protected"}]
    elif fault == "member_denial":
        membership_body["errors"] = page_reply[1]["errors"]
    elif fault == "member_actor":
        memberships["variables"]["actorUid"] = "another-actor"
    elif fault in {"malformed_active", "malformed_sensitive"}:
        field = "active" if fault == "malformed_active" else "canViewSensitive"
        data["collectionMembers"][0][field] = 1
    elif fault == "target_grant":
        # Even a matching admin expectation must not describe an active grant
        # for the scope being tested as foreign/revoked.
        table = "organizationMembers" if member == "organizationMember" else "collectionMembers"
        row = {"organizationId": _uuid(scope.organization_id), "active": True}
        if table == "collectionMembers":
            row.update(collectionId=_uuid(scope.collection_id), role="reviewer", canViewSensitive=True)
        expected[table].append(row)
        data[table].append(dict(row))
    elif fault == "page_data":
        page_reply[1]["data"]["specimens"] = [{"id": "protected"}]
    elif fault == "page_path":
        page_reply[1]["errors"][0]["path"] = ["specimens"]
    elif fault == "page_code":
        page_reply[1]["errors"][0]["extensions"]["code"] = "UNAUTHENTICATED"
    elif fault == "missing_page":
        attempts.pop()
    elif fault == "unknown_operation":
        page["operationName"] = "NotAConnectorOperation"
    if fault is None:
        _assert_adapter_denials(attempts, "list", scope, uid, member, expected)
    else:
        with pytest.raises(AssertionError):
            _assert_adapter_denials(attempts, "list", scope, uid, member, expected)


@pytest.mark.parametrize("operation", ("CreateSpecimenV3", "SaveSpecimenV3"))
@pytest.mark.parametrize("members", (
    ("collectionMember",), ("organizationMember",), ("organizationMember", "collectionMember"),
))
@pytest.mark.parametrize("fault", (
    None, "data", "path", "first_code", "missing_debug", "wrong_check", "other_check",
    "reversed_checks", "aborted_first", "cascade_path", "cascade_message",
))
def test_denial_oracle_redacted_mutation_replay(operation, members, fault):
    # checksum.gql nests both membership checks in query @redact. The round-3
    # local probe reports CreateSpecimenV3 failures at ['query'], naming the
    # exact failed children in debugDetails. Save's matching wrapper is derived
    # from source; this minimal synthetic replay is not engine qualification.
    source = (Path(__file__).resolve().parents[1] / "dataconnect/connector/checksum.gql").read_text()
    definition = source.split(f"mutation {operation}(", 1)[1].split("\n}", 1)[0]
    details = []
    for member in members:
        expression = re.search(rf'{member}\(.*?@check\(expr: "([^"]+)"', definition)[1]
        details.append(f'Check Requirement Evaluated: Every(path: query.{member}, '
                       f'DenyUnlessTrue(CEL("{expression}" -> Boolean)))')
    _, reply = _hosted_denial_fragment("foreign_actor")
    body = reply[1]
    result = "specimen_insert" if operation == "CreateSpecimenV3" else "specimen_updateMany"
    body["data"] = {result: None}
    first, cascade = body["errors"]
    first["path"] = ["query"]
    first["extensions"]["debugDetails"] = "\n".join(details)
    cascade["path"] = [result]
    if fault == "data":
        body["data"][result] = {"id": "protected"} if operation == "CreateSpecimenV3" else 1
    elif fault == "path":
        first["path"] = ["current"]
    elif fault == "first_code":
        first["extensions"]["code"] = "UNAUTHENTICATED"
    elif fault == "missing_debug":
        del first["extensions"]["debugDetails"]
    elif fault == "wrong_check":
        first["extensions"]["debugDetails"] = details[0].replace(f"query.{members[0]}", "current.specimen")
    elif fault == "other_check":
        first["extensions"]["debugDetails"] = details[0].replace(
            f"query.{members[0]}", "query.organizationMember" if members[0] == "collectionMember" else "query.collectionMember")
    elif fault == "reversed_checks":
        first["extensions"]["debugDetails"] = "\n".join(reversed(details)) if len(details) > 1 else ""
    elif fault == "aborted_first":
        body["errors"] = [cascade, first]
    elif fault == "cascade_path":
        cascade["path"] = ["query"]
    elif fault == "cascade_message":
        cascade["message"] = "aborted"
    if fault is None:
        _denied(reply, operation, "redacted mutation refusal replay", member=members[0])
    else:
        with pytest.raises(AssertionError):
            _denied(reply, operation, f"redacted mutation refusal replay: {fault}", member=members[0])


class _Session(requests.Session):
    """Pass-through HTTP observation, with a one-shot gate at V3 CAS dispatch."""

    def __init__(self, origin):
        super().__init__()
        self.trust_env = False
        self.headers["Authorization"] = "Bearer owner"
        self.origin = origin
        self.calls = []
        self.save_barrier = None

    def post(self, url, **kwargs):
        assert url.startswith(self.origin + "/v1/projects/demo-specimen-data/"), url
        body = kwargs["json"]
        if body.get("operationName") == "SaveSpecimenV3" and self.save_barrier:
            gate, self.save_barrier = self.save_barrier, None
            gate.wait(timeout=15)
        response = super().post(url, allow_redirects=False, **kwargs)
        self.calls.append((body, (response.status_code, response.json())))
        return response


class _Engine:
    def __init__(self, host, blobs):
        self.origin = "http://" + host
        self.host = host
        self.blobs = blobs
        self.service = self.origin + "/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service"
        self.sessions = []
        self.admin = self.session()

    def session(self):
        session = _Session(self.origin)
        self.sessions.append(session)
        return session

    def repo(self):
        return SqlConnectRepository(
            project="demo-specimen-data", emulator_host=self.host, session=self.session(), graph_blobs=self.blobs
        )

    def raw(self, query):
        response = self.admin.post(self.service + ":executeGraphql", json={"query": query}, timeout=30)
        return _ok((response.status_code, response.json()), "synthetic admin")

    def op(self, name, variables, *, mutation=False, impersonate=None):
        body = {"operationName": name, "variables": variables}
        if impersonate is not None:
            body["extensions"] = {"impersonate": impersonate}
        response = self.admin.post(
            self.service + "/connectors/specimen-server:impersonate" + ("Mutation" if mutation else "Query"),
            json=body, timeout=30,
        )
        return response.status_code, response.json()

    def footprint(self, scope):
        # Whole isolated collection, including failed-create IDs and leaked receipts.
        data = self.raw("query {" + " ".join(
            f"{table}(where:{{{_where(scope)}}},limit:1000) {{{fields}}}"
            for table, fields in TABLE_FIELDS.items()
        ) + "}")
        for table in TABLE_FIELDS:
            assert len(data[table]) < 1000, f"{table}: footprint was truncated"
            data[table].sort(key=_json)
        return data

    def members(self, scope, uid=OWNER):
        return self.raw(f'''query {{
          organizationMember(key:{{organizationId:"{scope.organization_id}",uid:"{uid}"}}) {{ organizationId uid active }}
          collectionMember(key:{{{_scope_key(scope)},uid:"{uid}"}}) {{ organizationId collectionId uid active role canViewSensitive }}
        }}''')

    def close(self):
        for session in self.sessions:
            session.close()


@pytest.fixture
def engine(tmp_path):
    assert os.getenv("SPECIMEN_TEST_SQL_EMULATOR") == "true", (
        "Explicit engine contracts require SPECIMEN_TEST_SQL_EMULATOR=true inside the live seeded wrapper"
    )
    assert os.getenv("SPECIMEN_SQL_EMULATOR_HOST"), "Explicit matching SQL emulator host required"
    host = sql_emulator_host()  # Refuses all non-loopback endpoints before HTTP.
    if os.getenv("FIREBASE_DATACONNECT_EMULATOR_HOST"):
        assert os.environ["FIREBASE_DATACONNECT_EMULATOR_HOST"] == host, "Python/connector hosts differ"
    lab = _Engine(host, LocalBlobs(tmp_path / "blobs"))
    try:
        seed = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        members = lab.members(seed)
        assert members == {
            "organizationMember": {"organizationId": _uuid(SYNTHETIC_ORG), "uid": OWNER, "active": True},
            "collectionMember": {"organizationId": _uuid(SYNTHETIC_ORG), "collectionId": _uuid(SYNTHETIC_COLLECTION),
                                 "uid": OWNER, "active": True, "role": "reviewer", "canViewSensitive": True},
        }, f"Canonical integration seed missing or changed: {members}"
        with verified_actor_context(OWNER):
            assert any(m["organization_id"] == SYNTHETIC_ORG and m["collection_id"] == SYNTHETIC_COLLECTION
                       for m in lab.repo().memberships(OWNER)), "Adapter cannot read canonical seed"
        yield lab
    finally:
        lab.close()


def _new_scope(engine, uid=OWNER, organization=None):
    scope = Scope(organization_id=organization or str(uuid4()), collection_id=str(uuid4()))
    org = "" if organization else f'organization_insert(data:{{id:"{scope.organization_id}",name:"V3 synthetic museum"}})'
    org_member = "" if organization else f'organizationMember_insert(data:{{organizationId:"{scope.organization_id}",uid:"{uid}",active:true}})'
    engine.raw(f'''mutation @transaction {{
      {org}
      collection_insert(data:{{organizationId:"{scope.organization_id}",id:"{scope.collection_id}",name:"V3 synthetic collection"}})
      {org_member}
      collectionMember_insert(data:{{{_scope_key(scope)},uid:"{uid}",active:true,role:"reviewer",canViewSensitive:true}})
    }}''')
    return scope


def _principal(scope, uid=OWNER):
    return Principal(user_id=uid, scope=scope, role="reviewer")


def _specimen(scope, blobs, uid=OWNER):
    # A valid synthetic PNG with a unique trailing nonce avoids checksum collisions.
    raw = synthetic_image() + uuid4().bytes
    checksum = blobs.put(raw)
    return Specimen(
        scope=scope,
        asset=Asset(sha256=checksum, blob_ref=checksum, sensitive=False, media_type="image/png",
                    size_bytes=len(raw), width=1000, height=520, filename="v3-synthetic.png", uploader=uid),
        run=Run(stage="pending"),
    )


def _variables(specimen, uid, key, expected=0):
    candidate = specimen.model_copy(deep=True)
    candidate.version = expected + 1
    payload = pack(candidate, None)
    variables = {
        "organizationId": specimen.scope.organization_id, "collectionId": specimen.scope.collection_id,
        "actorUid": uid, "id": specimen.id, "snapshot": payload, "snapshotSha256": digest(payload),
        "requestSha256": digest({"key": key}), "idempotencyKey": key,
        "operation": "save:" + specimen.id if expected else "create", "state": run_status(candidate.run),
        "sensitive": False, "contractVersion": "0.1", "workAvailableAt": work_available_at(candidate),
    }
    if expected:
        variables.update(expectedRevision=expected, activeRunId=candidate.run.id,
                         disposition=None, action="checkpoint_or_review")
    else:
        variables["sourceChecksum"] = candidate.asset.sha256
    return variables, candidate


def _base(scope, uid):
    return {"organizationId": scope.organization_id, "collectionId": scope.collection_id, "actorUid": uid}


def _assert_read(engine, specimen, uid=OWNER):
    scope = specimen.scope
    base = _base(scope, uid)
    with verified_actor_context(uid):
        fresh = engine.repo()
        assert fresh.get(scope, specimen.id) == specimen
        assert fresh.version(scope, specimen.id, specimen.version) == specimen
        assert specimen in fresh.list(scope)
    data = _ok(engine.op("GetSpecimen", dict(base, id=specimen.id)), "registered GetSpecimen positive control")
    assert data["specimen"]["revision"] == specimen.version
    assert Specimen.model_validate(data["specimenSnapshots"][0]["snapshot"]) == specimen
    row = _ok(engine.op("GetSnapshot", dict(base, id=specimen.id, revision=specimen.version)),
              "registered GetSnapshot positive control")["specimenSnapshot"]
    assert row["sha256"] == digest(row["snapshot"])
    assert Specimen.model_validate(row["snapshot"]) == specimen
    rows = _ok(engine.op("ListSpecimens", dict(base, limit=100, offset=0, includeSensitive=False)),
               "registered ListSpecimens positive control")["specimens"]
    assert any(_uuid(row["id"]) == _uuid(specimen.id) for row in rows)
    raw = engine.footprint(scope)
    snapshot = next(row for row in raw["specimenSnapshots"]
                    if _uuid(row["specimenId"]) == _uuid(specimen.id) and row["revision"] == specimen.version)
    assert snapshot["sha256"] == digest(snapshot["snapshot"])
    assert Specimen.model_validate(snapshot["snapshot"]) == specimen


def _assert_commit(before, after, specimen, uid, key, request_sha, expected):
    """Exactly one canonical transition and four matching append-only rows."""
    ident = _uuid(specimen.id)
    prior = [row for row in before["specimens"] if _uuid(row["id"]) == ident]
    current = [row for row in after["specimens"] if _uuid(row["id"]) == ident]
    assert len(prior) == (1 if expected else 0) and len(current) == 1
    assert current[0]["revision"] == expected + 1 == specimen.version
    assert current[0]["sensitive"] is False and current[0]["sourceChecksum"] == specimen.asset.sha256
    assert [row for row in before["specimens"] if _uuid(row["id"]) != ident] == [
        row for row in after["specimens"] if _uuid(row["id"]) != ident
    ], "Unrelated canonical row changed"
    if expected:
        mutable = {"revision", "state", "disposition", "activeRunId", "workAvailableAt", "updatedAt"}
        assert {k: v for k, v in prior[0].items() if k not in mutable} == {
            k: v for k, v in current[0].items() if k not in mutable
        }
    added = {}
    for table in TABLE_FIELDS.keys() - {"specimens"}:
        assert all(row in after[table] for row in before[table]), f"{table}: prior bytes changed"
        delta = [row for row in after[table] if row not in before[table]]
        assert len(after[table]) == len(before[table]) + 1 and len(delta) == 1, f"{table}: {delta}"
        added[table] = delta[0]
        assert _uuid(delta[0]["specimenId"]) == ident
        assert delta[0].get("revision", delta[0].get("aggregateRevision")) == expected + 1
    snapshot, receipt, audit, outbox = (added[table] for table in
        ("specimenSnapshots", "requestReceipts", "auditEvents", "outboxEvents"))
    assert Specimen.model_validate(snapshot["snapshot"]) == specimen
    assert snapshot["sha256"] == digest(snapshot["snapshot"])
    assert receipt["actorUid"] == audit["actorUid"] == uid
    assert receipt["idempotencyKey"] == key
    assert receipt["operation"] == ("save:" + specimen.id if expected else "create")
    assert receipt["requestSha256"] == audit["requestSha256"] == outbox["deduplicationKey"] == request_sha
    assert audit["action"] == ("checkpoint_or_review" if expected else "create")
    assert outbox["eventType"] == "specimen_committed"
    assert _uuid(outbox["payloadReferences"]["specimen_id"]) == ident


def _positive(engine, scope, uid=OWNER):
    repo = engine.repo()
    principal = _principal(scope, uid)
    before = engine.footprint(scope)
    key = "v3-create:" + str(uuid4())
    with verified_actor_context(uid):
        specimen = repo.create(principal, _specimen(scope, engine.blobs, uid), key, digest({"key": key}))
    assert any(body.get("operationName") == "CreateSpecimenV3" and body["variables"]["idempotencyKey"] == key
               for body, _ in repo.session.calls), "Adapter did not dispatch CreateSpecimenV3"
    after = engine.footprint(scope)
    _assert_commit(before, after, specimen, uid, key, digest({"key": key}), 0)
    return _save_positive(engine, specimen, uid, repo=repo)


def _save_positive(engine, specimen, uid=OWNER, repo=None):
    repo = repo or engine.repo()
    key = "v3-save:" + str(uuid4())
    candidate = specimen.model_copy(deep=True)
    candidate.run.dependencies["v3_contract"] = key
    before = engine.footprint(specimen.scope)
    with verified_actor_context(uid):
        saved = repo.save(_principal(specimen.scope, uid), candidate, specimen.version, key, digest({"key": key}))
    calls = [body for body, reply in repo.session.calls if body.get("operationName") == "SaveSpecimenV3"]
    assert any(body["variables"]["idempotencyKey"] == key for body in calls), "Adapter did not dispatch SaveSpecimenV3"
    _assert_commit(before, engine.footprint(specimen.scope), saved, uid, key, digest({"key": key}), specimen.version)
    receipt = _ok(engine.op("GetReceipt", dict(_base(specimen.scope, uid),
                  operation="save:" + specimen.id, idempotencyKey=key)), "registered GetReceipt positive control")["requestReceipt"]
    assert receipt["revision"] == saved.version and receipt["requestSha256"] == digest({"key": key})
    _assert_read(engine, saved, uid)
    return saved


def _direct_positive(engine, scope, uid):
    key = "direct-create:" + str(uuid4())
    variables, specimen = _variables(_specimen(scope, engine.blobs, uid), uid, key)
    before = engine.footprint(scope)
    _ok(engine.op("CreateSpecimenV3", variables, mutation=True), "registered V3 create positive control")
    _assert_commit(before, engine.footprint(scope), specimen, uid, key, variables["requestSha256"], 0)
    key = "direct-save:" + str(uuid4())
    variables, saved = _variables(specimen, uid, key, specimen.version)
    before = engine.footprint(scope)
    _ok(engine.op("SaveSpecimenV3", variables, mutation=True), "registered V3 save positive control")
    _assert_commit(before, engine.footprint(scope), saved, uid, key, variables["requestSha256"], specimen.version)
    _assert_read(engine, saved, uid)
    return saved


def _actor_memberships(engine, uid):
    """Independent admin rows for Memberships' actor and active predicates."""
    # operations.gql:70-73 selects these fields, only active rows for actorUid,
    # independently for organizations and collections (no organization join).
    data = engine.raw(f'''query {{
      organizationMembers(where:{{uid:{{eq:{_json(uid)}}}}},limit:1000) {{ uid organizationId active }}
      collectionMembers(where:{{uid:{{eq:{_json(uid)}}}}},limit:1000) {{ uid organizationId collectionId role canViewSensitive active }}
    }}''')
    expected = {}
    for table, rows in data.items():
        assert len(rows) < 1000, f"{table}: actor membership oracle was truncated"
        assert all(row["uid"] == uid and type(row["active"]) is bool for row in rows), rows
        expected[table] = [{key: value for key, value in row.items() if key != "uid"}
                           for row in rows if row["active"]]
    return expected


def _assert_actor_memberships(reply, expected, scope):
    """Success here may contain only the requesting actor's active memberships."""
    label = "adapter list actor memberships"
    data = _ok(reply, label)
    assert data.keys() == expected.keys() == {"organizationMembers", "collectionMembers"}, (
        f"{label}: unexpected selected fields: {data}"
    )
    for table, rows in data.items():
        assert isinstance(rows, list) and all(isinstance(row, dict) for row in rows), (
            f"{label}: malformed {table}: {rows}"
        )
        assert _json(sorted(rows, key=_json)) == _json(sorted(expected[table], key=_json)), (
            f"{label}: {table} differs from the actor's active admin rows: {rows}; expected {expected[table]}"
        )
    # A collection membership may still be active after organization revocation;
    # memberships() requires both. The refused scope must have no effective grant.
    organizations = {_uuid(row["organizationId"]) for row in data["organizationMembers"]}
    assert not any(_uuid(row["organizationId"]) == _uuid(scope.organization_id)
                   and _uuid(row["collectionId"]) == _uuid(scope.collection_id)
                   and _uuid(row["organizationId"]) in organizations
                   for row in data["collectionMembers"]), f"{label}: refused scope has an active grant"


def _assert_adapter_denials(attempts, label, scope, uid, member, memberships):
    # production.py: get/version stop at their first scoped read; create/save
    # stop at GetReceipt. list first reads actor memberships, then the scoped page.
    operations = {
        "get": ("GetSpecimen",), "snapshot": ("GetSnapshot",),
        "list": ("Memberships", "ListSpecimenPage"),
        "create": ("GetReceipt",), "save": ("GetReceipt",),
    }
    assert tuple(body["operationName"] for body, _ in attempts) == operations[label], (
        f"Adapter {label} did not reach the expected connector checks: {attempts}"
    )
    for body, reply in attempts:
        if body["operationName"] == "Memberships":
            assert body["variables"] == {"actorUid": uid}, body
            _assert_actor_memberships(reply, memberships, scope)
        else:
            assert all(body["variables"][key] == value for key, value in _base(scope, uid).items()), body
            _denied(reply, body["operationName"], f"adapter {label} foreign/revoked membership", member=member)


def _deny_scope(engine, specimen, uid, member):
    """Adapter guards and registered operations are separately exercised."""
    scope = specimen.scope
    principal = _principal(scope, uid)  # Matching actor/scope passes adapter's local precheck.
    candidate = _specimen(scope, engine.blobs, uid)
    before = engine.footprint(scope)
    repo = engine.repo()
    memberships = _actor_memberships(engine, uid)
    with verified_actor_context(uid):
        for label, call in (
            ("get", lambda: repo.get(scope, specimen.id)),
            ("snapshot", lambda: repo.version(scope, specimen.id, specimen.version)),
            ("list", lambda: repo.list(scope)),
            ("create", lambda: repo.create(principal, candidate, "denied-create:" + candidate.id, digest({"id": candidate.id}))),
            ("save", lambda: repo.save(principal, specimen, specimen.version, "denied-save:" + str(uuid4()), digest({"save": specimen.id}))),
        ):
            first_call = len(repo.session.calls)
            with pytest.raises((Conflict, PermissionError), match="SQL Connect"):
                call()
            attempts = repo.session.calls[first_call:]
            _assert_adapter_denials(attempts, label, scope, uid, member, memberships)
            assert engine.footprint(scope) == before, f"Adapter {label} denial changed rows"
    base = _base(scope, uid)
    for operation, variables in (
        ("GetSpecimen", dict(base, id=specimen.id)),
        ("GetSnapshot", dict(base, id=specimen.id, revision=specimen.version)),
        ("ListSpecimens", dict(base, limit=100, offset=0, includeSensitive=False)),
        ("GetReceipt", dict(base, operation="save:" + specimen.id, idempotencyKey="absent:" + str(uuid4()))),
    ):
        _denied(engine.op(operation, variables), operation,
                f"registered {operation} foreign/revoked membership", member=member)
        assert engine.footprint(scope) == before, f"{operation} denial changed rows"
    for operation, target, expected in (("CreateSpecimenV3", candidate, 0), ("SaveSpecimenV3", specimen, specimen.version)):
        variables, _ = _variables(target, uid, "denied-direct:" + str(uuid4()), expected)
        _denied(engine.op(operation, variables, mutation=True), operation,
                f"registered {operation} foreign/revoked membership", member=member)
        assert engine.footprint(scope) == before, f"{operation} denial changed canonical/snapshot/receipt/audit/outbox"


@pytest.mark.parametrize("case", ["foreign_actor", "foreign_organization", "foreign_collection"])
def test_v3_read_write_scope_denial(engine, case):
    own = _new_scope(engine)
    other_uid = "synthetic-foreign-" + uuid4().hex
    foreign_org = _new_scope(engine, other_uid)
    foreign_collection = _new_scope(engine, other_uid, organization=own.organization_id)
    # The sibling collection's rightful actor is also an active organization member.
    engine.raw(f'''mutation {{ organizationMember_insert(data:{{organizationId:"{own.organization_id}",uid:"{other_uid}",active:true}}) }}''')
    owned = _positive(engine, own)
    org_owned = _positive(engine, foreign_org, other_uid)
    collection_owned = _positive(engine, foreign_collection, other_uid)
    target, intruder, rightful = {
        "foreign_actor": (owned, other_uid, OWNER),
        "foreign_organization": (org_owned, OWNER, other_uid),
        "foreign_collection": (collection_owned, OWNER, other_uid),
    }[case]
    _direct_positive(engine, target.scope, rightful)
    member = "organizationMember" if case == "foreign_organization" else "collectionMember"
    _deny_scope(engine, target, intruder, member)
    _assert_read(engine, target, rightful)
    # Correct variables/ordinary snapshots isolate NO_ACCESS from membership and sensitivity.
    before = engine.footprint(target.scope)
    for client, impersonate in (("authenticated", {"authClaims": {"sub": rightful}}),
                                ("anonymous", {"unauthenticated": True})):
        for name, specimen, expected in (
            ("CreateSpecimenV3", _specimen(target.scope, engine.blobs, rightful), 0),
            ("SaveSpecimenV3", target, target.version),
        ):
            variables, _ = _variables(specimen, rightful, "client-denied:" + str(uuid4()), expected)
            _denied(engine.op(name, variables, mutation=True, impersonate=impersonate), name,
                    f"NO_ACCESS {name} {impersonate}", client=client)
            assert engine.footprint(target.scope) == before, "Client refusal changed rows"
    _save_positive(engine, target, rightful)


def test_v3_cas_has_one_winner_and_one_receipt(engine):
    scope = _new_scope(engine)
    specimen = _positive(engine, scope)
    before = engine.footprint(scope)
    repos = [engine.repo(), engine.repo()]
    assert repos[0] is not repos[1] and repos[0].session is not repos[1].session
    with verified_actor_context(OWNER):
        saved = [repo.get(scope, specimen.id) for repo in repos]
    assert saved[0] == saved[1] == specimen
    expected = specimen.version
    keys = ["cas:" + str(uuid4()), "cas:" + str(uuid4())]
    gate = Barrier(2)
    for repo in repos:
        repo.session.save_barrier = gate

    def writer(index):
        previous_actor = actor_uid.get()
        try:
            with verified_actor_context(OWNER):
                candidate = saved[index].model_copy(deep=True)
                candidate.run.dependencies["logical_writer"] = keys[index]
                try:
                    result = repos[index].save(_principal(scope), candidate, expected, keys[index], digest({"key": keys[index]}))
                except Conflict:
                    return "conflict", None
                return "success", result
        finally:
            assert actor_uid.get() == previous_actor, "Worker actor ContextVar leaked"
            repos[index].session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(writer, index) for index in range(2)]
        results = [future.result(timeout=90) for future in futures]
    assert sorted(kind for kind, _ in results) == ["conflict", "success"], (
        f"CAS requires exactly one logical winner and one Conflict, got {results}"
    )
    winner = next(index for index, (kind, _) in enumerate(results) if kind == "success")
    loser = 1 - winner
    for index, repo in enumerate(repos):
        attempts = [(body, reply) for body, reply in repo.session.calls
                    if body.get("operationName") == "SaveSpecimenV3"]
        assert len(attempts) == 1, f"Logical writer {index} retried/rebased V3: {attempts}"
        assert attempts[0][0]["variables"]["expectedRevision"] == expected
        assert attempts[0][0]["variables"]["actorUid"] == OWNER
        assert attempts[0][0]["variables"]["idempotencyKey"] == keys[index]
        if index == loser:
            assert attempts[0][1][0] == 200 and attempts[0][1][1].get("errors"), "Loser failed before connector CAS"
    after = engine.footprint(scope)
    committed = results[winner][1]
    assert committed.run.dependencies["logical_writer"] == keys[winner]
    _assert_commit(before, after, committed, OWNER, keys[winner], digest({"key": keys[winner]}), expected)
    assert not any(row["idempotencyKey"] == keys[loser] for row in after["requestReceipts"]), "Loser receipt leaked"
    _assert_read(engine, committed)  # New adapter/session plus independent synthetic-admin snapshot.


@contextmanager
def _outbox_poison(engine, specimen):
    scope, poison_id = specimen.scope, str(uuid4())
    before = engine.footprint(scope)
    engine.raw(f'''mutation {{ outboxEvent_insert(data:{{{_scope_key(scope)},id:"{poison_id}",
      specimenId:"{specimen.id}",aggregateRevision:{specimen.version + 1},eventType:"v3_test_poison",
      deduplicationKey:"{poison_id}",payloadReferences:{{test_poison:"{poison_id}"}}}}) }}''')
    try:
        poisoned = engine.footprint(scope)
        assert all(poisoned[table] == before[table] for table in TABLE_FIELDS.keys() - {"outboxEvents"})
        assert len(poisoned["outboxEvents"]) == len(before["outboxEvents"]) + 1
        assert all(row in poisoned["outboxEvents"] for row in before["outboxEvents"])
        yield poisoned
    finally:
        # Delete exactly this test's poison; never erase a failed write's leaked effects.
        at_cleanup = engine.footprint(scope)
        engine.raw(f'''mutation {{ outboxEvent_delete(key:{{{_scope_key(scope)},id:"{poison_id}"}}) }}''')
        cleaned = engine.footprint(scope)
        expected = {**at_cleanup, "outboxEvents": [row for row in at_cleanup["outboxEvents"] if _uuid(row["id"]) != _uuid(poison_id)]}
        assert cleaned == expected, "Poison teardown removed unrelated data or failed to remove poison"
        with verified_actor_context(OWNER):
            current = engine.repo().get(scope, specimen.id)
        _save_positive(engine, current)  # Always prove the unpoisoned transaction, also on assertion failure.


def test_v3_failed_write_rolls_back_snapshot_receipt_audit_outbox(engine):
    scope = _new_scope(engine)
    specimen = _positive(engine, scope)
    repo = engine.repo()
    key = "must-rollback:" + str(uuid4())
    candidate = specimen.model_copy(deep=True)
    candidate.run.dependencies["failed_write"] = key
    with _outbox_poison(engine, specimen) as before:
        with verified_actor_context(OWNER), pytest.raises(Conflict, match="SQL Connect transaction rejected"):
            repo.save(_principal(scope), candidate, specimen.version, key, digest({"key": key}))
        attempts = [(body, reply) for body, reply in repo.session.calls if body.get("operationName") == "SaveSpecimenV3"]
        assert len(attempts) == 1, "Rollback did not reach registered V3 save exactly once"
        body, reply = attempts[0]
        assert body["variables"]["expectedRevision"] == specimen.version
        assert reply[0] == 200 and reply[1].get("errors"), reply
        assert "specimen_unique_4" in _json(reply[1]), (
            f"Expected next-revision outbox uniqueness failure after snapshot/receipt insertion: {reply}"
        )
        after = engine.footprint(scope)
        assert after["requestReceipts"] == before["requestReceipts"], "Failed V3 transaction leaked a receipt"
        assert not any(row["idempotencyKey"] == key for row in after["requestReceipts"]), "Failed key persisted"
        assert after == before, "Failed V3 save changed canonical/snapshot/receipt/audit/outbox, including poison"
        _assert_read(engine, specimen)


@contextmanager
def _revoked(engine, specimen, table):
    scope = specimen.scope
    original = engine.members(scope)
    key = f'organizationId:"{scope.organization_id}",uid:"{OWNER}"' if table == "organizationMember" else f'{_scope_key(scope)},uid:"{OWNER}"'
    try:
        engine.raw(f"mutation {{ {table}_update(key:{{{key}}},data:{{active:false}}) }}")
        changed = engine.members(scope)
        assert changed[table] == {**original[table], "active": False}
        other = "collectionMember" if table == "organizationMember" else "organizationMember"
        assert changed[other] == original[other], "Revocation changed the other membership"
        yield
    finally:
        row = original[table]
        fields = ",".join(f"{name}:{_json(value)}" for name, value in row.items())
        engine.raw(f"mutation {{ {table}_upsert(data:{{{fields}}}) }}")
        assert engine.members(scope) == original, "Teardown did not restore the exact synthetic membership"
        with verified_actor_context(OWNER):
            current = engine.repo().get(scope, specimen.id)
        _save_positive(engine, current)


def test_v3_revocation_blocks_read_write(engine):
    scope = _new_scope(engine)
    specimen = _positive(engine, scope)
    _direct_positive(engine, scope, OWNER)
    for table in ("organizationMember", "collectionMember"):
        with _revoked(engine, specimen, table):
            _deny_scope(engine, specimen, OWNER, table)
        # The restoration positive control committed a new revision.
        with verified_actor_context(OWNER):
            specimen = engine.repo().get(scope, specimen.id)
        _assert_read(engine, specimen)
