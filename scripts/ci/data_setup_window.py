#!/usr/bin/env python3
"""Plan and execute the approved ten-minute data setup window.

The combined amendment of 2026-09-14 (docs/execution/RELEASE_AUTHORIZATION.md)
approved one fresh bounded setup window with exactly three IAM effects:

1. create the persistent custom role ``specimenDataOwnerBootstrap`` with only
   ``firebaseauth.users.get``, ``firebasedataconnect.services.executeGraphql``
   and ``firebasedataconnect.services.executeGraphqlRead``;
2. grant it at project scope to the existing DATA release identity for at most
   two hours;
3. renew only the 18 timestamps in the nine existing conditional DATA and
   restore-claim bindings, preserving every other permission, member and
   resource predicate. Initializer, disposal and ordinary access expire 75, 115
   and 120 minutes after the window opens.

``plan`` reads the live project policy (one read) and records an exact action
packet bound to the policy's etag; nothing changes. ``execute`` re-reads the
policy, refuses any drift, and performs the three effects with six requests,
all inside the 600-second clock that starts at the planned instant. It never
retries, never replays a recorded effect and never touches any other binding.

The renewed access is short-lived by design. Open the window only when the
data envelopes are minted and installed, so the protected data runs can start
the moment the receipt is written.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from owner_gcloud import (Gcloud, STAMP, canonical, durable_write, parse_stamp,  # noqa: E402
                          sha256_bytes, stamp)
from release_admission import private_bytes, require, strict_json  # noqa: E402
from release_context import PROJECT  # noqa: E402

SCHEMA = "data-setup-window/v1"
RECEIPT_SCHEMA = "data-setup-window-receipt/v1"
AUTHORITY = "docs/execution/RELEASE_AUTHORIZATION.md, approved combined amendment of 2026-09-14"
WINDOW_SECONDS = 600
REQUEST_CEILING = 187
PLANNED_REQUESTS = 6
DATA_IDENTITY = f"serviceAccount:specimen-data-release@{PROJECT}.iam.gserviceaccount.com"
INITIALIZER_IDENTITY = f"serviceAccount:specimen-data-initialize@{PROJECT}.iam.gserviceaccount.com"
# Role id, its single approved member, and the minutes of access after the window opens.
RENEWALS = (
    ("specimenDataInitializeTemporary", INITIALIZER_IDENTITY, 75),
    ("specimenDataInitializerDisposal", DATA_IDENTITY, 115),
    ("specimenDataCloneControl", DATA_IDENTITY, 120),
    ("specimenDataCloneCreate", DATA_IDENTITY, 120),
    ("specimenDataRestoreAllowanceClaim", DATA_IDENTITY, 120),
    ("specimenDataRuntimeAbsence", DATA_IDENTITY, 120),
    ("specimenDataSchemaPublish", DATA_IDENTITY, 120),
    ("specimenDataSourceBackup", DATA_IDENTITY, 120),
    ("specimenDataStorageRules", DATA_IDENTITY, 120),
)
BOOTSTRAP_ROLE_ID = "specimenDataOwnerBootstrap"
BOOTSTRAP_ROLE = f"projects/{PROJECT}/roles/{BOOTSTRAP_ROLE_ID}"
BOOTSTRAP_PERMISSIONS = ("firebaseauth.users.get",
                         "firebasedataconnect.services.executeGraphql",
                         "firebasedataconnect.services.executeGraphqlRead")
BOOTSTRAP_MINUTES = 120
BOOTSTRAP_TITLE = "specimen_owner_bootstrap_window"
TIME_CONDITION = re.compile(
    rf"request\.time >= timestamp\('(?P<start>{STAMP})'\) && "
    rf"request\.time < timestamp\('(?P<end>{STAMP})'\)(?P<rest>.*)", re.DOTALL)


def parse_start(text: str, now: float) -> int:
    """``now+SECONDS`` or an RFC 3339 UTC instant, never in the past."""
    now = int(now)
    if re.fullmatch(r"now\+[0-9]{1,5}", text or ""):
        start = now + int(text[4:])
    else:
        start = parse_stamp(text)
    require(now <= start <= now + 7 * 86400, "window start must be between now and seven days ahead")
    return start


def time_bound(start: int, minutes: int) -> str:
    return (f"request.time >= timestamp('{stamp(start)}') && "
            f"request.time < timestamp('{stamp(start + minutes * 60)}')")


def role_body() -> dict:
    return {"title": "Specimen data owner bootstrap",
            "description": ("Approved 2026-09-14: verify the administrator's account and execute "
                            "the reviewed bootstrap mutation through the protected data plane only."),
            "stage": "GA", "includedPermissions": list(BOOTSTRAP_PERMISSIONS)}


def bootstrap_binding(start: int) -> dict:
    return {"role": BOOTSTRAP_ROLE, "members": [DATA_IDENTITY],
            "condition": {"title": BOOTSTRAP_TITLE,
                          "description": ("Approved 2026-09-14: owner bootstrap through the protected "
                                          "data plane, at most two hours after the setup window opened."),
                          "expression": time_bound(start, BOOTSTRAP_MINUTES)}}


def binding_multiset(policy: dict) -> list[str]:
    """Google may reorder bindings; compare them as a canonical multiset."""
    return sorted(canonical(binding) for binding in policy.get("bindings", []))


def renewed_policy(policy: dict, start: int) -> tuple[dict, list[dict]]:
    """The exact after-policy: nine renewed conditions plus the one bootstrap grant."""
    require(isinstance(policy, dict) and policy.get("version") == 3
            and isinstance(policy.get("etag"), str) and policy["etag"]
            and set(policy) <= {"version", "etag", "bindings", "auditConfigs"},
            "IAM policy version 3 with an etag required")
    after = copy.deepcopy(policy)
    bindings = after.get("bindings")
    require(isinstance(bindings, list) and all(isinstance(b, dict) for b in bindings), "policy bindings required")
    require(all(b.get("role") != BOOTSTRAP_ROLE for b in bindings),
            "the bootstrap role is already bound; reconcile by hand, never replay")
    changes = []
    for role_id, member, minutes in RENEWALS:
        role = f"projects/{PROJECT}/roles/{role_id}"
        matches = [b for b in bindings if b.get("role") == role]
        require(len(matches) == 1, f"exactly one binding required for {role_id}")
        binding = matches[0]
        require(binding.get("members") == [member], f"{role_id} must be bound to its single approved identity")
        condition = binding.get("condition")
        require(isinstance(condition, dict) and set(condition) == {"title", "description", "expression"}
                and all(isinstance(condition[key], str) for key in condition),
                f"{role_id} must carry a titled, described condition")
        match = TIME_CONDITION.fullmatch(condition["expression"])
        require(match is not None and (match["rest"] == "" or match["rest"].startswith(" && ")),
                f"{role_id} condition is not the approved time-bound shape")
        renewed = time_bound(start, minutes) + match["rest"]
        changes.append({"role": role, "member": member, "minutes": minutes,
                        "before": condition["expression"], "after": renewed})
        condition["expression"] = renewed
    bindings.append(bootstrap_binding(start))
    return after, changes


def plan(policy: dict, start: int, now: float) -> dict:
    after, changes = renewed_policy(policy, start)
    require(len(changes) == len(RENEWALS), "nine renewed bindings required")
    return {
        "schema": SCHEMA, "project": PROJECT, "authority": AUTHORITY, "planned_at": stamp(now),
        "window": {"start": stamp(start), "start_unix": start, "seconds": WINDOW_SECONDS,
                   "deadline": stamp(start + WINDOW_SECONDS), "deadline_unix": start + WINDOW_SECONDS},
        "requests": {"planned": PLANNED_REQUESTS, "ceiling": REQUEST_CEILING},
        "effects": [
            {"effect": "role_create", "role": BOOTSTRAP_ROLE, "body": role_body()},
            {"effect": "role_grant", "binding": bootstrap_binding(start)},
            {"effect": "binding_renewal", "bindings": len(changes), "timestamps": 2 * len(changes),
             "changes": changes},
        ],
        "policy": {"etag": policy["etag"], "before": policy, "after": after,
                   "before_sha256": sha256_bytes(canonical(policy).encode()),
                   "after_sha256": sha256_bytes(canonical(after).encode())},
    }


def summary(packet: dict) -> str:
    window, effects = packet["window"], packet["effects"]
    lines = [f"Data setup window packet {packet['schema']} for project {packet['project']}",
             f"Authority: {packet['authority']}",
             f"Window: {window['start']} until {window['deadline']} ({window['seconds']} s); "
             f"{packet['requests']['planned']} requests of at most {packet['requests']['ceiling']}",
             f"Bound to policy etag {packet['policy']['etag']} "
             f"(before {packet['policy']['before_sha256'][:12]}, after {packet['policy']['after_sha256'][:12]})",
             f"Effect 1: create {effects[0]['role']} with exactly "
             f"{', '.join(effects[0]['body']['includedPermissions'])}",
             f"Effect 2: grant it to {effects[1]['binding']['members'][0]} while "
             f"{effects[1]['binding']['condition']['expression']}",
             f"Effect 3: renew {effects[2]['timestamps']} timestamps in {effects[2]['bindings']} bindings, "
             "every other predicate, member and permission unchanged:"]
    for change in effects[2]["changes"]:
        before, after = TIME_CONDITION.fullmatch(change["before"]), TIME_CONDITION.fullmatch(change["after"])
        lines.append(f"  {change['role'].rsplit('/', 1)[1]} ({change['member'].split(':')[1].split('@')[0]}): "
                     f"{before['start']} to {before['end']} becomes {after['start']} to {after['end']} "
                     f"({change['minutes']} min)")
    return "\n".join(lines)


def read_policy(gcloud: Gcloud) -> dict:
    return gcloud.json("projects", "get-iam-policy", PROJECT, "--format=json")


def intent(receipt_path: Path, effect: str, packet_sha256: str, now: float) -> None:
    """A durable record before every mutation; an existing record stops the run."""
    path = receipt_path.with_name(f"{receipt_path.stem}.{effect}.intent.json")
    durable_write(path, {"effect": effect, "packet_sha256": packet_sha256, "at": stamp(now)}, exclusive=True)


def execute(packet: dict, *, packet_sha256: str, receipt_path: Path, runner=None, clock=time.time) -> dict:
    require(packet.get("schema") == SCHEMA and packet.get("project") == PROJECT
            and packet.get("requests", {}).get("planned") == PLANNED_REQUESTS,
            "data setup window packet required")
    window = packet["window"]
    started = clock()
    require(window["start_unix"] <= started < window["deadline_unix"],
            "outside the planned window; plan a new packet")
    expected_after = binding_multiset(packet["policy"]["after"])
    gcloud = Gcloud(window["deadline_unix"], ceiling=PLANNED_REQUESTS, runner=runner, clock=clock)
    receipt = {"schema": RECEIPT_SCHEMA, "packet_sha256": packet_sha256, "window": window,
               "started_at": stamp(started), "steps": [], "verified": False}
    workspace = Path(tempfile.mkdtemp(prefix="data-setup-window-"))

    def step(name: str, **facts) -> None:
        receipt["steps"].append({"step": name, "at": stamp(clock()), **facts})

    try:
        live = read_policy(gcloud)
        require(live == packet["policy"]["before"], "the live policy differs from the planned packet; plan again")
        step("policy_verified", etag=live["etag"])
        code, _, err = gcloud("iam", "roles", "describe", BOOTSTRAP_ROLE_ID, "--format=json")
        require(code != 0 and "NOT_FOUND" in err, "the bootstrap role must be absent before creation; reconcile by hand")
        step("role_absent")

        intent(receipt_path, "role_create", packet_sha256, clock())
        role_file = workspace / "role.json"
        role_file.write_text(json.dumps(packet["effects"][0]["body"], indent=2) + "\n")
        role = gcloud.json("iam", "roles", "create", BOOTSTRAP_ROLE_ID, f"--file={role_file}", "--format=json")
        require(role.get("name") == BOOTSTRAP_ROLE and role.get("stage") == "GA"
                and sorted(role.get("includedPermissions", [])) == sorted(BOOTSTRAP_PERMISSIONS),
                "the created role does not match the approved definition")
        step("role_created", role=role["name"], etag=role.get("etag"))
        readback_role = gcloud.json("iam", "roles", "describe", BOOTSTRAP_ROLE_ID, "--format=json")
        require(all(readback_role.get(key) == role.get(key) for key in ("name", "stage", "title"))
                and sorted(readback_role.get("includedPermissions", [])) == sorted(BOOTSTRAP_PERMISSIONS),
                "the role readback does not match the created role")
        step("role_readback_verified", etag=readback_role.get("etag"))

        intent(receipt_path, "policy_set", packet_sha256, clock())
        policy_file = workspace / "policy.json"
        policy_file.write_text(json.dumps(packet["policy"]["after"], indent=2) + "\n")
        returned = gcloud.json("projects", "set-iam-policy", PROJECT, str(policy_file), "--format=json")
        require(binding_multiset(returned) == expected_after
                and isinstance(returned.get("etag"), str) and returned["etag"] not in ("", packet["policy"]["etag"]),
                "the returned policy does not match the planned policy")
        step("policy_set", etag=returned["etag"])
        readback = read_policy(gcloud)
        require(binding_multiset(readback) == expected_after and readback.get("etag") == returned["etag"],
                "the policy readback differs from the planned policy")
        step("policy_readback_verified", etag=readback["etag"])
        receipt.update(finished_at=stamp(clock()), requests_used=len(gcloud.calls), verified=True,
                       role=BOOTSTRAP_ROLE, policy_etag_after=readback["etag"],
                       policy_after_sha256=packet["policy"]["after_sha256"])
        return receipt
    except BaseException as error:
        receipt.update(failed=str(error)[:240], requests_used=len(gcloud.calls))
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        durable_write(receipt_path, receipt)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="record the exact packet from the live policy; changes nothing")
    planner.add_argument("--start", required=True,
                         help="when the window opens: an RFC 3339 UTC instant (...Z) or now+SECONDS")
    planner.add_argument("--output", required=True, type=Path, help="private packet path (written 0600)")
    planner.add_argument("--policy", type=Path, help="a saved get-iam-policy JSON instead of the live policy")
    executor = commands.add_parser("execute", help="perform the three approved effects inside the planned window")
    executor.add_argument("--packet", required=True, type=Path)
    executor.add_argument("--receipt", required=True, type=Path, help="private receipt path (written 0600)")
    args = parser.parse_args(argv)

    if args.command == "plan":
        now = time.time()
        start = parse_start(args.start, now)
        if args.policy is not None:
            policy = strict_json(args.policy.read_bytes())
        else:
            policy = read_policy(Gcloud(now + 60, ceiling=1))
        packet = plan(policy, start, now)
        raw = durable_write(args.output, packet)
        print(summary(packet))
        print(f"Packet written to {args.output} (sha256 {sha256_bytes(raw)}). Nothing was changed.")
        return 0

    raw = private_bytes(args.packet)
    packet = strict_json(raw)
    print(summary(packet))
    receipt = execute(packet, packet_sha256=sha256_bytes(raw), receipt_path=args.receipt)
    print(f"Setup window complete with {receipt['requests_used']} requests; policy etag "
          f"{receipt['policy_etag_after']}; receipt {args.receipt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
