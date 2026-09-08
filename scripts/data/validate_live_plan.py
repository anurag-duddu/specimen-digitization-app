"""Offline review gate for the proposal. Passing never authorizes deployment."""

import argparse
import json
from pathlib import Path


def validate_plan(plan: dict) -> None:
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    require(plan["schema_version"] == "live-data-plan/v1", "Unknown plan version")
    require(plan["status"] == "proposal_not_applied", "Proposal cannot claim deployment")
    require(plan["project_id"] == "specimen-digitization", "Wrong project")
    require(plan["database"]["instance_id"] == "specimen-digitization-instance"
            and plan["database"]["database"] == "specimen-digitization-database",
            "Database resource scope changed")
    cost = plan["cost_inputs"]
    require(cost["currency"] == "USD"
            and cost["approved_total_limit"] == 5
            and cost["approved_daily_limit"] == 5
            and cost["shared_across_sessions_and_retries"] is True
            and cost["daily_reset_allowed"] is False,
            "Shared five-dollar pilot ceiling required")
    approved_envelope = {
        "ordinary_reservation_target": 4,
        "contingency": 1,
        "proposed_backup_restore_allocation": 1,
        "approved_restore_clone_hours": 2,
        "proposed_restore_clone_hours_max": 2,
    }
    require(all(type(cost[name]) in (int, float) and cost[name] == value
                for name, value in approved_envelope.items()),
            "Reviewed allocation and two-hour restore boundary required")
    require(cost["new_persistent_sql_instances_proposed"] == 0
            and cost["isolated_restore_clone_count_proposed"] == 1,
            "Persistent SQL expansion or additional restore clone forbidden")
    require(plan["database"]["restore_rehearsal_instance"] in (
        None, "specimen-digitization-restore-20260908-r1"),
        "Restore must use only the approved isolated target")
    require(plan["data_connect"] == {
        "location": "us-east4", "service_id": "specimen-digitization-service",
        "connector_id": "specimen-server", "schema_validation": "COMPATIBLE",
        "readiness_operation": "Readiness"}, "SQL Connect resource scope changed")
    require(plan["data_connect"]["schema_validation"] == "COMPATIBLE", "Compatible migration required")
    pilot = plan["pilot"]
    require(pilot["specimen_limit"] == 10 and pilot["allow_expansion"] is False, "Pilot scope expanded")
    storage = plan["storage"]
    require(storage["bucket"] == "specimen-digitization.firebasestorage.app"
            and storage["runtime_object_prefix"] == "application/sha256/", "Storage resource scope changed")
    require(storage["direct_client_access"] == "deny_all", "Direct client storage access forbidden")
    require(storage["rules_file"] == "storage.rules", "Reviewed Storage rules required")
    require(storage["writes_require_generation_match"] == 0 and storage["reads_require_exact_generation"] is True,
            "Immutable generation preconditions required")
    permissions = {"firebasedataconnect.connectors.impersonateQuery",
                   "firebasedataconnect.connectors.impersonateMutation"}
    identities = plan["runtime_identity_proposals"]
    require({i["service_account_id"] for i in identities} == {"specimen-api-runtime", "specimen-worker-runtime"}
            and len(identities) == 2, "Unexpected runtime identities")
    for identity in identities:
        require(set(identity["sql_connector_permissions"]) == permissions, "Runtime SQL privileges changed")
        require(set(identity["storage_permissions"]) == {"storage.objects.get", "storage.objects.create"},
                "Runtime Storage privileges changed")
        require(identity["storage_scope"] == "bucket_condition_application_sha256_prefix", "Storage scope broadened")
        if identity["service_account_id"] == "specimen-api-runtime":
            require(identity["provider_policy"] == "none", "API cannot access provider secrets")
        else:
            require(identity["provider_policy"] == "separate_processing_exact_resource_only",
                    "Worker requires exact separate secret approval")
    maintenance = plan["privileged_maintenance"]
    require(maintenance["hosting_identity_changes"] is False and maintenance["cloud_apply_authorized"] is False,
            "Proposal cannot authorize cloud or Hosting IAM changes")
    require(maintenance["runtime_connector_contains_bootstrap"] is False, "Bootstrap must remain maintenance-only")
    require(maintenance["separate_maintenance_identity_required"] is True,
            "Separate maintenance identity required")
    require(plan["database"]["supplemental_sql"] == [
        "dataconnect/sql/paging-indexes.sql", "dataconnect/sql/search-indexes.sql"], "Supplemental SQL phase required")
    require(plan["database"]["migration_order"] == [
        "quiesce_api_writes_worker_dispatch_and_inflight_transactions",
        "capture_successful_backup_and_verify_isolated_restore",
        "review_exact_source_target_schema_and_required_compatible_sql",
        "apply_reviewed_schema_through_separate_approved_delivery",
        "verify_schema_managed_unique_constraints",
        "apply_exact_supplemental_indexes_after_schema_reconciliation",
        "verify_catalog_definitions_validity_rows_and_connector_invariants",
        "publish_compatible_connector_and_verify_again",
        "refresh_restored_planner_statistics_and_verify_query_plans",
        "resume_only_verified_runtime_revisions"], "Complete ordered migration gates required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("infra/live/data-resources.json"))
    args = parser.parse_args()
    try:
        validate_plan(json.loads(args.path.read_text()))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "Data proposal validation failed; inspect scope, permissions and migration gates.\n")
    print("PASS offline data proposal contract; cloud inventory/authorization/deployment not proven")


if __name__ == "__main__":
    main()
