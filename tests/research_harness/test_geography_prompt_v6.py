"""The pinned geography revision activates qualified sources and trusted geometry."""

import asyncio
import hashlib
import json
from pathlib import Path

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.committed_pins import _committed_registry
from specimen_digitization.research_harness.contracts import (
    FieldKey, ResearchScope, SourceQuery, SpecialistRequest, SpecialistRole, SourceCoverageState,
)
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_SOURCE_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)
from specimen_digitization.research_harness.sources import SourceBroker


def test_v6_is_an_append_only_supersession_of_v5_and_exactly_pinned():
    root = Path(prompts.__file__).parent
    old = (root / "specimen_geography-v5.txt").read_bytes()
    new = (root / "specimen_geography-v6.txt").read_bytes()
    assert new.startswith(old)
    assert hashlib.sha256(new).hexdigest() == "55a6b4f65b7e38a7c4d598b74b22f1a4491952ebe6961f260c39d2353cb74524"  # pragma: allowlist secret
    assert ROLE_PROMPTS[SpecialistRole.GEOGRAPHY] == (
        "specimen_geography-v6.txt", GEOGRAPHY_SOURCE_PROMPT_VERSION)
    added = new[len(old):].decode("ascii")
    for phrase in ("supersedes the v5 invitation", "georeference_history", "TGN, Wikidata and NGA",
                   "settlement_allowed false", "human_review_required true",
                   "automatic_settlement_allowed false", "Never invent", "trusted, model-free derivation worker"):
        assert phrase in added
    pin = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest="0" * 64,
        source_registry_digest="0" * 64, toolset_digest="0" * 64,
        model_route="harness-deepseek", output_schema_digest="0" * 64)
    assert pin.version == GEOGRAPHY_SOURCE_PROMPT_VERSION
    assert pin.digest == "2627afa2841b834bc705daa57394eadd0d8d792807618655ca4b3569d880e13b"  # pragma: allowlist secret


def test_worker_only_dataset_and_computed_source_are_not_model_lookup_capabilities():
    registry = _committed_registry()
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id="specimen",
        job_id="job", generation=1, input_digest="1" * 64,
        profile_digest="2" * 64, sensitive=False)
    pin = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=scope.profile_digest,
        source_registry_digest=registry.digest, toolset_digest="3" * 64,
        model_route="fixture", output_schema_digest="4" * 64)
    request = SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(FieldKey.CITY,), prompt=pin, field_revisions={FieldKey.CITY: 0})
    allowed = {policy.id for policy in registry.allowed(request)}
    assert {"tgn", "wikidata", "nga"} <= allowed
    assert "georeference_history" not in allowed and "georeference_spatial" not in allowed
    broker = SourceBroker(registry)
    assert "georeference_history" not in broker.available_sources(request)
    query = SourceQuery(source_id="georeference_history", field_key=FieldKey.CITY,
        query_text=json.dumps({"country": "GT", "name": "Yepocapa", "collected_on": "1948-04-25"}))
    result = asyncio.run(broker.query_source(request, query))
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED and result.receipt is None
