# Authenticated review scenarios for the latest app

Prepared 2026-10-05 by review acceptance chat
`01a10f67-73f5-7a30-b721-c5578cdd931a`, branch
`codex/review-acceptance-bridge-20261005`, source baseline
`540fbbe6c73fb060bb1234073421aa496874f370`.

This is a finite product observation script for the acceptance integrator. It
does not add a release gate or authorize model calls, retries, deployment,
membership changes, fault injection, or production repair. It supplements the
existing `UI-SAVE-REOPEN`, `UI-PROVENANCE-HISTORY`, `UI-DENIAL-RECOVERY`, and
`UI-NO-SYNTHETIC-FALLBACK` cases in `RELEASE_ACCEPTANCE.md`. Source inspection and
fixture tests cannot establish authenticated persistence through Firebase, App
Check, SQL Connect, and Storage.

## Execution ownership and starting state

- Primary chat `01a10f64-fd1d-7393-acb3-4231c83058d5` assigns each record,
  observer, browser session, and permitted mutation before execution. Lane P
  remains the sole merge and production writer. Observers must not manipulate
  the same browser concurrently or change the owner's account or settings.
- Confirm the integrated source through the normal release results in
  `DEPLOYMENT.md`: all five required checks and all three release workflows,
  Hosting `deployment.json`, API `/version`, and release smokes. Record the
  actual deployed SHA; this document's baseline is not a claim it was released.
- Use the assigned verified production identity and original organization,
  collection, specimen, active run, and image. Verify the application session
  is production and membership permits review. Browser profile identity alone
  does not establish application authentication.
- Keep identifiers, screenshots, response bodies, observation times, reasons,
  and record versions in the primary chat's private evidence directory. Do not
  retain bearer tokens, App Check tokens, signed URLs, or credentials. A short
  sanitized result may name the scenario, deployed SHA, observed revisions,
  expected/actual behavior, and private evidence location.
- Live execution of every scenario below is **Not run by this chat**. Existing
  original-image access on an earlier deployment does not prove latest Save,
  reopen, history, candidate locks, or location derivation.

## Finite observation script

Execute in order. A prerequisite that is absent leaves the affected scenario
`Blocked`; record the actual reason and proceed only with independent read-only
observations. A failed save/readback stops further mutation of that record until
the primary chat reconciles its persisted state.

### R01 — Open the authentic record and its original

1. In the assigned browser, open the queue and the assigned specimen through the
   normal app route. Record the current record revision and record version.
2. Open the source image, select its label regions, and inspect retained readings
   and field research for that record. Compare against the assigned original.
3. Verify that displayed scope, specimen, run, and evidence belong together.
   Record explicit operational failures, unresolved fields, policy/source waits,
   and unavailable images instead of assuming successful processing.

Expected: production content comes from the authenticated API. The original is
visible or an actionable failure is shown. No synthetic records or invented
completed research appear. Current source binding and historical research are
distinguished. This observation does not change the specimen.

### R02 — Stage and discard an ordinary evidence correction

1. Open `Specimen data`. Choose a field and source-supported correction assigned
   by the primary chat; do not use a guessed taxon, habitat, century, or identifier.
2. Stage the correction without saving. Verify the pending change count and the
   proposed field value. Use keyboard focus and visible controls at the assigned
   viewport; field input must retain ordinary editing shortcuts.
3. Navigate away through an app control. Choose to stay when prompted; the draft
   remains. Repeat and discard only this draft, then reopen the same record.

Expected: staging changes no server revision. Navigation requires a decision
about the unsaved draft. Discard returns to the persisted field value and leaves
the revision unchanged. The draft is never presented as a persisted correction.

### R03 — Save a literal correction and reopen from the server

1. Reopen the current record and record its revision `r` and record version.
   Stage the assigned ordinary evidence correction again.
2. Activate `Save 1 pending change`, enter the assigned factual reason, and
   confirm. Wait for the request and server readback to finish before navigating.
3. Observe a newer confirmed record revision, the exact saved value/state, the
   saved reason, and the disappearance of the acknowledged draft. If the app
   reports that the server recorded a decision but could not reopen the record,
   retain that unresolved result; do not submit a new edit to manufacture success.
