"""Free public reads, bounded no-OS code and repository procedures for the roster.

These providers use existing immutable capture and allowance fences. Tool output
is context only; deciding source settlement still uses the typed source broker.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.workspaces import LocalWorkspaceBackend
from pydantic_ai_harness import Memory, Skills
from pydantic_ai_harness.memory import MemoryFile

from .contracts import SpecialistRole, digest
from .shared_capabilities import (
    BrowserCapture, BrowserSourceBinding, IsolatedCodeOutput, IsolatedCodePolicy,
    RoleCapabilityPolicy, SharedResearchAdapters, SharedResearchCapability,
    VerifiedKnowledgeCatalog, VerifiedKnowledgeItem,
)

VERSION = "free-research-providers/v1"
BROWSER_ID = "bounded-public-http/v1"
BROWSER_PIN = digest({"provider": BROWSER_ID, "redirects": False, "paid": False,
    "transport": "BoundedHTTPTransport", "view_bytes": 4096})
CODE_ID = "monty-no-os/1.1.0/v1"
CODE_PIN = digest({"executor": CODE_ID, "mounts": False, "host_functions": False,
    "network": False, "fresh_session_per_effect": True})
PROCEDURES = {
    SpecialistRole.GEOGRAPHY: "Retain historical spellings and competing place interpretations. Research a distinct permitted alternative after ambiguity or no match, within the remaining bounds. Derive a parent only from captured hierarchy and matching collecting context. Coordinates and uncertainty filters require captured evidence. Keep a justified structured stop when the available evidence does not distinguish places.",
    SpecialistRole.TAXONOMY: "Query the independently retained reader assertions. GBIF decides taxonomy; GNV and Catalogue of Life support spelling and context. One confirmed reading plus an honestly captured alternate no match can settle when policy permits it. Preserve historical alternatives, rank and genus-only precision. A bare sp. number supplies no genus. Derive family or order only from verified authority context.",
    SpecialistRole.TEMPORAL: "Distinguish collecting, determination and preparation dates. Use exact accepted label event and span relations, preserve Roman months and written precision, and apply the declared short-year policy. A derived To requires the exact current settled From revision and resolution digest; preserve protected human dates. Related-label context requires a qualified event join.",
    SpecialistRole.MEASUREMENT: "Preserve the written quantity, unit, qualifier, range and uncertainty on its collecting event. One foot equals exactly 0.3048 metres. A derived-only endpoint consumes the exact current accepted source checkpoint. Equal numerals alone do not establish equal assertions. DEM remains reviewer context under its approved dataset and whole uncertainty-circle policy.",
    SpecialistRole.PARTIES: "Recover omitted exact raw spans only with trusted reader, assembly and event lineage. Distinguish collectors, preparers, determiners and places. A public biography cannot establish an EMu party IRN. Preserve deliberate null or Unknown IRN outcomes under the declared nonblocking policy, and never invent an identity.",
    SpecialistRole.COLLECTION: "Preserve catalogue prefixes and leading zeros. Recover omitted or multiline literal spans only through trusted assembly and role evidence. Habitat and method require their actual label semantics. Generic external specimen joins are not admitted. D/T/S has no approved formal definition; preserve its verbatim and report the exact missing prerequisite rather than selecting a guessed definition.",
}
SKILL_ROOT = Path(__file__).resolve().parent / "skills"


def provider_contract_digest():
    import hashlib
    directory = Path(__file__).resolve().parent
    parts = [(name, hashlib.sha256((directory / name).read_bytes()).hexdigest())
        for name in ("capability_providers.py", "shared_capabilities.py", "recovery.py")]
    parts += [(str(path.relative_to(directory)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(SKILL_ROOT.glob("specimen-*-research/SKILL.md"))]
    return digest([VERSION, parts])


class PublicHTTPBrowser:
    provider_id = BROWSER_ID
    registration_digest = BROWSER_PIN
    free_operation = True

    def __init__(self, transport, *, execution_class):
        self.transport, self.execution_class = transport, execution_class

    async def capture(self, url, *, policy, idempotency_key, authorize_navigation):
        authorize_navigation(url)
        status, body = await self.transport.get(url, policy=policy)
        # The full bytes remain captured. A bounded UTF-8 view is explicit
        # context, not a claim that a rendered page or authority was verified.
        text = body[:4096].decode("utf-8", errors="replace")
        if len(body) > 4096:
            text = text[:3950] + "\n[Response view truncated; full original response retained.]"
        return BrowserCapture(url, (url,), status, body, text)


class MontyCodeExecutor:
    executor_id = CODE_ID
    registration_digest = CODE_PIN
    isolation = "monty_no_os"
    free_operation = True

    def __init__(self, *, execution_class):
        self.execution_class = execution_class

    async def execute(self, code, inputs, *, policy, idempotency_key):
        from pydantic_monty import AsyncMonty, MontyError

        limits = {"max_memory": policy.memory_bytes,
            "max_feed_duration_secs": policy.timeout_seconds,
            "max_turn_duration_secs": policy.timeout_seconds,
            "max_recursion_depth": 100, "max_suspensions": 1,
            "max_total_sleep_secs": 0}
        # No mounts, OS callbacks, host function lookup or dependencies are
        # installed. A fresh session prevents one specimen seeing another.
        try:
            async with AsyncMonty(min_processes=1, max_processes=1) as pool:
                async with pool.checkout(limits=limits) as session:
                    value = await session.feed_run(code, inputs={"inputs": inputs},
                        print_callback=lambda *_: None)
        except (MontyError, SyntaxError, ValueError):
            return IsolatedCodeOutput(None, self.isolation, self.registration_digest, "invalid_code")
        except (TimeoutError, MemoryError, RecursionError):
            return IsolatedCodeOutput(None, self.isolation, self.registration_digest, "resource_limit")
        return IsolatedCodeOutput(value, self.isolation, self.registration_digest)


def reviewed_catalog(organization_id, collection_id):
    return VerifiedKnowledgeCatalog(items=tuple(VerifiedKnowledgeItem(
        id=f"{role.value}-procedure", kind="procedure", organization_id=organization_id,
        collection_id=collection_id, role=role, content=content,
        evidence_refs=("owner-specimen-research-contract", f"repository:{role.value}-prompt"),
        verified_by="repository procedure", verification_digest=digest([VERSION, str(role), content]))
        for role, content in PROCEDURES.items()))


def committed_role_policies(profile, registry, toolset_digest):
    catalog = reviewed_catalog(profile.organization_id, profile.collection_id)
    return {str(role): RoleCapabilityPolicy(organization_id=profile.organization_id,
        collection_id=profile.collection_id, profile_digest=digest(profile), role=role,
        toolset_digest=toolset_digest, owner_registration_digest=digest([VERSION, str(role), provider_contract_digest()]),
        execution_policy="free_local_public_http",
        browser_sources=tuple(BrowserSourceBinding(source_id=source.id,
            source_policy_digest=digest(source), provider_id=BROWSER_ID,
            provider_registration_digest=BROWSER_PIN) for source in registry.policies
            if source.ready and role in source.roles and source.source_type not in {"computed_local", "local_dataset"})[:8],
        code=IsolatedCodePolicy(executor_id=CODE_ID, isolation="monty_no_os",
            executor_registration_digest=CODE_PIN), knowledge_catalog_digest=catalog.digest
        ).model_dump(mode="json") for role in SpecialistRole}


class ReviewedMemoryStore:
    """Immutable procedure catalog; model writes cannot become learned authority."""

    def __init__(self, request, catalog):
        self.namespace = digest([request.scope.organization_id, request.scope.collection_id])
        self.path = f"{self.namespace}/{request.role.value}/MEMORY.md"
        self.items = tuple(item for item in catalog.items
            if item.organization_id == request.scope.organization_id
            and item.collection_id == request.scope.collection_id and item.role == request.role)
        self.content = "\n\n".join(f"{item.id}\n{item.content}\nEvidence: {', '.join(item.evidence_refs)}" for item in self.items)
        self.version = catalog.digest

    async def read(self, path, *, max_chars):
        if path != self.path:
            return None
        return MemoryFile(content=self.content[:max_chars], version=self.version, operation_id=None,
            truncated=len(self.content) > max_chars)

    async def get_operation(self, operation):
        return None

    async def write(self, *args, **kwargs):
        raise PermissionError("reviewed_memory_is_read_only")

    async def delete(self, *args, **kwargs):
        raise PermissionError("reviewed_memory_is_read_only")

    async def list_paths(self, prefix="", *, limit):
        return [self.path] if limit > 0 and self.path.startswith(prefix) else []


class ReviewedMemory(Memory):
    def get_toolset(self):
        # Official Memory injects this immutable catalog as user-role context.
        # On-demand reads use the captured scoped SharedResearchCapability.
        return None


def build_capability_factory(*, broker, scope, lease, registry, source_pins, transport, execution_class):
    def factory(request):
        policy = RoleCapabilityPolicy.model_validate(source_pins["role_capabilities"][str(request.role)])
        catalog = reviewed_catalog(request.scope.organization_id, request.scope.collection_id)
        adapters = SharedResearchAdapters(broker=broker, scope=scope, lease=lease,
            registry=registry, policy=policy, execution_class=execution_class,
            browsers=(PublicHTTPBrowser(transport, execution_class=execution_class),),
            code_executor=MontyCodeExecutor(execution_class=execution_class), knowledge=catalog)
        shared = SharedResearchCapability(request, adapters)
        memory = ReviewedMemory(store=ReviewedMemoryStore(request, catalog),
            namespace=digest([request.scope.organization_id, request.scope.collection_id]),
            agent_name=str(request.role), injection_errors="raise",
            guidance="Repository procedures are reviewed context, not specimen authority. Model guesses are never stored or used to retrain weights.")
        memory.toolset_digest = request.prompt.toolset_digest
        skills = Skills(".", include=[request.role.value.replace("_", "-") + "-research"],
            workspace=LocalWorkspaceBackend(SKILL_ROOT))
        skills.toolset_digest = request.prompt.toolset_digest
        return (shared, memory, skills)
    return factory
