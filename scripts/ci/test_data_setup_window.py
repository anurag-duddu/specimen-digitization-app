"""The approved ten-minute data setup window: exact packet, three effects, no replay."""
import copy
import json
import os
from pathlib import Path
import re
import stat

import pytest

import data_setup_window as W
from owner_gcloud import STAMP, Gcloud
from release_context import PROJECT

START = 1_790_000_000
DATA = W.DATA_IDENTITY
INIT = W.INITIALIZER_IDENTITY
OLD_START = "2026-09-13T20:25:15Z"
INSTANCE = ("resource.service == 'sqladmin.googleapis.com' && resource.type == 'sqladmin.googleapis.com/Instance'"
            " && (resource.name == 'projects/specimen-digitization/instances/specimen-digitization-restore-20260908-r1')")
BOTH = ("resource.service == 'sqladmin.googleapis.com' && resource.type == 'sqladmin.googleapis.com/Instance'"
        " && (resource.name == 'projects/specimen-digitization/instances/specimen-digitization-instance'"
        " || resource.name == 'projects/specimen-digitization/instances/specimen-digitization-restore-20260908-r1')")
CLAIM = ("resource.name == 'projects/_/buckets/specimen-digitization.firebasestorage.app/objects/"
         "application/release-control/first-production-restore.json'")


def timed(end, rest=""):
    return f"request.time >= timestamp('{OLD_START}') && request.time < timestamp('{end}')" + (f" && {rest}" if rest else "")


def binding(role_id, member, expression=None, title=None):
    entry = {"role": f"projects/{PROJECT}/roles/{role_id}", "members": [member]}
    if expression is not None:
        entry["condition"] = {"title": title or f"specimen_pr21_{role_id}", "expression": expression,
                              "description": "PR21 finite IAM access; SQL privilege separately capped."}
    return entry


def policy():
    """The live policy's shape on 2026-09-22: nine expired time-bound bindings, two inventory ones, two unrelated."""
    return {"version": 3, "etag": "BwFakeEtag0=", "bindings": [
        binding("specimenDataCloneControl", DATA, timed("2026-09-13T22:25:15Z", INSTANCE)),
        binding("specimenDataCloneCreate", DATA, timed("2026-09-13T22:25:15Z", INSTANCE)),
        binding("specimenDataInitializeTemporary", INIT, timed("2026-09-13T21:40:15Z", BOTH)),
        binding("specimenDataInitializerDisposal", DATA, timed("2026-09-13T22:20:15Z", BOTH)),
        {"role": f"projects/{PROJECT}/roles/specimenDataInventoryProjectRead", "members": [DATA]},
        binding("specimenDataInventorySqlConnect", DATA,
                "resource.name == 'projects/specimen-digitization/instances/specimen-digitization-instance'"
                " && resource.service == 'sqladmin.googleapis.com'", title="specimen_source_inventory_only"),
        binding("specimenDataRestoreAllowanceClaim", DATA, timed("2026-09-13T22:25:15Z", CLAIM),
                title="specimen_first_restore_claim"),
        binding("specimenDataRuntimeAbsence", DATA, timed("2026-09-13T22:25:15Z")),
        binding("specimenDataSchemaPublish", DATA, timed("2026-09-13T22:25:15Z")),
        binding("specimenDataSourceBackup", DATA, timed("2026-09-13T22:25:15Z")),
        binding("specimenDataStorageRules", DATA, timed("2026-09-13T22:25:15Z")),
        {"role": "roles/firebasehosting.admin",
         "members": [f"serviceAccount:github-firebase-hosting@{PROJECT}.iam.gserviceaccount.com"]},
        {"role": "roles/storage.admin",
         "members": [f"serviceAccount:firebase-adminsdk-fbsvc@{PROJECT}.iam.gserviceaccount.com"]},
    ]}


def find(policy_, role_id):
    return [b for b in policy_["bindings"] if b["role"] == f"projects/{PROJECT}/roles/{role_id}"]


