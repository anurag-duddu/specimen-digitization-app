"""Provision one restricted Picker key through owner_setup.sh --intake-only.

Google's web Picker guide requires both the application's origin and the
docs.google.com iframe origin. Browser calls here use only Picker; server-side
Drive requests use OAuth, so this key has no Drive API target.
https://developers.google.com/workspace/drive/picker/guides/web-picker#configure_your_environment
https://cloud.google.com/sdk/gcloud/reference/services/api-keys/create
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import intake_config as config

KEY_ID = "specimen-intake-google-picker"
DISPLAY_NAME = "Specimen intake Google Picker"
ANNOTATIONS = {"specimen-purpose": "intake-picker"}
ORIGIN = f"https://specimen-api-{config.settings.PROJECT_NUMBER}.{config.settings.REGION}.run.app"
REFERRERS = (ORIGIN + "/*", "https://docs.google.com/*")
RESOURCE = f"projects/{config.settings.PROJECT_NUMBER}/locations/global/keys/{KEY_ID}"
CONFIG_NAME = "specimen-cloud-import-config"
PENDING = "pending-dedicated-picker-key"


class Keys:
    def __init__(self, run=subprocess.run, pause=time.sleep):
        self.run, self.pause = run, pause

    def command(self, args, *, absent=False):
        try:
            result = self.run(["gcloud", "services", "api-keys", *args,
                f"--project={config.settings.PROJECT}", "--quiet"],
                capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise config.Refused("Picker key request outcome was not confirmed; provider output withheld") from None
        if result.returncode:
            if absent and b"NOT_FOUND" in result.stderr:
                return None
            raise config.Refused("Picker key request failed; verify API Keys service and owner permissions; output withheld")
        return result.stdout

    def describe(self):
        raw = self.command(["describe", KEY_ID, "--location=global",
            "--format=json(name,displayName,annotations,restrictions,deleteTime,serviceAccountEmail)"], absent=True)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            restrictions = value["restrictions"]
            targets = restrictions["apiTargets"]
            browser = restrictions["browserKeyRestrictions"]
            referrers = browser["allowedReferrers"]
            if (value["name"] != RESOURCE or value["displayName"] != DISPLAY_NAME
                or value.get("annotations") != ANNOTATIONS or value.get("deleteTime")
                or value.get("serviceAccountEmail")
                or set(restrictions) != {"browserKeyRestrictions", "apiTargets"}
                or set(browser) != {"allowedReferrers"} or not isinstance(referrers, list)
                or len(referrers) != len(REFERRERS) or set(referrers) != set(REFERRERS)
                or not isinstance(targets, list) or len(targets) != 1
                or set(targets[0]) - {"service", "methods"}
                or targets[0]["service"] != "picker.googleapis.com" or targets[0].get("methods", []) != []):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise config.Refused("Dedicated Picker key identity or exact API/browser restrictions differ; no key was changed") from None
        return value

    def create(self):
        # The key is restricted in the create request, never unrestricted first.
        # One write only. A lost response is reconciled by the deterministic ID.
        try:
            self.command(["create", f"--key-id={KEY_ID}", f"--display-name={DISPLAY_NAME}",
                "--annotations=specimen-purpose=intake-picker", "--api-target=service=picker.googleapis.com",
                f"--allowed-referrers={','.join(REFERRERS)}", "--format=value(name)"])
        except config.Refused:
            pass
        for attempt in range(3):
            if attempt:
                self.pause(attempt)
            if self.describe() is not None:
                return
        raise config.Refused("Picker key creation was not confirmed; rerun the same setup to reconcile its fixed ID")

    def key_string(self):
        try:
            value = self.command(["get-key-string", KEY_ID, "--location=global", "--format=value(keyString)"]).decode().strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", value):
                raise ValueError
            return value
        except (UnicodeError, ValueError):
            raise config.Refused("Dedicated Picker key value was not valid; private output withheld") from None


def resolved_entries(entries, key):
    result = dict(entries)
    value = copy.deepcopy(entries[CONFIG_NAME].value)
    value["google_drive"]["picker_api_key"] = key
    result[CONFIG_NAME] = replace(entries[CONFIG_NAME], value=value)
    return result


def save_wrapper(path, before, entry):
    """Replace only the selected wrapper, atomically, with private permissions."""
    if path.is_symlink() or path.read_bytes() != before:
        raise config.Refused("Private provider wrapper changed during setup; rerun without concurrent edits")
    descriptor, temporary = tempfile.mkstemp(prefix=".picker-config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(config.canonical({"version": entry.version, "value": entry.value}))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def provision(directory, *, dry_run, keys=None, secrets=None):
    keys, secrets = keys or Keys(), secrets or config.Secrets()
    entries = config.bundle(directory)
    try:
        provider = entries[CONFIG_NAME].value["google_drive"]
        current = provider["picker_api_key"]
        if not isinstance(current, str):
            raise ValueError
        path = Path(directory) / f"{CONFIG_NAME}.json"
        before = path.read_bytes()
        if config.canonical(json.loads(before)) != config.canonical({
                "version": entries[CONFIG_NAME].version, "value": entries[CONFIG_NAME].value}):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise config.Refused("Picker setup requires the approved Google provider wrapper with an empty or matching key") from None
    # Empty keys cannot pass the ordinary provisioner. This temporary value is
    # used only for validation/preflight and is never persisted or provisioned.
    pending = resolved_entries(entries, current or PENDING)
    config.validate(pending, secrets)
    existing = keys.describe()
    if existing is None:
        if current:
            raise config.Refused("The dedicated Picker key is absent but the wrapper already holds a key; no rotation attempted")
        plan = config.preflight(pending, secrets)
        versions = secrets.inventory(CONFIG_NAME)
        if versions is not None and entries[CONFIG_NAME].version in versions:
            raise config.Refused("The provider target already exists without a confirmed dedicated key; no key was created")
        if not dry_run:
            keys.create()
    if dry_run and existing is None:
        print(f"would create {KEY_ID} restricted to picker.googleapis.com and {', '.join(REFERRERS)}; values withheld")
    else:
        key = keys.key_string()
        if current and current != key:
            raise config.Refused("The private provider wrapper does not match the dedicated Picker key; no configuration was written")
        entries = resolved_entries(entries, key)
        secrets.inventories.clear()
        plan = config.preflight(entries, secrets)
        if not dry_run and not current:
            save_wrapper(path, before, entries[CONFIG_NAME])
        print(f"verified {KEY_ID} exact API/browser restrictions; values withheld")
    if dry_run:
        for entry, _ in plan:
            print(f"would provision {entry.name} version {entry.version}; values withheld")
        print("Picker/configuration dry run complete; no keys, private files, configuration or IAM changed")
        return
    # Re-read every target after resolving the key. Concurrent differences stop
    # all Secret Manager appends; a rerun reconciles the same key and wrapper.
    secrets.inventories.clear()
    config.provision(directory, dry_run=False, secrets=secrets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SPECIMEN_OWNER_SETUP_MODE") != "intake":
        raise config.Refused("Run Picker provisioning through owner_setup.sh --intake-only --intake-picker-key")
    provision(args.directory, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except config.Refused as error:
        sys.exit(f"Intake Picker provisioning refused: {error}")
    except (OSError, ValueError, TypeError, KeyError):
        sys.exit("Intake Picker provisioning refused; private values and provider output withheld")
