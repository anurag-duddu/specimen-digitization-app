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
# The exact text after the two time bounds of each time-bounded role's live binding, as read on 2026-09-23.
LIVE_ON_CLONE = (
    " && resource.service == 'sqladmin.googleapis.com' && resource.type == 'sqladmin.googleapis.com/Instance'"
    " && (resource.name == 'projects/specimen-digitization/instances/specimen-digitization-restore-20260908-r1')")
LIVE_ON_SOURCE_OR_CLONE = (
    " && resource.service == 'sqladmin.googleapis.com' && resource.type == 'sqladmin.googleapis.com/Instance'"
    " && (resource.name == 'projects/specimen-digitization/instances/specimen-digitization-instance'"
    " || resource.name == 'projects/specimen-digitization/instances/specimen-digitization-restore-20260908-r1')")
LIVE_PREDICATES = {
    "specimenDataInitializeTemporary": LIVE_ON_SOURCE_OR_CLONE,
    "specimenDataInitializerDisposal": LIVE_ON_SOURCE_OR_CLONE,
    "specimenDataCloneControl": LIVE_ON_CLONE,
    "specimenDataCloneCreate": LIVE_ON_CLONE,
    "specimenDataRestoreAllowanceClaim": (
        " && resource.name == 'projects/_/buckets/specimen-digitization.firebasestorage.app/objects/"
        "application/release-control/first-production-restore.json'"),
    "specimenDataRuntimeAbsence": "",
}
# The roles that stay time-bounded (golive/RELEASE.md section 1), each with its approved member and minutes of access.
TIME_BOUNDED = (("specimenDataInitializeTemporary", INIT, 75), ("specimenDataInitializerDisposal", DATA, 115),
                ("specimenDataCloneControl", DATA, 120), ("specimenDataCloneCreate", DATA, 120),
                ("specimenDataRestoreAllowanceClaim", DATA, 120), ("specimenDataRuntimeAbsence", DATA, 120))
# Every role the window manages: the time-bounded ones and the one-time bootstrap grant.
MANAGED = [(role_id, member) for role_id, member, _ in TIME_BOUNDED] + [("specimenDataOwnerBootstrap", DATA)]
# The roles G11 made standing, and the inventory roles, standing already with their conditions.
STANDING = ("specimenDataSchemaPublish", "specimenDataSourceBackup", "specimenDataStorageRules")
INVENTORY = ("specimenDataInventoryProjectRead", "specimenDataInventorySqlConnect")


def timed(end, rest=""):
    return f"request.time >= timestamp('{OLD_START}') && request.time < timestamp('{end}')" + (f" && {rest}" if rest else "")


def binding(role_id, member, expression=None, title=None):
    entry = {"role": f"projects/{PROJECT}/roles/{role_id}", "members": [member]}
    if expression is not None:
        entry["condition"] = {"title": title or f"specimen_pr21_{role_id}", "expression": expression,
                              "description": "PR21 finite IAM access; SQL privilege separately capped."}
    return entry


def policy():
    """The policy the window next reads: the six time-bounded bindings as they expired on 2026-09-13, the three roles
    G11 made standing, the two inventory ones with their conditions, and two unrelated."""
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
        *(binding(role_id, DATA) for role_id in STANDING),
        {"role": "roles/firebasehosting.admin",
         "members": [f"serviceAccount:github-firebase-hosting@{PROJECT}.iam.gserviceaccount.com"]},
        {"role": "roles/storage.admin",
         "members": [f"serviceAccount:firebase-adminsdk-fbsvc@{PROJECT}.iam.gserviceaccount.com"]},
    ]}


def expired(role_id):
    """The time-bound binding a standing role held until it expired on 2026-09-13."""
    return binding(role_id, DATA, timed("2026-09-13T22:25:15Z"))


def beside_expired(policy_):
    """The owner granted the three roles standing and left their expired bindings in place."""
    policy_["bindings"] += [expired(role_id) for role_id in STANDING]
    return policy_


def not_yet_standing(policy_):
    """The shape of 2026-09-22, before the owner's grants: the three roles hold only their expired bindings."""
    policy_["bindings"] = [expired(role_of(b)) if role_of(b) in STANDING else b for b in policy_["bindings"]]
    return policy_


def role_of(binding_):
    return binding_["role"].rsplit("/", 1)[1]


def standing(policy_):
    """The bindings of the five standing roles, in policy order."""
    return [b for b in policy_["bindings"] if role_of(b) in (*STANDING, *INVENTORY)]


def find(policy_, role_id):
    return [b for b in policy_["bindings"] if b["role"] == f"projects/{PROJECT}/roles/{role_id}"]


def test_plan_renews_exactly_twelve_timestamps_and_adds_the_bootstrap_grant():
    before = policy()
    packet = W.plan(before, START, START - 120)
    renewal = packet["effects"][2]
    assert (renewal["bindings"], renewal["timestamps"]) == (6, 12)
    assert sum(len(re.findall(STAMP, c["before"])) for c in renewal["changes"]) == 12
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
    assert text.count("becomes") == 6 and W.BOOTSTRAP_ROLE in text and "12 timestamps in 6 bindings" in text