def test_plan_renews_exactly_eighteen_timestamps_and_adds_the_bootstrap_grant():
    before = policy()
    packet = W.plan(before, START, START - 120)
    renewal = packet["effects"][2]
    assert (renewal["bindings"], renewal["timestamps"]) == (9, 18)
    assert sum(len(re.findall(STAMP, c["before"])) for c in renewal["changes"]) == 18
    for change in renewal["changes"]:
        # Only the two instants differ; the resource predicates are byte-identical.
        assert re.sub(STAMP, "T", change["before"]) == re.sub(STAMP, "T", change["after"])
        renewed = W.TIME_CONDITION.fullmatch(change["after"])
        assert (renewed["start"], renewed["end"]) == (W.stamp(START), W.stamp(START + change["minutes"] * 60))
    minutes = {c["role"].rsplit("/", 1)[1]: c["minutes"] for c in renewal["changes"]}
    assert minutes["specimenDataInitializeTemporary"] == 75
    assert minutes["specimenDataInitializerDisposal"] == 115
    assert all(value == 120 for key, value in minutes.items()
               if key not in {"specimenDataInitializeTemporary", "specimenDataInitializerDisposal"})

    after = packet["policy"]["after"]
    assert (after["etag"], after["version"]) == (before["etag"], 3)
    assert len(after["bindings"]) == len(before["bindings"]) + 1
    renewed_roles = {c["role"] for c in renewal["changes"]}
    for old, new in zip(before["bindings"], after["bindings"]):
        if old["role"] in renewed_roles:
            assert {k: v for k, v in old.items() if k != "condition"} == {k: v for k, v in new.items() if k != "condition"}
            assert {k: v for k, v in old["condition"].items() if k != "expression"} == \
                {k: v for k, v in new["condition"].items() if k != "expression"}
        else:
            assert old == new
    grant = after["bindings"][-1]
    assert grant == W.bootstrap_binding(START) == packet["effects"][1]["binding"]
    assert grant["members"] == [DATA] and grant["role"] == W.BOOTSTRAP_ROLE
    assert W.TIME_CONDITION.fullmatch(grant["condition"]["expression"])["end"] == W.stamp(START + 7200)
    assert packet["effects"][0]["body"]["includedPermissions"] == list(W.BOOTSTRAP_PERMISSIONS)
    assert packet["effects"][0]["body"]["stage"] == "GA"
    assert packet["requests"] == {"planned": 6, "ceiling": 187}
    assert packet["window"]["deadline_unix"] - packet["window"]["start_unix"] == 600
    assert before == policy(), "planning never mutates its input"
    text = W.summary(packet)
    assert text.count("becomes") == 9 and W.BOOTSTRAP_ROLE in text and "18 timestamps in 9 bindings" in text


def without(policy_, role_id):
    policy_["bindings"] = [b for b in policy_["bindings"] if b["role"] != f"projects/{PROJECT}/roles/{role_id}"]
    return policy_


def duplicated(policy_, role_id):
    policy_["bindings"].append(copy.deepcopy(find(policy_, role_id)[0]))
    return policy_


def rebound(policy_, role_id, member):
    find(policy_, role_id)[0]["members"] = [member]
    return policy_


def reshaped(policy_, role_id, expression):
    find(policy_, role_id)[0]["condition"]["expression"] = expression
    return policy_


def undocumented(policy_, role_id):
    del find(policy_, role_id)[0]["condition"]["description"]
    return policy_


def prebound(policy_):
    policy_["bindings"].append(W.bootstrap_binding(START - 86400))
    return policy_


def downgraded(policy_):
    policy_["version"] = 1
    return policy_


@pytest.mark.parametrize("mutate, message", [
    (lambda p: without(p, "specimenDataSchemaPublish"), "exactly one binding"),
    (lambda p: duplicated(p, "specimenDataSourceBackup"), "exactly one binding"),
    (lambda p: rebound(p, "specimenDataStorageRules", INIT), "single approved identity"),
    (lambda p: reshaped(p, "specimenDataRuntimeAbsence", INSTANCE), "time-bound shape"),
    (lambda p: reshaped(p, "specimenDataCloneCreate", timed("2026-09-13T22:25:15Z") + " || true"), "time-bound shape"),
    (lambda p: reshaped(p, "specimenDataCloneControl", "request.time < timestamp('2026-09-13T22:25:15Z')"),
     "time-bound shape"),
    (lambda p: undocumented(p, "specimenDataInitializerDisposal"), "titled, described"),
    (prebound, "already bound"),
    (downgraded, "version 3"),
])
def test_plan_refuses_a_policy_outside_the_approved_shape(mutate, message):
    with pytest.raises(ValueError, match=message):
        W.plan(mutate(policy()), START, START - 60)


def test_parse_start_accepts_only_the_near_future():
    assert W.parse_start("now+300", START) == START + 300
    assert W.parse_start(W.stamp(START + 3600), START + 0.7) == START + 3600
    for text in (W.stamp(START - 1), W.stamp(START + 8 * 86400), "tomorrow", "now+", "2026-09-23 10:00:00Z", ""):
        with pytest.raises(ValueError):
            W.parse_start(text, START)


