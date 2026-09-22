#!/usr/bin/env python3
"""Serve the built web release and check every route the router declares.

Why this exists
---------------
`scripts/ci/smoke_hosting.sh` checks the public site after a deploy. Nothing
checked the artifact before it, so the first reader of a broken deep link, a
shipped design system gallery or a malformed deployment marker was production.
This closes that gap inside the job that builds the artifact.

It serves `build/web` on the loopback interface with the rewrite rules
`firebase.json` declares, asks for every location
`apps/specimen_digitization/lib/src/app/app_router.dart` mounts, and checks:

1. Every declared route answers with the application shell. Firebase Hosting
   rewrites every unmatched path to `/index.html`, so a deep link, a reload and
   a bookmark all have to land on the application rather than on a 404. The
   rewrite is read out of `firebase.json` rather than assumed, and a real file
   is checked to still be served as itself.
2. The design system gallery is not in the release bundle. The route is mounted
   behind `if (!kReleaseMode)`, and the strings only the gallery can contribute
   must not appear in `main.dart.js`.
3. `deployment.json` carries exactly the marker `scripts/ci/deploy_hosting.sh`
   and `scripts/ci/smoke_hosting.sh` verify, in the exact shape their streaming
   `jq` filters accept. A marker that fails here fails the deploy guard later,
   where the only way to learn about it is a refused production release.
4. Every response carries the security headers `firebase.json` declares. The
   local server applies the declared `headers` blocks the same way Hosting
   does, and the sweep asks for them by name, so a header dropped from the
   configuration fails here rather than on the public site. What the set must
   contain is stated in `SECURITY_HEADERS` below; the values come out of
   `firebase.json`, so the two have to agree.

This script never contacts a live host. It binds 127.0.0.1 on an ephemeral
port, serves files out of a directory, and makes no outbound request. It
deploys nothing and it changes nothing in the artifact.

Python 3.12, standard library only.
"""

from __future__ import annotations

import argparse
import http.client
import json
import mimetypes
import posixpath
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

EXPECTED_REPOSITORY = "anurag-duddu/specimen-digitization-app"
EXPECTED_TITLE = "<title>Specimen Digitization</title>"
EXPECTED_BOOTSTRAP = "flutter_bootstrap.js"
MARKER_NAME = "deployment.json"
BUNDLE_NAME = "main.dart.js"

# The one occurrence of the gallery location the release bundle may carry.
#
# `AppRoutes.isGlobalLocation` in lib/src/app/routes.dart compares a location
# against `/gallery` so that opening the gallery does not send a signed in
# reviewer home. That comparison is live code in every build, so the literal
# survives tree shaking even though the route behind `if (!kReleaseMode)` does
# not. The gallery screen's own absence is what this file actually proves, by
# the marker strings below; this allowance keeps the location count honest
# instead of asserting something the compiler does not do.
GALLERY_LOCATION_ALLOWANCE = 1

# A gallery marker has to be long enough and specific enough that its presence
# in a bundle means gallery code was compiled into it.
MARKER_MIN_LENGTH = 16

