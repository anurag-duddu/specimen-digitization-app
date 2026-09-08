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


@pytest.mark.parametrize("change", [
    lambda p: p["database"].update(instance_id="other-instance"),
    lambda p: p["database"].update(database="other-database"),
    lambda p: p["cost_inputs"].update(approved_total_limit=6),
    lambda p: p["cost_inputs"].update(approved_daily_limit=6),
    lambda p: p["cost_inputs"].update(shared_across_sessions_and_retries=False),
    lambda p: p["cost_inputs"].update(daily_reset_allowed=True),
    lambda p: p["cost_inputs"].update(new_persistent_sql_instances_proposed=1),
    lambda p: p["cost_inputs"].update(isolated_restore_clone_count_proposed=2),
])
def test_proposal_pins_database_and_shared_five_dollar_boundary(change):
    plan = json.loads((ROOT / "infra/live/data-resources.json").read_text())
    change(plan)
    with pytest.raises(ValueError):
        module.validate_plan(plan)


@pytest.mark.parametrize("change", [
    lambda p: p["cost_inputs"].update(approved_restore_clone_hours=200),
    lambda p: p["cost_inputs"].update(proposed_restore_clone_hours_max=200),
    lambda p: p["cost_inputs"].update(proposed_backup_restore_allocation=500),
    lambda p: p["cost_inputs"].update(ordinary_reservation_target=500),
    lambda p: p["cost_inputs"].update(contingency=-1),
    lambda p: p["database"].update(restore_rehearsal_instance="production-other-instance"),
    lambda p: p["storage"].update(rules_file="open-storage.rules"),
    lambda p: p["privileged_maintenance"].update(separate_maintenance_identity_required=False),
])
def test_proposal_rejects_independently_reviewed_resource_and_cost_bypasses(change):
    plan = json.loads((ROOT / "infra/live/data-resources.json").read_text())
    change(plan)
    with pytest.raises(ValueError):
        module.validate_plan(plan)