class FakeCloud:
    """gcloud as the window sees it: reads, one role, one policy write, reordered readback."""

    def __init__(self, before, *, role_exists=False, drift=False, reject_set=False, readback_extra=None,
                 same_etag=False):
        self.current = copy.deepcopy(before)
        if drift:
            self.current["etag"] = "BwDrifted1="
        self.role_exists = role_exists
        self.reject_set = reject_set
        self.readback_extra = readback_extra
        self.same_etag = same_etag
        self.calls = []
        self.role_body = None
        self.created_role = None
        self.set_policy = None

    def __call__(self, args, timeout):
        assert args[-2:] == [f"--project={PROJECT}", "--quiet"] and 0 < timeout <= 30
        self.calls.append(args[:-2])
        head = args[:3]
        if head == ["projects", "get-iam-policy", PROJECT]:
            policy_ = copy.deepcopy(self.current)
            if self.readback_extra is not None and self.set_policy is not None:
                policy_["bindings"].append(self.readback_extra)
            return 0, json.dumps(policy_), ""
        if head == ["iam", "roles", "describe"]:
            if self.created_role is not None:
                return 0, json.dumps(self.created_role), ""
            if self.role_exists:
                return 0, json.dumps({"name": W.BOOTSTRAP_ROLE, "includedPermissions": ["x"]}), ""
            return 1, "", ("ERROR: (gcloud.iam.roles.describe) NOT_FOUND: The role named "
                           f"{W.BOOTSTRAP_ROLE} was not found.")
        if head == ["iam", "roles", "create"]:
            path = next(a for a in args if a.startswith("--file="))[7:]
            self.role_body = json.loads(Path(path).read_text())
            self.created_role = {"name": W.BOOTSTRAP_ROLE, "etag": "BwRole=", **self.role_body}
            return 0, json.dumps(self.created_role), ""
        if head == ["projects", "set-iam-policy", PROJECT]:
            policy_ = json.loads(Path(args[3]).read_text())
            assert policy_["etag"] == self.current["etag"], "compare-and-swap on the bound etag"
            if self.reject_set:
                return 1, "", "ERROR: (gcloud.projects.set-iam-policy) ABORTED: concurrent policy change"
            self.set_policy = policy_
            self.current = {**policy_, "etag": self.current["etag"] if self.same_etag else "BwNewEtag1=",
                            "bindings": list(reversed(policy_["bindings"]))}
            return 0, json.dumps(self.current), ""
        raise AssertionError(args)


def clock_at(instant):
    return lambda: float(instant)


def run(tmp_path, fake, packet, instant=START + 5):
    receipt = tmp_path / "window.receipt.json"
    try:
        return W.execute(packet, packet_sha256="a" * 64, receipt_path=receipt, runner=fake, clock=clock_at(instant))
    finally:
        run.receipt = json.loads(receipt.read_text()) if receipt.exists() else None


def test_execute_performs_the_three_effects_once_with_six_requests(tmp_path):
    before = policy()
    packet = W.plan(before, START, START - 60)
    fake = FakeCloud(before)
    receipt = run(tmp_path, fake, packet)
    assert receipt["verified"] is True and receipt["requests_used"] == 6
    assert [c[:3] for c in fake.calls] == [
        ["projects", "get-iam-policy", PROJECT], ["iam", "roles", "describe"], ["iam", "roles", "create"],
        ["iam", "roles", "describe"], ["projects", "set-iam-policy", PROJECT], ["projects", "get-iam-policy", PROJECT]]
    assert fake.role_body == W.role_body()
    assert fake.set_policy == packet["policy"]["after"]
    assert receipt["policy_etag_after"] == "BwNewEtag1=" and receipt["role"] == W.BOOTSTRAP_ROLE
    assert [step["step"] for step in receipt["steps"]] == [
        "policy_verified", "role_absent", "role_created", "role_readback_verified", "policy_set",
        "policy_readback_verified"]
    written = tmp_path / "window.receipt.json"
    assert stat.S_IMODE(written.stat().st_mode) == 0o600 and json.loads(written.read_text()) == receipt
    for effect in ("role_create", "policy_set"):
        intent = tmp_path / f"window.receipt.{effect}.intent.json"
        assert json.loads(intent.read_text())["packet_sha256"] == "a" * 64
        assert stat.S_IMODE(intent.stat().st_mode) == 0o600


@pytest.mark.parametrize("instant", [START - 1, START + 600, START + 86400])
def test_execute_refuses_outside_the_planned_window(tmp_path, instant):
    before = policy()
    fake = FakeCloud(before)
    with pytest.raises(ValueError, match="outside the planned window"):
        run(tmp_path, fake, W.plan(before, START, START - 60), instant)
    assert fake.calls == [] and run.receipt is None


