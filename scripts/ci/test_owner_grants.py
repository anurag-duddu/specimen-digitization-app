"""The owner's standing grants (RELEASE.md section 5): a read-only report, exact commands, no private value."""
from collections import Counter
import hashlib
import json
import re
import shlex
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import owner_grants as G

PROJECT = "specimen-digitization"
BUCKET = f"{PROJECT}.firebasestorage.app"
NOW = 1_790_000_000.0  # 2026-09-21: the setup window's bindings of 2026-09-13 have expired
MARKER = b"specimen-digitization runtime readiness marker v1\n"
DIGEST = "c" * 64
DEPLOY = re.compile("gcloud" + r"\s+[^\n]*\b" + "deploy" + r"\b", re.IGNORECASE)  # tests/test_deployment_policy.py
READS, REMOVE, WINDOW, REVIEW = ("Data release read permissions", "Grants to remove",
                                 "Time-bounded, through the setup window only", "Review: not in the table")
TITLES = ["Custom roles to create", READS, "Missing standing grants", "Grants to replace", REMOVE,
          "Waits for the first runtime release", "Waits for the SAM 3 checkpoint digest", WINDOW, REVIEW,
          "Other owner steps"]
EMAIL = "specimen-{}@specimen-digitization.iam.gserviceaccount.com".format
BUILD, RELEASE, API, WORKER, SAM, DATA, INIT = (f"serviceAccount:{EMAIL(name)}" for name in (
    "runtime-build", "runtime-release", "api-runtime", "worker-runtime", "sam-runtime", "data-release",
    "data-initialize"))
# The spec's conditions, written out rather than composed.
APP = ('resource.name.startsWith("projects/_/buckets/specimen-digitization.firebasestorage.app/objects/'
       'application/sha256/")', "specimen_application_objects")
SLIDES = ('resource.name.startsWith("projects/_/buckets/specimen-digitization.firebasestorage.app/objects/'
          'microscopic-slides/") || api.getAttribute("storage.googleapis.com/objectListPrefix", "")'
          '.startsWith("microscopic-slides/")', "specimen_source_slides")
CHECKPOINT = ('api.getAttribute("storage.googleapis.com/objectListPrefix", "").startsWith("application/sha256/'
              f'{DIGEST}/sam3-cache")', "specimen_sam3_checkpoint_listing")
SQL_SOURCE = ('resource.name == "projects/specimen-digitization/instances/specimen-digitization-instance" && '
              'resource.service == "sqladmin.googleapis.com" && resource.type == "sqladmin.googleapis.com/Instance"',
              "specimen_source_inventory_only")
EXPIRED = ("request.time >= timestamp('2026-09-13T20:25:15Z') && request.time < timestamp('2026-09-13T22:25:15Z')",
           "specimen_pr21_window")
# The version each accessor condition names: the pin in runtime_settings.SECRET_VERSIONS (RELEASE.md section 5).
VERSIONS = {"specimen-worker-logfire": 1, "specimen-google-maps-key": 1, "specimen-source-registry": 1,
            "specimen-collection-bindings": 1, "specimen-worker-actor-uid": 1, "huggingface-runtime-token": 2}
PERMISSIONS = {
    "specimenRuntimeRelease": ["run.services.create", "run.services.get", "run.services.update",
                               "run.services.getIamPolicy", "run.jobs.create", "run.jobs.get", "run.jobs.update",
                               "run.operations.get", "run.revisions.get"],
    "specimenRuntimeConnector": ["firebasedataconnect.connectors.impersonateQuery",
                                 "firebasedataconnect.connectors.impersonateMutation"],
    "specimenApiUserLookup": ["firebaseauth.users.get"]}
DATA_ROLES = {  # live definitions of the standing data-release roles that grant every read deploy_data.py makes
    "specimenDataSchemaPublish": ["firebasedataconnect.schemas.get", "firebasedataconnect.connectors.get"],
    "specimenDataStorageRules": ["firebaserules.releases.get", "firebaserules.rulesets.get"],
    "specimenDataSourceBackup": ["cloudsql.backupRuns.create"],
    "specimenDataInventorySqlConnect": ["cloudsql.instances.get", "cloudsql.databases.get"],
    "specimenDataInventoryProjectRead": ["resourcemanager.projects.get"]}
