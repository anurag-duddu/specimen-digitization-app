# Login improvements

## Agreed behavior

Keep at most two sign-in methods. Email links are the primary method. Google
sign-in is an optional secondary method, visible only in a build configured for
that provider. A separate institution SAML/OIDC connection and email one-time
codes are outside this change.

Entering an email in this app sends a sign-in link. Logging into Gmail to open
that message is separate from federating this app with the museum's identity
provider. The institution's SSO connection for another application does not
configure this Firebase project.

The entry screen keeps the existing bounded, responsive form. After sending,
show the recipient and the next action, with resend and change-email controls.
Received links retain the existing trusted-origin checks and other-browser
email confirmation. Recovery instructions must remain fully readable at large
text sizes. Allow email paste and expose email autofill hints.

## Evidence and design decisions

The Mobbin study inspected 60 distinct flows and 280 captured screens across web
and iOS. It is a purposeful sample, not exhaustive catalogue coverage. Plain
informed the simple entry hierarchy; email-link references informed recipient
recognition and recovery. Captured screens do not prove provider configuration,
account linking, accessibility conformance or native callback behavior.

Apply NN/G's heuristics through visible progress, familiar account language,
cancel/change-email recovery, consistent controls, early email validation,
recipient recognition, keyboard/autofill support, short copy, actionable errors
and contextual help. Keep identity authentication separate from collection
authorization.

## Implementation

1. Improve the production email-link screen and preserve cooldown, secure link
   completion, the exact existing owner exception and collection routing.
2. Add a Google provider adapter and a bounded sign-in controller. Web uses the
   Firebase popup started by a user gesture. Native uses the official Google
   SDK only when native client/callback configuration is explicitly enabled.
3. Withhold app session events and tokens until the returned Firebase identity
   is verified, allowed and consistent with the current Firebase UID. Reject
   unsupported identities, invalidate late completion after sign-out, and keep
   failed cleanup quarantined. Never merge users or memberships by email.
4. Add the approved Google button as an optional secondary action. Prevent
   simultaneous Google and email-link attempts. A Google account restriction
   produces a bounded error and leaves the email method available under the
   existing application policy.
5. Test production interfaces, not only the legacy password fixture. Cover
   web/tablet/mobile layouts, large text, keyboard focus, cancellation, blocked
   popups, unavailable configuration, unverified/foreign identities, session
   event races, email recovery and existing authorization regressions.

## Configuration and release

Read-only inspection on 2026-10-16 confirmed Identity Platform and email sign-in
enabled, with no configured Google, SAML or OIDC provider. Firebase web, Android
and iOS apps exist. Native OAuth client registration and physical handoff are
not confirmed. No provider settings were changed by this inspection.

`SPECIMEN_GOOGLE_SIGN_IN_ENABLED` defaults to false. Enable it only after Google
is configured in Firebase and real account eligibility is tested. Native also
requires `SPECIMEN_GOOGLE_NATIVE_ENABLED` and actual platform/client setup.
Google support does not establish that institution policy permits this OAuth
application. The user has chosen not to involve museum IT at this stage.

Release the working email improvements through the existing reviewed PR and
protected main workflows. Run `scripts/ci/verify.sh` before push, obtain an
independent review of the final head, wait for all required checks, then verify
Hosting, data and runtime workflows and both public source revision markers.
Do not describe an unconfigured Google option as live. No workstation deploys,
account deletions, membership changes or new release ceremony are part of this
work. Prune only owned merged work after preserving the append-only session log.

## Acceptance and rollback

- Email sign-in remains available when Google is disabled or unavailable.
- Existing account UID, collection roles and server token/App Check checks are
  unchanged. Real provider migration remains a separate live validation.
- Returning links, denied access and authorized pending routes retain their
  existing behavior. Popup sign-in does not add a full-page redirect path.
- Screen and controller tests do not count as physical device or real account
  acceptance. Record these evidence layers separately.
- Roll back through a reviewed revert/release; disable the optional entry
  point without unlinking users or deleting their accounts.

Primary references: [Firebase Flutter federation](https://firebase.google.com/docs/auth/flutter/federated-auth),
[Google button branding](https://developers.google.com/identity/branding-guidelines),
[Firebase provider configuration](https://firebase.google.com/docs/auth/configure-providers-cli),
and [Firebase session revocation](https://firebase.google.com/docs/auth/admin/manage-sessions).
