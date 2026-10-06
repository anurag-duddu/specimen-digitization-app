"""Offline correction of GBIF arguments before any durable source effect.

Synthetic SQLite ledgers and fixture bytes only. Retained live journals are
neither fixtures nor copied into this file, and existing holds are never settled.
"""
from __future__ import annotations

import asyncio
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from specimen_digitization.research_harness.contracts import FieldKey, LookupStatus, SourceCoverageState
from specimen_digitization.research_harness.persistence import BlobRef, HeldUnknown
from specimen_digitization.research_harness.source_capture_v2 import CaptureSourceBrokerV2
from specimen_digitization.research_harness.sources import (
    FixtureSourceTransport, SourceRegistry, canonical_json,
)

from test_source_capture_v2 import make_capture_rig, saved_envelope


INVALID_QUERY = "sp. 30"
INVALID_QUERY_SHA256 = "c244cbf48683c5c728ec5c7f4f8a465d05ccb82b2f2d290e3f5824ecff6eb05d"  # pragma: allowlist secret (known input digest)


def gbif_rig(tmp_path):
    rig = make_capture_rig(tmp_path, source_id="gbif")

    async def read(url, policy):
        rig.calls.append(url)
        # A valid bounded GBIF response proving no match, without inventing a
        # candidate or pretending a successful match is needed for a receipt.
        body = canonical_json({"diagnostics": {"matchType": "NONE"}}).encode()
        rig.bodies.append(body)
        return 200, body

    rig.transport = FixtureSourceTransport(read)
    rig.broker = CaptureSourceBrokerV2(rig.registry, {rig.source.id: rig.policy}, rig.effects,
        rig.durable_scope, rig.lease, transport=rig.transport, execution_class="offline")
    return rig


def invoke_query(rig):
    return asyncio.run(rig.broker.query_source(rig.request, rig.query))


def assert_actionable_preflight_result(result):
    assert result.status == LookupStatus.POLICY
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert result.receipt is None and result.evidence == () and result.candidate_json == ()
    reason = result.coverage.reason
    assert len(reason) <= 256 and INVALID_QUERY not in reason
    for instruction in ("actual genus", "full scientific name", "specimen evidence",
                        "do not invent", "abstain", "waiting_policy", "unresolved",
                        "declared missing-policy rule"):
        assert instruction in reason


def trace_effect_transitions(rig, monkeypatch):
    transitions = []
    for name in ("reserve_effect", "mark_sending"):
        original = getattr(rig.store, name)

        def recorded(*args, _name=name, _original=original, **kwargs):
            transitions.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(rig.store, name, recorded)
    return transitions


def test_genusless_gbif_query_is_correctable_before_reservation_or_send(
        tmp_path, monkeypatch):
    rig = gbif_rig(tmp_path)
    rig.query = rig.query.model_copy(update={"query_text": INVALID_QUERY})
    assert hashlib.sha256(rig.query.query_text.encode()).hexdigest() == INVALID_QUERY_SHA256
    before = rig.store._read(rig.durable_scope).state
    transitions = trace_effect_transitions(rig, monkeypatch)

    result = invoke_query(rig)
    assert_actionable_preflight_result(result)
    assert rig.calls == [] and transitions == []
    assert rig.store._read(rig.durable_scope).state == before
    assert rig.broker.broker.trusted_results == []
    assert rig.broker.effects.reservation_micro_usd == 1