SECRETS = {  # each role's secret_env as scripts/ci/runtime_settings.py commits it (T2b)
    "API": {"LOGFIRE_TOKEN": "specimen-worker-logfire", "SPECIMEN_SOURCE_REGISTRY_JSON": "specimen-source-registry",
            "SPECIMEN_COLLECTION_BINDINGS_JSON": "specimen-collection-bindings"},
    "WORKER": {"HF_TOKEN": "huggingface-runtime-token", "LOGFIRE_TOKEN": "specimen-worker-logfire",
               "SPECIMEN_GOOGLE_MAPS_API_KEY": "specimen-google-maps-key",  # pragma: allowlist secret (a name)
               "SPECIMEN_WORKER_ACTOR_UID": "specimen-worker-actor-uid",
               "SPECIMEN_COLLECTION_BINDINGS_JSON": "specimen-collection-bindings"},
    "SAM": {"LOGFIRE_TOKEN": "specimen-worker-logfire"}}
# Each resource is keyed by the words of its policy read.
P, B = f"projects get-iam-policy {PROJECT}", f"storage buckets get-iam-policy gs://{BUCKET}"
R = "artifacts repositories get-iam-policy specimen-runtime --location=us-east4"
JOB = "run jobs get-iam-policy specimen-worker --region=us-east4"
SA = "iam service-accounts get-iam-policy {}".format
SECRET = "secrets get-iam-policy {}".format  # pragma: allowlist secret (a read command, not a value)
CUSTOM = "projects/specimen-digitization/roles/{}".format
VIEW, CREATE, ACCESS = "roles/storage.objectViewer", "roles/storage.objectCreator", "roles/secretmanager.secretAccessor"


def pinned(name):
    version = VERSIONS[name]
    return f'resource.name.endsWith("/secrets/{name}/versions/{version}")', f"{name.replace('-', '_')}_v{version}"


# (read, role, member, condition) for every standing grant, written out from RELEASE.md section 5.
TABLE = {
    (R, "roles/artifactregistry.writer", BUILD, None), (P, CUSTOM("specimenDataInventoryProjectRead"), BUILD, None),
    (P, CUSTOM("specimenRuntimeRelease"), RELEASE, None), (R, "roles/artifactregistry.reader", RELEASE, None),
    *((SA(EMAIL(name)), "roles/iam.serviceAccountUser", RELEASE, None)
      for name in ("api-runtime", "worker-runtime", "sam-runtime")),
    (P, CUSTOM("specimenDataInventoryProjectRead"), RELEASE, None),
    (P, CUSTOM("specimenRuntimeConnector"), API, None), (P, CUSTOM("specimenRuntimeConnector"), WORKER, None),
    *((B, role, runtime, APP) for runtime in (API, WORKER, SAM) for role in (VIEW, CREATE)),
    (B, VIEW, API, SLIDES), (P, CUSTOM("specimenApiUserLookup"), API, None),
    *((P, CUSTOM(name), DATA, None) for name in ("specimenDataSchemaPublish", "specimenDataStorageRules",
                                                 "specimenDataSourceBackup", "specimenDataInventoryProjectRead")),
    (P, CUSTOM("specimenDataInventorySqlConnect"), DATA, SQL_SOURCE),
    *((SECRET(name), ACCESS, API, pinned(name))
      for name in ("specimen-worker-logfire", "specimen-source-registry", "specimen-collection-bindings")),
    *((SECRET(name), ACCESS, WORKER, pinned(name))
      for name in ("huggingface-runtime-token", "specimen-worker-logfire", "specimen-google-maps-key",
                   "specimen-worker-actor-uid", "specimen-collection-bindings")),
    (SECRET("specimen-worker-logfire"), ACCESS, SAM, pinned("specimen-worker-logfire"))}
