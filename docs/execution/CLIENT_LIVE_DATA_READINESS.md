# Client live data readiness

Written 2026-09-17 by the wave B slot `fe/release-client`
(`docs/execution/FRONT_END_REFACTOR.md` section 3I, B3).

> Corrections (2026-09-22): PR42 merged on 2026-09-14 as `461936d`, so item 1
> of the quoted checklist is closed. The environment band's pilot state is
> wired: `scripts/ci/build_web.sh` and `.github/workflows/ci-cd.yml` forward
> `SPECIMEN_PILOT_SCOPE` on main pushes, so the "not wired" finding below is
> resolved and only the repository variable remains unset. The current order
> of work is in [GO_LIVE_RUNBOOK.md](GO_LIVE_RUNBOOK.md).

**What this is.** An honest statement of what the Flutter client can be
trusted to do when it meets real specimens, and of everything that still
stands between the deployed client and the first real record. It covers the
client only. The items in section 5 are the user's, protected CI's and the
backend workstreams', and nothing in this document closes any of them.

**What this is not.** Evidence that the pilot can run. No item that
`docs/execution/CURRENT_RELEASE_CHECKLIST.md` marks open is marked done here.
No test in this repository has ever spoken to the live API: the thousand real
slides are in Cloud Storage and are not reachable from a workstation, and the
production API has no published address yet (section 5, item 8).

---

## 1. What the client verifies

Every row is a test that runs in `flutter test` from
`apps/specimen_digitization`. The shapes the tests use are in
`test/fixtures/live_shapes/`, each carrying, in its own `evidence` field, the
document it was shaped from. None of them is real data and each says so.

### 1.1 The wire contract

`test/live_wire_contract_test.dart`, eight tests.

| What it holds | How |
|---|---|
| The client reads the contract the API published | The client's `test/fixtures/backend-wire-examples.json` is byte identical to `docs/execution/backend-wire-examples.json` and matches the digest `docs/execution/FLUTTER.md` pins |
| Every route the client can reach is a route the contract describes | The probe drives `ApiSpecimenRepository` through every public method, records the twenty nine distinct paths it builds, and matches each against `docs/execution/backend-openapi.json` or the named amendment |
| Every property the client sends is one the request model declares | Each body is checked against the OpenAPI schema for its route. Every request model is `extra="forbid"`, so an undeclared property is a 422 rather than a warning |
| The intake bounds are the contract's bounds | `intakeMaximumBytes` and `intakeMaximumSide` are read against `ItemInput`'s own maxima rather than restated |
| An unknown field never breaks a record | A workspace response carrying fields from a later release still parses, still yields twenty fields and still yields the photograph |
| An absence is never a zero | A source page with no `matching_count` keeps null, an unfinished run keeps a null disposition, an unsettled cost reads "Not recorded" |

The probe asserts a floor of twenty nine routes. It once recorded a single
path and reported that every path the client makes was described, because the
repository refuses protected calls until a session is verified; the floor is
what stops that from being silent again.

**The published request contract is stale, and the client is right.** The
snapshot in `docs/execution/backend-openapi.json` describes twenty routes; the
backend serves thirty seven. It also predates four request properties and
two whole request models. The
test carries both gaps as shrink only backlogs, each entry naming the line of
backend source that declares the route or the property:

| Missing from the snapshot | Declared at |
|---|---|
| Fifteen routes: history, history by revision, active graph, phases, authority results and their raw form, observation raw, declarations and metadata, disagreements, image preflight, sources, source objects, import from source, batch decisions | `src/specimen_digitization/application/api.py`, lines named in the test |
| `BatchInput.sensitive`, `ItemInput.sensitive` | `application/api.py:89`, `:98` |
| `Region.rotation_quarter_turns` | `application/domain.py:125` |
| `ClassificationInput.profile_collection_id` | `application/api.py:158` |
| `DecisionBatchInput` and `BatchDecisionInput`, whole models | `application/api.py:138`, `:124` |
| `ItemInput.width` and `height` are required in the snapshot and optional in the backend | `application/api.py:105`, `:106` |

Regenerating `backend-openapi.json` from the running application empties both
backlogs. Until then the client is checked against the backend source rather
than against a snapshot that would call five correct requests malformed. This
is a backend workstream item, not a front end one, and it is item 12 in
section 5.

### 1.2 Live shaped records on the screens

