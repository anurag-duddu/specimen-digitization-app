"""Actual no-OS runtime and production capability composition, no external reads."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.research_harness.capability_providers import (
    BROWSER_ID, BROWSER_PIN, CODE_ID, CODE_PIN, MontyCodeExecutor, PublicHTTPBrowser,
    ReviewedMemory, ReviewedMemoryStore, build_capability_factory, committed_role_policies,
    reviewed_catalog,
)
from specimen_digitization.research_harness.contracts import SpecialistRole, digest
from specimen_digitization.research_harness.shared_capabilities import (
    BrowserSourceBinding, CodeRun, IsolatedCodePolicy, SharedResearchAdapters, SharedResearchCapability,
)
from test_shared_capabilities import make_rig, PAGE, BODY


def code_policy(**kw):
    return IsolatedCodePolicy(executor_id=CODE_ID, executor_registration_digest=CODE_PIN,
        isolation="monty_no_os", **kw)


def execute(code, inputs=None, **kw):
    return asyncio.run(MontyCodeExecutor(execution_class="offline").execute(code, inputs or {},
        policy=code_policy(**kw), idempotency_key="offline-probe"))


def test_actual_monty_executes_input_only_arithmetic():
    outcome = execute('inputs["feet"] * 0.3048', {"feet": 1000})
    assert outcome.exit_status == "completed" and outcome.value == 304.8
    assert outcome.executor_registration_digest == CODE_PIN


@pytest.mark.parametrize("code", ['open("/etc/passwd").read()',
    'import os\nos.environ["HOME"]', 'import subprocess\nsubprocess.run(["pwd"])',
    'import socket\nsocket.create_connection(("example.com",443))', 'while True:\n    pass'])
def test_actual_monty_cannot_read_host_run_commands_or_make_network_calls(code):
    assert execute(code, timeout_seconds=0.05).exit_status != "completed"


def test_monty_sessions_do_not_share_prior_specimen_variables():
    assert execute("secret=17\nsecret").value == 17
    assert execute("secret").exit_status == "invalid_code"


def test_public_browser_uses_bounded_source_transport_and_admits_navigation_first(tmp_path):
    rig = make_rig(tmp_path)
    calls=[]
    class Transport:
        async def get(self,url,*,policy):
            assert calls == [url]
            return 200,BODY
    browser=PublicHTTPBrowser(Transport(),execution_class="offline")
    page=asyncio.run(browser.capture(PAGE,policy=rig.adapters.registry.get("fixture_authority"),
        idempotency_key="fixture",authorize_navigation=calls.append))
    assert page.body == BODY and page.visited_urls == (PAGE,) and page.url == PAGE


def test_committed_role_policies_cover_exact_six_scoped_roles(tmp_path):
    rig=make_rig(tmp_path)
    from specimen_digitization.research_harness.contracts import CollectionProfile
    profile=CollectionProfile.model_validate(rig.store.job(rig.scope)["pins"]["profile"])
    policies=committed_role_policies(profile,rig.adapters.registry,rig.request.prompt.toolset_digest)
    assert set(policies) == {str(role) for role in SpecialistRole}
    assert all(item["execution_policy"] == "free_local_public_http" for item in policies.values())
    assert policies[str(rig.request.role)]["browser_sources"][0]["provider_id"] == BROWSER_ID


def test_production_factory_connects_actual_official_memory_skills_and_captured_tools(tmp_path):
    rig=make_rig(tmp_path)
    from specimen_digitization.research_harness.contracts import CollectionProfile
    profile=CollectionProfile.model_validate(rig.store.job(rig.scope)["pins"]["profile"])
    policies=committed_role_policies(profile,rig.adapters.registry,rig.request.prompt.toolset_digest)
    factory=build_capability_factory(broker=rig.broker,scope=rig.scope,lease=rig.adapters.lease,
        registry=rig.adapters.registry,source_pins={"role_capabilities":policies},
        transport=None,execution_class="offline")
    capabilities=factory(rig.request)
    from pydantic_ai_harness import Skills
    assert isinstance(capabilities[0],SharedResearchCapability)
    assert isinstance(capabilities[1],ReviewedMemory) and capabilities[1].get_toolset() is None
    assert isinstance(capabilities[2],Skills)
    seen=[]
    def respond(messages,info):
        seen.extend(messages)
        return ModelResponse([TextPart("Procedure context inspected")])
    agent=Agent(FunctionModel(respond),name=str(rig.request.role),capabilities=capabilities[1:])
    result=asyncio.run(agent.run("Inspect procedure context",deps=SimpleNamespace(for_agent=lambda name:rig.request)))
    assert result.output == "Procedure context inspected"
    assert any("Retain historical spellings" in str(message) for message in seen)


def test_reviewed_memory_is_tenant_scoped_and_never_accepts_model_writes(tmp_path):
    rig=make_rig(tmp_path)
    catalog=reviewed_catalog(rig.request.scope.organization_id,rig.request.scope.collection_id)
    store=ReviewedMemoryStore(rig.request,catalog)
    assert asyncio.run(store.read("other/specimen_geography/MEMORY.md",max_chars=8192)) is None
    assert asyncio.run(store.read(store.path,max_chars=8192)).version == catalog.digest
    with pytest.raises(PermissionError,match="read_only"):
        asyncio.run(store.write(store.path,"model guess",expected_version=None))