INVOKERS = {("run services get-iam-policy specimen-api --region=us-east4", "roles/run.invoker", "allUsers", None),
            (JOB, "roles/run.invoker", API, None), (JOB, "roles/run.invoker", WORKER, None),
            ("run services get-iam-policy specimen-sam --region=us-east4", "roles/run.invoker", WORKER, None)}


def settings(**changes):
    values = {role: {"service_account": EMAIL(f"{role.lower()}-runtime"), "secret_env": env}
              for role, env in SECRETS.items()}
    values.update(PENDING=None, READINESS_GENERATION=None, SAM_CHECKPOINT_SHA256=None, SECRET_VERSIONS=VERSIONS,
                  READINESS_OBJECT="application/sha256/" + hashlib.sha256(MARKER).hexdigest())
    return SimpleNamespace(**{**values, **changes})


class Cloud:
    """gcloud as the plan sees it, keyed by the read's words; an unknown describe answers NOT_FOUND."""

    def __init__(self, answers=None):
        self.answers, self.calls = dict(answers or {}), []

    def __call__(self, args, timeout):
        assert args[-3:] == ["--format=json", f"--project={PROJECT}", "--quiet"] and 0 < timeout <= 30
        key = " ".join(args[:-3])
        assert key.split()[1 if key.split()[0] in ("projects", "secrets") else 2] in ("get-iam-policy", "describe")
        self.calls.append(key)
        answer = self.answers.get(key)
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            return (0, '{"etag": "BwE="}', "") if "get-iam-policy" in key else (1, "", "ERROR: NOT_FOUND")
        return answer if isinstance(answer, tuple) else (0, json.dumps(answer), "")


def live(rows, answers=None):
    """Policies holding exactly these (read, role, member, condition) rows."""
    answers = dict(answers or {})
    for read, role, member, condition in rows:
        binding = {"role": role, "members": [member]}
        if condition:
            binding["condition"] = {"expression": condition[0], "title": condition[1], "description": "d"}
        answers.setdefault(read, {"version": 3, "etag": "BwE=", "bindings": []})["bindings"].append(binding)
    return answers


def existing(data_roles=DATA_ROLES):
    """Every secret, Cloud Run resource and custom role exists; the new roles are exact."""
    answers = {f"secrets describe {name}": {"name": "n"} for name in VERSIONS}
    answers.update({f"run {read.split()[1]} describe {read.split()[3]} --region=us-east4": {} for read, *_ in INVOKERS})
    return answers | {f"iam roles describe {name}": {"stage": "GA", "includedPermissions": permissions}
                      for name, permissions in (PERMISSIONS | data_roles).items()}


def report(answers=None, cloud=None, **changes):
    return G.plan(settings(**changes), runner=cloud or Cloud(answers), clock=lambda: NOW)


def sections(text):
    parts, current = {}, None
    for line in text.splitlines():
        if line.endswith(":") and line[:-1] in TITLES:
            current = parts[line[:-1]] = []
        elif current is not None and line:
            current.append(line)
    return parts


def grants(lines):
    """(read, role, member, condition) of every add-iam-policy-binding command, conditions from their YAML files."""
    found, files = set(), {}
    for index, line in enumerate(lines):
        if line.startswith("cat > "):
            files[shlex.split(line)[2]] = yaml.safe_load("\n".join(lines[index + 1:lines.index("EOF", index)]))
        elif " add-iam-policy-binding " in line:
            words = shlex.split(line)
            assert shlex.join(words) == line
            flags = dict(word[2:].split("=", 1) for word in words if word.startswith("--"))
            condition = files.get(flags.get("condition-from-file"))
            read = " ".join(w for w in words[1:] if not w.startswith(("--project=", "--member=", "--role=", "--cond")))
            found.add((read.replace("add-iam-policy-binding", "get-iam-policy"), flags["role"], flags["member"],
                       condition and (condition["expression"], condition["title"])))
    return found


