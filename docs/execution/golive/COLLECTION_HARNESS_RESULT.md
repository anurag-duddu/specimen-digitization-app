# Collection details harness — local implementation

Task ID: `collection-harness-20261007-13a6`. Branch: `codex/harness-collection`.
Worktree: `/Users/anuragduddu/.codex/worktrees/13a6/specimen-digitization-app`.
Starting source and remote main verified: `7890de551c75fe3b06836c7fb224f85dd2a2423a`.

## Concrete change

The collection v6 prompt uses `settle_collection({"field_key": ...})` for each
requested, defined collection field. Trusted recovery scans original reading text,
not organiser offsets or hints, and creates exact assemblies only with independent
reader agreement and existing native quotes. It recovers omitted/misfiled spans,
explicit multiline assertions and a valid quote retained only for the other raw
reader. One uncertain field does not suppress a qualified sibling.

Catalogue digits remain strings, including leading zeros. Parser-supported prefix
variants can agree without rewriting either raw reading. An incomplete catalogue
token cannot be clipped at punctuation into a valid number. A prefix is neither a
Collection Code nor an EMu IRN. Code requires explicit code context; habitat and
method have separate qualification and reject locality, person, catalogue and
preparation text. Explicit unusual phrases can qualify without being in a universal
vocabulary; the small unmarked phrase recognizers are a conservative local route.

Settlement considers every qualified complete assertion across labels and every
independent reader, including later labels. A continuation relation permits joining
parts but cannot override a part's explicit locality/preparation/other-field role.
Original organiser proposals and raw/adjudicated reading declarations are retained.

The local utility has no external effect receipt. Publication recomputes its exact
result from the immutable request. Catalogue parsing now requires the catalogue
field and an assembly from that field. A model cannot stop unresolved while an
available local collection settlement is supported. Actual engine/gateway failures
still occur outside model acceptance and preserve existing operational behavior.

New recovery and stricter settlement are pinned to collection v6; frozen v5 jobs
retain their earlier graph and validation. The collection module's bytes/version
enter the toolset pin. Acceptance validator v4 retains the earlier version/hash
pairs; the historical hand-over fixtures explicitly exercise their v5 contract.

## Field outcomes and stop rules

| Field | Supported result | Hold |
| --- | --- | --- |
| `fmnh_ins_number` | Exact parser-qualified digits, with raw prefix retained | No catalogue context, invalid complete identifier, absent quote or conflicting readers/labels |
| `collection_code` | Exact explicit code text, including spaced alphanumeric codes | Prefix/catalogue/preparation notation, ambiguous kind or absent qualified quote |
| `habitat` | Exact qualified ecological text, including supported multiline spans | Locality/method/person/preparation kind, absent quote or conflicting assertions |
| `collection_method` | Exact qualified collecting-method text | Habitat/locality/preparation kind, absent quote or conflicting assertions |
| `verbatim_dts` | No machine settlement until reviewed definition/examples exist | Existing `waiting_policy:verbatim_dts_definition_examples`; preserve genuine verbatim |

Absent, unqualified or conflicting collection evidence produces the committed
structured missing-policy review outcome, with the specific reason. No specimen
user is asked a conversational question. The public queue categories are unchanged:
Cleared, Needs Human, Deferred. This lane does not make temporary outages Deferred.

D/T/S distinction: PLAN section 2.3 makes its undefined G45 **kind mismatch** a
finding only. It does not remove genuine mandatory missing/unresolved review. The
research validator currently imposes a definition hold even for present exact
verbatim; this implementation retains that stronger existing boundary. The owner's
tentative expansion was not promoted into an approved definition or validator.

## Evidence scope

- Reproduction before fixes: the real factory/validator accepted habitat=`light
  trap`, method=`oak woodland margin`, habitat=`Davao Prov.`, catalogue/preparation
  text as code, and one chosen event of two conflicting habitat labels. The broker
  and publication replay also accepted catalogue parsing targeted at collection code.
- The focused fixtures use real recovery, qualification, validator, broker,
  Pydantic AI tool/output feedback and utility replay. HTTP is refused in the
  workflow fixtures; no paid model or external specimen-publisher call is made.
