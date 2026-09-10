# Staff email-link sign-in

The production Flutter client sends a Firebase sign-in link to an exact
`fieldmuseum.org` address. The first successful link can create the Firebase Auth
account. Signing in does not assign collection membership or roles; the API
continues to enforce verified identity and collection authorization.

The client lowercases ASCII addresses, permits normal local-part punctuation,
and rejects whitespace, control characters, extra `@` characters, Unicode
lookalikes, foreign domains and subdomains. Existing foreign Firebase sessions
cannot request a collection token or mount the collection UI.

The SDK calls are `sendSignInLinkToEmail`, `isSignInWithEmailLink` and
`signInWithEmailLink` from the locked `firebase_auth` 6.6.1. The only return URL is
`https://specimen-digitization.web.app/`, with `handleCodeInApp: true`. No email,
collection identifier or user-selected redirect is embedded in that URL. No
dynamic-link domain or mobile app-link configuration is added. This feature
qualifies the web flow; native app-link handling is not claimed.

On the same browser, the locally remembered address completes the link. On a
different browser, the user must enter the address that received it. Email URL
parameters are never used as an identity. Firebase checks that the address and
one-time code match. The existing Firebase session persistence is unchanged.

Only the email and a 60-second resend timestamp are stored in SharedPreferences.
They survive a refresh; the cooldown also survives changing the address. Action
codes are never stored in preferences or logged. The active callback URL stays
available while confirmation is pending, so refreshing can resume the flow.
Completion, cancellation and terminal invalid/expired/reused-link outcomes clean
the original callback URL. A late SDK completion still cleans up after widget
disposal, while a newer unrelated browser URL is preserved. Successful completion
also removes the remembered address. If browser storage is unavailable, users
can still enter their address to confirm a link.

The UI covers send/loading/error, inbox and spam guidance, resend cooldown,
change email, cross-browser confirmation, invalid/expired/reused links, and sign
out. It does not display raw Firebase exceptions or log addresses or URLs.
Firebase Auth remains usable before the application API is configured; no
collection repository mounts until the existing verification/setup gates pass.
The explicit local synthetic fixture-token flow is unchanged and never calls
Firebase.

Deployment requires the email provider and email-link sign-in enabled, signup
allowed, and the fixed Hosting domain authorized. Configuration is coordinator
owned. Source tests use local fake SDKs only and do not prove mail delivery,
hosted-handler forwarding, inbox access or a successful live authentication.
Those checks must use the final deployed source and a user-requested link; no
automated test sends mail. Collection acceptance remains separate.

References: [Firebase Flutter email-link guide](https://firebase.google.com/docs/auth/flutter/email-link-auth)
and [Firebase web completion and security guidance](https://firebase.google.com/docs/auth/web/email-link-auth).
