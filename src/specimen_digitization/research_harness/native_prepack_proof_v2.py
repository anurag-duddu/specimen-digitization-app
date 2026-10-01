"""Lossless, versioned pure-policy/prepack/packed receipt proof.

This does not normalize away metadata. Original active_graph metadata is retained
in two immutable prepack bodies; only the declared pack replacement is applied
when comparing the actual repository-rehydrated graph. Old missing proofs HOLD.
"""
from __future__ import annotations

import copy
import json
from typing import Mapping

from specimen_digitization.application.storage import digest as graph_digest
from .contracts import digest
from .native_canonical import fail

PROOF_VERSION = "research-prepack-proof/v2"
_KEYS = {"contract_version", "policy_graph_json", "policy_graph_digest",
         "post_audit_graph_json", "post_audit_graph_digest", "packing_metadata",
         "packed_snapshot_digest"}


def _decode(text):
    if type(text) is not str or len(text.encode("utf-8")) > 16 * 1024 * 1024:
        fail("native_v2_prepack_body_unavailable")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("native_v2_prepack_duplicate_key")
            result[key] = value
        return result
    def reject(_):
        fail("native_v2_prepack_nonfinite")
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, TypeError):
        fail("native_v2_prepack_body_unavailable")
    if not isinstance(value, dict):
        fail("native_v2_prepack_body_unavailable")
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _types_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_types_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_types_equal(a, b) for a, b in zip(left, right))
    return left == right


def _audit_transition(policy, post, *, audit_id, actor_uid, operation_digest, resulting_revision, native_record_version_id):
    before = policy.get("audit")
    after = post.get("audit")
    if (not isinstance(before, list) or not isinstance(after, list)
            or len(after) != len(before) + 1 or not _types_equal(before, after[:-1])):
        fail("native_v2_prepack_audit_unproved")
    own = after[-1]
    if (not isinstance(own, dict) or own.get("id") != str(audit_id)
            or own.get("actor") != actor_uid or own.get("action") != "research_publication"
            or own.get("reason") != operation_digest
            or own.get("before") != {"revision": resulting_revision - 1}
            or own.get("after") != {"revision": resulting_revision, "record_version_id": str(native_record_version_id)}):
        fail("native_v2_prepack_audit_unproved")
    expected = copy.deepcopy(policy)
    expected["audit"] = copy.deepcopy(after)
    if not _types_equal(expected, post):
        fail("native_v2_prepack_unauthorized_delta")


def make_prepack_proof_v2(policy_graph, post_audit_graph, packed_snapshot, *, progress,
                          audit_id, actor_uid, operation_digest, native_record_version_id):
    policy = policy_graph.model_dump(mode="json")
    post = post_audit_graph.model_dump(mode="json")
    _audit_transition(policy, post, audit_id=audit_id, actor_uid=actor_uid,
                      operation_digest=operation_digest, resulting_revision=post_audit_graph.version,
                      native_record_version_id=native_record_version_id)
    if (graph_digest(policy) != progress.result_digest
            or policy_graph.run.stage != progress.run_stage
            or str(policy_graph.run.disposition) != progress.disposition):
        fail("native_v2_prepack_policy_unproved")
    return {"contract_version": PROOF_VERSION,
            "policy_graph_json": _json(policy), "policy_graph_digest": graph_digest(policy),
            "post_audit_graph_json": _json(post), "post_audit_graph_digest": graph_digest(post),
            "packing_metadata": copy.deepcopy(packed_snapshot.get("active_graph")),
            "packed_snapshot_digest": graph_digest(packed_snapshot)}


def verify_prepack_proof_v2(proof, *, expected_digest, retained, packed_snapshot,
                            progress, audit_id, actor_uid, operation_digest, native_record_version_id):
    if (not isinstance(proof, Mapping) or set(proof) != _KEYS
            or proof["contract_version"] != PROOF_VERSION or digest(dict(proof)) != expected_digest):
        fail("native_v2_prepack_proof_unavailable")
    policy = _decode(proof["policy_graph_json"])
    post = _decode(proof["post_audit_graph_json"])
    if (graph_digest(policy) != proof["policy_graph_digest"]
            or graph_digest(post) != proof["post_audit_graph_digest"]
            or proof["policy_graph_digest"] != progress.result_digest
            or graph_digest(packed_snapshot) != proof["packed_snapshot_digest"]
            or not _types_equal(proof["packing_metadata"], packed_snapshot.get("active_graph"))):
        fail("native_v2_prepack_digest_unproved")
    _audit_transition(policy, post, audit_id=audit_id, actor_uid=actor_uid,
                      operation_digest=operation_digest, resulting_revision=retained.version,
                      native_record_version_id=native_record_version_id)
    # Ordinary pack intentionally replaces this one field even for an already
    # externally stored graph. The prior value remains in post_audit_graph_json.
    expected = copy.deepcopy(post)
    expected["active_graph"] = copy.deepcopy(proof["packing_metadata"])
    if (not _types_equal(expected, retained.model_dump(mode="json"))
            or retained.run.stage != progress.run_stage
            or str(retained.run.disposition) != progress.disposition):
        fail("native_v2_prepack_rehydrated_graph_unproved")
    return policy
