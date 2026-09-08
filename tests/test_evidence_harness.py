from test_authority_registry import authority_server as authority_server
import json

import pytest

from test_authority_registry import query
from test_geography import payload, service
from specimen_digitization.application.evidence_harness import (
    BudgetUsage,
    FieldProposal,
    HarnessRunner,
    HarnessSpec,
    PhaseInput,
    PhaseSpec,
    SourceLiteral,
    ToolCall,
    run_phase,
)


def spec(**changes):
    return HarnessSpec(
        profile_id="synthetic-insects",
        profile_version="1",
        phases=tuple(
            PhaseSpec(
                name=p,
                version="1",
                allowed_tools=("geography",) if p == "lookup" else (),
            )
            for p in (
                "parse",
                "plan",
                "lookup",
                "resolve",
                "normalize",
                "validate",
                "finalize",
            )
        ),
        **changes,
    )


def literal(**changes):
    values = dict(
        field_key="province_state",
        literal="Illinois",
        source_excerpt="Illinois 1900",
        asset_id="asset-1",
        region_id="region-1",
        observation_ids=("obs-1", "obs-2"),
        evidence_ids=("pixel-evidence-1",),
    )
    values.update(changes)
    return SourceLiteral(**values)


def test_all_phases_keep_candidates_and_meaningful_failed_gates(authority_server):
    state, client = authority_server
    state["body"] = json.dumps(payload()).encode()
    lookup = service(client)[0].lookup(
        query(historical_context="historical jurisdiction unknown")
    )
    parsed = run_phase(spec(), PhaseInput(phase="parse", literals=(literal(),)))
    assert parsed.proposals[0].candidate == "Illinois"
    enriched = run_phase(
        spec(),
        PhaseInput(
            phase="normalize",
            literals=(literal(),),
            lookups=(lookup,),
            proposals=parsed.proposals,
        ),
    )
    assert (
        len(enriched.proposals) == 2 and enriched.proposals[-1].relation == "unresolved"
    )
    resolved = run_phase(
        spec(), PhaseInput(phase="resolve", proposals=enriched.proposals)
    )
    assert resolved.findings[0].code == "candidate_resolution_requires_review"
    for phase in ("validate", "finalize"):
        result = run_phase(
            spec(),
            PhaseInput(
                phase=phase,
                proposals=enriched.proposals,
                required_fields=("province_state", "identified_by_irn"),
            ),
        )
        assert {f.code for f in result.findings} >= {
            "field_semantics_unconfirmed",
            "mandatory_evidence_unresolved",
        }
        assert "disposition" not in result.model_dump()
    assert (
        run_phase(spec(), PhaseInput(phase="lookup")).findings[0].code
        == "lookup_evidence_missing"
    )
    assert (
        run_phase(spec(), PhaseInput(phase="plan")).reason
        == "no_external_tools_configured"
    )


def test_source_provenance_and_input_output_digests_replay():
    inputs = PhaseInput(
        phase="parse", literals=(literal(), literal(literal="invented"))
    )
    first = run_phase(spec(), inputs)
    assert len(first.proposals) == 1 and first.proposals[0].evidence_ids == (
        "pixel-evidence-1",
    )
    assert first.findings[0].code == "literal_not_in_source_excerpt"
    assert run_phase(spec(), inputs).model_dump() == first.model_dump()
    assert (
        first.input_sha256
        != run_phase(
            spec(), PhaseInput(phase="parse", literals=(literal(),))
        ).input_sha256
    )


def test_applicability_missing_phase_and_budget_are_explicit():
    empty = HarnessSpec(profile_id="x", profile_version="1", phases=())
    assert run_phase(empty, PhaseInput(phase="validate")).applicability == "blocked"
    exempt = empty.model_copy(
        update={
            "phases": (
                PhaseSpec(
                    name="lookup",
                    version="1",
                    not_applicable_reason="No authority fields in synthetic profile",
                ),
            )
        }
    )
    assert (
        run_phase(exempt, PhaseInput(phase="lookup")).applicability == "not_applicable"
    )
    assert (
        run_phase(
            spec(), PhaseInput(phase="parse", usage=BudgetUsage(elapsed_seconds=120))
        ).reason
        == "elapsed_budget_exhausted"
    )