`test/live_shapes_test.dart`, eleven tests, each at 390 by 844 and at 1180 by
820, with every frame's overflow collected and asserted empty. Every shape is
sent through `ApiSpecimenRepository` before a screen sees it, so the record
under test is the one the client's own parse built.

| Shape | What it proves |
|---|---|
| Twelve label regions, two readers, every region in disagreement | Both readers stay named on every reading, each disagreement is counted in words rather than coloured, and the blocker count is a number the reviewer can act on. Nothing overflows at either window |
| A transcription of four hundred characters | The whole reading is on screen rather than an ellipsis of it, and the measured difference fraction renders as measured |
| An original of 6000 by 4000 pixels | Section 1.4 |
| Every measurement missing | Every field reads "Unknown", the disposition stays null, the cost stays unsettled, and no string on the screen is "0", "None" or "null" |
| A queue of one thousand rows | The count is of what was loaded, never of a total the list API does not answer. See the finding in section 6 |

### 1.3 Environment and entry

`test/live_environment_test.dart`, nineteen tests.

The band has three states now, not two. Production has always drawn nothing,
because the condition it would name is the normal one. A bounded pilot is a
third condition: the records are real, which is the whole difference from a
test build, and the scope is limited, which a reviewer needs before they go
looking for a record that is not in it.

| Environment | Pilot stamp | Band |
|---|---|---|
| `production` | empty | none, exactly as before |
| `production` | set | "Bounded pilot: `<scope>`. Records here are real." |
| anything else | either | "Test environment. Not approved museum records." |

A test build carrying a pilot stamp shows the test band. It is the stronger
statement, and two bands would be two regions saying one thing (13 section
2.4).

The server has no word for a pilot: the backend's `create_app` takes exactly
`synthetic`, `emulator` and `production`. A deployment stamps it in through
`SPECIMEN_PILOT_SCOPE`, the way it already stamps the administrator contact
and the API address. **Nothing wires it yet**: see section 6.

Each band names an administrator where one is named, and says nothing where
none is. `AdministratorContact` answers a sentence either way, and the
sentence for an unstamped build says where a contact would be published rather
than naming one; that belongs in the help sheet (07 section 10), not on a band
that is two lines at every text scale (finding V-15).

**The contact forms, and why the client and the deployment gate differ.**
`scripts/ci/validate_public_settings.py` runs inside
`scripts/ci/build_web.sh` on a push to `main` and nowhere else, and it is the
only way `SPECIMEN_ADMIN_CONTACT` reaches a released build. It admits exactly
three forms, all of which carry an address: `Name <address>`, `Name, address`
and a bare address. Its own `scripts/ci/test_public_settings.py` rejects a
bare name by name.

`lib/src/administrator_contact.dart` parses a fourth, a bare name such as
"The entomology data team", and documents it as an accepted spelling.

**They should differ, and the difference is which source is being read.** The
parser serves two: the build stamp, which the gate settles, and the collection
document, which it has no jurisdiction over. A collection that publishes "The
entomology data team" has named its administrator even though it has given no
address, and a client that refused that would lose the authoritative source to
satisfy a build setting. Through the stamp the fourth form cannot arrive at
all, so nothing in a released build depends on it.

Pinned in `test/live_environment_test.dart`: each of the gate's three accepted
strings parses into the two halves the gate assumes, each reaches the band as
a sentence beginning "Ask", and a bare name parses into a name with no address
and therefore offers no mail link. Two documentation lines still say the wrong
thing and are in section 6.

Entry screens: every Firebase Auth code `emailLinkError` and
`authErrorMessage` name is asserted to reach a sentence that says what to do
next, never the raw code and never the exception type. A code from a later SDK
still gets a recovery.

### 1.4 Connectivity and image memory

`test/live_connectivity_test.dart`, eleven tests, each driving a real
`ApiSpecimenRepository` over a failing transport under a real
`WorkspaceController`, and reading the sentence and the recovery a reviewer is
left holding (07 section 11).

| Failure | Sentence | Recovery | Access |
|---|---|---|---|
| Offline (`ClientException`) | "Connection interrupted." plus what the records on screen still are | Retry | kept |
| Timeout | "The request timed out." plus reconcile, because a timed out write may have landed | Retry | kept |
| 401 | the service's own sentence plus "could not be verified" | Check access again | cleared |
| 403 `access_denied` | as 401 | Check access again | cleared |
| 403 `email_verification_required` | the service's sentence reaches the banner | Check access again | cleared |
| 409 and 412 | "Another reviewer saved a new version while you were working. Your decision was not saved." | Refresh and compare | kept |
| 5xx | the service's sentence plus the last successful load | Retry | kept |

