"""Private, append-only configuration provisioning called by owner_setup.sh."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
import runtime_settings as settings  # noqa: E402

ALLOWED = frozenset({"specimen-external-emails", "specimen-cloud-import-config",
    "specimen-collection-job-routes", "specimen-google-drive-client", "specimen-dropbox-client",
    "specimen-collection-bindings"})


class Refused(ValueError):
    """Messages are fixed, non-secret reasons only."""


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


@dataclass(frozen=True)
class Entry:
    name: str
    version: int
    value: object


def bundle(directory):
    directory = Path(directory)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise Refused("Intake configuration requires an absolute private directory")
    result = {}
    try:
        for path in sorted(directory.glob("*.json")):
            if path.stem not in ALLOWED or path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
                raise Refused("Intake configuration contains an unsupported file")
            data = json.loads(path.read_bytes())
            if (not isinstance(data, dict) or set(data) != {"version", "value"}
                or type(data["version"]) is not int or data["version"] < 1):
                raise Refused("Each intake configuration file requires a numbered version and value")
            canonical(data["value"])
            result[path.stem] = Entry(path.stem, data["version"], data["value"])
    except (OSError, UnicodeError, ValueError, TypeError):
        raise Refused("Intake configuration files could not be validated; private values withheld") from None
    if not result:
        raise Refused("No approved intake configuration files were found")
    return result


class Secrets:
    def __init__(self, run=subprocess.run):
        self.run = run
        self.inventories = {}

    def command(self, args, *, absent=False):
        try:
            result = self.run(["gcloud", "secrets", *args, f"--project={settings.PROJECT}", "--quiet"],
                capture_output=True, check=False)
        except OSError:
            raise Refused("Configuration storage command could not run") from None
        if result.returncode:
            if absent and b"NOT_FOUND" in result.stderr:
                return None
            raise Refused("Configuration storage request failed; private provider output withheld")
        return result.stdout

    def inventory(self, name):
        if name in self.inventories:
            return self.inventories[name]
        exists = self.command(["describe", name, "--format=value(name)"], absent=True)
        if exists is None:
            answer = None
        else:
            try:
                rows = json.loads(self.command(["versions", "list", name, "--format=json(name,state)"]))
                if not isinstance(rows, list):
                    raise ValueError
                answer = {}
                for row in rows:
                    match = re.fullmatch(r"projects/(?:" + re.escape(settings.PROJECT) + "|" + settings.PROJECT_NUMBER
                        + r")/secrets/" + re.escape(name) + r"/versions/([1-9][0-9]*)", row["name"])
                    if not match or int(match[1]) in answer or row["state"] not in {"ENABLED", "DISABLED", "DESTROYED"}:
                        raise ValueError
                    answer[int(match[1])] = row["state"]
            except (ValueError, TypeError, KeyError):
                raise Refused("Configuration version inventory was not valid") from None
        self.inventories[name] = answer
        return answer

    def read(self, name, version):
        versions = self.inventory(name)
        if versions is None or versions.get(version) != "ENABLED":
            raise Refused("A required numbered configuration version is unavailable")
        return self.command(["versions", "access", str(version), f"--secret={name}"])

    def json(self, name, version):
        try:
            return json.loads(self.read(name, version))
        except (ValueError, TypeError):
            raise Refused("Stored configuration was not valid JSON; private values withheld") from None


def validate(entries, secrets):
    """All local shapes and cross-secret dependencies, before any write."""
    from specimen_digitization.application.runtime_auth import validated_external_emails
    from specimen_digitization.application.runtime_config import collection_worker_jobs
    from uuid import UUID

    try:
        for name, entry in entries.items():
            value = entry.value
            if name == "specimen-external-emails":
                if not isinstance(value, list): raise ValueError
                validated_external_emails(value)
            elif name in {"specimen-google-drive-client", "specimen-dropbox-client"}:
                if (not isinstance(value, dict) or set(value) != {"client_secret"}
                    or not isinstance(value["client_secret"], str) or not 1 <= len(value["client_secret"]) <= 4096
                    or not value["client_secret"].isprintable()):
                    raise ValueError
        config = entries.get("specimen-cloud-import-config")
        if config:
            if not isinstance(config.value, dict) or not config.value or set(config.value) - {"google_drive", "dropbox"}:
                raise ValueError
            for provider, value in config.value.items():
                expected_secret = "specimen-google-drive-client" if provider == "google_drive" else "specimen-dropbox-client"  # pragma: allowlist secret (resource names)
                expected_keys = {"client_id", "client_secret_ref", "redirect_uri"}
                if provider == "google_drive": expected_keys |= {"picker_api_key", "picker_app_id"}
                if not isinstance(value, dict) or set(value) != expected_keys:
                    raise ValueError
                if any(not isinstance(field, str) or not field or not field.isprintable() for field in value.values()):
                    raise ValueError
                if value["redirect_uri"] != f"https://specimen-api-{settings.PROJECT_NUMBER}.{settings.REGION}.run.app/v1/intake/oauth/callback":
                    raise ValueError
                match = re.fullmatch(r"projects/(?:" + settings.PROJECT + "|" + settings.PROJECT_NUMBER
                    + ")/secrets/" + expected_secret + r"/versions/([1-9][0-9]*)", value["client_secret_ref"])
                if not match or (expected_secret in entries and int(match[1]) != entries[expected_secret].version):
                    raise ValueError
                if expected_secret not in entries:
                    client = secrets.json(expected_secret, int(match[1]))
                    if not isinstance(client, dict) or not isinstance(client.get("client_secret"), str) or not client["client_secret"]:
                        raise ValueError
                if provider == "google_drive" and (value["picker_app_id"] != settings.PROJECT_NUMBER
                        or not value["client_id"].endswith(".apps.googleusercontent.com")):
                    raise ValueError
        bindings_entry = entries.get("specimen-collection-bindings")
        routes_entry = entries.get("specimen-collection-job-routes")
        if bindings_entry or routes_entry:
            before = secrets.json("specimen-collection-bindings", settings.CORE_SECRET_VERSIONS["specimen-collection-bindings"])
            bindings = bindings_entry.value if bindings_entry else before
            if (not isinstance(before, dict) or not isinstance(bindings, dict)
                or any(bindings.get(key) != value for key, value in before.items())):
                raise ValueError
            for key, value in bindings.items():
                if str(UUID(key)) != key or not isinstance(value, str) or not value: raise ValueError
            additions = set(bindings) - set(before)
            e2e = {key for key, value in bindings.items() if value == "intake-e2e"}
            if len(e2e) != 1 or additions - e2e or len(additions) > 1:
                raise ValueError
            if routes_entry:
                routes = dict(collection_worker_jobs({"SPECIMEN_COLLECTION_WORKER_JOBS_JSON": json.dumps(routes_entry.value)}, settings.PROJECT))
                actor = secrets.read("specimen-worker-actor-uid", settings.CORE_SECRET_VERSIONS["specimen-worker-actor-uid"]).decode()
                if len(routes) != 1: raise ValueError
                for scope, route in routes.items():
                    if scope.split("/")[1] not in e2e or route["actor_uid"] != actor: raise ValueError
                    for lane in ("intake", "worker"):
                        if not route[f"{lane}_job"].startswith(f"{settings.PREFIX}/jobs/specimen-{lane}-"):
                            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise Refused("Intake configuration shapes, pinned references or additive collection bindings do not match") from None


def preflight(entries, secrets):
    validate(entries, secrets)
    plan = []
    for name, entry in entries.items():
        versions = secrets.inventory(name)
        if versions is not None and entry.version in versions:
            if versions[entry.version] != "ENABLED" or canonical(secrets.json(name, entry.version)) != canonical(entry.value):
                raise Refused("An existing target version differs; no configuration was written")
            continue
        if entry.version != max(versions or {}, default=0) + 1:
            raise Refused("The requested target is not the next numbered version; no configuration was written")
        plan.append((entry, versions is None))
    return plan


def provision(directory, *, dry_run, secrets=None):
    secrets = secrets or Secrets()
    entries = bundle(directory)
    plan = preflight(entries, secrets)
    for entry, create in plan:
        if dry_run:
            print(f"would provision {entry.name} version {entry.version}; values withheld")
            continue
        if create:
            secrets.command(["create", entry.name, "--replication-policy=automatic", "--format=value(name)"])
        with tempfile.TemporaryDirectory(prefix="specimen-intake-config-") as work:
            path = Path(work) / "payload.json"
            path.write_bytes(canonical(entry.value))
            path.chmod(0o600)
            result = secrets.command(["versions", "add", entry.name, f"--data-file={path}", "--format=value(name)"])
        expected = {f"projects/{project}/secrets/{entry.name}/versions/{entry.version}".encode()
                    for project in (settings.PROJECT, settings.PROJECT_NUMBER)}
        if result.strip() not in expected:
            raise Refused("Created configuration version did not match the requested number")
        secrets.inventories.pop(entry.name, None)
        if canonical(secrets.json(entry.name, entry.version)) != canonical(entry.value):
            raise Refused("Created configuration version did not match its private file")
        print(f"verified {entry.name} version {entry.version}; values withheld")
    print(f"configuration bundle: {len(plan)} version(s) {'would be added' if dry_run else 'added'}; runtime pins unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SPECIMEN_OWNER_SETUP_MODE") != "intake":
        raise Refused("Run configuration provisioning through owner_setup.sh --intake-only")
    provision(args.directory, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Refused as error:
        sys.exit(f"Intake configuration provisioning refused: {error}")
    except (OSError, ValueError, TypeError):
        sys.exit("Intake configuration provisioning refused; private values and provider output withheld")