def test_single_effect_checkpoint_and_replay_over_actual_http(authority_server):
    state, client = authority_server
    state["body"] = json.dumps(payload()).encode()
    adapter, _ = service(client)
    runner = HarnessRunner({"geography": adapter})
    call = ToolCall(
        call_id="call-1",
        phase="lookup",
        tool_id="geography",
        tool_version=adapter.version,
        reserved_cost_microunits=0,
    )
    saved = []
    result = runner.execute_one(spec(), call, query(), BudgetUsage(), saved.append)
    assert [r.state for r in saved] == ["intent", "completed"]
    assert result.usage.tool_calls == 1 and len(state["requests"]) == 1
    assert (
        runner.execute_one(spec(), call, query(), result.usage, saved.append, result)
        == result
    )
    assert len(state["requests"]) == 1
    unknown = runner.execute_one(
        spec(), call, query(), result.usage, saved.append, saved[0]
    )
    assert unknown.reason == "external_outcome_unknown" and len(state["requests"]) == 1
    with pytest.raises(ValueError):
        runner.execute_one(
            spec(),
            call,
            query(historical_context="changed"),
            result.usage,
            saved.append,
            result,
        )
    with pytest.raises(ValueError):
        runner.execute_one(
            spec(),
            call,
            query(),
            result.usage,
            saved.append,
            result.model_copy(update={"output_sha256": "tampered"}),
        )


def test_allowlist_cost_and_budget_prevent_effect_and_checkpoint_failure_does_not_call(
    authority_server,
):
    state, client = authority_server
    adapter, _ = service(client)
    runner = HarnessRunner({"geography": adapter})
    call = ToolCall(
        call_id="call",
        phase="lookup",
        tool_id="geography",
        tool_version=adapter.version,
        reserved_cost_microunits=0,
    )
    for changed, usage in (
        (call.model_copy(update={"tool_id": "shell"}), BudgetUsage()),
        (call.model_copy(update={"reserved_cost_microunits": None}), BudgetUsage()),
        (call, BudgetUsage(tool_calls=10)),
    ):
        assert (
            runner.execute_one(spec(), changed, query(), usage, lambda _: None).state
            == "blocked"
        )

    def broken_checkpoint(receipt):
        raise OSError("synthetic database unavailable")

    with pytest.raises(OSError):
        runner.execute_one(spec(), call, query(), BudgetUsage(), broken_checkpoint)
    assert not state["requests"]


def test_contradictory_normalized_sources_are_never_selected():
    proposals = tuple(
        FieldProposal(
            field_key="country",
            literal="Historical Country",
            candidate=value,
            relation=relation,
            evidence_ids=(evidence,),
            source_id=source_id,
            reason="source comparison",
        )
        for value, relation, evidence, source_id in (
            ("A", "supports", "e1", "s1"),
            ("B", "contradicts", "e2", "s2"),
        )
    )
    result = run_phase(spec(), PhaseInput(phase="resolve", proposals=proposals))
    assert result.proposals == proposals
    assert result.comparisons[0].relation == "contradicts"
    assert result.comparisons[0].evidence_ids == ("e1", "e2")
    assert result.findings[0].evidence_ids == ("e1", "e2")


def test_search_snippet_without_captured_authority_response_cannot_normalize(
    authority_server,
):
    state, client = authority_server
    state["body"] = json.dumps(payload()).encode()
    lookup = service(client)[0].lookup(query()).model_copy(update={"raw_ref": None})
    result = run_phase(
        spec(), PhaseInput(phase="normalize", literals=(literal(),), lookups=(lookup,))
    )
    assert not result.proposals
    assert result.findings[0].code == "authority_capture_missing"
