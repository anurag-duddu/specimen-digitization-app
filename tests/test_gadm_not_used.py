"""GADM is not used, not even as a measurement (PLAN 4.8): no source, no wiring,
no request. The coordinator's licence ruling of 2026-09-25 removes the GBIF GADM
geography adapter; until the harness's geography tool lands, place fields get no
geography authority and go to review."""

import json
import re

# ruff: noqa: F811 -- pytest fixture injection shares the imported fixture name
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr
from test_application import client, intake
from test_authority_registry import authority_server, source  # noqa: F401
from test_parties import payload

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.authority_registry import AuthorityRegistry
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.domain import Principal, Profile, Run, Scope
from specimen_digitization.application.evidence_runtime import plan_authorities
from specimen_digitization.application.parties import PartiesAdapter, PartiesConnection
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow

SOURCE = Path(__file__).resolve().parents[1] / "src" / "specimen_digitization"
# The forms of GADM's and GBIF's geocoder names the reviews of #216 listed. A bare
# "GADM" is left out on purpose: the comments that say it is not used name it.
GADM = re.compile(
    r"gbif[_-]gadm|gadm_search|geocode/(gadm|reverse)|api\.gbif\.org/v1/geocode"
    r"|gadm\.org|ucdavis\.edu/(data/)?gadm|gadm\d",
    re.I,
)
OLD_PIN = {
    "version": "gbif-gadm-1",
    "registry_sha256": "0" * 64,
    "connection_sha256": None,
    "reserved_cost_microunits": 0,
}


def test_production_wiring_holds_no_gadm_source(tmp_path):
    adapters = ProductionAdapters(LocalBlobs(tmp_path))

    assert set(adapters.authority_tools) == {"parties"}
    assert "geography" not in adapters.authority_cost_reservations
    assert all(
        tool.operation != "gadm_search" for tool in adapters.authority_tools.values()
    )
    assert "geography" not in Workflow(None, adapters.blobs, adapters).authority_pins()


def test_no_code_path_names_the_gadm_source_or_its_endpoint():
    modules = sorted(SOURCE.rglob("*.py"))

    assert modules
    assert not (SOURCE / "application" / "geography.py").exists()
    for module in modules:
        assert not GADM.search(module.read_text()), module


def test_a_profile_naming_geography_plans_no_geography_lookup():
    run = Run(
        profile=Profile(synthetic=True),
        profile_snapshot={"tools": ("taxonomy_verifier", "geography")},
    )

    assert plan_authorities(SimpleNamespace(run=run)) == []


def at_the_first_authority_step(tmp_path, authority_server):
    """A synthetic run with the parties tool, pinned and planned, stopped before
    its first authority step."""
    state, http = authority_server
    state["body"] = json.dumps(payload(name="Synthetic Collector")).encode()
    blobs = LocalBlobs(tmp_path / "blobs")
    parties = PartiesAdapter(
        AuthorityRegistry(
            version="synthetic-source-registry",
            sources=(source(True, scopes=((SYNTHETIC_ORG, SYNTHETIC_COLLECTION),)),),
        ),
        blobs,
        PartiesConnection(
            source_id="parties",
            source_system="emu",
            connection_id="synthetic-read",
            tenant="fmnh",
            environment="synthetic",
        ),
        SecretStr("synthetic-token"),
        http,
    )
    profiles = application_registry(True)
    profiles = profiles.model_copy(
        update={
            "profiles": (
                profiles.profiles[0].model_copy(
                    update={
                        "tools": ("taxonomy_verifier", "parties"),
                        "data_sources": ("gbif-col-xr", "parties"),
                    }
                ),
            )
        }
    )
    text = SYNTHETIC_TEXT.replace("synthetic:eparties:1", "Synthetic Collector")
    row = intake(client(tmp_path))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": 1}))
    workflow = Workflow(
        repo,
        blobs,
        SyntheticAdapters(blobs, text),
        profile_registry=profiles,
        authority_tools={"parties": parties},
        authority_cost_reservations={"parties": 0},
    )
    for _ in range(40):
        specimen = repo.get(scope, specimen.id)
        if Workflow.next_step(specimen.run).startswith("authority:"):
            break
        workflow.step(principal, specimen.id)
    assert Workflow.next_step(specimen.run) == "authority:0:parties"
    return state, repo, workflow, principal, specimen


def test_a_run_pinned_with_the_removed_tool_still_resumes(tmp_path, authority_server):
    # S3's check: a run pinned before the removal holds a "geography" pin; each
    # authority step compares only its own tool's pin, so the run goes on.
    state, repo, workflow, principal, specimen = at_the_first_authority_step(
        tmp_path, authority_server
    )
    specimen.run.dependencies["authority_pins"]["geography"] = OLD_PIN
    repo.save(principal, specimen, specimen.version, "old-pin", digest({"old": 1}))

    run = workflow.drain(principal, specimen.id).run

    assert run.blocker != "authority_configuration_changed_requires_new_run"
    assert [r["state"] for r in run.authority_receipts.values()] == ["completed"]
    assert len(state["requests"]) == 1


def test_a_run_planned_with_the_removed_tool_blocks_without_a_request(
    tmp_path, authority_server
):
    # A plan made before the removal still names a "geography" task, put first
    # here. Its step finds no tool, so it blocks with a typed reason and sends no
    # request; in main's order, the parties step before it still runs.
    state, repo, workflow, principal, specimen = at_the_first_authority_step(
        tmp_path, authority_server
    )
    task = {"tool_id": "geography", "field_key": "province_state", "required": True}
    specimen.run.authority_plan = [task, *specimen.run.authority_plan]
    specimen.run.dependencies["authority_pins"]["geography"] = OLD_PIN
    repo.save(principal, specimen, specimen.version, "old-plan", digest({"old": 2}))

    run = workflow.drain(principal, specimen.id).run

    assert run.stage == "processing_blocked"
    assert run.blocker == "tool_not_allowlisted_or_version_mismatch"
    assert state["requests"] == []
