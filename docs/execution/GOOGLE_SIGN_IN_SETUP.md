# Google sign-in alongside email

The app offers email links and, when configured, Google. Google sign-in uses
this app's Firebase OAuth provider. It does not reuse ChatGPT Enterprise's SAML
connection or require the museum's SAML metadata. A museum Workspace policy
could restrict this OAuth app; that is a separate question, established by an
actual policy rejection rather than assumed from the use of Workspace.

Email remains available throughout setup. The existing verified-email domain
and owner admission rules still apply to both methods. Authentication does not
grant collection membership. Native Google client registration and callback
handling require their own qualification; enabling the web provider does not
establish that Android or iOS Google sign-in works.

## Release path

Only the main `Data release` workflow configures the provider. It installs
`firebase-tools@15.8.0` before obtaining cloud credentials, then runs
`scripts/release/provision_auth.py` after data and georeferencing publication.
The workflow uses its existing `data-production` environment and keyless
`specimen-data-release` service account. No new GitHub secret is required.

The script reads the existing passwordless email setting and authorized
domains with explicit partial-response fields, then reads Google's enabled
state and client ID. It never requests a password hash or provider secret.

- An enabled Google provider with a valid client ID is retained without writes.
- An existing disabled Google provider receives only an `enabled=true` patch.
  Its client ID, secret and branding are retained.
- A missing provider is provisioned using the pinned CLI's Auth-only target
  and the separate `firebase.auth.json`. The script first requires the single
  existing production web app, `1:716045864126:web:a193fa80c7a98bcac8e2ef`;
  it refuses a missing or ambiguous app instead of creating a different one.

The Google-only config contains the public display name `Specimen Digitization`
and the existing public owner/support mailbox `anurag@infinative.com`. It has no
email, anonymous, domain or Hosting configuration. The CLI runs in a temporary
directory so private debug output is removed and never copied to workflow
logs. The CLI invocation is restricted to `deploy --only auth` for the exact
project; it is not a workstation deployment command.

After a change, the script rereads email/domain settings and requires them to
match the preflight snapshot, then verifies the enabled Google provider and a
valid client ID. A failure stops the Data release. It never attempts to repair
email/domain drift by overwriting live settings. Reads retry transient failures;
the explicit enabled-only patch is sent once. A failed CLI operation is not
automatically repeated by this script; rerunning Data release reads live state
first. The CLI has its own bounded provisioning/operation handling.

On CLI failure, the release reports only a recognized request stage and
bounded status/error identifiers. Raw CLI output, API payloads and private
debug logs are never published. A last observed response is diagnostic context,
not proof that a particular permission is missing; a generic exit code alone
does not authorize additional grants.

## One-time permission setup

Existing role names alone do not prove that the release identity lacks effective
permissions. If the live release reports a permission failure, the project owner
can grant the reviewed, narrowly scoped role using:

```bash
bash scripts/ops/owner_setup.sh --auth-only --dry-run
bash scripts/ops/owner_setup.sh --auth-only
```

The first command reads state and prints changes. The second creates or
reconciles only `projects/specimen-digitization/roles/specimenAuthConfiguration`
and grants it only to the existing
`specimen-data-release@specimen-digitization.iam.gserviceaccount.com` at the
project. If the exact role cannot be reconciled, it is not newly bound. This
mode does not execute the script's general setup: it does not change SQL roles,
WIF conditions, other grants, GitHub variables or secrets, and starts no release.
It requires a project IAM administrator and `gcloud`; it does not require `gh`.
The owner runs it. An agent requires the owner's first-hand authorization for
this exact setup run, as specified in `docs/DEPLOYMENT.md`.

| Permission | Purpose |
| --- | --- |
| `clientauthconfig.clients.create` | Required with `firebase.projects.update` to register the reviewed Android signing fingerprints on the existing Firebase app. |
| `firebase.clients.get` | Read the existing Firebase app. |
| `firebase.clients.list` | Resolve the existing web app. |
| `firebase.projects.get` | Read the Firebase project used by the CLI. |
| `firebase.projects.update` | Required by the pinned CLI's Auth deploy preflight/provisioning path. |
| `firebaseauth.configs.get` | Read email/domain and Google provider configuration. |
| `firebaseauth.configs.update` | Provision Google or enable the existing provider. |

Auth configuration permissions are project-wide. IAM cannot restrict this role
to the `google.com` provider or to the read fields used by this script. In
particular, the provider resource schema includes `clientSecret`; the field
mask protects this implementation's reads, not every possible use of the role.
The role includes no user management, password-hash, Secret Manager, IAM or
Hosting permissions. Client creation is required by the Firebase SHA registration
API; the release limits it to fixed fingerprints on the existing Android app.
The existing workflow's main-only WIF
conditions and environment remain unchanged.

Permission selection is based on the exact pinned CLI source and documented
Auth APIs. The CLI's internal `firebase:provisionFirebaseApp` operation does not
publish a complete independent IAM mapping. Actual acceptance must therefore
be established by the protected workflow. If it fails, retain the bounded
failing-step diagnostic and fix the reviewed configuration; do not infer a
need for Owner, Firebase Admin or Auth Admin and grant them wholesale.

After setup, rerun the failed `Data release` run or dispatch `data-release.yml`
on `main`. Do not run the provisioning script or Firebase deploy locally.

## Activation and acceptance

Hosting and Data release start independently on a merge. Keep
`SPECIMEN_GOOGLE_SIGN_IN_ENABLED` off during the initial provisioning release.
After Data release has verified the live provider and automated contracts pass,
set the public repository variable to `true`, then rerun **all jobs** of the
current merged main push CI/CD run (or use the next protected main merge).
An explicit manual Hosting dispatch does not deploy or forward the flag, and a
failed-jobs-only rerun cannot reuse another attempt's web artifact. A provider
GET alone does not prove the sign-in journey works.

Check the released app, public deployment marker, all three workflow outcomes,
and API version according to `docs/DEPLOYMENT.md`. Then check a real browser
handoff, cancellation/retry, successful admission, and the email fallback.
Account interaction requires the user's own participation or explicit
authorization; synthetic tests cannot establish museum account eligibility.
These live checks are required before calling the login release complete; they
follow button activation so the released flow can actually be exercised.
If Google reports an organization policy block, record its actual error and
request the specific Workspace app approval. Email stays available. If the
provider itself fails, disable the Google flag, rerun the complete current main
push CI/CD workflow, and fix forward through a PR.

## References

- [Firebase CLI provider configuration](https://firebase.google.com/docs/auth/configure-providers-cli)
- [Flutter federated sign-in](https://firebase.google.com/docs/auth/flutter/federated-auth)
- [Google sign-in for the web](https://firebase.google.com/docs/auth/web/google-signin)
- [Read a provider configuration](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/projects.defaultSupportedIdpConfigs/get)
- [Provider resource fields](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/projects.defaultSupportedIdpConfigs)
- [Identity Platform access control](https://docs.cloud.google.com/identity-platform/docs/access-control)
- [Workspace third-party app controls](https://support.google.com/a/answer/7281227)

Implementation reference: `firebase-tools@15.8.0`, `lib/commands/deploy.js`,
`lib/deploy/auth/{prepare,deploy}.js`, and
`lib/management/provisioning/provision.js`. The CLI chooses an existing/default
web app and provisions the Google OAuth client through Firebase; the release
does not invent a client ID or supply a copied client secret.