- The composed production workflow uses scripted FunctionModels, SQLite research
  state, retained blobs and a fake SQL Connect connector with the real native
  publication/materialization path. It automatically publishes catalogue `0010001`,
  code `INSECTS`, multiline habitat and method `light trap` from a misfiled organiser
  hint. D/T/S leaves the fixture finalized in Needs Human. This is offline composed
  publication proof, not a live connector transaction or production acceptance.
- An invalid final answer receives real agent feedback and is corrected without
  repeating utility calls. An engine cancellation after a local utility preserves an
  earlier sibling checkpoint; resume narrows the request and replays the same local
  result. The latter uses the scheduler test journal, not a production journal.

## Shared integration and remaining prerequisites

- Geography owns the additive shared BrowserUse/Shell/CodeMode/Memory/Skills and
  interruption-history integration. The worktree environment verifies AI 2.51.0
  and harness 0.36.0; those capabilities are exported but remain unconnected here.
  Collection v6 supplies a reusable pinned domain procedure and deterministic tools;
  this does not claim an installed long-term Memory or Skills capability.
- No new native Evidence row is manufactured. Raw-only omissions lacking any
  retained covering quote need a trusted observation-to-native-evidence capture
  adapter through the shared publication interface. Existing exact quotes can be
  reused regardless of the organiser's field assignment.
- No trusted mid-run immutable graph update/registration interface is added.
  Recovery happens before specialist dispatch. Cross-label joins require existing
  accepted event/continuation records; production initial requests still do not
  populate general cross-label relations.
- There is no connected exact specimen-publisher metadata join for these fields.
  External research must preserve qualified source registration, exact specimen
  joins, captured effects, unknown-send holds and the original/native lineage.
- No shared message-history restoration or per-field salvage of an invalid final
  batch is claimed. Already saved sibling checkpoints are preserved; valid new
  siblings in a rejected final output remain a shared engine integration concern.
- Lane P owns integration, full canonical verification, independent PR-head review,
  protected merge, paid canaries and production release. None occurred in this lane.

## Exact shared hunks for integration

- `initial_requests.py`: version-gated collection recovery in `__call__` and
  `_build_graph`; additive keyword preserves reconstruction of frozen inputs.
- `evidence.py`: v6 collection guards before unresolved acceptance and the literal
  fallback; external deciding-source handling and other role branches stay separate.
- `sources.py`: one `local_settlement_result` branch and utility roster/scoping hunk.
- `local_utility_proof_v2.py`: one roster entry, exact collection replay branch and
  catalogue field/assembly fence.
- `agents.py`: include collection settlement in the existing compact utility view.
- `committed_pins.py`: collection module version/byte digest in `_toolset_digest`.
- `accepted_output.py`: v4 validator bytes plus retained historical version/hash pairs.
- `prompts/__init__.py`: collection entry/version only; v5 file remains unchanged.

## Validation

Final focused batch: **328 passed**, with the expected unconfigured offline Logfire
warning. Command:

```sh
.venv/bin/python -m pytest -q tests/research_harness/test_collection_qualification.py tests/research_harness/test_collection_workflow.py tests/research_harness/test_local_utility_publication_v2.py tests/research_harness/test_specialist_feedback.py tests/research_harness/test_committed_pins.py tests/research_harness/test_organiser_handover.py tests/research_harness/test_unqualified_label_policy.py tests/research_harness/test_organiser_handover_engine.py
```

Composer compatibility: **10 passed**, with the same offline Logfire warning:

```sh
.venv/bin/python -m pytest -q tests/research_harness/test_organiser_handover_composer.py
```

The composer compatibility run preceded the last metadata-only refusal hunk;
the final focused batch then reverified the changed guard and the new composed
automatic-publication case. `git diff --check` passed. Installed dependency versions
and the acceptance validator byte pin match the declared source.

Full canonical `scripts/ci/verify.sh`, CI, PR, push, merge and live release: **not run**.
No live source/model, paid processing or production mutation is claimed. Commit
identity and the append-only closeout are recorded in `docs/SESSION_LEARNINGS.md`.