A 401 or a 403 clears the queue, the scope and the open record: nothing
editable survives a denial.

The thirty second wire wait is one named constant,
`apiRequestTimeout`, read by all seven waits (the sign in refresh, the App
Check token, every JSON request, the evidence stream and the two on the source
photograph). A test holds it there by counting `Duration(` in
`lib/src/api_repository.dart`, which is now one. The
`no_literal_geometry` backlog for that file went from seven to one.

**Image memory.** `lib/src/source_pixels.dart` decodes at the size the
photograph is drawn, never at the size it was captured. A 6000 by 4000
original decoded whole is ninety six million bytes of premultiplied pixels
held in the image cache, for one record, on a phone that still has the queue
behind it. The bound is the window in device pixels, and the pane's own width
where the pane knows it. The test reads the pixels the engine actually
produced, not the argument the widget was given.

---

## 2. What CI proves

`.github/workflows/ci-cd.yml` runs four jobs on every pull request and on
`main`, and `scripts/ci/verify.sh` runs the same gates on a workstation.

| Job | Proves |
|---|---|
| Repository checks | the pre-commit hooks, including secret scanning |
| Python tests | the backend suite |
| Flutter checks and web build | `flutter analyze --fatal-infos` and `flutter test` for the design system and for the application, the string lint against its baseline, and a release web build that is uploaded as the artifact the deploy job later downloads |
| Mobile builds | an Android and an iOS build from a temporary synthetic native configuration |

Every test in section 1 runs inside the Flutter job. **CI proves the client
against fixtures and against the published contract. It has never spoken to
the live API**, and no job in this repository is allowed to: `AGENTS.md`
forbids a deploy or a cloud command from any workstation or agent shell.

Slot `fe/release-ci` owns everything in this section. Where a gate this wave
added is not yet in `verify.sh`, that slot lands it.

---

## 3. What a merge to main deploys

**This has now happened once.** Pull request #64 was merged to `main` at
15:37 UTC on 2026-09-17 as the squash `4f9f518`, and the `main` CI/CD run
`35241427956` deployed the client to Firebase Hosting with the deployment
marker verified. The public site serves the rebuilt client against whatever
backend environment the public settings name. That last clause is deliberate:
this worktree cannot reach the cloud, so what the settings name is established
by a browser check and by nothing written here. The merge is reported by the
wave's CI slot and by the coordinator, not observed from here.

Nothing below changes because of it. It is the runbook for the next merge, and
item 8 of section 5 is still open: a deployed client is not a connected one.

One thing is deployed: the web client, to Firebase Hosting.

`deploy-hosting` runs only on a push to `main`, only after all four test jobs
pass, in the `production` GitHub environment, over keyless Workload Identity
Federation. It downloads the exact artifact the Flutter job built and tested,
deploys it, and then verifies the public site against the commit, run and
attempt that produced it. A pull request cannot deploy.

It does **not** deploy the API, the database, the model workers, the Storage
rules or the SQL schemas. Those are `runtime-release.yml` and
`data-release.yml`, each main only, each with its own environment and
identity, each gated by the approved contract in `docs/DEPLOYMENT.md`.

The client the deploy job ships reads three build stamps, supplied from
GitHub repository variables and only on `main`:
`SPECIMEN_API_BASE_URL`, `SPECIMEN_RECAPTCHA_SITE_KEY` and
`SPECIMEN_ADMIN_CONTACT` (`ci-cd.yml` lines 113 to 115,
`scripts/ci/build_web.sh`), and `build_web.sh` validates them through
`validate_public_settings.py` before the build, on `main` and nowhere else.

Whether they are set is not visible from this repository. The last recorded
observation is `docs/execution/PRODUCTION_RELEASE_PLAN.md` gate G8, "Not
accepted: fresh public browser shows Collection connection required and API
not configured", which is what an unset `SPECIMEN_API_BASE_URL` looks like
from a browser. Only a browser check settles it now, and settling it is item 8
of section 5 either way: a deployed client with no API to reach is still a
client with nothing to show.

---

## 4. Where the contract lives

For anyone reconciling the client against the API later:

- `docs/execution/CONTRACTS.md` is canonical. Its canonical wire freeze adopts
  the explicit HTTP serializers in `src/specimen_digitization/application/api.py`
  and supersedes every earlier serializer proposal.