def reasoned(lines):
    """Every command follows its reason, directly or after its condition file or an earlier command of its step."""
    for index, line in enumerate(lines):
        if line.startswith(("gcloud ", "printf ", "- remove ")):
            before = index - 1
            while lines[before] == "EOF" or lines[before].startswith(("gcloud ", "cat > ", "expression: ", "title: ")):
                before -= 1
            assert lines[before].startswith("# ") and len(lines[before]) > 8, line


def test_an_empty_live_state_lists_every_custom_role_and_grant_with_its_reason(capsys):
    text = report()
    parts = sections(text)
    assert list(parts) == TITLES and text == report(), "every section, in a deterministic order"
    assert G.main(["plan"], runner=Cloud(), settings=settings()) == 0 and capsys.readouterr().out == text + "\n"
    creates = [shlex.split(line) for line in parts["Custom roles to create"] if line.startswith("gcloud ")]
    assert [words[:5] for words in creates] == [["gcloud", "iam", "roles", "create", name] for name in PERMISSIONS]
    for words in creates:
        flags = dict(word[2:].split("=", 1) for word in words[5:])
        assert flags["permissions"].split(",") == PERMISSIONS[words[4]] and flags["title"] and flags["description"]
        assert (flags["project"], flags["stage"]) == (PROJECT, "GA")
    missing = parts["Missing standing grants"]
    assert grants(missing) == TABLE and sum(line.startswith("gcloud ") for line in missing) == len(TABLE)
    assert grants(parts["Waits for the first runtime release"]) == INVOKERS
    assert "application/sha256/<checkpoint digest>/sam3-cache" in parts["Waits for the SAM 3 checkpoint digest"][1]
    assert [parts[title] for title in ("Grants to replace", REMOVE, WINDOW, REVIEW)] == [["(none)"]] * 4
    assert parts[READS] == ["- not compared: a standing data-release role could not be read; see Other owner steps"]
    assert "# owner prerequisite: the custom role specimenDataStorageRules does not exist; restore it" in text
    assert "specimenDataClone" not in text, "the clone roles are never standing"
    assert "sam3-cache" not in "\n".join(parts["Other owner steps"]), "the checkpoint is uploaded: no step names it"
    for title in ("Custom roles to create", "Missing standing grants", "Waits for the first runtime release",
                  "Other owner steps"):
        reasoned(parts[title])


