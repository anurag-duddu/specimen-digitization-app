# Bulk photo intake

The explicit boundary is **Add photos → review → Submit → intake progress →
specimen pipeline**. One accepted photo creates one specimen. Saving bytes,
restoring a draft, browsing a source, and editing a photo never dispatch scientific
processing. The specimen Queue keeps its existing Needs Human, Cleared and
Deferred meanings.

## Implementation and compatibility

`application/intake_models.py` defines private drafts/items, submissions/results,
and provider connections. Collection-scoped routes are under
`/v1/organizations/{org}/collections/{collection}/intake`. Every operation checks
current collection membership, the draft owner, and sensitivity. Draft items have
stable immutable content identities. The draft manifest uses revision checks;
Submit atomically freezes that manifest and creates an intake-job outbox pointer.
A worker can reconstruct the submission if the request dies after that commit.
A lost acknowledgement is reconciled by identity before retrying a write.

Items and results are separate SQL Connect auxiliary documents. Metadata pages
and bulk reads have ownership filters in the connector. Bytes and thumbnails use
private content-addressed blob storage. HTTP upload chunks are bounded at 4 MiB;
the client sends 1 MiB chunks and hashes file streams. Existing size, pixel, and
optional HEIC/DNG decoding limits remain in force through shared validation.
The legacy upload-completion APIs remain compatible with installed clients.

A private `specimen-intake` Cloud Run job uses the API image and receives no model
inference credentials. It claims persisted leases, validates/stages photos,
retries bounded transient provider failures with backoff, and hands submitted
photos to the existing pipeline. A submission waiting for client bytes sleeps
until a saved-item wakeup. A collection-level wake lease coalesces starts; the
worker has a bounded idle grace period. Pipeline wakeups occur after a group of
accepted photos has been persisted. Cancellation never rolls back an accepted
specimen. Failed launches and uncertain handoffs remain visible and retryable.

The Flutter repository/controller owns file-backed transfer and draft recovery;
widgets render the shared grid, inspector, capture tray, and progress view.
`specimen_ui/UiPhotoTile` uses the package's existing tokens and controls.
Native recovery copies live under the app support directory in an owner/collection
namespace and are released after the server acknowledges staged bytes. Browser
files require reselection if they were not safely staged before leaving; the
workspace warns about that before leaving and restores the metadata honestly.
The warning includes transfers belonging to older submissions, even while a new
draft is open. Each submission can reselect its unfinished originals by checksum
and length, resuming the same immutable item and acknowledged byte offset.
If all bytes arrived but the browser lost the final acknowledgement before save,
**Finish saved transfers** validates those retained bytes without asking for the
originals again. Progress headers and their recovery actions scroll with the
virtualized item list, including on a phone at 200% text.
Removing a draft is a logical discard; shared blobs are never blindly deleted,
because a submitted specimen may reference the same content. Physical blob GC
requires reference-aware retention policy and is not performed by a discard.

## Sources and permissions

All sources return selections to the same draft. A source selection is limited
to 500 photos; oversized folders require narrowing, and no list is silently
truncated. Subfolders are opt-in. Provider originals are never changed.
Source browsers provide an explicitly requested, authenticated image preview
using the same decoding limits in temporary private staging. Links name the
selected provider account; multiple connections are never silently substituted.

- Google Picker uses `drive.file` without combining previously granted scopes.
  Folder browsing requires a separate
  `drive.readonly` connection. Resource keys on shared links are preserved.
- Dropbox shared files and folders use authenticated read-only sharing APIs,
  including relative paths within folder links; they do not become anonymous
  direct-URL downloads.
- Registered sources preserve their existing sensitive inventory protection by
  default. An administrator can explicitly register `sensitive: false` for a
  non-sensitive source. Its allowed media types remain enforced. A mandatory
  source classification survives replacement edits.