- `docs/execution/backend-openapi.json` is the generated request contract, and
  is stale as section 1.1 records.
- `docs/execution/backend-wire-examples.json` is the generated response
  contract. `docs/execution/FLUTTER.md` pins the client's copy by digest.
- `src/specimen_digitization/application/domain.py` is the authoritative typed
  source. Every model extends `Record` with `extra="forbid"`.
- `dataconnect/schema/schema.gql` is the persistence schema. The client never
  speaks GraphQL; `schema.gql` line 2 says only named server operations are
  exposed.

---

## 5. What stands between the deployed client and real data

Quoted from `docs/execution/CURRENT_RELEASE_CHECKLIST.md`, updated
2026-09-14T09:25:00Z. Its current checkpoint supersedes the historical
snapshots below it in that file, including their budget and pending decision
statements. Every row below is a box that file leaves unchecked. None of them
is a front end item and none is closed by this wave.

The checklist assigns them: "Root owns native credentials, IAM, operational
scopes, ledger admission and activation." Release: data and cloud readiness
"owns source integration, canonical checks, PR and protected DATA work."
Release: runtime and model processing "owns runtime setup/controller source
and processing." Release: product journey and acceptance "owns the final
authenticated journeys."

| # | Open item | Owner | Blocks |
|---|---|---|---|
| 1 | "Complete the integrated source release through protected CI." Candidate `bd80f92` is open as PR42 with CI/CD and candidate runs in flight; "Final merged source remains unselected until all checks and review pass" | Data and cloud readiness | everything |
| 2 | "Finish actual credential acquisition composition." Neither the reader nor the capture launcher "has been activated with real credentials" | Root | 4, 5, 7 |
| 3 | "Resolve current App Check registration and organization-level assessment pricing/usage from actual settings; project-level zero usage alone is insufficient" | Root | 8 |
| 4 | "Qualify one final merged source, all five exact-source checks, protected workflow inputs, existing account credentials and complete cost reservations before any new native effects" | Root, with data and cloud readiness | 5 onward |
| 5 | "Execute protected DATA initialization, recovery verification, clone cleanup and first owner bootstrap before the runtime authorization clock begins" | Data and cloud readiness, protected CI | 7 |
| 6 | "Repair the cached Google user-credential lifecycle before admission." Google gives a one hour user token; the helper requires at least 3631 seconds residual at API start | Root | 5, 7 |
| 7 | "Record a genuine immutable original runtime authorization at API start, with worker timing T equal to that start" | Runtime and model processing | 8 |
| 8 | "Verify the prepared API, authentication denial, owner membership and App Check. Publish the paired API URL/site key through protected Hosting" | Runtime, then protected Hosting | the client reaching anything at all |
| 9 | "Import the ten original objects through the authenticated app, activate one bounded worker, and retain actual SAM/reader/model/trace evidence for every region" | Product journey and acceptance | 10 |
| 10 | "Review each actually ready specimen while remaining processing continues when its lease and API permit" | Product journey and acceptance | 11 |
| 11 | "Compare, correct, save and reopen all ten through the live URL; independently reconcile source, data, costs, cleanup and acceptance" | Product journey and acceptance, plus independent review | acceptance |
| 12 | Regenerate `docs/execution/backend-openapi.json` from the running application, so the fifteen routes, four properties and two models of section 1.1 stop living in a test's amendment map | Backend workstream | nothing; it unblocks a gate rather than a release |

**The one user action the checklist names** is not engineering: "The
outstanding user action is unlocking the Mac for the remaining browser
verification; an asynchronous request is already pending."

**On budget.** The checklist's current checkpoint records the USD12 cumulative
and daily ceiling as approved, along with one 3500 second worker and the three
reviewed IAM changes. The unanswered combined decision further down that file
is in the historical snapshot section, which the checkpoint explicitly
supersedes. `docs/execution/PRODUCTION_RELEASE_PLAN.md` still carries an
entry, dated 2026-09-13T21:38Z and therefore older than the checkpoint,
computing the whole path at about USD8.24 against a USD5 ceiling. Treat the
checkpoint as current and the plan entry as superseded, and do not infer a
fresh approval from either.

### The order

1 must land before 4. 2 and 6 must land before 5 and 7, because an
authorization clock cannot start on a credential that expires inside it. 3
must land before 8. 5 before 7, 7 before 8. 8 before anything the client does,
because until the API address and the site key are published through protected
Hosting, the deployed client has nothing to reach. Then 9, 10 and 11 in order.
12 can happen at any time and blocks nothing.

