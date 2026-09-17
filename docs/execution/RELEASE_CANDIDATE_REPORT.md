# Release candidate report: the front end refactor on pull request 64

Written 2026-09-17 by wave B slot B1 (`fe/release-ci`). It answers one
question: what is actually proved about
[pull request 64](https://github.com/anurag-duddu/specimen-digitization-app/pull/64)
before anyone merges it, and what is only proved afterwards.

Every number below was measured. Where a proof is unavailable this says so and
names what is missing instead of describing the gap as a pass. Nothing here
deployed anything, changed a check, a protection, an environment, an IAM
binding, a pinned action SHA or a smoke assertion. `docs/DEPLOYMENT.md` is the
contract; this is a reading of it against one candidate.

## 1. The candidate

| Item | Value |
|---|---|
| Pull request | 64, `front-end-refactor` into `main`, open, not a draft |
| Head when this slot started | `f3b6363` |
| Head when this slot finished | `3fa61d7` |
| Size | 234 commits ahead of `main`, 0 behind, 980 files changed |
| Test merge commit | `2a43cd7` |

The head moved twice while this was being written. Section 3 says exactly which
measurement belongs to which commit.

## 2. The required checks, as the repository actually enforces them

Read from `repos/anurag-duddu/specimen-digitization-app/branches/main/protection`
on 2026-09-17. Read only; nothing was changed.

| Protection | Value |
|---|---|
| Required status checks | `Repository checks`, `Python tests`, `Flutter checks and web build` |
| Strict (branch up to date before merge) | true |
| Conversation resolution required | true |
| Administrators included | true |
| Required approving reviews | 0 |

Those three names are the whole of branch protection. `Flutter android build`,
`Flutter ios build`, `Runtime candidate structure validation` and the three
runtime image builds also run on the pull request and the Hosting deploy job
waits for the two mobile matrix entries, but they are not protection contexts.
This matches `docs/DEPLOYMENT.md`, which says the three protected names remain
unchanged and that additive branch protection administration is a separate
reviewed change.

The branch is 0 behind `main`, so the strict rule is satisfied as it stands. It
stops being satisfied the moment anything else merges to `main`.

## 3. What CI proves on the pull request head

### 3.1 The Flutter check had never passed on this branch until today

Every `CI/CD` run on `front-end-refactor`, read through the Actions API:

| Run | Head | Design system tests | Client tests | Web build | Artifact upload |
|---|---|---|---|---|---|
| 35189966241 | `9bbca9a` | cancelled | skipped | skipped | skipped |
| 35190042166 | `d4830ce` | failure | skipped | skipped | skipped |
| 35195247198 | `18452a6` | failure | skipped | skipped | skipped |
| 35237037954 | `50b82a9` | success | failure | skipped | skipped |
| 35237915721 | `f3b6363` | success | failure | skipped | skipped |
| 35240271692 | `3fa61d7` | success | success | success | success |

The steps run in order and the job stops at the first failure, so until
`50b82a9` fixed the package golden comparator the client suite had never run on
a Linux runner at all, and until `3fa61d7` **no tested web artifact had ever
existed for this branch**. That is the single most important fact in this
report: the refactor reached its final review with its release build unbuilt by
CI.

### 3.2 What failed at `f3b6363`, and what it was

Run 35237915721, job `Flutter checks and web build`: the design system's 685
tests passed on Linux, client analysis passed, and the client suite reported
**1160 passed, 20 failed, 128 skipped**. The same commit, the same suite, run
in this worktree on macOS: **1301 passed, 7 skipped, exit 0**. The 20 were
Linux only.

All 20 were pixel sampling contrast assertions, in four files:

| File | Failures |
|---|---|
| `test/verification/dark_mode_windows_test.dart` | 9 |
| `test/theme/dark_mode_test.dart` | 6 |
| `test/accessibility/guidelines_test.dart` | 3 |
| `test/accessibility/workbench_guidelines_test.dart` | 2 |

The failure text is what identifies them. The sign in screen reported the same
three semantics nodes in the light run and in the dark run, with identical
sampled colours in both: lightest `#F0EBF2`, darkest `#F7F398`, ratio 0.98
against a required 4.5. A screen that samples identically in both modes, with
no dark pixel anywhere in a rectangle that holds text, has not rendered its
text into the raster the guideline reads. That is a rasterisation difference
between the runners, not a contrast defect: the same tests, on the same commit,
pass on macOS, and `design/12-verification-report-v2.md` measured those same
tokens at 8:1 and better.

Two commits on the integration branch, `76b01d8` and `3fa61d7`, gate those
instruments to the platform where the goldens are drawn, which is the same
treatment the 121 screen goldens and the 336 package gallery goldens already
had. This slot owns none of those files and changed none of them.

### 3.3 What passes at `3fa61d7`

Run 35240271692, read after it completed:

Run 35240271692 completed green. Every job, read from the API:

| Job | Result |
|---|---|
| `Repository checks` | success, 1m53s |
| `Python tests` | success, 9m14s |
| `Flutter checks and web build` | success, all 14 steps |
| `Flutter android build` | success, 5m13s |
| `Flutter ios build` | success, 4m54s |
| `Deploy Firebase Hosting` | skipped |

**All three protected checks pass on `3fa61d7`.** Inside the Flutter job:
design system 685 tests passed, client **1092 passed and 161 skipped**,
`Built build/web`, the deployment stamp written, and the artifact uploaded.
`Deploy Firebase Hosting` is skipped rather than failed, which is correct: its
`if` requires a push to `refs/heads/main`, and a pull request has no way to
satisfy it.

### 3.4 The artifact

| Item | Value |
|---|---|
| Name | `flutter-web-2a43cd74479bb0de9130db0f66bc0daa25339706-35240271692-1` |
| Uploaded size | 12,201,913 bytes |
| Digest | `sha256:4361871de0109d2e03ffd3b51e83ed75ee6ade0ed74272bf6599e0792a3476f2` |
| Retention | expires 2026-09-24 |
| Same build, unpacked in this worktree | 35,146,003 bytes over 41 files |
| `main.dart.js` | 3,272,537 bytes |

Of the unpacked 35 MB, 21.4 MB is the four CanvasKit wasm binaries the Flutter
web engine ships; the application's own compiled code is the 3.27 MB
`main.dart.js`.

The artifact name carries `2a43cd7`, which is the pull request's **test merge
commit**, not its head. On a `pull_request` event `github.sha` is the ephemeral
merge ref, so a pull request artifact can never satisfy the deploy guard: that
guard requires `push`, `refs/heads/main`, and a marker whose `commitSha`,
`runId` and `runAttempt` equal the protected run's own. This is the mechanism
by which a pull request cannot deploy, and it is worth knowing it is the
artifact identity rather than only the job `if` that enforces it.

## 4. What only a push to `main` proves

Nothing on a pull request exercises any of these. Each one first runs on the
merge commit, in a run nobody can rehearse:

| Proof | Why a pull request cannot give it |
|---|---|
| The real FlutterFire configuration compiles and boots | `Restore production FlutterFire configuration` is skipped on a pull request; pull requests build against `lib/firebase_options.ci.dart`, whose app id ends `:ci-placeholder`, and `main.dart` branches on exactly that suffix |
| `SPECIMEN_API_BASE_URL`, `SPECIMEN_RECAPTCHA_SITE_KEY` and `SPECIMEN_ADMIN_CONTACT` reach the client | `build_web.sh` forwards them only when `GITHUB_EVENT_NAME` is `push` and `GITHUB_REF` is `refs/heads/main`; on a pull request the defines are empty and the client renders the setup screen |
| `validate_public_settings.py` accepts the configured values | It runs inside the same main push branch of `build_web.sh` |
| `deployment.json` carries the real merge SHA, run and attempt | On a pull request it carries the test merge commit, as section 3.4 shows |
| The Hosting deploy runs at all | The job's `if` requires a push to `refs/heads/main`, plus the `production` environment and an OIDC token no pull request receives |
| The public marker matches | `scripts/ci/smoke_hosting.sh` reads `https://specimen-digitization.web.app/deployment.json` and compares repository, exact SHA, run ID and attempt |
| The public site serves the new client | Same script, same run |

A release is complete only when the `main` run is green **and** the public
marker reports that exact merge SHA. `docs/DEPLOYMENT.md` rule 11.

## 5. What this slot added to the gates

Two checks, both additive. No existing check, protection, environment, IAM
binding, pinned action SHA or smoke assertion was touched.

### 5.1 Dart formatting

`scripts/ci/verify.sh` and the `Flutter checks and web build` job now run

```
dart format --output=none --set-exit-if-changed \
  lib test packages/specimen_ui/lib packages/specimen_ui/test
```

The wave G integration formatted the tree once; from here on drift fails a gate
instead of turning a later review into a diff of whitespace. The scope is the
client and the design system, and deliberately not
`docs/execution/qa-evidence`, which is frozen evidence. Measured on this
worktree: 393 files, 0 changed.

### 5.2 A route smoke over the built artifact

`scripts/ci/smoke_web_routes.py` is new. In CI it runs between the deployment
stamp and the artifact upload, so a build that fails it is never uploaded and
therefore can never be deployed. It serves `build/web` on 127.0.0.1 with the
rewrites `firebase.json` declares, contacts no host, holds no credential and
deploys nothing.

It reads the route table out of `lib/src/app/app_router.dart` and
`lib/src/app/routes.dart` rather than restating it, so a route added, renamed
or nested reaches the gate without anyone editing it. The ten locations it
found, each of which answered with the application shell:

```
/  /sign-in  /verify  /setup  /help  /gallery
/c/:collection/queue          /c/:collection/queue/:specimen
/c/:collection/intake         /c/:collection/intake/sources
/c/:collection/intake/sources/:source
```

It also checks that `/main.dart.js` and `/flutter_bootstrap.js` are still
served as themselves, because a rewrite that swallowed every path would make
the route sweep prove nothing.

**The gallery, measured rather than asserted.** The brief for this slot
expected the gallery route string to be absent from a release
`main.dart.js`. It is not, and the reason is worth recording rather than
gating around:

| Build | `/gallery` in `main.dart.js` | Gallery only strings present |
|---|---|---|
| `flutter build web --release` | 1 | 0 of 220 |
| `flutter build web --profile` | 2 | 218 of 220 |

The single surviving occurrence in the release bundle is
`if(i==="/help"||i==="/gallery")return m`, the compiled form of
`AppRoutes.isGlobalLocation` in `lib/src/app/routes.dart`. That comparison is
live code in every build, so the literal cannot be tree shaken, while the
`GoRoute` behind `if (!kReleaseMode)` is. The gallery **screen** is genuinely
absent: not one of the 220 strings that only the gallery can contribute appears
in the release bundle, and 218 of them appear in a profile build of the same
source. The gate therefore asserts the screen's absence, and allows the one
router comparison by name. Judged as a release build, the profile bundle fails
both halves, which is the evidence that the check measures something.

**The deployment marker.** The script restates, in Python, the rules the two
shell guards enforce with streaming `jq`: exactly six fields, no duplicate key,
no second document, `schemaVersion` the number 1, the repository string, a 40
character lowercase hex `commitSha`, `runId` and `runAttempt` as positive
integers written as strings, and a `builtAt` that round trips through
`%Y-%m-%dT%H:%M:%SZ`. Thirteen tests run the marker through **the filter
actually read out of `scripts/ci/smoke_hosting.sh`** and assert the two agree
on every case, so the restatement cannot drift from the guard. One divergence
was found that way and closed: `True == 1` in Python and `true == 1` is false
in jq, so a `schemaVersion` of `true` was accepted here and would have been
refused at the deploy.

`scripts/ci/test_smoke_web_routes.py` is 64 tests and passes.

### 5.3 What the green run at `3fa61d7` does not include

Neither of these two checks ran in it. They are on `fe/release-ci` and reach
`front-end-refactor` only when the integrator merges this slot. The first run
that exercises them is the first `CI/CD` run after that merge.

## 6. The compiled settings the client consumes

Every `fromEnvironment` in the client and the design system, where it is read
and whether the pipeline can deliver it.

| Define | Read at | What consumes it | Forwarded by `build_web.sh` |
|---|---|---|---|
| `SPECIMEN_API_BASE_URL` | `lib/main.dart:33` | `ConnectionConfig.apiUrl`, validated by `ConnectionConfig.validate`, then the base URL of `ApiSpecimenRepository` | Yes, main push only, and only paired with the site key |
| `SPECIMEN_RECAPTCHA_SITE_KEY` | `lib/main.dart:37` | `ConnectionConfig.siteKey`, then App Check activation. On web an empty key is a `FormatException` and the window lands on the setup screen | Yes, main push only, paired with the API URL |
| `SPECIMEN_ADMIN_CONTACT` | `lib/src/administrator_contact.dart:62` | `AdministratorContact.fromBuild`, the fallback used wherever no collection document publishes a contact, which is every screen raised before a collection exists: sign in, setup, verification, and the help sheet | Yes, main push only, independently of the pair |
| `SPECIMEN_LOCAL_SYNTHETIC` | `lib/main.dart:34` | The local fixture session. `validate_public_settings.py` refuses any value but `false` in a main build | Never |
| `SPECIMEN_AUTH_EMULATOR_HOST` | `lib/main.dart:39` | `ConnectionConfig.authEmulatorHost`, which `validate` rejects outside synthetic mode. The validator refuses it set at all in a main build | Never |
| `APP_BUILD` | `lib/src/app/help_screen.dart:59` | `appBuild`, rendered as `Build: $appBuild` at `help_screen.dart:252` | **Never, by anything in this repository** |

The API URL and the site key are paired in both directions: the validator
refuses one without the other, and `ConnectionConfig.validate` refuses an empty
site key on web. Both unset is the deliberate third state, which keeps the
setup screen releasable before the backend exists. That is the state the site
is in today, and the release plan expects it until the API is configured.

The administrator contact is the one the client reads the way the plan expects.
`validate_public_settings.py` accepts `Name <address>`, `Name, address` and a
bare address, and `AdministratorContact.fromBuild` parses exactly those three
into the sentence that replaces "ask your administrator". Verified by running
the validator over all three.

## 7. Findings

### 7.1 `APP_BUILD` is read by the client and set by nothing

`help_screen.dart:252` renders `Build: $appBuild` in the help sheet so a
reviewer can name the build when they write to an administrator. No workflow,
script or build step anywhere in the repository passes
`--dart-define=APP_BUILD=...`, so the constant keeps its default and every
deployed build says `Build: Not stamped by the build`. Verified by grep over
every `.sh`, `.yml` and `.py` in the tree.

The value is already at hand: `write_deployment_metadata.sh` writes
`$GITHUB_SHA` into the artifact one step later. Forwarding the same SHA as
`APP_BUILD` in `build_web.sh`, beside the three defines it already forwards,
would close it. `build_web.sh` is not this slot's file and was merged from
`main` only recently, so this is recorded rather than done.

### 7.2 The client documents a contact form the pipeline refuses

`administrator_contact.dart` lists `The entomology data team` among the
accepted spellings, `AdministratorContact.fromBuild` parses a bare name into
`name`, and `test/screens/help_and_contact_test.dart:142` asserts that
behaviour with `'Your curator'`. `validate_public_settings.py` refuses a bare
name: verified by running it, which exits 1 with `invalid administrator
contact`.

The validator is the stricter of the two, so nothing bad can reach the client.
The defect is that a documented and tested form can never be delivered, which
will read as a bug to whoever sets the repository variable and watches the
build fail. Either the doc comment and the test should drop the bare name form,
or the validator should accept it. This is a decision for whoever owns the
contact, not a change to make silently.

### 7.3 The pixel sampling instruments are platform dependent

Section 3.2. Diagnosed here, fixed on the integration branch by `76b01d8` and
`3fa61d7` while this was being written. Recorded because the shape recurs: this
is the third family of pixel reading tests on this branch to need the same
macOS gate, after the 121 screen goldens and the 336 package gallery goldens.
A test that reads rasterised pixels is a macOS test in this repository, and a
new one should be written that way rather than discovered by a red CI run.

## 8. Merging

The branch is up to date with `main`, all three protected checks are green on
`3fa61d7`, and merging is done through GitHub, never by pushing to `main`:

```bash
gh pr checks 64 --watch
gh pr merge 64 --merge
```

`docs/DEPLOYMENT.md` step 6 writes this as `gh pr merge --merge
--delete-branch`. Do not add `--delete-branch` yet: it deletes
`front-end-refactor`, which is the branch every live `fe/*` slot worktree was
cut from and merges back into. Delete it once every slot has merged and its
worktree is retired.

After the merge, `docs/DEPLOYMENT.md` section 7 is the procedure that has to be
followed to completion: watch the `main` run, confirm all six jobs including
`Deploy Firebase Hosting`, then independently re-run

```bash
scripts/ci/smoke_hosting.sh \
  https://specimen-digitization.web.app \
  "$(git rev-parse HEAD)" \
  EXPECTED_RUN_ID EXPECTED_RUN_ATTEMPT
```

and record the merge SHA, the pull request URL, the run URL, the deploy job
result, the public URL and the smoke result. Until that marker reads the merge
SHA, the release is incomplete, whatever the workflow says.

## 9. What this report does not prove

- **The public site.** Nothing here touched `https://specimen-digitization.web.app`. The route smoke serves a local directory on loopback; it says the artifact is well formed, not that anything is deployed.
- **Anything at a head later than `3fa61d7`.** The head moved twice in the two hours this took. A green run is evidence about the commit it ran on and about nothing else, and this slot's own two checks are not in it (section 5.3).
- **The production FlutterFire configuration.** Never exercised on a pull request. First proved on the merge run.
- **The live data pilot.** Out of scope for wave B entirely. Its open items are in `docs/execution/CURRENT_RELEASE_CHECKLIST.md`: protected DATA initialisation, runtime authorisation, App Check registration, credential lifecycle, and the pending cost ceiling decision. None is a front end gate, and none of them is changed by this pull request.
- **Anything about the runtime or data planes.** `runtime-release.yml` and `data-release.yml` fail closed at admission on every push while no release inputs are installed, and that is their correct behaviour, not a regression this branch introduced.
