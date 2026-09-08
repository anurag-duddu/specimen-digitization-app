"""Read-only cloud metadata inventory, saved privately with sanitized console output.

Never enables APIs, accesses secret versions, executes SQL, downloads objects, or
changes gcloud identity/project defaults. Run only after account authentication.
Grouping and source order must be established separately before freezing ten.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from specimen_digitization.application.pilot_manifest import write_private

PROJECT = "specimen-digitization"
BUCKET = "specimen-digitization.firebasestorage.app"


def run_gcloud(command, timeout):
    # A read command must never offer to enable a missing API or prompt for auth.
    env = dict(os.environ, CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API="false",
               CLOUDSDK_CORE_DISABLE_PROMPTS="true")
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, env=env)


def inventory(destination: Path):
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(destination, 0o700)
    queries = {
        "buckets": ["storage", "buckets", "list"],
        "bucket_policy": ["storage", "buckets", "get-iam-policy", "gs://" + BUCKET],
        # A bare bucket means bucket/*, omitting nested originals. This CLI
        # includes live and noncurrent generations by default; do not use stat.
        "objects": ["storage", "objects", "list", "gs://" + BUCKET + "/**"],
        "sql": ["sql", "instances", "describe", "specimen-digitization-instance"],
        "backups": ["sql", "backups", "list", "--instance=specimen-digitization-instance"],
        "databases": ["sql", "databases", "list", "--instance=specimen-digitization-instance"],
        "project_iam": ["projects", "get-iam-policy", PROJECT],
        "service_accounts": ["iam", "service-accounts", "list"],
        "secret_metadata": ["secrets", "list"],
    }
    for label, operation in queries.items():
        command = ["gcloud", *operation, "--project=" + PROJECT, "--format=json"]
        result = run_gcloud(command, timeout=180)
        observed = datetime.now(timezone.utc).isoformat()
        if result.returncode:
            write_private(destination / (label + ".json"), {
                "observed_at": observed, "status": "failed", "command": command,
                "private_error": result.stderr,
            })
            raise RuntimeError("Cloud metadata query failed; inspect private evidence. No data scope frozen.")
        data = json.loads(result.stdout)
        write_private(destination / (label + ".json"), {
            "observed_at": observed, "status": "confirmed", "command": command, "data": data,
        })
        print(json.dumps({"query": label, "status": "confirmed",
                          "records": len(data) if isinstance(data, list) else None}))
    # gcloud has no stable SQL Connect resource surface; use documented REST GET.
    token = run_gcloud(["gcloud", "auth", "print-access-token", "--project=" + PROJECT], timeout=60)
    if token.returncode:
        raise RuntimeError("SQL Connect metadata authentication unavailable")
    root = ("https://firebasedataconnect.googleapis.com/v1/projects/" + PROJECT
            + "/locations/us-east4/services/specimen-digitization-service")
    for label, suffix in (("data_connect_service", ""), ("connectors", "/connectors"), ("schemas", "/schemas")):
        pages, page_token = [], None
        while True:
            from urllib.parse import urlencode
            url = root + suffix + ("?" + urlencode({"pageToken": page_token}) if page_token else "")
            request = Request(url, headers={"Authorization": "Bearer " + token.stdout.strip()})
            try:
                with urlopen(request, timeout=30) as response:
                    data = json.load(response)
            except HTTPError as exc:
                write_private(destination / (label + ".json"), {"status": "failed", "http_status": exc.code})
                raise RuntimeError("SQL Connect metadata unavailable; no schema or connector readiness proven") from None
            pages.append(data)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        write_private(destination / (label + ".json"), {
            "observed_at": datetime.now(timezone.utc).isoformat(), "status": "confirmed", "pages": pages,
        })
        print(json.dumps({"query": label, "status": "confirmed", "pages": len(pages)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory outside Git")
    args = parser.parse_args()
    try:
        # Validate location before any network I/O or metadata is written.
        if any((p / ".git").exists() for p in args.output_dir.resolve().parents):
            raise ValueError("Private cloud metadata must remain outside Git")
        inventory(args.output_dir)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        parser.exit(2, "Inventory incomplete; inspect private evidence and authentication. No cloud writes performed.\n")


if __name__ == "__main__":
    main()
