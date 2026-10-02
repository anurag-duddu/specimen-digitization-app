"""The closed SourceAsset two-merge unique swap; no general migration authority.

The source gate decides whether this exact merge needs the native readback.
Only the release's native connector supplies that readback. SQL rechecks it
immediately before running the one committed drop; unknown outcomes block.
"""
from __future__ import annotations

import schema_gate
from release_admission import require

READ_BACK = ("SourceAsset: @unique specimen_unique_1 is dropped only after "
             "the release reads the live database back")


def swap_required(live_schema, merged_schema, live_connector, merged_connector):
    refusals = schema_gate.check_additive(live_schema, merged_schema, live_connector, merged_connector)
    if READ_BACK not in refusals:
        return False
    # This cannot waive an unrelated schema or operation refusal. The hardened
    # gate must admit the entire merge once its sole physical readback is met.
    require(refusals == [READ_BACK] and not schema_gate.check_additive(
        live_schema, merged_schema, live_connector, merged_connector, unique_read_back=True),
        "the unique swap accompanies another refused change")
    return True


def verify_readback(value, source_sha):
    require(type(value) is dict and set(value) == {"version", "source_sha", "instance", "valid"}
            and value.get("valid") is True
            and value == {"version": "source-asset-unique-readback/v1", "source_sha": source_sha,
                          "instance": "specimen-digitization-instance", "valid": True},
            "the live per-specimen unique was not proven")


def verify_drop(value, source_sha):
    require(type(value) is dict and set(value) == {"version", "source_sha", "instance", "valid", "old_absent"}
            and value.get("valid") is True and value.get("old_absent") is True
            and value == {"version": "source-asset-unique-drop/v1", "source_sha": source_sha,
                          "instance": "specimen-digitization-instance", "valid": True, "old_absent": True},
            "the fixed old unique drop was not reconciled")