def test_commands_are_exact_round_trip_through_shlex_and_never_deploy():
    text = report(SAM_CHECKPOINT_SHA256=DIGEST)
    lines, parts = text.splitlines(), sections(text)
    for command in (  # --condition=None wherever gcloud's add-iam-policy-binding takes a condition; run jobs does not
        f"gcloud projects add-iam-policy-binding {PROJECT} --member={RELEASE} "
        f"--role={CUSTOM('specimenRuntimeRelease')} --condition=None",
        f"gcloud storage buckets add-iam-policy-binding gs://{BUCKET} --member={API} --role={VIEW} "
        "--condition-from-file=specimen_source_slides.yaml",
        f"gcloud artifacts repositories add-iam-policy-binding specimen-runtime --location=us-east4 "
        f"--project={PROJECT} --member={BUILD} --role=roles/artifactregistry.writer --condition=None",
        f"gcloud iam service-accounts add-iam-policy-binding {EMAIL('sam-runtime')} --project={PROJECT} "
        f"--member={RELEASE} --role=roles/iam.serviceAccountUser --condition=None",
        f"gcloud secrets add-iam-policy-binding huggingface-runtime-token --project={PROJECT} --member={WORKER} "
        f"--role={ACCESS} --condition-from-file=huggingface_runtime_token_v2.yaml",
        f"gcloud run services add-iam-policy-binding specimen-api --region=us-east4 --project={PROJECT} "
        "--member=allUsers --role=roles/run.invoker --condition=None",
        f"gcloud run jobs add-iam-policy-binding specimen-worker --region=us-east4 --project={PROJECT} "
        f"--member={WORKER} --role=roles/run.invoker",
    ):
        assert command in lines
    for title, expression in (("specimen_source_slides", SLIDES[0]), ("huggingface_runtime_token_v2",
                              'resource.name.endsWith("/secrets/huggingface-runtime-token/versions/2")')):
        start = lines.index(f"cat > {title}.yaml <<'EOF'")
        assert lines[start + 1:start + 4] == [f"expression: '{expression}'", f"title: {title}", "EOF"]
    missing = grants(parts["Missing standing grants"])
    assert (B, VIEW, SAM, CHECKPOINT) in missing and parts["Waits for the SAM 3 checkpoint digest"] == ["(none)"]
    assert {c for *_, c in missing if c} == {APP, SLIDES, CHECKPOINT, SQL_SOURCE, *map(pinned, VERSIONS)}
    assert all(shlex.split(line) for line in lines if line.startswith(("gcloud ", "printf ", "cat > ")))
    assert not DEPLOY.search(text) and not [l for l in lines if "deploy" in l.lower() and not l.startswith("# ")]
    other = parts["Other owner steps"]
    assert f"gcloud storage buckets update gs://{BUCKET} --public-access-prevention" in other
    assert f"gcloud services enable billingbudgets.googleapis.com --project={PROJECT}" in other
    assert [shlex.split(line) for line in other if line.startswith("gcloud billing budgets create ")] == [[
        "gcloud", "billing", "budgets", "create", "--billing-account=BILLING_ACCOUNT_ID",
        "--display-name=specimen-digitization USD 25", "--budget-amount=25USD", f"--filter-projects=projects/{PROJECT}",
        "--threshold-rule=percent=0.5", "--threshold-rule=percent=0.9", "--threshold-rule=percent=1.0"]]
    assert any("BILLING_ACCOUNT_ID" in line and "never paste it anywhere" in line for line in other)
    marker = f"gs://{BUCKET}/application/sha256/{hashlib.sha256(MARKER).hexdigest()}"
    upload = shlex.split(next(line for line in other if line.startswith("printf ")))
    assert upload[1].replace("\\n", "\n").encode() == MARKER, "printf writes exactly the committed marker"
    assert upload[2:] == ["|", "gcloud", "storage", "cp", "--if-generation-match=0", "-", marker]
    assert f"gcloud storage objects describe {marker} --format='value(generation)'" in other
    with pytest.raises(ValueError, match="64 lowercase hex"):
        report(SAM_CHECKPOINT_SHA256='c") || true || ("')


def test_a_fully_satisfied_live_state_leaves_nothing_to_do():
    answers = live(TABLE | INVOKERS | {(B, VIEW, SAM, CHECKPOINT)}, existing())
    parts = sections(report(answers, SAM_CHECKPOINT_SHA256=DIGEST, READINESS_GENERATION=1))
    assert all(parts[title] == ["(none)"] for title in TITLES[:-1] if title != READS)
    assert len(parts[READS]) == 6 and all(": granted by specimenData" in line for line in parts[READS])
    assert [line.split()[:3] for line in parts["Other owner steps"] if not line.startswith("# ")] == [
        ["gcloud", "storage", "buckets"], ["gcloud", "services", "enable"], ["gcloud", "billing", "budgets"]]


def test_each_data_release_read_names_the_role_granting_it_or_the_command_that_adds_it():
    roles = {**DATA_ROLES, "specimenDataSchemaPublish": ["firebasedataconnect.schemas.get"],
             "specimenDataStorageRules": ["firebaserules.rulesets.create"],
             "specimenDataSourceBackup": ["cloudsql.databases.get"],
             # A Data Connect read inside the Cloud SQL role's conditioned binding reaches no Data Connect resource.
             "specimenDataInventorySqlConnect": ["cloudsql.instances.get", "firebasedataconnect.connectors.get"]}
    lines = sections(report(existing(roles)))[READS]
    assert [line for line in lines if not line.startswith("# ")] == [
        "- firebasedataconnect.schemas.get: granted by specimenDataSchemaPublish",
        "- cloudsql.instances.get: granted by specimenDataInventorySqlConnect, within its condition "
        "specimen_source_inventory_only",
        "- cloudsql.databases.get: granted by specimenDataSourceBackup",
        f"gcloud iam roles update specimenDataSchemaPublish --project={PROJECT} "
        "--add-permissions=firebasedataconnect.connectors.get",
        f"gcloud iam roles update specimenDataStorageRules --project={PROJECT} "
        "--add-permissions=firebaserules.releases.get,firebaserules.rulesets.get"]
    reasoned(lines)
    for role in set(G.DATA_READS.values()):  # the narrowest standing role only the data release holds
        assert {grant.member for grant in G.STANDING if grant.role == CUSTOM(role)} == {DATA}
        assert role not in G.WINDOW_ONLY and role != "specimenDataInventoryProjectRead"


