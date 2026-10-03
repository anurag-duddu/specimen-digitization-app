"""Deploy the pushed API image to Cloud Run and keep the service public; runtime-release.yml runs this.

Every setting comes from scripts/ci/runtime_settings.py, so a changed value is a reviewed pull request.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
import runtime_settings as settings  # noqa: E402

SERVICE = "specimen-api"
LOCATION = ["--region", settings.REGION, "--project", settings.PROJECT]
IMAGE = re.compile(rf"{settings.REGION}-docker\.pkg\.dev/{settings.PROJECT}/specimen-runtime/api@sha256:[0-9a-f]{{64}}")
SHA = re.compile(r"[0-9a-f]{40}")
RUN = re.compile(r"[1-9][0-9]*")
OWNER_HINT = "public access is not set: the owner runs scripts/ops/owner_setup.sh once"
READ_POLICY = ["gcloud", "run", "services", "get-iam-policy", SERVICE, *LOCATION, "--format", "json"]
ADD_PUBLIC = ["gcloud", "run", "services", "add-iam-policy-binding", SERVICE, *LOCATION,
              "--member", "allUsers", "--role", "roles/run.invoker", "--quiet"]


def api_env() -> dict[str, str]:
    generation = settings.READINESS_GENERATION
    if type(generation) is not int or generation < 1:
        raise ValueError("READINESS_GENERATION is not set in runtime_settings.py")
    return {**settings.API["env"], "SPECIMEN_READINESS_GENERATION": str(generation)}


def env_file_text() -> str:
    """A YAML mapping; JSON quoting keeps values such as "true" and "1.0" strings, which gcloud requires."""
    return "".join(f"{name}: {json.dumps(value)}\n" for name, value in sorted(api_env().items()))


def secret_flag() -> str:
    """ENV=secret:version pairs. The version is a committed number, never "latest", so a rotation is a reviewed change."""
    pairs = []
    for name, secret in settings.API["secret_env"].items():
        version = settings.SECRET_VERSIONS[secret]
        if type(version) is not int or version < 1:
            raise ValueError(f"secret {secret} has no pinned numeric version in runtime_settings.py")
        pairs.append(f"{name}={secret}:{version}")
    return ",".join(pairs)


def revision_suffix(sha: str, run_id: str, attempt: str) -> str:
    suffix = f"{sha[:12]}-{run_id}-{attempt}"
    # Cloud Run names the revision "<service>-<suffix>": at most 63 lowercase letters, digits and dashes.
    if len(f"{SERVICE}-{suffix}") > 63 or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", suffix):
        raise ValueError(f"revision name {SERVICE}-{suffix} is not a valid Cloud Run name")
    return suffix


def deploy_command(image: str, sha: str, run_id: str, attempt: str, env_file: Path) -> list[str]:
    if not IMAGE.fullmatch(image):
        raise ValueError("the image must be the pushed API digest: "
                         f"{settings.REGION}-docker.pkg.dev/{settings.PROJECT}/specimen-runtime/api@sha256:<64 hex>")
    if not SHA.fullmatch(sha) or not RUN.fullmatch(run_id) or not RUN.fullmatch(attempt):
        raise ValueError("GITHUB_SHA, GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT must name this release run")
    api = settings.API
    # No allow-unauthenticated flag either way: the release identity may deploy before it may change access,
    # and ensure_public() below owns that one binding.
    return [
        "gcloud", "run", "deploy", SERVICE, *LOCATION, "--platform", "managed", "--quiet",
        "--image", image, "--service-account", api["service_account"],
        "--ingress", "all", "--port", "8080", "--cpu", api["cpu"], "--memory", api["memory"],
        "--min-instances", "0", "--max-instances", str(api["max_instances"]),
        "--concurrency", str(api["concurrency"]), "--timeout", str(api["timeout_seconds"]),
        "--execution-environment", "gen2", "--cpu-throttling", "--no-cpu-boost",
        "--revision-suffix", revision_suffix(sha, run_id, attempt),
        "--labels", f"source-sha={sha},release-run={run_id}",
        "--env-vars-file", str(env_file), "--set-secrets", secret_flag(),
    ]


def is_public(policy: object) -> bool:
    bindings = policy.get("bindings", []) if isinstance(policy, dict) else []
    return any(binding.get("role") == "roles/run.invoker" and "allUsers" in binding.get("members", [])
               and not binding.get("condition") for binding in bindings)


def ensure_public(env: dict[str, str]) -> None:
    # Read first: once the binding exists, later releases change no access policy at all.
    read = subprocess.run(READ_POLICY, env=env, capture_output=True, text=True, check=False)
    try:
        if read.returncode == 0 and is_public(json.loads(read.stdout)):
            print("public access: already set", flush=True)
            return
    except ValueError:
        pass
    if subprocess.run(ADD_PUBLIC, env=env, check=False).returncode != 0:
        sys.exit(OWNER_HINT)
    print("public access: set", flush=True)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        sys.exit("usage: deploy_api.py IMAGE_DIGEST_REFERENCE")
    with tempfile.TemporaryDirectory() as temp:
        env_file = Path(temp) / "api-env.yaml"
        try:
            command = deploy_command(argv[1], os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_RUN_ID", ""),
                                     os.environ.get("GITHUB_RUN_ATTEMPT", ""), env_file)
            settings_text = env_file_text()
        except ValueError as error:
            sys.exit(f"not deployed: {error}")
        if shutil.which("gcloud") is None:
            sys.exit("not deployed: gcloud is not on PATH; the release job needs the Google Cloud CLI")
        env_file.write_text(settings_text)
        # Never wait at a prompt, and skip gcloud's "is the API enabled" lookup: the release identity cannot read it.
        env = {**os.environ, "CLOUDSDK_CORE_DISABLE_PROMPTS": "1", "CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API": "false"}
        print("deploy:", shlex.join(command), flush=True)
        if subprocess.run(command, env=env, check=False).returncode != 0:
            sys.exit("not deployed: gcloud run deploy failed; its output is above")
    ensure_public(env)
    print(f"deployed {argv[1]} as revision {SERVICE}-{command[command.index('--revision-suffix') + 1]}", flush=True)


if __name__ == "__main__":
    main(sys.argv)