4. Leave and reopen the specimen, then refresh the application and reopen it
   again through the queue. Use a fresh authenticated app session only if the
   primary chat assigned a test identity/session for that action.
5. Compare exact field text, uncertainty state, reason, revision, record version,
   raw readings, and source evidence before and after fresh reads.

Expected: the persisted correction survives fresh API reads; original readings
and source bytes remain unchanged. Ordinary field edits may consume one revision
per decision; do not assume a multi-field ordinary save is one transaction.
Saving does not itself clear unresolved fields, approve scientific semantics, or
prove a complete harness run. A wrong-record, unchanged, inaccessible, or
unverifiable acknowledgment must not appear as a confirmed save.

### R04 — Save server-owned research candidates and verify human locks

Prerequisite: the assigned field exposes a current retained selectable source
candidate and canonical binding, including its completed qualified source
capture. Report the actual reason when that field's eligible candidate or binding
is unavailable. Unrelated pending fields or absent autonomous accepted publication
do not alone block a valid human candidate save.

1. Expand the assigned field's research and inspect its retained candidate,
   evidence, literal source, normalized value, and authority identifier.
2. Stage one or, when assigned, two eligible candidate choices. Verify that
   staging alone leaves the persisted record untouched.
3. Save once with a reason. Observe the normal authenticated candidate-bearing
   batch request and subsequent workspace readback, with credentials excluded
   from evidence.
4. Freshly reopen the record. Compare selected normalized/parsed values,
   authority identifiers, original literals, retained evidence, human decision
   events, and the saved fields' human locks using supported read views.

Expected: the candidate-bearing batch uses opaque selection identifiers and one
current record CAS; applied decisions in that group report the same `r + 1`
record revision/version. The server supplies accepted values and evidence;
caller-supplied invented values are not a supported UI path. Human-locked fields
are retained in the saved record. The older research binding is historical and
cannot silently become editable again. A research lock is a saved field decision;
the current UI exposes no separate reviewer claim/lease control.

### R05 — Reject a stale save without overwriting the confirmed record

Prerequisite: the primary chat explicitly assigns the record and two stale/current
views or observers. Never create a second actor or change access to run this case.
Perform the actions serially under that assignment; do not share a browser with
another active observer.

1. Retain one allowed draft/candidate view at revision `r` without saving it.
2. In the designated current view, save a different assigned correction and
   confirm its newer persisted revision. Preserve both views' evidence.
3. Submit the stale view only if the app still permits it; otherwise record the
   app's pre-submit stale-draft reconciliation as the observed protection.
4. If a stale request was sent, inspect its rejection and reopen the current
   server record. Compare with the confirmed correction from step 2.

Expected: a stale base revision/version cannot overwrite current data. The
supported API rejects a conflicting mutation with 409; the UI may prevent that
request earlier after a refresh. Failed/unverified changes are retained for
comparison or explicitly discarded, never silently replayed as current choices.
Old candidate selections and human-lock inputs cannot bypass the current binding.

### R06 — Inspect history and optionally restore an assigned version

1. Open `History` after a confirmed save. Find the correction and reason, then
   open the retained version before it and the saved version. Load older pages
   where present and verify contiguous revisions through the requested boundary.
2. Compare historical field values, original/run/evidence lineage, and current
   version. Reopening historical content must remain read-only.
3. Restore only if the primary chat assigned that mutation on this record. Save
   or discard drafts first; choose the assigned retained version and enter a
   factual reason. Confirm the response and fresh current workspace readback.

Expected: history and reasons survive fresh reads. Restore appends a new current
revision with retained restore provenance; it does not rewrite the prior version
or schedule inference. It creates a review-required record rather than treating
the historical disposition as fresh approval. No stale binding becomes editable;
any exposed retained research report is historical/read-only, and a missing report
is an explicit unavailable result. Read-only history inspection can pass without
running a restore mutation.

### R07 — Inspect “Fill the rest” capability, then observe assigned location work

