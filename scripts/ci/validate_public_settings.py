#!/usr/bin/env python3
"""Check approved public web settings without printing their values."""
import os
import re
from urllib.parse import urlsplit


def validate(env):
    api = env.get("SPECIMEN_API_BASE_URL", "")
    key = env.get("SPECIMEN_RECAPTCHA_SITE_KEY", "")
    if env.get("SPECIMEN_AUTH_EMULATOR_HOST") or env.get("SPECIMEN_LOCAL_SYNTHETIC", "false") != "false":
        raise ValueError("production cannot use emulator or synthetic settings")
    if not api and not key:
        return  # Existing Hosting setup screen remains releasable before bootstrap.
    if not api or not key:
        raise ValueError("public API URL and App Check site key must be configured together")
    try:
        parsed = urlsplit(api)
        port = parsed.port
    except ValueError:
        raise ValueError("invalid public API URL") from None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or "?" in api or "#" in api or "\\" in api or re.search(r"\s", api)
            or port not in (None, 443)
            or parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("invalid public API URL")
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,256}", key):
        raise ValueError("invalid public App Check site key")


if __name__ == "__main__":
    try:
        validate(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Public build settings validated; values omitted.")