def test_the_window_renews_only_the_six_time_bounded_roles_and_keeps_the_bootstrap_grant():
    """RELEASE.md T4c: the renewals drop the three roles G11 made standing; the bootstrap handling is unchanged."""
    assert W.RENEWALS == TIME_BOUNDED
    assert not {role_id for role_id, _, _ in W.RENEWALS} & {*STANDING, *INVENTORY, W.BOOTSTRAP_ROLE_ID}
    packet = W.plan(policy(), START, START - 60)
    create, grant, renewal = packet["effects"]
    assert [(c["role"], c["member"], c["minutes"]) for c in renewal["changes"]] == [
        (f"projects/{PROJECT}/roles/{role_id}", member, minutes) for role_id, member, minutes in TIME_BOUNDED]
    assert (W.BOOTSTRAP_ROLE, W.BOOTSTRAP_MINUTES) == (f"projects/{PROJECT}/roles/specimenDataOwnerBootstrap", 120)
    assert (create["effect"], create["role"], create["body"]) == ("role_create", W.BOOTSTRAP_ROLE, W.role_body())
    assert (grant["effect"], grant["binding"]) == ("role_grant", W.bootstrap_binding(START))
    assert grant["binding"]["members"] == [DATA]
    assert W.TIME_CONDITION.fullmatch(grant["binding"]["condition"]["expression"])["end"] == W.stamp(START + 7200)


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
    (lambda p: without(p, "specimenDataRestoreAllowanceClaim"), "exactly one binding"),
    (lambda p: duplicated(p, "specimenDataInitializeTemporary"), "exactly one binding"),
    (lambda p: rebound(p, "specimenDataRuntimeAbsence", INIT), "single approved identity"),
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
    assert "Nothing was changed" in printed and "Effect 3: renew 12 timestamps" in printed


def test_cli_execute_requires_an_owner_only_packet(tmp_path):
    packet = tmp_path / "window.packet.json"
    packet.write_text(json.dumps(W.plan(policy(), START, START - 60)))
    os.chmod(packet, 0o644)
    with pytest.raises(ValueError, match="owned private regular file"):
        W.main(["execute", "--packet", str(packet), "--receipt", str(tmp_path / "r.json")])


@pytest.mark.parametrize("shape", [
    lambda p: p, beside_expired, not_yet_standing,
    # Each was a refusal while the window renewed these roles; none is the window's concern any longer.
    lambda p: without(p, "specimenDataSchemaPublish"),
    lambda p: duplicated(p, "specimenDataSourceBackup"),
    lambda p: rebound(p, "specimenDataStorageRules", INIT),
], ids=["standing", "beside-expired", "not-yet-standing", "absent", "duplicated", "rebound"])
def test_standing_roles_plan_cleanly_and_are_never_renewed_or_revoked(tmp_path, shape):
    before = shape(policy())
    kept = standing(before)
    assert set(INVENTORY) <= {role_of(b) for b in kept}
    packet = W.plan(before, START, START - 60)
    assert [role_of(change) for change in packet["effects"][2]["changes"]] == [r for r, _, _ in TIME_BOUNDED]
    assert standing(packet["policy"]["after"]) == kept, "every standing binding is carried over byte for byte"
    fake = FakeCloud(before)
    assert run(tmp_path, fake, packet)["verified"] is True
    assert standing(fake.set_policy) == kept, "the one policy write keeps every standing binding"


def revocation(role_id, member):
    """The exact command that removes an unconditional binding, as the owner runs it."""
    return (f"gcloud projects remove-iam-policy-binding {PROJECT} --member={member} "
            f"--role=projects/{PROJECT}/roles/{role_id} --condition=None")


@pytest.mark.parametrize("replacing", [False, True], ids=["beside-its-timed-binding", "replacing-it"])
@pytest.mark.parametrize("role_id, member", MANAGED, ids=[role_id for role_id, _ in MANAGED])
def test_an_untimed_binding_of_each_managed_role_is_refused_with_its_revocation_command(role_id, member, replacing):
    before = without(policy(), role_id) if replacing else policy()
    if role_id == "specimenDataOwnerBootstrap" and not replacing:
        before = prebound(before)  # an earlier window's grant, which carries its time bound
    before["bindings"].append(binding(role_id, member))
    with pytest.raises(ValueError, match="untimed binding") as refused:
        W.plan(before, START, START - 60)
    assert str(refused.value).splitlines()[1:] == [f"  {revocation(role_id, member)}"]


