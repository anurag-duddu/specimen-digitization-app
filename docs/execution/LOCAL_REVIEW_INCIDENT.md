# Local review availability and sign-in incident

Observed 2026-09-08 after the first local review handoff. Production and the
published PR source were unchanged at `285534c39d483de18605d398dd2e79ab8b52e746`.

## What failed

The user saw a loaded frontend with no working collection operations, and a
made-up email appeared to sign in. Both local ports 3000/8000 refused connections;
the original API/web/launcher PIDs 3406/3408/3407 were absent. Those processes had
been launched through task-owned exec sessions, without an independent supervisor.
Their logs contained startup but no recorded termination reason. The exact kill
trigger or signal is **not confirmed**. It was incorrect to treat those sessions
as a durable user handoff merely because they were alive during verification.

An already loaded Flutter page can remain visible without a reachable server.
The original local fixture client also set its in-memory signed-in state before
requesting `/v1/session`. Any test email is intentionally allowed in synthetic
mode, but an arbitrary password or offline API could therefore expose the shell
before server authentication failed. This was not Firebase account creation or
backend authorization bypass: the API compares the bearer and rejects invalid
tokens with 401. The displayed connection/no-collection state was misleading.

## Restoration and verified evidence

The same retained local data and token were reused without rotation or reseeding.
The API and a freshly compiled release web artifact now run as separate user
launchd jobs, independent of the task's exec-process lifetime:

- `org.fieldmuseum.specimen-review-285534c-api`
- `org.fieldmuseum.specimen-review-285534c-web`

The API was verified with launchd as parent PID 1. Both jobs are registered and
listen only on 127.0.0.1:8000 and127.0.0.1:3000. This setup is supervised within
the user's login session; restart after logout/reboot is not configured or claimed.
An observed later-turn survival check remains a separate verification step.

Both `http://localhost:3000/local-review.json` and the 127.0.0.1 equivalent return
200, the exact source SHA above, `mode: synthetic`, the local API URL and the
served JavaScript digest. Static responses use `Cache-Control: no-store,
no-cache, must-revalidate`. The release build explicitly enables local synthetic
mode and embeds no bearer. The unchanged ignored CI Firebase placeholder was
removed after building.

The parent observed old sign-in text after the first normal reload of the auth
repair, even though direct retrieval of `main.dart.js` matched the new marker,
contained Fixture token/new copy, and lacked the old copy. A second normal reload
displayed the patched form and correctly rejected an invalid token. The build's
bootstrap enabled Flutter's offline-first service worker; activation/cache lag
is a supported explanation, but the exact controlling worker was not captured.
A marker alone is not proof of the code running in an already open tab. The
repository runner uses `--pwa-strategy=none` for local reviews to avoid new
offline-first caching; production build behavior is unchanged. Existing tabs may
still need reload/reopen when moving away from an older worker. Verify actual
visible form behavior, not only the artifact marker.

The retained bearer returned 200 from `/v1/session` with synthetic mode. An
intentionally invalid bearer returned 401. Authenticated retrieval confirmed
specimen `4e99dab8-9c35-56f0-8e29-fc12d38f1940` still at revision 21, cleared under
the explicit synthetic policy. These probes emitted no bearer. They verify local
availability and retained state, not production identity or model quality.

## Operator commands and private access

The repository-owned macOS runner is `scripts/dev/local_review.py`. It requires
the pinned local tools and `uv sync --frozen`; it does not install a login item,
enable a cloud service, invoke a model provider or deploy anything. Choose a
review directory outside the repository. The token is created privately once
and never silently replaced; existing user Firebase configuration is preserved.

```bash
python3 scripts/dev/local_review.py start --review-dir /tmp/my-specimen-review
python3 scripts/dev/local_review.py status --review-dir /tmp/my-specimen-review
python3 scripts/dev/local_review.py stop --review-dir /tmp/my-specimen-review
```

The default ports are 8000/3000. For independent checks, pass distinct
`--api-port` and `--web-port` values when first starting. Existing configuration
is reused on subsequent starts. The runner checks job ownership and occupied
ports; it does not replace unrelated listeners. `rebuild` prepares a new web
artifact before restarting only the named review jobs, retaining source data
and credentials. Pass the configured ports again when rebuilding a non-default
instance. Source SHA, dirty-worktree state, explicit synthetic mode and the
JavaScript digest are recorded in the artifact marker. A reviewed handoff
should be rebuilt from a clean, verified commit.

The status command checks both supervisor registrations, exact served marker,
and a server-verified synthetic session without printing the bearer. Start/status
commands return normally while launchd owns the serving processes. Stop retains
all state and artifacts. For non-macOS systems, use the manual commands in
HANDOFF.md with an appropriate separately reviewed local supervisor.

The first restored instance below uses the same design through the private
incident helpers; migrating to the repository runner must preserve its state
and token and deliberately remove only the old named jobs.

Local launch helpers and state are intentionally outside Git in
`/tmp/specimen-review-285534c`. Existing private `ACCESS.md` and `token` files are
mode 0600. Login instructions and an operator clipboard shortcut are in that
private note; tokens must not appear in URLs, repository files or chat output.

```bash
python3 /tmp/specimen-review-285534c/start.py
python3 /tmp/specimen-review-285534c/status.py
python3 /tmp/specimen-review-285534c/stop.py
```

`start.py` registers only missing named jobs and refuses occupied ports; it does
not stop an existing process. `status.py` checks supervisor registration, the
served provenance marker, authorized session and retained specimen without
printing the token. `stop.py` verifies the named jobs belong to the local review
directory before removing them. It does not delete state, rotate credentials or
touch other services. After logout/reboot, rerun start if the disposable files
remain available; `/tmp` is not a durable backup location.

The helper entrypoints are `start_api.py` (retained token/state, synthetic API) and
`serve_static.py` (loopback static web, no-store). The web artifact is a copy of
the explicitly configured build from the verified integration worktree. A new
source candidate requires a deliberate rebuild and marker update; a source
commit alone does not change the served artifact.

## Follow-up and acceptance boundary

Owner patch `a8a999d` is integrated as
`26317ab46d35eb2a8407a9ae5b45c15f531182c8`. `/v1/session` validation now precedes
local sign-in success, and offline/unauthorized/no-membership states remain
distinct with explicit synthetic context. The email is described as a test label;
the credential field is named Fixture token. Integration passed the six focused
auth HTTP/widget tests and built the explicit synthetic release artifact. The
patched artifact is served by the existing supervised web job, while the API,
retained token and specimen revision 21 remained unchanged. The earlier baseline
artifact was retained separately.

The repository runner's four guard tests passed: token preservation/private
permissions, symlink/repository-state rejection, foreign-job refusal, and existing
Firebase configuration preservation. An actual isolated launch on API 8132/web
3032 returned to the caller while launchd continued serving; status verified the
marker and authorized session, a repeated start preserved both jobs, and stop
removed only those jobs while retaining the token and database. Evidence:
`/tmp/specimen-runner-check-launch.log` and
`/tmp/specimen-runner-check-285534c`. User-facing ports 8000/3000 were not touched
by those tests. The check artifact explicitly recorded its dirty worktree state;
it was not presented as a final verified release.

Independent QA uses isolated outage-test ports, preserving the user's restored
services and retained state. The patch still requires independent UI checks,
exact-head canonical verification, an updated PR and all five current-head CI
jobs. No production authentication change or paid inference is authorized by
this repair.