def test_a_binding_with_an_expired_other_or_no_condition_is_replaced_never_satisfied():
    rows = [(P, CUSTOM("specimenDataSchemaPublish"), DATA, EXPIRED), (B, VIEW, API, APP),
            (B, VIEW, API, (SLIDES[0], "specimen_slides_v0")), (B, CREATE, WORKER, None),
            (SECRET("specimen-worker-logfire"), ACCESS, SAM, None)]
    parts = sections(report(live(rows, existing())))
    replace, missing = parts["Grants to replace"], grants(parts["Missing standing grants"])
    assert grants(replace) == {(P, CUSTOM("specimenDataSchemaPublish"), DATA, None), (B, VIEW, API, SLIDES),
                               (B, CREATE, WORKER, APP),
                               (SECRET("specimen-worker-logfire"), ACCESS, SAM, pinned("specimen-worker-logfire"))}
    assert (B, VIEW, API, APP) not in missing and (B, VIEW, WORKER, APP) in missing and not missing & grants(replace)
    notes = "\n".join(line for line in replace if line.startswith("# "))
    assert all(kind in notes for kind in ("an expired time-bound condition", "another condition", "no condition"))
    assert parts[REVIEW] == parts[REMOVE] == ["(none)"]


def test_grants_outside_the_table_are_removed_time_bounded_or_reviewed_never_missing():
    window_roles = ("specimenDataOwnerBootstrap", "specimenDataInitializerDisposal", "specimenDataCloneCreate",
                    "specimenDataCloneControl", "specimenDataRuntimeAbsence", "specimenDataRestoreAllowanceClaim")
    untimed = ("resource.name.startsWith('projects/specimen-digitization/instances/')", "specimen_untimed_scope")
    rows = [(P, "roles/editor", RELEASE, None), (P, "roles/storage.admin", API, None),
            (SA(EMAIL("api-runtime")), "roles/iam.serviceAccountTokenCreator", WORKER, None),
            (P, CUSTOM("specimenDataInitializeTemporary"), INIT, EXPIRED),
            *((P, CUSTOM(name), DATA, EXPIRED) for name in window_roles),
            (P, CUSTOM("specimenDataCloneCreate"), DATA, None),
            (P, CUSTOM("specimenDataOwnerBootstrap"), DATA, untimed)]
    text = report(live(rows))
    parts = sections(text)
    assert [line for line in parts[REMOVE] if not line.startswith("# ")] == [
        f"gcloud projects remove-iam-policy-binding {PROJECT} --member={RELEASE} --role=roles/editor --condition=None",
        f"gcloud projects remove-iam-policy-binding {PROJECT} --member={DATA} "
        f"--role={CUSTOM('specimenDataCloneCreate')} --condition=None",
        f"- remove {CUSTOM('specimenDataOwnerBootstrap')} for {DATA} on project {PROJECT}; its binding has a "
        "condition without request.time, whose text is not printed"]
    reasoned(parts[REMOVE])
    assert parts[REVIEW] == [
        f"- review: not in the table: roles/iam.serviceAccountTokenCreator for {WORKER} on service account "
        f"{EMAIL('api-runtime')}, with no condition",
        f"- review: not in the table: roles/storage.admin for {API} on project {PROJECT}, with no condition"]
    one, bounded = "- one-time, managed by data_setup_window.py", "- time-bounded; opened through the setup window only"
    restore = f"{bounded} for the first apply's restore check"
    assert {line.split("/roles/")[1].split()[0]: line.split(": projects/")[0] for line in parts[WINDOW]} == {
        **dict.fromkeys(("specimenDataInitializeTemporary", "specimenDataOwnerBootstrap",
                         "specimenDataInitializerDisposal"), one), "specimenDataRuntimeAbsence": bounded,
        **dict.fromkeys(("specimenDataCloneCreate", "specimenDataCloneControl",
                         "specimenDataRestoreAllowanceClaim"), restore)}
    assert len(parts[WINDOW]) == 7 and all(line.endswith(", with an expired time-bound condition")
                                           for line in parts[WINDOW])
    assert "specimen_untimed_scope" not in text and "startsWith('projects" not in text, "no live condition text"
    granted = "\n".join(parts["Missing standing grants"] + parts["Grants to replace"])
    assert not re.search("specimenData(Clone|RuntimeAbsence|RestoreAllowanceClaim|OwnerBootstrap|Initializ)", granted)


