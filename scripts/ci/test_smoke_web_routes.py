"""Tests for the web route smoke.

Two kinds. The first read the repository's own sources, so a route added or
renamed, a rewrite changed in `firebase.json` or a gallery rewritten reaches
this file as a failure rather than as a gate that quietly stopped measuring.
The second drive the whole gate over a synthetic build directory, so every
verdict it can reach is exercised without a Flutter build.

Nothing here contacts a network. The server binds 127.0.0.1 on an ephemeral
port and the client speaks to that port only.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_web_routes", Path(__file__).with_name("smoke_web_routes.py")
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
# Registered before it is executed: a frozen dataclass in the module reads
# `sys.modules[cls.__module__]` while it is being built, and a module loaded
# straight off a path is not there yet.
sys.modules["smoke_web_routes"] = MODULE
SPEC.loader.exec_module(MODULE)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "apps" / "specimen_digitization"
ROUTES_DART = APP / "lib" / "src" / "app" / "routes.dart"
ROUTER_DART = APP / "lib" / "src" / "app" / "app_router.dart"

SHELL = (
    "<!DOCTYPE html>\n<html>\n<head>\n"
    "<title>Specimen Digitization</title>\n</head>\n"
    '<body><script src="flutter_bootstrap.js" async></script></body>\n</html>\n'
)

MARKER = {
    "schemaVersion": 1,
    "repository": "anurag-duddu/specimen-digitization-app",
    # A counted out fake, not a commit. The 40 hex characters the marker shape
    # requires read as high entropy to detect-secrets, so it is marked here the
    # way ci-cd.yml marks the workload identity provider path.
    "commitSha": "0123456789abcdef0123456789abcdef01234567",  # pragma: allowlist secret
    "runId": "35237915721",
    "runAttempt": "1",
    "builtAt": "2026-09-17T15:05:16Z",
}


# ---------------------------------------------------------------------------
# What the repository actually declares
# ---------------------------------------------------------------------------


def test_the_route_table_is_the_one_the_router_mounts():
    constants = MODULE.read_route_constants(ROUTES_DART)
    routes = MODULE.parse_declared_routes(ROUTER_DART, constants)
    assert {route.location for route in routes} == {
        "/sign-in",
        "/verify",
        "/setup",
        "/help",
        "/gallery",
        "/c/:collection/queue",
        "/c/:collection/queue/:specimen",
        "/c/:collection/intake",
        "/c/:collection/intake/sources",
        "/c/:collection/intake/sources/:source",
    }


def test_only_the_gallery_is_mounted_behind_the_release_check():
    constants = MODULE.read_route_constants(ROUTES_DART)
    routes = MODULE.parse_declared_routes(ROUTER_DART, constants)
    assert [route.location for route in routes if route.debug_only] == ["/gallery"]


def test_a_nested_route_keeps_its_parents_path():
    constants = MODULE.read_route_constants(ROUTES_DART)
    routes = MODULE.parse_declared_routes(ROUTER_DART, constants)
    record = next(r for r in routes if r.location.endswith(":specimen"))
    assert record.parameters == ("collection", "specimen")
    assert MODULE.sample_location(record) == (
        "/c/smoke-collection/queue/smoke-specimen"
    )


def test_hosting_config_is_read_rather_than_assumed():
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    assert config.public == "apps/specimen_digitization/build/web"
    assert ("**", "/index.html") in config.rewrites
    assert "/deployment.json" in config.no_store
    assert [source for source, _pairs in config.headers] == [
        "**",
        "/deployment.json",
    ]


def test_gallery_markers_are_strings_only_the_gallery_ships():
    markers = MODULE.gallery_markers(
        APP / "packages" / "specimen_ui" / "lib", APP / "lib"
    )
    assert len(markers) > 50
    assert all(len(marker) >= MODULE.MARKER_MIN_LENGTH for marker in markers)
    # A page title only the gallery draws, so the set is really being read out
    # of the gallery rather than coming back empty.
    assert "Fields and glass" in markers


def test_a_marker_may_not_be_part_of_a_string_the_client_ships():
    """The client carries `Approve this record?` and the gallery carries
    `Approve this record`. A marker set built by dropping equal strings keeps
    the second, and then every release bundle fails for a gallery it does not
    contain. A marker has to occur nowhere in the client, as a substring of
    anything, and these three are what proved it."""
    markers = MODULE.gallery_markers(
        APP / "packages" / "specimen_ui" / "lib", APP / "lib"
    )
    for near_miss in (
        "Approve this record",
        "Each reading names the model and provider that produced it.",
        "The model reading",
    ):
        assert near_miss not in markers


# ---------------------------------------------------------------------------
# Reading Dart
# ---------------------------------------------------------------------------


def test_mask_source_blanks_comments_and_string_contents():
    masked = MODULE.mask_source("a(); // GoRoute(\nb('GoRoute(');\n/* x( */ c();")
    assert "GoRoute(" not in masked
    assert masked.count("(") == 3
    assert len(masked) == len("a(); // GoRoute(\nb('GoRoute(');\n/* x( */ c();")


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("AppRoutes.signIn", "/sign-in"),
        ("'sources'", "sources"),
        ("':${AppRoutes.specimenParameter}'", ":specimen"),
        (
            "'${AppRoutes.collectionPrefix}/'\n':${AppRoutes.collectionParameter}"
            "/queue'",
            "/c/:collection/queue",
        ),
    ],
)
def test_path_expressions_the_router_uses(expression, expected):
    constants = MODULE.read_route_constants(ROUTES_DART)
    assert MODULE.evaluate_path_expression(expression, constants) == expected


@pytest.mark.parametrize(
    "expression", ["AppRoutes.notAConstant", "'${AppRoutes.missing}'", "buildPath()"]
)
def test_an_unreadable_path_expression_fails_loudly(expression):
    constants = MODULE.read_route_constants(ROUTES_DART)
    with pytest.raises(MODULE.SmokeError):
        MODULE.evaluate_path_expression(expression, constants)


def test_an_unsupported_rewrite_pattern_fails_rather_than_never_matching():
    with pytest.raises(MODULE.SmokeError):
        MODULE.matches_hosting_glob("@(a|b)", "/a")


def test_rewrite_matching():
    config = MODULE.HostingConfig(
        public="x", rewrites=(("**", "/index.html"),), no_store=frozenset()
    )
    assert MODULE.rewrite_for(config, "/anything/at/all") == "/index.html"
    assert MODULE.rewrite_for(
        MODULE.HostingConfig(public="x", rewrites=(), no_store=frozenset()), "/a"
    ) is None


# ---------------------------------------------------------------------------
# The shell and the marker
# ---------------------------------------------------------------------------


def test_the_real_index_html_is_the_shell():
    index = APP / "web" / "index.html"
    assert MODULE.app_shell_problems(index.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "body,problem",
    [
        ("<html><title>Specimen Digitization</title>flutter_bootstrap.js", "doctype"),
        ("<!DOCTYPE html><title>Specimen Digitization</title>", "html element"),
        ("<!DOCTYPE html><html><body>flutter_bootstrap.js</body>", "title"),
        ("<!DOCTYPE html><html><title>Specimen Digitization</title>", "bootstrap"),
    ],
)
def test_a_response_that_is_not_the_shell_is_named(body, problem):
    problems = MODULE.app_shell_problems(body)
    assert problems and any(problem in entry for entry in problems)


def test_the_marker_write_deployment_metadata_emits_is_accepted():
    assert MODULE.marker_problems(json.dumps(MARKER, indent=2)) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", 2),
        ("schemaVersion", "1"),
        # True == 1 in Python and true == 1 is false in jq.
        ("schemaVersion", True),
        ("repository", "someone-else/specimen-digitization-app"),
        # Uppercase hex: the guards accept lowercase only.
        ("commitSha", "0123456789ABCDEF0123456789abcdef01234567"),  # pragma: allowlist secret
        ("commitSha", "0123456"),
        ("runId", 35237915721),
        ("runId", "0"),
        ("runAttempt", ""),
        ("builtAt", "2026-09-17T15:05:16+00:00"),
        ("builtAt", "2026-09-17 15:05:16Z"),
    ],
)
def test_a_marker_the_deploy_guard_would_refuse_is_refused_here(field, value):
    marker = dict(MARKER, **{field: value})
    assert MODULE.marker_problems(json.dumps(marker)) != []


def test_a_missing_or_extra_marker_field_is_named():
    short = {key: value for key, value in MARKER.items() if key != "runId"}
    assert any("missing runId" in p for p in MODULE.marker_problems(json.dumps(short)))
    wide = dict(MARKER, deployedBy="a person")
    assert any("unknown fields" in p for p in MODULE.marker_problems(json.dumps(wide)))


def test_a_duplicate_field_and_a_second_document_are_refused():
    duplicate = json.dumps(MARKER)[:-1] + ', "runId": "2"}'
    assert any("duplicate" in p for p in MODULE.marker_problems(duplicate))
    two = json.dumps(MARKER) + "\n" + json.dumps(MARKER)
    assert any("more than one document" in p for p in MODULE.marker_problems(two))


def test_the_application_shell_is_not_a_marker():
    assert MODULE.marker_problems(SHELL) != []


# ---------------------------------------------------------------------------
# The whole gate, over a synthetic build
# ---------------------------------------------------------------------------


def build_dir(tmp_path, *, shell=SHELL, bundle="a();", marker=None):
    """A web build with the files the gate reads and nothing else."""
    root = tmp_path / "web"
    root.mkdir(parents=True)
    (root / "index.html").write_text(shell, encoding="utf-8")
    (root / "main.dart.js").write_text(bundle, encoding="utf-8")
    (root / "flutter_bootstrap.js").write_text("// bootstrap\n", encoding="utf-8")
    if marker is not None:
        (root / "deployment.json").write_text(marker, encoding="utf-8")
    return root


def run(root, **kwargs):
    import io

    out = io.StringIO()
    code = MODULE.run(
        repo_root=REPO_ROOT,
        build_dir=root,
        release=kwargs.pop("release", True),
        require_marker=kwargs.pop("require_marker", False),
        out=out,
    )
    return code, out.getvalue()


def test_a_release_build_with_no_gallery_passes(tmp_path):
    code, report = run(build_dir(tmp_path))
    assert code == 0, report
    assert "/c/smoke-collection/queue/smoke-specimen" in report
    assert "/gallery appears 0 time(s)" in report


def test_every_declared_route_is_actually_requested(tmp_path):
    _code, report = run(build_dir(tmp_path))
    constants = MODULE.read_route_constants(ROUTES_DART)
    for route in MODULE.parse_declared_routes(ROUTER_DART, constants):
        assert f"shell {MODULE.sample_location(route)}" in report


def test_a_build_whose_shell_is_not_the_application_fails(tmp_path):
    code, report = run(build_dir(tmp_path, shell="<!DOCTYPE html><html>nope"))
    assert code == 1
    assert "is not the application shell" in report


def test_a_release_bundle_carrying_the_gallery_fails(tmp_path):
    marker = MODULE.gallery_markers(
        APP / "packages" / "specimen_ui" / "lib", APP / "lib"
    )[0]
    code, report = run(build_dir(tmp_path, bundle=f"x('{marker}');"))
    assert code == 1
    assert "gallery strings are in the release bundle" in report


def test_a_release_bundle_mounting_the_gallery_route_fails(tmp_path):
    code, report = run(build_dir(tmp_path, bundle='a="/gallery";b="/gallery";'))
    assert code == 1
    assert "over the allowance" in report


def test_the_allowance_covers_the_routers_own_comparison(tmp_path):
    code, report = run(build_dir(tmp_path, bundle='if(x==="/gallery")return y;'))
    assert code == 0, report


def test_a_non_release_build_must_carry_the_gallery(tmp_path):
    code, report = run(build_dir(tmp_path), release=False)
    assert code == 1
    assert "proves nothing about a release build" in report

    marker = MODULE.gallery_markers(
        APP / "packages" / "specimen_ui" / "lib", APP / "lib"
    )[0]
    code, report = run(build_dir(tmp_path / "two", bundle=f"'{marker}'"), release=False)
    assert code == 0, report


def test_a_missing_marker_is_skipped_or_required(tmp_path):
    code, report = run(build_dir(tmp_path))
    assert code == 0 and "skip  /deployment.json" in report
    code, report = run(build_dir(tmp_path / "two"), require_marker=True)
    assert code == 1
    assert "write_deployment_metadata.sh has not run" in report


def test_a_stamped_marker_is_read_from_the_file_not_the_rewrite(tmp_path):
    code, report = run(
        build_dir(tmp_path, marker=json.dumps(MARKER, indent=2)),
        require_marker=True,
    )
    assert code == 0, report
    assert "ok    /deployment.json" in report


def test_a_stamped_marker_the_deploy_guard_would_refuse_fails(tmp_path):
    broken = json.dumps(dict(MARKER, commitSha="not-a-sha"))
    code, report = run(build_dir(tmp_path, marker=broken), require_marker=True)
    assert code == 1
    assert "commitSha" in report


def test_a_missing_build_directory_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(MODULE.SmokeError):
        run(tmp_path / "absent")


def test_a_missing_bundle_fails(tmp_path):
    root = build_dir(tmp_path)
    (root / "main.dart.js").unlink()
    code, report = run(root)
    assert code == 1
    assert "main.dart.js" in report


def test_the_site_listens_on_loopback_only(tmp_path):
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    with MODULE.LoopbackSite(build_dir(tmp_path), config) as site:
        assert site._server.server_address[0] == "127.0.0.1"
        status, headers, body = site.get("/main.dart.js")
        assert status == 200
        assert MODULE.app_shell_problems(body) != []
        assert "text/javascript" in headers["content-type"]


def test_the_no_store_header_the_config_declares_is_applied(tmp_path):
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    root = build_dir(tmp_path, marker=json.dumps(MARKER))
    with MODULE.LoopbackSite(root, config) as site:
        _status, headers, _body = site.get("/deployment.json")
        assert headers["cache-control"] == "no-store"


def test_a_path_outside_the_build_cannot_be_read(tmp_path):
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    with MODULE.LoopbackSite(build_dir(tmp_path), config) as site:
        status, _headers, body = site.get("/../../firebase.json")
        assert status == 200
        assert MODULE.app_shell_problems(body) == []


# ---------------------------------------------------------------------------
# The security headers
# ---------------------------------------------------------------------------


def lowercased(pairs):
    return {key.lower(): value for key, value in pairs.items()}


def test_firebase_json_declares_every_header_the_gate_requires():
    """The configuration and the required set are two files, and this is the
    one place they have to agree. A header added to `SECURITY_HEADERS` without
    a `firebase.json` entry fails here rather than on the public site."""
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    applied = lowercased(MODULE.headers_for(config, "/"))
    for name, value in MODULE.SECURITY_HEADERS.items():
        assert applied.get(name) == value


def test_the_policy_deliberately_names_no_script_or_style_source():
    """Flutter web boots from an inline script and fetches CanvasKit from
    gstatic, so a `script-src` or `style-src` narrow enough to be worth having
    would break the engine. Cross origin isolation is not wanted either: COOP
    and COEP would break the reCAPTCHA Enterprise frame App Check uses. This
    is the decision, written down where a later edit has to argue with it."""
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    applied = lowercased(MODULE.headers_for(config, "/"))
    policy = applied["content-security-policy"]
    for directive in ("script-src", "style-src", "default-src"):
        assert directive not in policy
    for header in ("cross-origin-opener-policy", "cross-origin-embedder-policy"):
        assert header not in applied


def test_the_permissions_policy_denies_what_the_web_client_never_asks_for():
    """The header denies camera, microphone and geolocation, and the reason it
    can is that the web build asks for none of them: the in-app camera is
    behind `!kIsWeb`, so the capture button is not drawn on the web, and
    nothing reads a microphone or a location. If a web capture flow is ever
    added, this test is where the header has to be revisited."""
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    applied = lowercased(MODULE.headers_for(config, "/"))
    for feature in ("camera", "microphone", "geolocation"):
        assert f"{feature}=()" in applied["permissions-policy"]

    intake = (APP / "lib" / "src" / "intake.dart").read_text(encoding="utf-8")
    assert re.search(r"_cameraAvailable\s*=>\s*!kIsWeb", intake), (
        "the in-app camera is no longer web-excluded, so Permissions-Policy "
        "camera=() would now deny something the client wants"
    )
    for root in (APP / "lib", APP / "web"):
        for path in sorted(root.rglob("*")):
            if path.suffix in (".dart", ".html", ".js"):
                text = path.read_text(encoding="utf-8", errors="replace")
                assert "getUserMedia" not in text, path
                assert "navigator.geolocation" not in text, path


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({}, "is missing"),
        (
            dict(MODULE.SECURITY_HEADERS, **{"x-frame-options": "SAMEORIGIN"}),
            "rather than",
        ),
        # A directive dropped out of the policy leaves a prefix, which a
        # containment test would accept and an exact comparison refuses.
        (
            dict(
                MODULE.SECURITY_HEADERS,
                **{"content-security-policy": "frame-ancestors 'none'"},
            ),
            "rather than",
        ),
    ],
)
def test_a_weakened_header_is_named(headers, expected):
    problems = MODULE.security_header_problems(headers)
    assert problems and any(expected in problem for problem in problems)


def test_a_response_carrying_the_declared_headers_has_no_problems():
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    applied = lowercased(MODULE.headers_for(config, "/"))
    assert MODULE.security_header_problems(applied) == []


def deepest_sample_location():
    constants = MODULE.read_route_constants(ROUTES_DART)
    routes = MODULE.parse_declared_routes(ROUTER_DART, constants)
    deepest = max(routes, key=lambda route: route.location.count("/"))
    return MODULE.sample_location(deepest)


def test_the_headers_reach_the_root_and_a_deep_route(tmp_path):
    """A deep route is served out of `index.html` by the `**` rewrite. Hosting
    matches a header block against the URL that was asked for, not against the
    file the rewrite resolved to, so the deep link has to carry them too."""
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    deep = deepest_sample_location()
    assert deep.count("/") >= 4
    with MODULE.LoopbackSite(build_dir(tmp_path), config) as site:
        for location in ("/", deep, "/main.dart.js"):
            _status, headers, _body = site.get(location)
            assert MODULE.security_header_problems(headers) == [], location


def test_the_marker_carries_both_the_security_headers_and_no_store(tmp_path):
    config = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    root = build_dir(tmp_path, marker=json.dumps(MARKER))
    with MODULE.LoopbackSite(root, config) as site:
        _status, headers, _body = site.get("/deployment.json")
        assert headers["cache-control"] == "no-store"
        assert MODULE.security_header_problems(headers) == []


def test_the_whole_gate_reports_the_headers(tmp_path):
    code, report = run(build_dir(tmp_path))
    assert code == 0, report
    assert f"{len(MODULE.SECURITY_HEADERS)} security headers on" in report


def test_a_header_dropped_from_the_configuration_fails_the_gate(
    tmp_path, monkeypatch
):
    """The gate's teeth: with the `**` block gone from the configuration the
    server stops sending the headers, and the sweep says so once per header
    rather than once per location."""
    real = MODULE.read_hosting_config(REPO_ROOT / "firebase.json")
    stripped = MODULE.HostingConfig(
        public=real.public,
        rewrites=real.rewrites,
        no_store=real.no_store,
        headers=tuple(
            (source, pairs) for source, pairs in real.headers if source != "**"
        ),
    )
    monkeypatch.setattr(MODULE, "read_hosting_config", lambda _path: stripped)
    code, report = run(build_dir(tmp_path))
    assert code == 1
    assert report.count("security header:") == len(MODULE.SECURITY_HEADERS)
    assert "x-frame-options is missing" in report


def test_an_unreadable_headers_block_fails_rather_than_being_skipped(tmp_path):
    for broken in (
        {"hosting": {"public": "x", "headers": [{"headers": []}]}},
        {
            "hosting": {
                "public": "x",
                "headers": [{"source": "**", "headers": [{"key": "A"}]}],
            }
        },
    ):
        path = tmp_path / "firebase.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(MODULE.SmokeError):
            MODULE.read_hosting_config(path)


def test_a_later_block_wins_a_key_an_earlier_one_set():
    config = MODULE.HostingConfig(
        public="x",
        rewrites=(),
        no_store=frozenset(),
        headers=(
            ("**", (("X-Frame-Options", "SAMEORIGIN"),)),
            ("/deployment.json", (("X-Frame-Options", "DENY"),)),
        ),
    )
    assert MODULE.headers_for(config, "/")["X-Frame-Options"] == "SAMEORIGIN"
    assert (
        MODULE.headers_for(config, "/deployment.json")["X-Frame-Options"] == "DENY"
    )


# ---------------------------------------------------------------------------
# The Python rules and the shell guard's jq rules agree
# ---------------------------------------------------------------------------


def hosting_marker_filter():
    """The marker filter `scripts/ci/smoke_hosting.sh` actually runs.

    Read out of the script rather than copied, so the two cannot drift apart
    without this test saying so.
    """
    import re

    script = (REPO_ROOT / "scripts" / "ci" / "smoke_hosting.sh").read_text(
        encoding="utf-8"
    )
    found = re.search(
        r"jq --exit-status --raw-output --null-input --stream[^']*'(.*?)'"
        r"\s*\"\$metadata_file\"",
        script,
        re.S,
    )
    assert found, "the marker filter could not be read out of smoke_hosting.sh"
    return found.group(1)


def jq_accepts(raw, tmp_path):
    import subprocess

    path = tmp_path / "marker.json"
    path.write_text(raw, encoding="utf-8")
    result = subprocess.run(
        [
            "jq",
            "--exit-status",
            "--raw-output",
            "--null-input",
            "--stream",
            "--arg",
            "repository",
            MODULE.EXPECTED_REPOSITORY,
            hosting_marker_filter(),
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


needs_jq = pytest.mark.skipif(
    __import__("shutil").which("jq") is None, reason="jq is not installed"
)


@needs_jq
def test_the_shell_guard_accepts_the_marker_this_file_accepts(tmp_path):
    raw = json.dumps(MARKER, indent=2)
    assert MODULE.marker_problems(raw) == []
    assert jq_accepts(raw, tmp_path)


@needs_jq
@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(dict(MARKER, schemaVersion="1")),
        json.dumps(dict(MARKER, schemaVersion=True)),
        json.dumps(dict(MARKER, repository="someone-else/x")),
        json.dumps(dict(MARKER, commitSha="0123456")),
        json.dumps(dict(MARKER, runId=1)),
        json.dumps(dict(MARKER, runAttempt="0")),
        json.dumps(dict(MARKER, builtAt="2026-09-17T15:05:16+00:00")),
        json.dumps(dict(MARKER, deployedBy="a person")),
        json.dumps({k: v for k, v in MARKER.items() if k != "runId"}),
        json.dumps(MARKER)[:-1] + ', "runId": "2"}',
        json.dumps(MARKER) + "\n" + json.dumps(MARKER),
        SHELL,
    ],
)
def test_the_two_guards_refuse_the_same_markers(raw, tmp_path):
    assert MODULE.marker_problems(raw) != []
    assert not jq_accepts(raw, tmp_path)