# The headers every response from the deployed site has to carry, by lowercase
# name and exact value. `firebase.json` is what actually sets them; this table
# is what makes their absence a failure, so an entry deleted from the hosting
# configuration is caught in the job that builds the artifact.
#
# There is deliberately no `script-src` or `style-src`. Flutter web boots from
# an inline script the build writes into `index.html` and fetches CanvasKit and
# its wasm from `gstatic.com`, so a source list narrow enough to be worth
# having would have to name the engine's own hosts and would break on the next
# engine revision. What is here is the part a document policy can state without
# guessing: the page may not be framed, may embed no plugin, and may not have
# its base URL rewritten. There is no COOP or COEP either: cross origin
# isolation is not required by anything this client does, and turning it on
# would break the reCAPTCHA Enterprise frame App Check depends on.
#
# `Permissions-Policy` denies all three: the web client asks for none of them.
# The in app camera is behind `!kIsWeb` (`lib/src/intake.dart`,
# `_cameraAvailable`), so the capture button is not drawn on the web at all,
# and nothing under `lib/` or `web/` reads a microphone or a location.
SECURITY_HEADERS: dict[str, str] = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "content-security-policy": (
        "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    ),
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


class SmokeError(Exception):
    """A check could not be run at all, as opposed to a check that failed."""


# ---------------------------------------------------------------------------
# Dart source reading
# ---------------------------------------------------------------------------


def mask_source(source: str) -> str:
    """Return `source` with comments and string contents blanked.

    Indices are preserved, so the result can be searched for code structure
    (parentheses, argument names, `if (!kReleaseMode)`) without a comment or a
    string literal ever being mistaken for code. Quote characters are kept, so
    a literal's boundaries are still visible.
    """
    out = list(source)
    i = 0
    n = len(source)
    while i < n:
        char = source[i]
        if char == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if char == "/" and i + 1 < n and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for position in range(i, end):
                if source[position] != "\n":
                    out[position] = " "
            i = end
            continue
        if char in "'\"":
            triple = source[i : i + 3]
            if triple in ("'''", '"""'):
                end = source.find(triple, i + 3)
                end = n if end < 0 else end + 3
                for position in range(i + 3, min(end - 3, n)):
                    if source[position] != "\n":
                        out[position] = " "
                i = end
                continue
            i += 1
            while i < n:
                if source[i] == "\\":
                    out[i] = " "
                    if i + 1 < n:
                        out[i + 1] = " "
                    i += 2
                    continue
                if source[i] == char or source[i] == "\n":
                    i += 1
                    break
                out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def read_route_constants(routes_dart: Path) -> dict[str, str]:
    """The `AppRoutes` string constants, by name."""
    source = routes_dart.read_text(encoding="utf-8")
    pattern = re.compile(r"static\s+const\s+String\s+(\w+)\s*=\s*'([^']*)'\s*;")
    constants = {m.group(1): m.group(2) for m in pattern.finditer(source)}
    if not constants:
        raise SmokeError(f"no AppRoutes constants found in {routes_dart}")
    return constants


def _match_parens(masked: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(masked)):
        char = masked[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index
    raise SmokeError("unbalanced parentheses in the router source")


def evaluate_path_expression(expression: str, constants: dict[str, str]) -> str:
    """Evaluate a `path:` argument to the location it names.

    Handles the three shapes the router uses: a bare `AppRoutes.name`, one
    string literal, and several adjacent literals carrying `${AppRoutes.name}`
    interpolations. Anything else raises, so a shape this cannot read is a
    failure rather than a silently missing route.
    """
    text = mask_source(expression)
    bare = re.fullmatch(r"\s*AppRoutes\.(\w+)\s*", text)
    if bare:
        name = bare.group(1)
        if name not in constants:
            raise SmokeError(f"AppRoutes.{name} is not a string constant")
        return constants[name]

    parts: list[str] = []
    for match in re.finditer(r"'([^'\n]*)'", expression):
        parts.append(match.group(1))
    if not parts:
        raise SmokeError(f"unreadable path expression: {expression.strip()!r}")
    joined = "".join(parts)

    def resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in constants:
            raise SmokeError(f"AppRoutes.{name} is not a string constant")
        return constants[name]

    joined = re.sub(r"\$\{AppRoutes\.(\w+)\}", resolve, joined)
    if "$" in joined:
        raise SmokeError(f"unresolved interpolation in path: {joined!r}")
    return joined


@dataclass(frozen=True)
class DeclaredRoute:
    """One location the router mounts."""

    location: str
    debug_only: bool

    @property
    def parameters(self) -> tuple[str, ...]:
        return tuple(
            segment[1:]
            for segment in self.location.split("/")
            if segment.startswith(":")
        )


@dataclass
class _RawRoute:
    start: int
    end: int
    path: str
    debug_only: bool
    children: list["_RawRoute"] = field(default_factory=list)


def parse_declared_routes(
    router_dart: Path, constants: dict[str, str]
) -> list[DeclaredRoute]:
    """Every location `buildAppRouter` mounts, in declaration order.

    Reads the `GoRoute` tree out of the source rather than restating it, so a
    route added, moved or renamed reaches this gate without anybody editing
    it. A child path without a leading slash is joined onto its parent, which
    is what go_router does with it.
    """
    source = router_dart.read_text(encoding="utf-8")
    masked = mask_source(source)

    raw: list[_RawRoute] = []
    for match in re.finditer(r"\bGoRoute\s*\(", masked):
        opening = match.end() - 1
        closing = _match_parens(masked, opening)
        before = masked[: match.start()]
        debug_only = (
            re.search(r"if\s*\(\s*!\s*kReleaseMode\s*\)\s*$", before) is not None
        )
        raw.append(
            _RawRoute(start=match.start(), end=closing, path="", debug_only=debug_only)
        )
    if not raw:
        raise SmokeError(f"no GoRoute found in {router_dart}")

    # Own text is the span with the child spans removed, so the `path:` found
    # in it is the route's own and never a child's.
    raw.sort(key=lambda route: route.start)
    for index, route in enumerate(raw):
        own = list(masked[route.start : route.end + 1])
        for other in raw[index + 1 :]:
            if other.start > route.end:
                break
            for position in range(other.start, min(other.end + 1, route.end + 1)):
                own[position - route.start] = " "
        own_text = "".join(own)
        found = re.search(r"\bpath\s*:", own_text)
        if not found:
            raise SmokeError(
                f"a GoRoute at offset {route.start} in {router_dart} declares no path"
            )
        cursor = route.start + found.end()
        depth = 0
        while cursor <= route.end:
            char = masked[cursor]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif char == "," and depth == 0:
                break
            cursor += 1
        route.path = evaluate_path_expression(
            source[route.start + found.end() : cursor], constants
        )

    roots: list[_RawRoute] = []
    stack: list[_RawRoute] = []
    for route in raw:
        while stack and route.start > stack[-1].end:
            stack.pop()
        if stack:
            stack[-1].children.append(route)
        else:
            roots.append(route)
        stack.append(route)

    declared: list[DeclaredRoute] = []

    def walk(route: _RawRoute, prefix: str, debug_only: bool) -> None:
        if route.path.startswith("/"):
            location = route.path
        else:
            location = posixpath.join(prefix or "/", route.path)
        inherited = debug_only or route.debug_only
        declared.append(DeclaredRoute(location=location, debug_only=inherited))
        for child in route.children:
            walk(child, location, inherited)

    for route in roots:
        walk(route, "", False)
    return declared


def sample_location(route: DeclaredRoute) -> str:
    """A concrete, obviously synthetic location for a declared route pattern."""
    segments = []
    for segment in route.location.split("/"):
        segments.append("smoke-" + segment[1:] if segment.startswith(":") else segment)
    return "/".join(segments)


def gallery_markers(package_lib: Path, app_lib: Path) -> list[str]:
    """Strings that only the design system gallery can put in a bundle.

    Computed rather than listed: every literal in the gallery source that
    appears nowhere else in the package or in the client. A gallery page
    renamed or rewritten therefore keeps the marker set true, and a marker set
    that has emptied is a failure rather than a check that quietly passes.
    """
    gallery_root = package_lib / "src" / "gallery"
    if not gallery_root.is_dir():
        raise SmokeError(f"the gallery source is missing at {gallery_root}")

    def prepared(path: Path) -> str:
        """The source with comments dropped and adjacent literals joined.

        Dart concatenates `'one ' 'two'` at compile time, so the string that
        reaches the bundle is the joined one. Joining here is what makes a
        marker the sentence the compiler emits rather than the fragment the
        author typed, and it is what lets the exclusion below see that a
        gallery fragment is part of a sentence the client ships anyway.
        """
        source = re.sub(r"//.*", "", path.read_text(encoding="utf-8"))
        return re.sub(r"'\s*'", "", source)

    def literals(source: str) -> set[str]:
        found = set()
        for match in re.finditer(r"'([^'\\\n$]+)'", source):
            value = match.group(1)
            if len(value) >= MARKER_MIN_LENGTH and " " in value and "/" not in value:
                found.add(value)
        return found

    inside: set[str] = set()
    for path in sorted(gallery_root.rglob("*.dart")):
        inside |= literals(prepared(path))

    # Substring, not equality. `Approve this record` is a gallery literal and
    # `Approve this record?` is the client's, so a marker set built by
    # subtracting equal strings would hold one the client puts in every bundle
    # on its own. A marker has to occur nowhere in the source that ships in a
    # release build, as a substring of anything.
    outside = "\n".join(
        prepared(path)
        for root in (package_lib, app_lib)
        for path in sorted(root.rglob("*.dart"))
        if gallery_root not in path.parents
    )

    markers = sorted(value for value in inside if value not in outside)
    if not markers:
        raise SmokeError(
            "no string is unique to the gallery, so its absence from a bundle "
            "would prove nothing"
        )
    return markers


# ---------------------------------------------------------------------------
# Firebase Hosting configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HostingConfig:
    public: str
    rewrites: tuple[tuple[str, str], ...]
    no_store: frozenset[str]
    # Every declared `headers` block, in declaration order, as
    # (source glob, ((key, value), ...)).
    headers: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()


def headers_for(config: HostingConfig, path: str) -> dict[str, str]:
    """The headers Hosting would attach to a response for `path`.

    Every block whose source matches contributes, in declaration order, and a
    later block wins a key an earlier one already set. This repository's two
    blocks set disjoint keys, so the precedence is not load bearing; it is
    written down so a third block added later behaves the way the file reads.
    """
    applied: dict[str, str] = {}
    for source, pairs in config.headers:
        if matches_hosting_glob(source, path):
            for key, value in pairs:
                applied[key] = value
    return applied


def read_hosting_config(firebase_json: Path) -> HostingConfig:
    document = json.loads(firebase_json.read_text(encoding="utf-8"))
    hosting = document.get("hosting")
    if isinstance(hosting, list):
        hosting = hosting[0] if hosting else None
    if not isinstance(hosting, dict):
        raise SmokeError(f"{firebase_json} declares no hosting configuration")
    public = hosting.get("public")
    if not isinstance(public, str) or not public:
        raise SmokeError(f"{firebase_json} declares no hosting public directory")

    rewrites: list[tuple[str, str]] = []
    for entry in hosting.get("rewrites", []):
        source = entry.get("source")
        destination = entry.get("destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise SmokeError("a hosting rewrite names no source and destination pair")
        rewrites.append((source, destination))

    no_store: set[str] = set()
    blocks: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for entry in hosting.get("headers", []):
        source = entry.get("source")
        if not isinstance(source, str) or not source:
            raise SmokeError("a hosting headers block names no source")
        pairs: list[tuple[str, str]] = []
        for header in entry.get("headers", []):
            key = header.get("key")
            value = header.get("value")
            if not isinstance(key, str) or not isinstance(value, str):
                raise SmokeError(
                    f"a header under {source!r} names no key and value pair"
                )
            pairs.append((key, value))
            if key.lower() == "cache-control" and "no-store" in value.lower():
                no_store.add(source)
        blocks.append((source, tuple(pairs)))
    return HostingConfig(
        public=public,
        rewrites=tuple(rewrites),
        no_store=frozenset(no_store),
        headers=tuple(blocks),
    )


def matches_hosting_glob(pattern: str, path: str) -> bool:
    """Match the subset of Hosting glob syntax this repository's config uses.

    A pattern this cannot read raises, so an unrecognised rewrite fails the
    gate instead of being treated as no match.
    """
    if pattern == "**":
        return True
    if re.fullmatch(r"[A-Za-z0-9_./-]+", pattern):
        return path == pattern
    if pattern.startswith("**/") and re.fullmatch(r"[A-Za-z0-9_.-]+", pattern[3:]):
        return path.rsplit("/", 1)[-1] == pattern[3:]
    raise SmokeError(f"unsupported hosting rewrite pattern: {pattern!r}")


def rewrite_for(config: HostingConfig, path: str) -> str | None:
    for pattern, destination in config.rewrites:
        if matches_hosting_glob(pattern, path):
            return destination
    return None


# ---------------------------------------------------------------------------
# The loopback server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """Serves one directory the way the declared Hosting configuration does."""

    server_version = "SpecimenWebRoutesSmoke/1"
    root: Path
    config: HostingConfig

    def do_GET(self) -> None:  # noqa: N802 (the base class names it)
        requested = unquote(urlsplit(self.path).path)
        served = self._resolve(requested)
        if served is None:
            self.send_error(404, "no file and no rewrite for this path")
            return
        body = served.read_bytes()
        kind, _ = mimetypes.guess_type(served.name)
        self.send_response(200)
        self.send_header("Content-Type", kind or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        # Attached to the requested location, not to the file the rewrite
        # resolved to: Hosting matches a header block against the URL the
        # browser asked for, so a deep link served from `/index.html` still
        # gets whatever `**` declares.
        for key, value in headers_for(self.config, requested).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _resolve(self, requested: str) -> Path | None:
        direct = self._file_for(requested)
        if direct is not None:
            return direct
        destination = rewrite_for(self.config, requested)
        if destination is None:
            return None
        return self._file_for(destination)

    def _file_for(self, requested: str) -> Path | None:
        relative = posixpath.normpath(requested).lstrip("/")
        if relative in ("", "."):
            relative = "index.html"
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            return None
        if candidate.is_dir():
            candidate = candidate / "index.html"
        return candidate if candidate.is_file() else None

    def log_message(self, *_args: object) -> None:
        return


class LoopbackSite:
    """The built artifact, served on 127.0.0.1 and nowhere else."""

    def __init__(self, root: Path, config: HostingConfig) -> None:
        handler = type("_BoundHandler", (_Handler,), {"root": root, "config": config})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def __enter__(self) -> "LoopbackSite":
        self._thread.start()
        return self

    def __exit__(self, *_exception: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def get(self, path: str) -> tuple[int, dict[str, str], str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.getheaders()}
            return response.status, headers, body
        finally:
            connection.close()


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def app_shell_problems(body: str) -> list[str]:
    """What is missing from a response that should be the application shell.

    The same three facts `scripts/ci/smoke_hosting.sh` asks of the public site,
    plus the bootstrap script, so the local gate and the public gate agree on
    what the shell is.
    """
    problems: list[str] = []
    if not re.match(r"\s*<!doctype html>", body, re.IGNORECASE):
        problems.append("no doctype")
    if not re.search(r"<html[\s>]", body, re.IGNORECASE):
        problems.append("no html element")
    if EXPECTED_TITLE not in body:
        problems.append(f"no {EXPECTED_TITLE}")
    if EXPECTED_BOOTSTRAP not in body:
        problems.append(f"no {EXPECTED_BOOTSTRAP} reference")
    return problems


def security_header_problems(headers: dict[str, str]) -> list[str]:
    """What `SECURITY_HEADERS` asks of a response that this one does not give.

    The comparison is exact on the value, not a containment test: a policy
    that has had a directive dropped out of it is a weaker policy, and a gate
    that accepted a prefix would not say so.
    """
    problems: list[str] = []
    for name, expected in SECURITY_HEADERS.items():
        actual = headers.get(name)
        if actual is None:
            problems.append(f"{name} is missing")
        elif actual != expected:
            problems.append(f"{name} is {actual!r} rather than {expected!r}")
    return problems


def marker_problems(raw: str) -> list[str]:
    """Everything the deploy guard would refuse this deployment marker for.

    `scripts/ci/deploy_hosting.sh` and `scripts/ci/smoke_hosting.sh` read the
    marker with a streaming `jq` filter that rejects a duplicate key, a second
    document, a field the shape does not name and a value of the wrong type.
    This restates those rules so a marker that would refuse a production
    release fails here instead, in the job that wrote it.
    """
    problems: list[str] = []

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                problems.append(f"duplicate marker field {key}")
            seen.add(key)
        return dict(pairs)

    # Passed to the constructor, not assigned afterwards: `JSONDecoder` wires
    # the hook into its scanner while it is being built, so a hook set on a
    # finished decoder is silently ignored and every duplicate key would be
    # accepted with its last value, which is the exact laundering the deploy
    # guard's streaming filter exists to refuse.
    decoder = json.JSONDecoder(object_pairs_hook=object_pairs)
    try:
        document, end = decoder.raw_decode(raw.lstrip())
    except ValueError as error:
        return [f"the marker is not one JSON document: {error}"]
    if raw.lstrip()[end:].strip():
        problems.append("the marker file carries more than one document")
    if not isinstance(document, dict):
        return problems + ["the marker is not a JSON object"]

    expected_fields = {
        "builtAt",
        "commitSha",
        "repository",
        "runAttempt",
        "runId",
        "schemaVersion",
    }
    if set(document) != expected_fields:
        missing = sorted(expected_fields - set(document))
        extra = sorted(set(document) - expected_fields)
        if missing:
            problems.append(f"the marker is missing {', '.join(missing)}")
        if extra:
            problems.append(f"the marker carries unknown fields {', '.join(extra)}")

    version = document.get("schemaVersion")
    # `True == 1` in Python and `true == 1` is false in jq, so the bool has to
    # be excluded by hand or this restatement would accept a marker the deploy
    # guard refuses.
    if isinstance(version, bool) or version != 1:
        problems.append("schemaVersion is not the number 1")
    if document.get("repository") != EXPECTED_REPOSITORY:
        problems.append("repository is not this repository")
    sha = document.get("commitSha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        problems.append("commitSha is not a 40 character lowercase hex string")
    for name in ("runId", "runAttempt"):
        value = document.get(name)
        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
            problems.append(f"{name} is not a positive integer written as a string")
    built = document.get("builtAt")
    if not isinstance(built, str):
        problems.append("builtAt is not a string")
    else:
        try:
            parsed = datetime.strptime(built, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            problems.append("builtAt is not an exact UTC second in the emitted shape")
        else:
            if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != built:
                problems.append("builtAt does not round trip through the marker shape")
    return problems


def bundle_problems(bundle: Path, markers: list[str], release: bool) -> list[str]:
    """Whether the gallery is in the bundle, and whether it should be."""
    problems: list[str] = []
    text = bundle.read_text(encoding="utf-8", errors="replace")
    present = [marker for marker in markers if marker in text]
    if release and present:
        problems.append(
            f"{len(present)} gallery strings are in the release bundle, "
            f"starting with {present[0]!r}"
        )
    if not release and not present:
        problems.append(
            "no gallery string is in a bundle built outside release mode, so "
            "this check proves nothing about a release build"
        )
    return problems


def gallery_location_count(bundle: Path, location: str) -> int:
    text = bundle.read_text(encoding="utf-8", errors="replace")
    return text.count(location)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


STATIC_PROBES = (f"/{BUNDLE_NAME}", f"/{EXPECTED_BOOTSTRAP}")


def run(
    repo_root: Path,
    build_dir: Path | None,
    release: bool,
    require_marker: bool,
    out=sys.stdout,
) -> int:
    app = repo_root / "apps" / "specimen_digitization"
    config = read_hosting_config(repo_root / "firebase.json")
    root = build_dir or (repo_root / config.public)
    if not root.is_dir():
        raise SmokeError(
            f"the web build is missing at {root}. Run flutter build web first."
        )

    constants = read_route_constants(app / "lib" / "src" / "app" / "routes.dart")
    routes = parse_declared_routes(
        app / "lib" / "src" / "app" / "app_router.dart", constants
    )
    markers = gallery_markers(
        app / "packages" / "specimen_ui" / "lib", app / "lib"
    )
    failures: list[str] = []

    print(f"Serving {root} with the rewrites and headers "
          f"{repo_root / 'firebase.json'} declares.", file=out)
    print(f"{len(routes)} routes declared, {len(markers)} gallery markers "
          f"computed.", file=out)

    # One entry per distinct problem, naming every location that had it. A
    # header dropped from `firebase.json` is missing from every response, and a
    # failure list with one line per location would bury the other checks.
    header_problems: dict[str, list[str]] = {}
    header_checked: list[str] = []

    def check_headers(location: str, headers: dict[str, str]) -> None:
        header_checked.append(location)
        for problem in security_header_problems(headers):
            header_problems.setdefault(problem, []).append(location)

    with LoopbackSite(root, config) as site:
        for location in ["/"] + [sample_location(route) for route in routes]:
            status, headers, body = site.get(location)
            problems = app_shell_problems(body) if status == 200 else ["no shell"]
            if status != 200 or problems:
                failures.append(
                    f"{location} answered {status} and is not the application "
                    f"shell ({', '.join(problems)})"
                )
                print(f"  fail  {location}", file=out)
            else:
                print(f"  shell {location}", file=out)
            if status == 200:
                check_headers(location, headers)

        for probe in STATIC_PROBES:
            status, headers, body = site.get(probe)
            if status == 200:
                check_headers(probe, headers)
            if status != 200:
                failures.append(f"{probe} answered {status}; the artifact is short "
                                f"a file the shell loads")
                print(f"  fail  {probe}", file=out)
            elif not app_shell_problems(body):
                failures.append(
                    f"{probe} was rewritten to the shell; a real file must be "
                    f"served as itself or the route sweep proves nothing"
                )
                print(f"  fail  {probe}", file=out)
            else:
                print(f"  file  {probe}", file=out)

        # Asked of the file, not of the response: the `**` rewrite answers a
        # missing marker with the shell, so a marker nobody stamped would read
        # as a marker made of HTML.
        if not (root / MARKER_NAME).is_file():
            if require_marker:
                failures.append(
                    f"/{MARKER_NAME} is missing; "
                    f"scripts/ci/write_deployment_metadata.sh has not run"
                )
                print(f"  fail  /{MARKER_NAME}", file=out)
            else:
                print(f"  skip  /{MARKER_NAME} (not stamped in this build)",
                      file=out)
        else:
            _status, headers, body = site.get(f"/{MARKER_NAME}")
            check_headers(f"/{MARKER_NAME}", headers)
            problems = marker_problems(body)
            if f"/{MARKER_NAME}" not in config.no_store:
                problems.append(
                    "firebase.json does not serve it with Cache-Control no-store"
                )
            elif headers.get("cache-control") != "no-store":
                problems.append("the declared no-store header was not applied")
            if problems:
                failures.extend(
                    f"/{MARKER_NAME}: {problem}" for problem in problems
                )
                print(f"  fail  /{MARKER_NAME}", file=out)
            else:
                print(f"  ok    /{MARKER_NAME}", file=out)

        for problem, locations in sorted(header_problems.items()):
            failures.append(
                f"security header: {problem} on {len(locations)} of "
                f"{len(header_checked)} responses, first {locations[0]}"
            )
            print(f"  fail  header {problem}", file=out)
        if not header_problems:
            print(
                f"  ok    {len(SECURITY_HEADERS)} security headers on "
                f"{len(header_checked)} responses",
                file=out,
            )

    bundle = root / BUNDLE_NAME
    if not bundle.is_file():
        failures.append(f"{BUNDLE_NAME} is missing from the build")
    else:
        for problem in bundle_problems(bundle, markers, release):
            failures.append(problem)
        gallery = [route for route in routes if route.debug_only]
        for route in gallery:
            count = gallery_location_count(bundle, route.location)
            allowance = GALLERY_LOCATION_ALLOWANCE if release else count
            verdict = "ok   " if count <= allowance else "fail "
            print(
                f"  {verdict} {route.location} appears {count} time(s) in "
                f"{BUNDLE_NAME}, allowance {allowance}",
                file=out,
            )
            if count > allowance:
                failures.append(
                    f"{route.location} appears {count} times in {BUNDLE_NAME}, "
                    f"over the allowance of {allowance}"
                )
        if release and not gallery:
            failures.append(
                "the router mounts no route behind a release check, so the "
                "gallery exclusion is no longer being proved"
            )

    if failures:
        print("", file=out)
        print(f"{len(failures)} web route checks failed:", file=out)
        for failure in failures:
            print(f"  {failure}", file=out)
        return 1
    gallery = (
        "the gallery is not in the release bundle"
        if release
        else "the gallery is in this non release bundle, so the release check "
        "is measuring something real"
    )
    print("", file=out)
    print(
        f"Every declared route answers with the application shell and carries "
        f"the {len(SECURITY_HEADERS)} security headers, {gallery}, and the "
        f"deployment marker is the one the deploy guard accepts.",
        file=out,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Serve the built web release on loopback and check every route the "
            "router declares. Contacts no live host and deploys nothing."
        )
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="The built web directory. Defaults to firebase.json's hosting public.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="The repository root.",
    )
    parser.add_argument(
        "--bundle",
        choices=("release", "debug"),
        default="release",
        help=(
            "What the build is. release requires the gallery to be absent from "
            "main.dart.js; debug requires it to be present, which is what "
            "proves the release check has teeth."
        ),
    )
    parser.add_argument(
        "--require-marker",
        action="store_true",
        help="Fail when deployment.json is absent rather than skipping it.",
    )
    args = parser.parse_args(argv)
    try:
        return run(
            repo_root=args.repo_root.resolve(),
            build_dir=args.build_dir.resolve() if args.build_dir else None,
            release=args.bundle == "release",
            require_marker=args.require_marker,
        )
    except SmokeError as error:
        print(f"smoke_web_routes: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
