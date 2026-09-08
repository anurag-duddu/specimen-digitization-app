"""Read immutable build provenance embedded inside the installed package."""

import json
from importlib.resources import files


def version():
    try:
        metadata = json.loads(
            files("specimen_digitization").joinpath("_build.json").read_text()
        )
        source_sha = metadata.get("source_sha", "unknown")
    except (FileNotFoundError, ValueError):
        source_sha = "unknown"
    return {"service": "specimen-worker", "source_sha": source_sha}
