# Published risk-policy resolution and label-level triage

Worktree `/Users/anuragduddu/.codex/worktrees/5178/specimen-digitization-app`;
branch `codex/profile-label-risk`; clean base
`681d1e0cf0848705e0ef6ad70c6380af247308d9`. Only existing review_risk.py,
its matching test_review_risk.py and this new report change. No domain,
collection-profile, workflow, API, dependency or other-worktree edits occur.
The implementation commit is sent to backend, coordinator and collection owner
after canonical verification.

## Published policy contract

RiskPolicy retains the legacy fields and adds explicit `id` and `synthetic`.
Its canonical `sha256` covers the full immutable definition, including weights,
feature version and calibration dataset metadata. `reference` returns a frozen
RiskPolicyReference with exactly `id`, `version`, `digest`.

RiskPolicyEntry wraps a definition and draft/published/revoked status. A frozen
RiskPolicyRegistry has a version and bounded entries, rejecting duplicate
ID/version definitions and duplicate component weights. `resolve(reference,
allow_synthetic=False)` returns a typed RiskPolicyResolution. Missing references,
unknown IDs/versions, digest mismatch, draft/revoked entries and synthetic policies
outside an explicitly synthetic runtime are blocked. A blocked resolution has no
executable policy and no fallback. Resolved output validates the exact reference
against the contained policy; serialization preserves the pin.

The collection owner owns `CollectionProfile.scoring_policy_ref` as an equivalent
structured reference, retaining its legacy scoring_policy string only for old
snapshot compatibility. Backend converts the profile reference with
`RiskPolicyReference.model_validate(profile.scoring_policy_ref.model_dump())`.
A legacy string or absent structured reference is not permission to use the old
default. Policy existence/status and exact version/digest belong to the registry.
A changed definition under the same ID/version cannot silently satisfy an older
pin; its digest mismatch blocks. Registry publication/history administration is
outside this module, and immutable snapshots must remain in application history.

`synthetic_risk_policies()` exposes two explicit test policies:

- `synthetic-review-risk-balanced`, version `1`: numeral-disagreement weight 20.
- `synthetic-review-risk-numeral-sensitive`, version `1`: numeral weight 40.

Other test weights are identical. Both are explicitly synthetic and require
allow_synthetic=True. This task supplies no institution-approved production risk
policy or inferred quality threshold. A calibration dataset name does not establish
calibration: scoped results remain calibrated=False and never claim accuracy.

The legacy `review_risk(signals, policy=RiskPolicy())` arithmetic primitive remains
for backward compatibility, now also reporting policy ID/digest. New published
runtime composition must call the resolver and scoped assessment APIs instead;
the legacy default is not a runtime policy-selection mechanism.

## Label, field and specimen assessment

`assess_risk(signals, resolution, scope, target_id, unmeasured=(),
blocked_reasons=())` accepts scope label/field/specimen and returns ScopedReviewRisk.
It retains exact policy reference, registry/feature version, every measured
component and its signal/evidence/count/weight/contribution, reasons, unmeasured
dimensions, input digest and creation time. Status is scored, unmeasured or blocked.
Unknown component weights are explicitly unmeasured instead of silently contributing
zero to a supposedly complete composite. Missing metadata or caller-supplied
unmeasured dimensions leave composite null while retaining measured components.
Operational blocks or policy resolution failures likewise leave composite null.

`label_review_risk(region_id, observation_ids, alignments, metadata, resolution,
additional_signals=(), unmeasured=())` returns that same typed label assessment.
It consumes bounded ReadingAlignment/ReadingMetadata produced by reading_evidence,
not the legacy short-reading SequenceMatcher helper. It validates region and
observation lineage, rejects duplicate comparison pairs and metadata, and requires
all pairs of the supplied observation set before comparisons can be considered
measured. Bounds are eight observations, 28 pairs, eight metadata records and
100 additional signals. Missing comparisons, language/script metadata, or
conflicting declarations stay unmeasured. A blocked long or truncated reading
retains its exact block reason and cannot become agreement or a zero label risk.

Distinct pair/span signals are aggregated by code/field with all contributing
evidence IDs retained. Counts represent observed pair/span findings, not verified
error rate. This helper does not establish model independence, complete segmentation,
or the expected observation set: backend supplies the profile's required set and
keeps existing clearance checks. Additional actual quality/coverage/validation
signals may be supplied, with any absent or blocked applicable feature explicitly
listed in unmeasured. The helper never fabricates unprovided quality components or
claims complete coverage of dimensions that were not requested.

Example exercised in tests: two source readings containing non-BMP/Latin text and
one differing numeral produce a label composite of 40 under balanced and 60 under
numeral-sensitive. Both results expose the two component weights/contributions,
both observation IDs, reason codes and different policy pins. A zero configured
weight leaves a hard-validation reason intact and cannot clear a field/specimen.
Scoped results have clearance_authority=False and no disposition operation.

## Verification and remaining integration

Tests exercise both synthetic policies, explicit weight differences, version/digest
pinning and immutability, missing/unknown/version-mismatched/draft/revoked policies,
synthetic policy denial, invalid resolved pins, label/field/specimen scopes,
missing comparison/metadata/quality dimensions, Unicode long-input blocks,
unknown weights, duplicate/wrong-source pairs and zero-weight hard-validation
reasons. Existing reading tests continue to cover raw Unicode offsets and bounded
alignment. No fixture confidence or calibration is presented as observed quality.

Canonical verification results are appended before handoff. Backend owns replacing
runtime default selection, published profile binding, per-label plus field/specimen
assembly and actual HTTP/SQL fixtures; collection owner owns profile-reference
storage. Flutter receives the resulting serialized scope/status/components through
that shared API. These integration gates are not claimed by isolated module tests.
No private data, paid/model/provider calls, provisioning, push, merge or deployment
occurs. This implements SCR-001..004/006 component behavior and preserves prior
TRN-006/007 uncertainty rather than introducing another clearance policy.

Verification: 32 combined risk/reading tests passed (nine risk, 23 reading).
Canonical `scripts/ci/verify.sh` passed with 141 Python tests and two existing
emulator skips, repository/secret checks and Flutter analyze/widget/web build.
Ruff undefined/unused-name checks and `git diff --check` passed. Existing
Starlette deprecation and unconfigured Logfire warnings remain unchanged.