1. On the assigned record's Country field, open research and inspect whether `Fill the
   rest` is available for the current record. Inspect the request sheet and
   eligible fields before submitting. Cancellation must not queue work.
2. Submit only after the primary chat assigns the request and confirms its
   unchanged spending conditions. This chat has no paid-flow authority. Missing
   capability, prerequisite inputs, budget, or publication is a blocking result.
3. Observe the saved request ID, source revision and queued revision. Use
   `Refresh suggestion status` to read that retained request's state.
4. If the primary chat executes the supported worker flow and real proposals
   appear, inspect proved location evidence and offered fields. Accept an
   assigned proposal only through R04, then freshly reopen the saved record.

Expected: this flow requests location suggestions only. Saving a request is not
completed derivation, accepted evidence, or an automatic field write. The accepted
request targets the current source revision and reports queued revision `r + 1`;
retained progress may remain queued/blocked. Existing supported/human-locked fields
and original literals remain unchanged. Proposal selection must use current proof
and record binding. Changed records make old suggestions stale. No “fill every
blank,” fabricated coordinate, or resumed legacy finalized-run claim is valid.

### R08 — Observe denial and recovery using assigned access controls

1. Use only a separately assigned denial fixture or already denied test session.
   Inspect unauthorized workspace, image, history, candidate save, and derivation
   access where that fixture permits the check. Do not revoke the owner's role,
   change membership, switch the owner's account, or expose another collection.
2. Record the app's actionable sign-in/access message. A late result from before
   denial must not restore record content or enable a save.
3. With the assigned positive session, explicitly reverify access and reopen the
   retained record; compare with its last confirmed server state.

Expected: production requests require both identity and App Check plus current
scope authorization. 401/403 invalidates access; old asynchronous results cannot
restore it. Recovery uses an authenticated server read, with no synthetic fallback.
No assertion of real access revocation is made without that assigned experiment.

## Source and fixture coverage map

These files explain expected behavior; they are not live observation evidence.
No implementation change or additional test is needed merely to execute this
script. Focused regressions are justified only by a concrete newly found defect.

| Scenarios | Source | Existing focused coverage |
|---|---|---|
| R01, R08 | `api_repository.dart`, `workspace.dart`, `research/research_host.dart` | `product_acceptance_regressions_test.dart`, `research/research_host_test.dart`, `research/derivation_controller_test.dart` |
| R02, R03, R05 | `workbench.dart`, `workspace.dart`, `screens/workbench/pending_changes.dart` | `review_readback_test.dart`, `review_batch_test.dart`, `api_candidate_batch_test.dart` |
| R04, R05 | `api_repository.dart`, `application/api.py`, `research_harness/human_review.py` | `api_candidate_batch_test.dart`, `test_research_candidate_decisions.py`, `research/research_server_contract_test.dart` |
| R06 | `audit_history.dart`, `api_repository.dart`, `application/history_restore.py` | `live_history_test.dart`, `history_timeline_panel_test.dart`, `test_history_restore_http.py` |
| R07 | `research/derivation_controller.dart`, `research/derivation_repository.dart`, `research_harness/derivation_service.py` | `research/derivation_controller_test.dart`, `research/derivation_repository_test.dart`, `test_research_derivation_api.py` |

Dart paths are under `apps/specimen_digitization/lib/src` or its `test` directory;
Python source is under `src/specimen_digitization`, with tests under `tests`.

## Explicit residuals

- CSV export has no current app control or API route in this audited baseline;
  it is outside this script and no export acceptance is claimed.
- Ten-specimen processing, newly published native canonical evidence, supported
  fresh V2 job admission, scientific accuracy, real worker retries/restarts, and
  spend reconciliation remain with their assigned owners. This script cannot
  upgrade offline results or old finalized runs to live acceptance.
- Canonical Save commits before normalized V2 projection in
  `application/production.py`; projection may remain incomplete while Save
  succeeds. Confirmed workspace persistence and current native research
  materialization therefore require separate observations. Historical research
  after a save is expected behavior, not proof that a fresh projection exists.
- Check the specimen evidence literally: a query spelling is not a validated
  selected taxon; a trap does not prove habitat; event/assembly dates and unknown
  centuries remain distinct. A correction requires actual assigned evidence.
- Root records scenario results as `Pass`, `Fail`, `Blocked`, or `Not run`, with
  observations and remaining scope. Passing these cases alone does not establish
  the full P0 acceptance matrix or acceptance for every specimen.