def test_secret_grants_follow_runtime_settings_per_identity_secret_and_pinned_version():
    before = grants(sections(report())["Missing standing grants"])
    accessors = [(member, condition) for _, role, member, condition in before if role == ACCESS]
    assert Counter(member for member, _ in accessors) == {API: 3, WORKER: 5, SAM: 1}
    assert {condition[1] for _, condition in accessors} == {  # version 2 of the Hugging Face token, version 1 else
        "specimen_worker_logfire_v1", "specimen_google_maps_key_v1", "specimen_source_registry_v1",
        "specimen_collection_bindings_v1", "specimen_worker_actor_uid_v1", "huggingface_runtime_token_v2"}
    sam = {"service_account": EMAIL("sam-runtime"),
           "secret_env": {**SECRETS["SAM"], "HF_TOKEN": "huggingface-runtime-token"}}
    after = grants(sections(report(SAM=sam))["Missing standing grants"])
    assert after - before == {(SECRET("huggingface-runtime-token"), ACCESS, SAM, pinned("huggingface-runtime-token"))}
    with pytest.raises(ValueError, match="another identity"):
        report(SAM={**sam, "service_account": EMAIL("api-runtime")})
    with pytest.raises(ValueError, match="SECRET_VERSIONS"):
        report(SECRET_VERSIONS={**VERSIONS, "specimen-worker-logfire": None})


def test_no_private_value_reaches_the_output():
    private = ("user:owner-private@example.org", "PRIVATE-UID-7f3a", "PRIVATE-PAYLOAD", "PRIVATE-STDERR", "424242",
               "BwPRIVATEetag")
    answers = live([(P, "roles/viewer", private[0], None), (P, CUSTOM("specimenDataOwnerBootstrap"), private[0], None),
                    (P, ACCESS, f"principal://iam.googleapis.com/projects/{private[4]}/subject/{private[1]}", None),
                    (P, CUSTOM("specimenDataSchemaPublish"), DATA, (f"request.auth.uid == '{private[1]}'", private[1])),
                    (P, CUSTOM("specimenDataRuntimeAbsence"), DATA, (f"resource.name == '{private[1]}'", private[1])),
                    (P, f"organizations/{private[4]}/roles/specimenPrivate", RELEASE, None)])
    answers[P]["etag"], answers[B] = private[5], (1, "", f"ERROR: PERMISSION_DENIED {private[3]}")
    answers["secrets describe specimen-worker-actor-uid"] = {
        "name": f"projects/{private[4]}/secrets/specimen-worker-actor-uid", "labels": {"uid": private[1]},
        "payload": {"data": private[2]}}
    text = report(answers)
    assert [value for value in private if value.lower() in text.lower()] == []
    assert f"- review: not in the table: a role defined outside this project for {RELEASE}" in text
    assert f"- remove {CUSTOM('specimenDataOwnerBootstrap')} for a member whose id is not printed" in text