- Direct links are HTTPS images only. DNS addresses are checked and the actual
  connection is pinned to the checked public address. Every redirect is checked
  again; byte count and elapsed download time are bounded. No webpage scraping.

### Connector interaction

Drive and Dropbox start with one short description and **Connect**, continue
through provider consent, and immediately open photo selection. Google reuses the
user-opened sign-in popup for Picker; Dropbox opens its folder browser in the
source sheet. Native clients use Google's system-browser Picker during OAuth
(`trigger_onepick=true`), with `drive.file` as the only requested scope. The
provider returns selected file IDs to the HTTPS callback; the app then completes
the connection with its original session proof. Returning native users choose
files through that same provider flow, preserving the saved account identity.
The server validates each selected file and retains the selection for authenticated
polling after a lost completion reply. Selection does not create a draft or submit
a specimen. Returning users see their saved account and photo selection. A
single connected account is selected automatically; multiple accounts require an
explicit choice. Keep account switching, disconnect/reconnect, and Google's
optional folder access in the provider's overflow menu. Folder-wide selection
and subfolder inclusion live under **Folder options**; subfolders stay opt-in.

Do not repeat privacy explanations, account-management buttons, or permission
choices around the import action. Import links starts with the link field; only
providers found in entered links expose connection/account controls. Direct
image links do not show unrelated connectors.

After a failed attempt, show the confirmed reason and Retry. Administrator
instructions and copying are under **Administrator help**, initially collapsed.
Copying preserves the reason on screen. Users can share the details outside the
app and retry after access changes; the app sends no notification and invents no
approval request. Failures retain successful selections. A failed web Picker launch
retries selection with the connected account. Native Picker retries use the
provider's required consent and selection flow.