@pytest.mark.parametrize("name,rank", [("Danaus", "GENUS"), ("Danaus plexippus", "SPECIES")])
def test_valid_genus_or_full_name_keeps_real_capture_and_strict_receipt(
        tmp_path, monkeypatch, name, rank):
    rig = gbif_rig(tmp_path)
    rig.query = rig.query.model_copy(update={"query_text": name})
    before_policy = rig.store._read(rig.durable_scope).state["budget_policy"]
    transitions = trace_effect_transitions(rig, monkeypatch)
    result = invoke_query(rig)

    assert result.status == LookupStatus.NO_MATCH
    assert transitions == ["reserve_effect", "mark_sending"] and len(rig.calls) == 1
    params = parse_qs(urlparse(rig.calls[0]).query)
    assert params["scientificName"] == [name] and params["taxonRank"] == [rank]
    effect, envelope = saved_envelope(rig, result)
    assert effect["status"] == "completed" and effect["held_micro_usd"] == 0
    assert effect["actual_micro_usd"] == 0 and len(effect["attempts"]) == 1
    assert result.receipt.scope == rig.request.scope
    assert envelope.original_request == rig.request and envelope.query == rig.query
    assert len(envelope.responses) == 1
    captured = envelope.responses[0]
    assert rig.blobs.get(BlobRef(**captured.body.model_dump())) == rig.bodies[0]
    assert captured.response_fingerprint == result.evidence[0].response_digest
    assert captured.source_policy_digest == rig.policy.source_policy_digest
    assert rig.store._read(rig.durable_scope).state["budget_policy"] == before_policy


def test_invalid_argument_preserves_a_prior_unknown_hold_and_correction_cannot_bypass_it(
        tmp_path, monkeypatch):
    rig = gbif_rig(tmp_path)
    # This is a separate synthetic historical effect. Marking a send intent is
    # deliberately not evidence of a provider request or a captured response.
    prior = rig.store.reserve_effect(rig.durable_scope, rig.lease, "synthetic-prior-source",
        {"synthetic": "prior request"}, 1, execution_class="offline", field_keys=("taxon",))
    rig.store.mark_sending(rig.durable_scope, rig.lease, prior["effect_id"])
    rig.store.hold_unknown(rig.durable_scope, prior["effect_id"], "synthetic-retained-unknown")
    before = rig.store._read(rig.durable_scope).state
    transitions = trace_effect_transitions(rig, monkeypatch)
    rig.query = rig.query.model_copy(update={"query_text": INVALID_QUERY})

    assert_actionable_preflight_result(invoke_query(rig))

    assert rig.store._read(rig.durable_scope).state == before
    assert rig.calls == [] and transitions == []
    retained = rig.store.effect(rig.durable_scope, prior["effect_id"])
    assert retained["status"] == "held_unknown" and retained["held_micro_usd"] == 1
    assert retained["actual_micro_usd"] is None and retained["receipt"] is None

    rig.query = rig.query.model_copy(update={"query_text": "Danaus plexippus"})
    with pytest.raises(HeldUnknown):
        invoke_query(rig)
    assert rig.store._read(rig.durable_scope).state == before
    assert rig.calls == [] and transitions == []


@pytest.mark.parametrize("guard", ["field_scope", "sensitive", "source_qualification"])
def test_invalid_argument_correction_keeps_prior_source_admission_guards(
        tmp_path, monkeypatch, guard):
    rig = gbif_rig(tmp_path)
    rig.query = rig.query.model_copy(update={"query_text": INVALID_QUERY})
    if guard == "field_scope":
        rig.query = rig.query.model_copy(update={"field_key": FieldKey.COLLECTORS})
    elif guard == "sensitive":
        rig.request = rig.request.model_copy(update={
            "scope": rig.scope.model_copy(update={"sensitive": True})})
    else:
        # Keep a correctly pinned registry for this synthetic request while
        # retaining GBIF's established unqualified policy behavior.
        registry = SourceRegistry(tuple(
            policy.model_copy(update={"qualification_state": SourceCoverageState.UNQUALIFIED})
            if policy.id == "gbif" else policy for policy in rig.registry.policies))
        rig.broker.broker.registry = registry
        rig.request = rig.request.model_copy(update={
            "prompt": rig.request.prompt.model_copy(update={"source_registry_digest": registry.digest})})
    before = rig.store._read(rig.durable_scope).state
    transitions = trace_effect_transitions(rig, monkeypatch)

    if guard == "field_scope":
        with pytest.raises(ValueError, match="escaped specialist field scope"):
            invoke_query(rig)
    else:
        result = invoke_query(rig)
        assert result.status == LookupStatus.POLICY
        assert result.coverage.state == SourceCoverageState.UNQUALIFIED
        assert result.receipt is None and "actual genus" not in result.coverage.reason
        assert INVALID_QUERY not in result.coverage.reason
    assert rig.calls == [] and transitions == []
    assert rig.store._read(rig.durable_scope).state == before
