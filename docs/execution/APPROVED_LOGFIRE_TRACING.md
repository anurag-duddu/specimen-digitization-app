# Approved bounded Logfire tracing — September 14, 2026

The user approved the reviewed bounded tracing proposal at
2026-09-14T06:09:07.640Z in release task
`01a082b2-c2c3-70d2-be90-7bfb622c9102`. This adds metadata export to the existing
US Logfire project, one worker-only writer secret and its temporary access grant.
It does not replace the [cumulative budget approval](APPROVED_RELEASE_BUDGET.md),
the [original worker clock](APPROVED_WORKER_TIMING.md), or the protected release
and full-cohort acceptance requirements.

The immutable approval and proposal digests are:

| Record | SHA256 |
|---|---|
| Direct user approval, original record including newline | `06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48` |
| Reviewed `bounded-logfire-release-proposal/v3` | `cf0319a527ff930b5a9e367d655d51a6b5a17e4ae17282815195337788b707e5` |
| Combined access and tracing decision | `41aeebfb3857a5b86b794497d224c85af419ad6c1befcf2e6ec1ce4bc1df7f86` |

The original private user record and proposal remain with the coordinator.
The approval is additive: the budget authority remains
`3303d129e5fde28d828729cd5b034a7981968c5cbbbad882a05367a5c361df2a`.
No original scope digest, consumed fence, ledger row, cost, reservation or
unknown outcome changes. The USD12 total and daily ceilings cover every session,
attempt and day; this approval is neither a new budget nor a complete price quote.

## Destination and permitted content

Only the existing project
`https://logfire-us.pydantic.dev/anuragduddu/specimen-digitization` is approved.
Trace requests use only `https://logfire-us.pydantic.dev/v1/traces`. The
coordinator may make one bounded identity GET to
`https://logfire-us.pydantic.dev/v1/info` to verify the existing writer credential
before any specimen metadata is sent. A browser session or a well-formed digest
does not qualify a writer token or substitute for that identity evidence.

The export may contain specimen, run, region and observation identifiers;
model/provider identity; token usage; timing/status; and source/trace lineage.
The exporter must build an explicit allowlist. Prompts, label text, images,
model response bodies, provider error bodies, exception-local variables and
Firebase/Google credentials are excluded. Raw SDK attributes, resource data,
baggage, exception events or arbitrary links must not create a second export path.

Existing application evidence and human review remain required. The tracing
approval does not authorize publishing raw specimen content, expanding the cohort,
skipping actual regions, changing readers, or substituting traces for save/reopen
and the other retained product journeys.

## Export and timing bounds

| Dimension | Maximum |
|---|---:|
| Records across supervisor and all children | 10,000 |
| Trace POST attempts across all processes | 500 |
| Coordinator identity GET attempts | 1 |
| Charged application trace-request bytes | 67,108,864 |
| Charged bytes per trace request | 2,097,152 |
| Identity response body | 65,536 bytes |
| Redirects and retries | 0 |

The shared durable ledger must reserve records, attempts and charged bytes before
dispatch. A claim binds the exact body and is usable once. Unknown outcomes remain
held across child loss; no replay, refund, process restart or counter reset creates
another allowance. Application-byte limits are not physical wire-byte limits;
the complete cost reservation must also cover reviewed framing, response, network
and audit bounds.

Each effect retains its original deadline. Tracing must fit inside the original
worker useful-work deadline, T+3485 seconds, with all owned cleanup inside
T+3500 seconds. It must not extend a model effect, SAM, worker or cleanup clock.
There is no background export, retry worker or after-deadline flush.

A known successful HTTP response is distinct from timely local completion.
Ledger writes, commit, connection finalization and synchronous flush must finish
before the original deadline. Accepted accounting counters cannot replace the
actual completion result. Late/unknown work stays unsuccessful without a later
compensating mutation or extra grace interval.

The default SDK trace/log/metric exporters, remote variable lookup and ambient
endpoint/proxy/export settings must not bypass the bounded transport. The worker
owns the ledger inside its existing supervisor workspace. API and SAM receive no
writer token, trace environment or telemetry transport authority.

## Writer secret and setup effects

The only new parent is
`projects/specimen-digitization/secrets/specimen-worker-logfire`, replicated in
`us-east4`. It may be created only when absent, followed by one checksum-bound,
acknowledged immutable numeric version. An existing parent requires reconciliation;
this approval does not permit adoption, replacement, deletion or version destruction.

Only `specimen-worker-runtime@specimen-digitization.iam.gserviceaccount.com`
may receive `roles/secretmanager.secretAccessor`. The grant must combine the
original runtime expiration with the exact immutable version resource condition.
API, SAM, Hosting, GitHub and other identities gain no writer access. Cleanup uses
a fresh-policy compare-and-swap and readback to remove only the acknowledged owned
grant. The writer value never belongs in Git, review evidence, command output,
the release plan, a launch payload or the identity receipt.

The runtime completion successor preserves the original action set and adds four
effects: create the new parent, add its immutable version, grant the bounded worker
access, and remove that owned grant. Its total ceilings are:

| Setup dimension | Maximum |
|---|---:|
| Requests | 220 |
| Effects | 44 |
| Charged request bytes | 52,265,180 |
| Ordinary requests / effects | 172 / 32 |
| Reserved cleanup requests / effects | 48 / 12 |
| Secret-stage requests | 40 |
| Capture-stage requests | 65 |
| Charged bytes per request | 237,569 |
| Reserved cleanup charged bytes | 11,403,312 |
| Retained audit ceiling | 100,663,296 bytes |
| Each secret payload / five-payload aggregate | 65,536 / 327,680 bytes |

The separately approved bootstrap remains exactly three IAM effects within its
187-request/600-second setup envelope. This tracing successor does not enlarge,
reissue or reset it. No source helper is qualified from an intermediate commit;
all dependencies and exact inputs require independent review against the final
merged source before issuance or use.

## Cost, retention and activation

Current native account/plan facts and the complete retained cost ledger must
qualify before activation. No new account, subscription, plan upgrade or quota
upgrade is approved. A provisional fully paid records allowance does not establish
the current Logfire plan. Free usage observed in one project also does not prove
organization-wide reCAPTCHA billing applicability or refund a prior liability.

The provisional writer-secret storage quote uses 31 days as a pricing horizon.
That is not automatic expiry, and a disabled version still incurs storage charges.
Activation requires a reviewed end-of-life or continued-storage arrangement inside
the unchanged USD12 limit. This proposal authorizes no secret/version destruction.
Logfire's retention setting is a separate property from Google secret storage.

Source implementation, independent privacy/bounds review, actual writer identity,
the acknowledged secret version and conditional access, current cost/retention
admission, all five checks on exact merged source and the separate protected
workflows remain required. The approval itself proves none of those outcomes.
Release completion still requires matching deployed revisions and the authenticated
original-ten product journeys described in [DEPLOYMENT.md](../DEPLOYMENT.md).
