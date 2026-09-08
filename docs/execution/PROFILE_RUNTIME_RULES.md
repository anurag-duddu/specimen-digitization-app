# Published profile runtime rules

Worktree `/Users/anuragduddu/.codex/worktrees/23ec/specimen-digitization-app`;
branch `codex/profile-runtime-rules`, base
`effb708e461033b6b2c9b4ba9d0b8b5cbb42b544`. Only `collection_profiles.py`,
`test_collection_profiles.py` and this report change. The additional image metric
proposal was cancelled by coordinator before implementation; image diagnostics
remain untouched. No shared core, dependencies, other worktrees or cloud changes.

## Exact additive fields

- `language_handling: LanguageHandlingRule` has exactly the existing application
  JSON shape: `version: language-handling-v1`, `unknown: unmeasured | review`
  (default unmeasured), `mixed` and `conflicting` with the same enum (default
  review). These are handling rules for opaque declarations, not language-code
  validators or confidence/calibration assertions. Other versions/actions reject.
- `scoring_policy_ref: PolicyReference | None` contains `id`, `version` and a
  lowercase SHA-256 `digest`. Legacy `scoring_policy` remains readable, but its
  string is not silently used to instantiate a default RiskPolicy.
- `segmentation_settings: SegmentationSettings | None` pins
  `version: sam3-settings-v1`, `adapter_version: sam3-http-v1`,
  `model_id: facebook/sam3`, the already pinned model revision,
  a nonblank prompt of at most 1,000 characters, and `parameters: {}`.
  `Sam3Parameters` is frozen and rejects extra fields. Backend accepted this
  exact shape instead of introducing new model-confidence/IoU/service knobs.
  The existing 64-region response bound stays in the adapter. Unknown setting,
  adapter, model or model revision values reject; no new service is implied.

All nested objects are frozen and extra-forbid. The supported language defaults
match `reading_declarations.LanguageHandling`; backend adapts with model_validate.
No institutional approval or semantics flags are changed, and accepted image
formats still default to JPEG/PNG.

## Runtime resolution and history compatibility

`resolve_profile_rules(profile, supported_scoring_policies=())` returns a frozen
`ResolvedProfileRules` containing profile ID/version/digest and the exact language,
scoring reference and segmentation settings. Missing scoring ref, missing explicit language rule, missing settings,
unknown scoring ID/version, mismatched digest or duplicate matching supported
references fail closed with explicit errors. Nested language/segmentation objects
are revalidated so unchecked model_copy updates cannot bypass supported versions.

The supplied scoring references must come from the backend's successful
`RiskPolicyRegistry.resolve` for this profile/scope and allowed synthetic mode.
An arbitrary reference tuple from a client is not approval. This owned module
checks exact reference identity; the evidence owner's registry remains responsible
for published/revoked status, synthetic gates and content/digest resolution.
The default supported tuple is empty, never a permissive default policy.

Definition deserialization and classification-node mapping remain compatible:
`CollectionProfileRegistry.resolve` still maps a node/version. Backend must call
runtime resolution before inference/selection completion and retain the exact
settings with the run. It must use published prompt/settings for the actual SAM
request and preserve resolved policies through history/restart. This module does
not claim the shared runtime is already wired.

A wrap serializer omits the three new fields when they were absent in the original
input (`model_fields_set`). Thus an old definition retains its exact JSON bytes
and hash after loading through the additive schema. Defaults are available for
reading old language policy, but absent scoring/settings cause runtime resolution
to block. No old snapshot or audit artifact is rewritten. Any explicit legacy
runtime mapping must be named and separately owned by backend; this module does
not infer one from the legacy strings.

Tests retain the exact pre-extension draft JSON captured from reviewed `effb708`
and compare both bytes and SHA-256 after reload. New explicitly supplied rules are
serialized, hashed and immutable. Omission and explicit null are distinct retained
states. Existing source/profile publication uniqueness remains the storage owner's
responsibility, as in the original registry contract.

## Synthetic fixture version

`insects_registry(synthetic=True)` now emits `synthetic-v2-runtime-rules`, not a
changed definition under the old `synthetic-v1` name. It explicitly pins language
handling, prompt `label`, and the evidence owner's generated reference:
`synthetic-review-risk-balanced`, version `1`. Its exact digest is stored in
`SYNTHETIC_SCORING_POLICY` and was supplied by the evidence owner's
`synthetic_risk_policies()` factory. This is uncalibrated synthetic-only policy;
backend must pass `allow_synthetic=True` only in synthetic mode. It is not a
production museum scoring approval. Production `insects_registry()` remains the
same draft with no implicit scoring or segmentation resolution.

Two additional synthetic test definitions select different language actions,
scoring references and segmentation prompts, retain distinct profile digests and
round-trip unchanged. These reference-only tests do not duplicate scoring weights;
actual risk-policy computation belongs to the evidence/backend integration tests.

## Verification and handoff

Focused command:

```bash
uv run pytest tests/test_collection_profiles.py tests/test_classification.py -q
```

**19 passed**: legacy bytes/hash, two selected rule sets, immutability, JSON
round-trip, unknown language/settings/model revisions, unsupported parameter,
missing/mismatched/unknown scoring references, draft flags and explicit synthetic
factory version. Backend and evidence owners received exact interfaces directly.
Backend owns actual selected-policy risk differences, HTTP/SQL history/restart and
SAM request wiring tests. Canonical result and commit are supplied below after
verification. No production policy, calibration, provisioning, push or deployment.

Final staged-code canonical gate **passed**: **110 Python tests passed, 10
explicit optional codec/SQL skips**, repository/secret checks, Flutter analysis,
widget tests and release web build. Ruff F checks and staged diff checks passed.
Log: `/tmp/profile-runtime-rules-final-verify.log`. Two individually reviewed
non-secret entropy findings have exact inline annotations: the existing SAM model
revision matched `hub_models.py`, and the synthetic scoring digest independently
matched the evidence owner's actual factory output (read with bytecode writes
disabled). No scanner rule, threshold, baseline or whole-file exclusion changed.
This final evidence paragraph is documentation-only after the staged-code gate;
commit hooks check it. No push or production changes.
