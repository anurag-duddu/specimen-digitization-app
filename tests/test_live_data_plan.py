import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_live_plan", ROOT / "scripts/data/validate_live_plan.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_public_proposal_matches_release_boundary():
    module.validate_plan(json.loads((ROOT / "infra/live/data-resources.json").read_text()))


@pytest.mark.parametrize("change", [
    lambda p: p["pilot"].update(specimen_limit=11),
    lambda p: p["runtime_identity_proposals"][0]["storage_permissions"].append("storage.objects.delete"),
    lambda p: p["runtime_identity_proposals"][1]["sql_connector_permissions"].append("firebasedataconnect.services.executeGraphql"),
    lambda p: p["runtime_identity_proposals"][0].update(provider_policy="all"),
    lambda p: p["privileged_maintenance"].update(cloud_apply_authorized=True),
    lambda p: p["privileged_maintenance"].update(hosting_identity_changes=True),
    lambda p: p["database"]["migration_order"].pop(0),
    lambda p: p["database"].update(migration_order=p["database"]["migration_order"][:1]),
    lambda p: p["runtime_identity_proposals"][1].update(provider_policy="all"),
    lambda p: p["storage"].update(runtime_object_prefix=""),
    lambda p: p["data_connect"].update(connector_id="other-connector"),
])
def test_proposal_rejects_privilege_or_scope_expansion(change):
    plan = json.loads((ROOT / "infra/live/data-resources.json").read_text())
    change(plan)
    with pytest.raises(ValueError):
        module.validate_plan(plan)