def test_a_failed_read_is_reported_without_values_and_the_rest_continues():
    denied = (1, "", "ERROR: PERMISSION_DENIED PRIVATE-STDERR")
    text = report(cloud=Cloud(existing() | {
        B: denied, "iam roles describe specimenDataStorageRules": denied,
        "secrets describe specimen-google-maps-key": subprocess.TimeoutExpired(["gcloud"], 30)}))
    parts = sections(text)
    assert parts["Other owner steps"][:3] == [
        "# could not read the custom role specimenDataStorageRules; rerun the plan",
        f"# could not read bucket gs://{BUCKET}; its grants were not compared: rerun the plan",
        "# could not read secret specimen-google-maps-key; its grants were not compared: rerun the plan"]
    unread = (B, SECRET("specimen-google-maps-key"))
    # The Cloud Run resources exist here, so their invoker grants no longer wait: they are missing.
    assert grants(parts["Missing standing grants"]) == {row for row in TABLE | INVOKERS if row[0] not in unread}
    assert parts["Waits for the first runtime release"] == ["(none)"] and "PRIVATE" not in text
    assert "Timeout" not in text


def test_the_plan_sends_only_reads_and_refuses_any_write():
    cloud = Cloud()
    report(cloud=cloud)
    assert len(cloud.calls) == 3 + 5 + 1 + 1 + 3 + 1 + 6 + 3, "roles, project, registry, accounts, bucket, secrets, run"
    calls, gcloud = list(cloud.calls), G.Gcloud(NOW + 60, ceiling=10, runner=cloud, clock=lambda: NOW)
    for write in (("projects", "set-iam-policy", PROJECT, "policy.json"),
                  ("projects", "remove-iam-policy-binding", PROJECT),
                  ("secrets", "versions", "access", "latest", "--secret=specimen-worker-logfire"),
                  ("iam", "roles", "create", "specimenRuntimeRelease"), ("run", "services", "update", "specimen-api"),
                  ("storage", "cp", "-", f"gs://{BUCKET}/x"), ("run", "services", "describe-x", "specimen-api")):
        with pytest.raises(ValueError, match="read-only"):
            G.read(gcloud, *write)
    assert cloud.calls == calls, "a refused command never reaches gcloud"


def test_a_custom_role_with_other_permissions_or_deleted_is_set_exactly():
    release = [*PERMISSIONS["specimenRuntimeRelease"], "run.services.delete"]
    lines = sections(report({
        "iam roles describe specimenRuntimeRelease": {"stage": "GA", "includedPermissions": release},
        "iam roles describe specimenRuntimeConnector": {
            "stage": "GA", "deleted": True, "includedPermissions": PERMISSIONS["specimenRuntimeConnector"]}}))
    commands = [shlex.split(line) for line in lines["Custom roles to create"] if line.startswith("gcloud ")]
    assert [words[3:5] for words in commands] == [
        ["update", "specimenRuntimeRelease"], ["undelete", "specimenRuntimeConnector"],
        ["update", "specimenRuntimeConnector"], ["create", "specimenApiUserLookup"]]
    assert commands[0][5:] == [f"--project={PROJECT}", "--permissions=" + ",".join(release[:-1]), "--stage=GA"]
    reasoned(lines["Custom roles to create"])


def test_the_committed_runtime_settings_agree_with_this_table():
    real = pytest.importorskip("runtime_settings", reason="scripts/ci/runtime_settings.py lands with T2b")
    assert (real.PROJECT, real.REGION, real.BUCKET) == (G.PROJECT, G.REGION, G.BUCKET) == (PROJECT, "us-east4", BUCKET)
    for role in SECRETS:
        assert getattr(real, role)["secret_env"] == SECRETS[role]
        assert getattr(real, role)["service_account"] == getattr(settings(), role)["service_account"]
    assert real.SECRET_VERSIONS == VERSIONS and real.PENDING is None
    assert real.READINESS_OBJECT == settings().READINESS_OBJECT