The client's own work is done before 1 and is not in this list.

---

## 6. Found and not fixed

Each of these is another slot's file. Recorded with the line rather than
edited, per this wave's ownership rules.

| Finding | File and line | Owner |
|---|---|---|
| **The queue builds every row a collection has.** `ListView(children: ...)` is the eager constructor, so a page of a thousand rows builds a thousand `QueueRow`s whether or not one is on screen. Measured: 1000 of 1000 at both windows. 13 section 4.2 rebuilds this screen as one scroll, which is a `CustomScrollView` with a `SliverList.builder`; that fixes it | `lib/src/screens/queue/queue_screen.dart:416` | A3 |
| **A thumbnail decodes the whole original.** `SpecimenThumbnail` draws into a list row's leading slot and passes no `cacheWidth`, so a 6000 by 4000 capture is decoded at full size into a square of about forty logical pixels. The queue never passes bytes today, so only the intake manifest reaches it, once per row | `lib/src/widgets/thumbnail.dart:59`, fed from `lib/src/screens/intake/manifest_panel.dart:390` | unowned; nearest is A3 |
| **The pre upload preview decodes at the original's dimensions.** `cacheWidth: q.width, cacheHeight: q.height` is the capture's own size, which is a bound in name only | `lib/src/capture_quality.dart:329` | capture slot |
| **Closed on `fe/compose-record` (2026-09-17).** The record screen's segments were below the fold on a phone: at 390 by 844 the Readings, Fields and History strip laid out at y about 1010, so the readings, which are the work, were off screen. The screen is one `CustomScrollView` now (13 sections 2.1 and 4.1): the segments sit at y 644 of 844 and the first reading at 824, both inside the first viewport, with the photograph 344 dp of it, and `test/screens/record_composition_test.dart` measures the cell | `lib/src/workbench.dart` and `lib/src/screens/workbench/` | A2 |
| **The environment band's pilot state is not wired.** `EnvironmentBanner` reads `SPECIMEN_PILOT_SCOPE` and defaults to empty, so nothing changes until a deployment stamps it. Two lines are needed: pass it through `build_web.sh` beside `SPECIMEN_ADMIN_CONTACT`, and add the repository variable to `ci-cd.yml` beside lines 113 to 115 | `scripts/ci/build_web.sh:12`, `.github/workflows/ci-cd.yml:115` | B1 |
| **The band does not name the collection's own administrator inside the shell.** `EnvironmentBanner` takes `contactSentence` and falls back to the build stamp. Inside the collection shell the collection document is open and knows better | `lib/src/app/shell.dart:239`, pass `AdministratorContact.of(controller.scope).sentence` | A3 |
| **Two documentation lines disagree about the contact forms.** `lib/src/administrator_contact.dart` lists a bare name among the spellings of the build stamp, and the deployment gate refuses one; the validator's own docstring says the client parses three forms when it parses four. The behaviour is right on both sides (section 1.3) and only the prose is wrong | `lib/src/administrator_contact.dart:57` and `scripts/ci/validate_public_settings.py:43` | unowned, and B1 |
| **A stale unverified address gets the generic denial sentence.** The production API answers 403 `email_verification_required` (`docs/execution/LIVE_API.md`); the client normally never reaches it because `lib/src/auth.dart:53` gates on the local flag first. When the local flag is stale the service's own sentence does reach the banner, and the recovery, an access recheck, does resolve it. The banner does not say "verify your address" in those words | `lib/src/app/shell.dart`, the entry screens | A3 |

---

## 7. What could not be tested here

- **Anything against the live API.** There is no published address (section 5,
  item 8) and no workstation may reach one.
- **Real specimen bytes.** The thousand slides are in Cloud Storage. Every
  shape in `test/fixtures/live_shapes/` is built from the wire contract and
  from documented evidence, and each fixture says so in its own `not_real`
  field.
- **Real Firebase Auth.** The codes are asserted against the client's own
  mapping with constructed exceptions. `docs/execution/LIVE_API.md` calls this
  what it is: SDK tests with injected returns are local contract tests, not
  real Firebase validation.
- **A 6000 by 4000 photograph end to end.** The metadata is real shaped and
  the decode bound is asserted on the small checked in photograph. A repository
  does not check in twenty four megabytes to prove a bound it can prove on a
  thousand pixels.
- **Cost, IAM, App Check registration and every native effect.** Root's, and
  out of this client's reach by design.