def test_the_refusal_lists_every_untimed_binding_and_prints_no_condition_or_other_member():
    before = reshaped(policy(), "specimenDataRuntimeAbsence", INSTANCE)
    before["bindings"] += [binding("specimenDataCloneCreate", DATA),
                           binding("specimenDataCloneControl", "user:owner@example.com")]
    with pytest.raises(ValueError, match="time-bound shape") as refused:
        W.plan(before, START, START - 60)
    text, role = str(refused.value), f"projects/{PROJECT}/roles/"
    assert text.splitlines()[1:] == [
        f"  - remove {role}specimenDataRuntimeAbsence for {DATA} on project {PROJECT}; its binding has a condition "
        "without request.time, whose text is not printed",
        f"  {revocation('specimenDataCloneCreate', DATA)}",
        f"  - remove {role}specimenDataCloneControl for a member whose id is not printed on project {PROJECT}"]
    assert "sqladmin" not in text and "example.com" not in text


def test_a_standing_grant_made_after_planning_stops_execute_instead_of_being_revoked(tmp_path):
    before = not_yet_standing(policy())
    packet = W.plan(before, START, START - 60)
    granted = copy.deepcopy(before)
    granted["bindings"].append(binding("specimenDataSchemaPublish", DATA))
    granted["etag"] = "BwGranted1="
    fake = FakeCloud(granted)
    with pytest.raises(ValueError, match="differs from the planned packet"):
        run(tmp_path, fake, packet)
    assert len(fake.calls) == 1 and fake.set_policy is None and fake.role_body is None


def with_rest(policy_, role_id, rest):
    """The role's binding keeps its two time bounds; only the text after them becomes ``rest``."""
    condition = find(policy_, role_id)[0]["condition"]
    bounds = W.TIME_CONDITION.fullmatch(condition["expression"])
    condition["expression"] = condition["expression"][:bounds.start("rest")] + rest
    return policy_


def test_each_time_bounded_role_accepts_exactly_its_live_predicate():
    assert W.PREDICATES == LIVE_PREDICATES, "the composed predicates reproduce the live bindings exactly"
    assert set(W.PREDICATES) == {role_id for role_id, _, _ in W.RENEWALS}
    before = policy()
    assert {role_id: W.TIME_CONDITION.fullmatch(find(before, role_id)[0]["condition"]["expression"])["rest"]
            for role_id in LIVE_PREDICATES} == LIVE_PREDICATES, "the fixture carries the live predicates"
    packet = W.plan(before, START, START - 60)
    assert {role_of(change): change["after"] for change in packet["effects"][2]["changes"]} == {
        role_id: W.time_bound(START, minutes) + LIVE_PREDICATES[role_id] for role_id, _, minutes in TIME_BOUNDED}
    assert packet["effects"][1]["binding"]["condition"]["expression"] == W.time_bound(START, 120), \
        "the bootstrap grant the window creates carries the time bound only, as before"


def other_predicates():
    """Every text after the time bounds that some role must refuse, each labelled."""
    renamed = {"specimen-digitization-restore-20260908-r1": "specimen-digitization-restore-20260909-r1",
               "first-production-restore.json": "second-production-restore.json"}
    for role_id, own in LIVE_PREDICATES.items():
        cases = {"or-true": own + " || true", "ternary": own + " ? true : true",
                 "another-role": next(other for other in LIVE_PREDICATES.values() if other != own),
                 "and-true": own + " && true"}
        if own:
            cases["missing"] = ""
        else:  # RuntimeAbsence has no predicate to miss: any text at all is refused, even a narrowing one.
            cases["non-empty"] = " && resource.service == 'sqladmin.googleapis.com'"
        for old, new in renamed.items():
            if old in own:
                cases["changed-name"] = own.replace(old, new)
        for case, rest in cases.items():
            yield pytest.param(role_id, rest, id=f"{role_id}-{case}")


@pytest.mark.parametrize("role_id, rest", list(other_predicates()))
def test_each_time_bounded_role_refuses_any_other_predicate_without_printing_it(role_id, rest):
    with pytest.raises(ValueError) as refused:
        W.plan(with_rest(policy(), role_id, rest), START, START - 60)
    assert str(refused.value) == f"{role_id} condition is not the approved time-bound shape"


@pytest.mark.parametrize("shape", [lambda p: p, beside_expired], ids=["standing", "beside-expired"])
def test_an_old_packet_cannot_replay_once_the_standing_grants_move_the_policy(tmp_path, monkeypatch, shape):
    """A packet planned before T4c renews nine roles; the owner's standing grants change the policy it is bound to."""
    monkeypatch.setattr(W, "RENEWALS", (*W.RENEWALS, *((role_id, DATA, 120) for role_id in STANDING)))
    monkeypatch.setattr(W, "PREDICATES", {**W.PREDICATES, **dict.fromkeys(STANDING, "")})
    old = W.plan(not_yet_standing(policy()), START, START - 60)
    monkeypatch.undo()
    assert (old["schema"], old["effects"][2]["bindings"], old["effects"][2]["timestamps"]) == (W.SCHEMA, 9, 18)
    live = shape(policy())
    live["etag"] = "BwStanding1="
    fake = FakeCloud(live)
    with pytest.raises(ValueError, match="differs from the planned packet"):
        run(tmp_path, fake, old)
    assert len(fake.calls) == 1 and fake.set_policy is None and fake.role_body is None
    assert not list(tmp_path.glob("*.intent.json")) and run.receipt["verified"] is False
