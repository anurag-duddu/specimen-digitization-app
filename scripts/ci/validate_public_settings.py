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


ADDRESS = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
CONTACT_FORMS = (
    re.compile(rf"^(?P<name>[^<>@,]{{1,120}}?)\s*<(?P<address>{ADDRESS})>$"),
    re.compile(rf"^(?P<name>[^<>@,]{{1,120}}?)\s*,\s*(?P<address>{ADDRESS})$"),
    re.compile(rf"^(?P<address>{ADDRESS})$"),
)


def validate_contact(env):
    """The optional administrator contact shown in the client's help and
    "ask your administrator" messages. It is public and non-secret; the
    client parses "Name <address>", "Name, address" or a bare address
    (see lib/src/administrator_contact.dart), so the same three forms are
    the only ones accepted here."""
    contact = env.get("SPECIMEN_ADMIN_CONTACT", "")
    if not contact:
        return
    if len(contact) > 200 or re.search(r"[\x00-\x1f\x7f\"']", contact):
        raise ValueError("invalid administrator contact")
    if not any(form.fullmatch(contact.strip()) for form in CONTACT_FORMS):
        raise ValueError("invalid administrator contact")


PILOT_SCOPE_MAX = 80


def validate_pilot_scope(env):
    """The bounded pilot this deployment serves, in the reviewer's own words.

    `scripts/ci/build_web.sh` forwards it to `pilotScopeDefine` in
    lib/src/widgets/environment_banner.dart, where it is drawn straight into
    the band's headline: "Bounded pilot: <scope>. Records here are real."

    It is optional and stands alone: a pilot can be stamped on a build that
    has no API URL yet, and the empty default is the honest state of a build
    nobody stamped, which shows no band. What it may not be is a value the
    band cannot draw. The band promises one line or two at every text scale,
    so the scope is bounded at 80 characters. It is compared against its own
    trimmed form because the client trims before deciding whether a pilot was
    stamped at all: a value that is only whitespace would silently turn the
    pilot band off, and a value with an accidental trailing newline from a
    repository variable would be a stamp nobody can see is wrong. Control
    characters cannot reach the band as anything a reviewer can read.

    The value is public and non-secret, but it is never printed here: a
    reason names the rule that failed, not the string that failed it.
    """
    scope = env.get("SPECIMEN_PILOT_SCOPE", "")
    if not scope:
        return
    if scope != scope.strip():
        raise ValueError("invalid pilot scope: leading or trailing whitespace")
    if len(scope) > PILOT_SCOPE_MAX:
        raise ValueError(
            f"invalid pilot scope: longer than {PILOT_SCOPE_MAX} characters")
    if not scope.isprintable():
        raise ValueError("invalid pilot scope: unprintable character")


if __name__ == "__main__":
    try:
        validate(os.environ)
        validate_contact(os.environ)
        validate_pilot_scope(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Public build settings validated; values omitted.")