def test_execute_refuses_a_drifted_policy_before_any_effect(tmp_path):
    before = policy()
    fake = FakeCloud(before, drift=True)
    with pytest.raises(ValueError, match="differs from the planned packet"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 1 and fake.role_body is None and fake.set_policy is None
    assert run.receipt["verified"] is False and "differs" in run.receipt["failed"]
    assert not list(tmp_path.glob("*.intent.json"))


def test_execute_refuses_an_existing_role(tmp_path):
    before = policy()
    fake = FakeCloud(before, role_exists=True)
    with pytest.raises(ValueError, match="must be absent"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 2 and fake.role_body is None and not list(tmp_path.glob("*.intent.json"))


def test_execute_never_replays_a_recorded_effect(tmp_path):
    before = policy()
    fake = FakeCloud(before)
    (tmp_path / "window.receipt.role_create.intent.json").write_text("{}\n")
    with pytest.raises(ValueError, match="never replayed"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 2 and fake.role_body is None


def test_execute_stops_when_the_policy_write_is_rejected(tmp_path):
    before = policy()
    fake = FakeCloud(before, reject_set=True)
    with pytest.raises(ValueError, match="set-iam-policy specimen-digitization failed"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 5 and fake.role_body == W.role_body()
    assert run.receipt["requests_used"] == 5 and run.receipt["verified"] is False


def test_execute_refuses_a_readback_that_differs_from_the_plan(tmp_path):
    before = policy()
    extra = {"role": "roles/viewer", "members": [DATA]}
    fake = FakeCloud(before, readback_extra=extra)
    with pytest.raises(ValueError, match="readback differs"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 6 and run.receipt["verified"] is False


def test_execute_refuses_an_unchanged_etag_after_the_write(tmp_path):
    before = policy()
    fake = FakeCloud(before, same_etag=True)
    with pytest.raises(ValueError, match="returned policy does not match"):
        run(tmp_path, fake, W.plan(before, START, START - 60))
    assert len(fake.calls) == 5


def test_execute_requires_the_planned_request_count():
    packet = W.plan(policy(), START, START - 60)
    packet["requests"]["planned"] = 7
    with pytest.raises(ValueError, match="packet required"):
        W.execute(packet, packet_sha256="a" * 64, receipt_path=Path("/nonexistent"), runner=lambda a, t: (1, "", ""),
                  clock=clock_at(START + 1))


def test_gcloud_stops_at_the_deadline_and_the_ceiling():
    calls = []
    gcloud = Gcloud(START + 10, ceiling=1, runner=lambda a, t: calls.append((a, t)) or (0, "{}", ""), clock=clock_at(START))
    assert gcloud.json("projects", "get-iam-policy", PROJECT) == {}
    assert calls[0][0][-2:] == [f"--project={PROJECT}", "--quiet"] and calls[0][1] == 10
    with pytest.raises(ValueError, match="exhausted"):
        gcloud("projects", "get-iam-policy", PROJECT)
    late = Gcloud(START, ceiling=5, runner=lambda a, t: (0, "{}", ""), clock=clock_at(START))
    with pytest.raises(ValueError, match="run out"):
        late("projects", "get-iam-policy", PROJECT)
    assert len(calls) == 1


def test_cli_plan_writes_a_private_packet_from_a_saved_policy(tmp_path, capsys):
    saved = tmp_path / "policy.json"
    saved.write_text(json.dumps(policy()))
    output = tmp_path / "private" / "window.packet.json"
    output.parent.mkdir()
    assert W.main(["plan", "--start", "now+120", "--output", str(output), "--policy", str(saved)]) == 0
    packet = json.loads(output.read_text())
    assert packet["schema"] == W.SCHEMA and stat.S_IMODE(output.stat().st_mode) == 0o600
    assert packet["window"]["start_unix"] - int(packet["window"]["start_unix"]) == 0
    printed = capsys.readouterr().out
    assert "Nothing was changed" in printed and "Effect 3: renew 18 timestamps" in printed


def test_cli_execute_requires_an_owner_only_packet(tmp_path):
    packet = tmp_path / "window.packet.json"
    packet.write_text(json.dumps(W.plan(policy(), START, START - 60)))
    os.chmod(packet, 0o644)
    with pytest.raises(ValueError, match="owned private regular file"):
        W.main(["execute", "--packet", str(packet), "--receipt", str(tmp_path / "r.json")])