References inspected for this simplification:
- [Claude's connector rows](https://mobbin.com/screens/e6ade293-ed67-4901-8d3c-4196c31b842e): provider, connection state/action, and secondary management.
- [Attio's storage-connection flow](https://mobbin.com/flows/518e0a7f-f070-40ca-b66e-ecfc969591e3): connect a provider; manage a saved account only after opening its disclosure.
- [ChatGPT's connection flow](https://mobbin.com/flows/72826030-df1b-43b4-884e-cafad0cc2e06): authorize at the provider and return to the task. This Mobbin example is GitHub/Codex, not Drive; [OpenAI's Drive instructions](https://help.openai.com/en/articles/10929079-internal-knowledge-google-workspace-admin-managed-setup) confirm the connect, account, consent, and return sequence.

These are interaction references, not evidence of our provider or institutional
acceptance. The earlier Dropbox Dash failure reference informed recovery behavior,
but its guidance is not a template for the normal import screen.

Account authorization, organization policy, application membership and individual
file access produce distinct recovery states. The UI never invents an approval
request or says approval is pending without a provider-confirmed state. A personal
Google account cannot establish institutional acceptance.

OAuth refresh tokens and PKCE verifier material stay in Secret Manager. Client
secret references pin numeric versions. OAuth completion requires the same signed-in
application user and an initiating session proof that is never put in the provider
URL. The callback forwards its one-use code to the original browser window or native
app; it does not exchange credentials itself or expose the code through polling.
The browser validates both popup identity and callback origin. Native callbacks use
`specimenintake://oauth/callback`; a different app cannot complete the connection
without the original session proof. Disconnect disables local use before provider
revocation and exposes a retry if revocation could not be confirmed.
Reconnect preserves the connection identity used by queued photos and verifies
the provider account identity before replacing credentials. A different account
requires a new connection and an explicit new source selection.

Google Picker needs a short-lived access token in browser memory. Its one-use
bootstrap is in the URL fragment, removed from browser history before a POST
exchange, and never included in the server request URL. Picker pages and callbacks
are uncached with a restrictive CSP. OAuth callbacks send no referrer; the web
Picker page sends only its origin so a restricted developer key can verify the
site. Refresh tokens never reach that page. Native clients receive selected IDs
through their callback and do not open the hosted JavaScript Picker.

## Provisioning and rollout

New release clients default `BULK_INTAKE_ENABLED=false`. Debug/tests enable the new
workspace. Release the compatible backend and SQL connector first, verify the
private intake job and its permissions, then enable the client with
`--dart-define=BULK_INTAKE_ENABLED=true` in a subsequent reviewed client release.

Only the existing protected main workflows deploy. `runtime-release.yml` defines
and verifies the intake job using `scripts/release/deploy_intake.py`; it does not
execute a transfer. The API runtime identity needs the existing SQL/blob grants,
access to the pinned worker actor UID secret, and an invoker grant on the intake
job. The owner setup script includes those grants. On first creation, the job
must exist before its resource-level IAM binding can be applied; a missing grant
fails verification and is fixed through owner setup and the protected workflow.
No workstation deployment is a substitute.

Provider provisioning remains explicit. Configure `SPECIMEN_INTAKE_OAUTH_JSON`
with a provider-keyed object. Each configured provider requires `client_id`,
`client_secret_ref` (a numeric Secret Manager version), and `redirect_uri` ending
at the API's `/v1/intake/oauth/callback`. Google also requires `picker_api_key` and
`picker_app_id`, restricted to the intended Picker use and origins. These are
real owner-provisioned values, not sample credentials. The API and intake worker
must receive the same reviewed configuration. The API identity requires creation
of connection-token secrets plus access/add-version grants restricted to the
`specimen-intake-` prefix, and access to the separately pinned client-secret
versions. Do not give it blanket secret-reading or deletion privileges.

The optional pins in `scripts/ci/runtime_settings.py` start unset. A positive
number in `OPTIONAL_SECRET_VERSIONS` activates only its real, provisioned secret:
`specimen-external-emails` supplies `SPECIMEN_EXTERNAL_EMAIL_ALLOWLIST_JSON`,
`specimen-cloud-import-config` supplies `SPECIMEN_INTAKE_OAUTH_JSON`, and
`specimen-collection-job-routes` supplies `SPECIMEN_COLLECTION_WORKER_JOBS_JSON`.
The API/intake receive the first two; API, intake and scientific workers receive
the same routes pin. Client-secret names and numbered versions are listed in
`OAUTH_CLIENT_SECRET_VERSIONS`. Configuration and client-secret names must stay
outside the dynamic `specimen-intake-<UUID>` credential namespace.

Each routes entry maps an exact `organization UUID/collection UUID` to
`worker_job`, `intake_job` and the existing `actor_uid`. The release reads that
one numbered secret privately and defines the corresponding dedicated jobs in
the existing project and region. Their names start with `specimen-worker-` and
`specimen-intake-`; each keeps the original resource limits, actor secret,
source image and cumulative budget ledger. Their environment fixes
`SPECIMEN_WORKER_SCOPE_JSON` and their own continuation jobs. Shared workers
derive exclusions from the same routing secret. An unset routes pin creates no
dedicated jobs and leaves existing deployment inputs unchanged.

The bounded owner command is `bash scripts/ops/owner_setup.sh --intake-only`
(add `--dry-run` to inspect). This mode needs the checkout and `uv`, grants only
secret container creation on the project, add/access on numbered dynamic credential
versions, and the separately pinned configuration/client reads. It also grants
private invoker/read permissions on configured dedicated jobs. It starts no
release or job. `INTAKE_PROVIDER_APIS` can explicitly name Drive and Picker;
enabling either requires pinned provider configuration and client-secret
prerequisites. No provider API is enabled by default. A newly defined job can
need a second owner setup pass before the protected release verifies its IAM.

To provision private values, add `--intake-config-dir /absolute/private/path`
to that same owner command. Each approved `<secret-name>.json` file contains
exactly `{"version": 1, "value": ...}`; its `value` alone becomes the secret
payload. The approved names are the three optional configuration secrets above,
`specimen-google-drive-client`, `specimen-dropbox-client`, and
`specimen-collection-bindings`. Client values contain only `client_secret`.
Every local shape and every remote target is checked before any write, including
IAM. Matching versions are skipped; differing/disabled targets and skipped
version numbers are refused. Missing containers are created, then one numbered
version is appended and privately compared with the file. Values and provider
error output are never printed. Runtime pins remain unchanged.

The binding value must preserve every current mapping and contain exactly one
`intake-e2e` mapping, either already present or added. A routing value must name
that collection, the original pinned worker actor, and dedicated jobs in this
project/region. Google configuration must refer to the matching approved client
secret version, the exact API callback and the same Picker project number.
After provisioning, activating the verified numbers still requires the reviewed
runtime-settings change and protected release.

Before submitting E2E work, verify that all definitions carry the reviewed
routes pin and that older shared executions have finished. A running execution
retains its original image/environment; updating its job does not retrofit scope
exclusions. The isolated test collection inherits the Insects profile through a
distinct collection node, preserving the original unique budget-ledger binding.

Google setup must enable both the Drive and Picker APIs. The OAuth client must
register the exact API callback URL. The web Picker key's website restrictions
must include the API origin serving the Picker and `https://docs.google.com/*`,
and its API restrictions allow only Picker. Backend Drive calls use the OAuth
bearer token. The `picker_app_id` is the
project number of the same Google Cloud project that owns the OAuth client.
Dropbox needs an application that can read existing files (Full Dropbox content
access), the exact HTTPS callback, offline access, and these read scopes:
`account_info.read files.metadata.read files.content.read sharing.read`.
Users connect to the configured application; they do not create their own OAuth
applications. Provider application setup, user consent, organizational policy and
individual file permissions are separate requirements and recovery messages.

Application sign-in is a separate boundary. The client validates email syntax;
the server checks verified Firebase identity and App Check, then the institution
domain or an exact server-owned external-account allowlist. Optional external
addresses are configured through `SPECIMEN_EXTERNAL_EMAIL_ALLOWLIST_JSON`, a JSON
array supplied from a pinned server secret. It accepts no domain wildcards and
does not normalize provider-specific dot or plus aliases. Admission grants no
collection role: current SQL Connect membership still decides collection access
and every write. The actual user must complete normal sign-in, provider account
choice, consent and selection. None of those steps is established by a successful
mock or by provisioning an allowlist entry.

Secret Manager may return numeric project resource names even when creation used
the project ID. Credential reads accept only the configured project ID and exact
configured project number, with numbered secret versions in either form.

Google OAuth verification and an institution's app-access decision are separate.
See [Google scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
and [shared-link resource keys](https://developers.google.com/workspace/drive/api/guides/resource-keys).
Native Picker follows [Google's desktop and mobile integration contract](https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker);
web key restrictions follow [the official web Picker guide](https://developers.google.com/workspace/drive/picker/guides/web-picker#configure_your_environment).
Dropbox shared links follow the [official SDK/API contracts](https://dropbox-sdk-python.readthedocs.io/en/latest/api/sharing.html).

## Acceptance evidence boundaries

Automated API contracts cover saved-draft isolation, no pre-Submit specimens,
replayed uploads/Submit, atomic outbox recovery, carry-forward drafts, cancellation,
500-item pagination, access failures, provider version changes, SSRF rejection,
and connection session/revocation handling. Full-shell widget/visual tests cover
phone/tablet/desktop and 200% text; a fake camera covers 30 consecutive captures;
the 500-photo grid test checks bounded widget construction.

These tests are synthetic. They do not establish a physical-device memory budget,
real camera operation, VoiceOver/TalkBack behavior, personal Drive/Dropbox consent,
managed-account policy acceptance, deployment, or successful live pipeline handoff.
Record each genuine result and each unresolved provisioning dependency separately
in `docs/SESSION_LEARNINGS.md`; never promote one evidence category to another.
