# Field parts: the wire contract

Status: **planned, not in force.** Nothing in this file is built, merged or
released. It changes no behaviour, no schema, no operation and no stored
record. It is an engineering agreement between two sessions, the harness
session (the writer) and the schema and app session (the reader). It is not an
owner ruling, and nothing here needs one except where section 8 says so.

Written 2026-10-09 against `main` at `cb38a8be5`. A citation `path:line` is
that commit unless a branch or pull request is named. "Guess" marks a
statement I could not confirm in code. The inputs:

- The PRD section "Field model v2: four groups" in
  `docs/product-requirements/PRD.md` (pull request #283, head `9c4f0bd7e`,
  docs only, approved and about to merge): the four groups, "How every value
  is recorded", "Value kinds", "Naming a part", "v1 keys from v2 parts".
- The harness session's proposal `harness-derivation-proposal.md` (sections A
  to D, G.4, G.5) and the shared plan `schema-harness-plan.md` (S2, S2b, H1 to
  H6). Both live in `~/specimen-golive/status/`, outside this repository.
- Pull request #284 (`field_research`, head `777d3e3b8`), #285
  (`application/field_model.py`, head `08f83d2a8`) and #286
  (`value_basis.dart`, head `d9d9e8553`). None is merged. Where this file cites
  them it names the pull request.

## 1. Purpose and status

A field value today (`FieldValue`, `domain.py:242-275`) holds one text and one
state for a whole field. The field model v2 records a basis, support, state
and review need for each part of a value: the country, island and province
inside a locality, the unit inside an elevation, one collector inside the
collectors. This file fixes the wire shape of that per-part record, called
`parts`, so that neither session has to guess.

| Role | Who | What they do with `parts` |
|---|---|---|
| Writer | Harness session | Field research (`field_research`, run by the processing workflow) builds parts and writes them in its one save, with the evidence they cite. The decision handler for a person's choice on a part (section 6) is listed under the harness's own code changes (proposal G.2). |
| Reader, server | Schema and app session | The `FieldValue` model, the API workspace (`api.py:379-425`), history and reprocess code that copies a `FieldValue`. |
| Reader, app | Schema and app session | The workspace reader (`api_repository.dart:974-1000`), the specimen data tab, the review list (`blockers.dart`) and the research thread reader's embedded schema (`research_models.dart:1180`). |

This contract is additive. It does not add a key to the 20 v1 keys, does not
add a Data Connect operation, does not change a published pilot record and
does not decide which flagged parts block clearance (PRD, "Not decided by this
section"; shared plan H1). The v1 keys stay mandatory and stay the published
shape. Parts ride beside them.

Where the two sessions' texts disagree, this file decides the small ones and
lists the rest in section 8:

- **The size figure.** The numbers 1.5 MB and 873 KB circulate as the run
  snapshot's cap and a field-research run's size. They describe the old
  six-specialist research state (`FIELD_RESEARCH.md` line 52
  on #284; `MAX_STATE_BYTES = 1_500_000` at
  `research_harness/persistence.py:35`), which field research retires. Parts
  are stored in the specimen snapshot, whose limits are different (section
  2.8).
- **The root of the place tree.** The proposal calls it `location` (section C).
  PR #285's parser rejects `location` alone and names the root
  `location/verbatim`. This file follows the parser.
- **A date path.** The PRD's naming examples include `when/start`. PR #285's
  parser has no such path; its date parts are `when/collected/start`,
  `when/collected/end`, `when/collected/time` and `when/identified/start`.
  This file follows the parser.
- **`level`, `reading_names`, `inputs`, `options`.** The proposal's
  `PartAnswer` (section A) has them. Section 2.3 says where each went.

## 2. The shape

### 2.1 Where parts live

Parts live in an optional member `parts` of `FieldValue`. A part belongs to
exactly one field, its carrier, chosen by the first segments of its path.

| Path prefix | Carrier field | Status |
|---|---|---|
| `location/*` | `precise_location` | Settled. The proposal puts nodes with no v1 key on the verbatim locality's field (section D), and PRD "Naming a part" names the tree. First release. |
| `elevation/*` | `elevation_from_m` | Guess: the first of the four elevation keys, and metres are canonical (PRD "Value kinds"). Not in the first release. |
| `collectors/n` | `collectors` | Guess. Not in the first release. |
| `when/collected/*` | `date_visited_from` | Guess. Not in the first release. |
| `when/identified/*` | `date_identified` | Guess. Not in the first release. |
| `taxon/*` | `taxon` | Guess. Not in the first release. |
| `ids/catalog_number`, `ids/collection` | `fmnh_ins_number`, `collection_code` | Guess. Not in the first release. |
| `habitat/text`, `collection_method/text` | `habitat`, `collection_method` | Guess. Not in the first release. |
| `identified_by/n` | `identified_by_irn` | Open. V1 has no key for a determiner's name, and this key waits for EMu Parties (G16). Section 8. |

The app needs the same table, because a part reason code names only a path
(section 5) and the app finds the field to open from the carrier. A part
whose prefix a reader does not know is ignored: the field shows its own value
as today.

The carrier's own members keep their v1 meaning. For `precise_location` the
`literal` is the verbatim locality as read, the root of the tree
(`location/verbatim`). That root is never a list entry.

### 2.2 What `FieldValue` gains

Three optional members, each omitted from the JSON at its default
(`exclude_if`, the pattern used at `domain.py:106`, `392-412`, `516-531`).

| Member | Type | Default, omitted when | Meaning |
|---|---|---|---|
| `parts` | list of `FieldPart` | empty | The per-part records of this carrier. At most 24 entries (section 2.8). |
| `basis` | `label`, `derived` or `inferred` | none | How this whole value was obtained. The app already reads a stated `basis` from the field map and lets it win over the one it computes (`value_basis.dart:167` on #286). |
| `review` | `ReviewNeed` | none | A person is asked about this whole value, and why. By convention written only for a value that has no parts; a part's review never sets the carrier's. |

`layer` is unchanged and gains no value (PRD, "Basis is a separate thing from
the layer"). The research thread's `FieldThread.review` (`thread_view.py:343`)
is a different object and is not touched.

### 2.3 `FieldPart`

A new `Record` (so it forbids extra keys, `domain.py:23-24`). Every optional
member is omitted from the JSON at its default.

| Member | Type | Required | Rule |
|---|---|---|---|
| `path` | text, at most 64 | always | `<value>/<part>[/n]`, parsed by `parse_part_path` of PR #285. Not `location/verbatim`. Its value segment matches the carrier (section 2.1). |
| `state` | a `ValueState` | always | The existing seven values (`domain.py:27-34`). |
| `value` | text, 1 to 240 | when `state` is `supported` | The part's value. A number is decimal text, never a JSON number; a date is `YYYY`, `YYYY-MM` or `YYYY-MM-DD`; an elevation is exact metres. Absent for any other state. |
| `basis` | `label`, `derived` or `inferred` | exactly when `value` is present | How the value was obtained (PRD, "How every value is recorded"). |
| `wording` | text, 1 to 240 | when `basis` is `derived` | The label's words the value came from, as read ("P.I."). PRD rule 4. For `label`, absent means the wording equals `value`. Optional for `inferred`. |
| `parent` | path | on every `location/*` part, never elsewhere | The path of the next broader node. The broadest node names `location/verbatim`. A tree, not a fixed list of levels: an unlisted level is data, flagged for review, never rejected (shared plan S2b.2). |
| `authority_id` | text, at most 240 | no | The matched candidate's id in the form the sources return, `<source>:<record id>` (`sources.py:893` on #284). |
| `derived_from` | list of paths, at most 8 | no | The parts whose values this one was computed from, in any carrier. The harness's `inputs`. Same name and idea as `FieldValue.derived_from` (`domain.py:270`), but paths, not field keys. |
| `evidence_ids` | list of ids, at most 12 | one or more when `state` is `supported`, unless `decision` is present | Evidence rows cited, section 2.6. |
| `evidence_relations` | map from id to `decides`, `supports` or `contradicts` | always matches `evidence_ids` | Same type as `FieldValue.evidence_relations` (`domain.py:271-273`). Every cited id has exactly one relation, as the projection needs (`projection.py:682-683`). |
| `alternatives` | list of `PartAlternative`, at most 4 | for a conflict | The other values a person can choose. |
| `review` | `ReviewNeed` | no | Present means a person is asked. |
| `decision` | `PartDecision` | no | Present means a person decided this part (section 6). |

Decisions about the proposal's `PartAnswer`:

- **`level` is not a member.** It is the second segment of `path`
  (`parse_part_path(path).part`). A stored copy could disagree with the path.
  A level's role (first-level administrative unit, settlement) is a table in
  code, as in `field_model.py` of #285, not a stored member.
- **`name` and `value` are one member, `value`.** For a place node the value is
  the node's name.
- **`reading_names` is not a member.** The readings that contain the value are
  the `literal` evidence rows the part cites; each already links its reading
  through `observation_ids` (`domain.py:227-239`).
- **`reasoning` is not a member.** It is one cited Evidence row of kind
  `reasoning` (section 2.6), as the PRD and the shared plan (S2b.5) say. It is
  not duplicated inline.
- **`options` became `alternatives`.** Each alternative carries a value, its
  own basis and its own evidence, so a "choose" decision can copy all three.
- **`inputs` became `derived_from`,** to match the member that already exists.

### 2.4 The three small records

`ReviewNeed`: `code` (`conflict`, `doubt` or `no_support`) and `reason` (text,
1 to 240, at most three sentences). The reason is composed by the writer from a
fixed template for the code, never copied from model text, so that the app can
show it behind a "Why" and it passes `design/02-ux-writing-guidelines.md`
section 6. There is no `needed: false`: a part with nothing to check has no
`review`. A budget stop is `doubt` with the budget in the reason (proposal C,
last section).

`PartAlternative`: `value` (text, 1 to 240), `basis`, `wording` (optional),
`evidence_ids` (at most 2, each also in the part's `evidence_ids`).

`PartDecision`: `event_id` (the id of the audit event that recorded the
decision, `AuditEvent.id`, `domain.py:534-535`) and `action` (`accept`, `choose` or
`edit`).

### 2.5 Rules the model checks

These can be checked on the part list alone, so they belong in the model's
validators and in the app's reader.

1. `path` parses, is unique, is not `location/verbatim`, and its value segment
   matches the carrier. `derived_from` entries parse and none is the part's own
   path.
2. `value` and `basis` are both present or both absent. `supported` needs a
   value. `ambiguous` has no value, at least two alternatives and
   `review.code == conflict`: the writer could not pick a best-supported
   value. When it can pick one (PRD rule 3), the state is `supported`, the
   other values are alternatives and the review is `conflict`.
3. `basis == derived` needs `wording`.
4. `evidence_relations` has exactly the keys of `evidence_ids`, with no
   duplicates. A `supported` part cites at least one row unless a person
   decided it.
5. `parent` is present exactly on `location/*` parts. It names a part in the
   same list or `location/verbatim`, and following parents never loops.
6. `review.code == no_support` needs no value. `conflict` needs alternatives or
   the `ambiguous` state.
7. Every alternative's evidence ids are among the part's `evidence_ids`.
8. Text members have no control characters; counts and sizes are within section
   2.8.

Rules that need the run's evidence list belong to the writer's own validator
(proposal B), and the model cannot check them: every cited id is a row of
`run.evidence`; an `inferred` part cites exactly one `reasoning` row and at
least one other row; the basis rules themselves. This file fixes where support
is recorded, not what a basis needs.

### 2.6 Support: where each kind goes

Support uses the mechanism that exists: Evidence rows plus the part's
`evidence_ids` and `evidence_relations`. `Evidence.kind` is free text
(`domain.py:229`).

| Support | Evidence row | Relation |
|---|---|---|
| The wording as read | kind `literal`, `observation_ids` names the reading (built at `step.py:350-361` on #284) | `supports` when it states the same text, `contradicts` when a reading states different text (`step.py:461-467`) |
| A lookup: source, query, result | the stored source response, kind `authority` or `lookup`, with its `ToolCallRecord` holding the query and outcome (`domain.py:278-298`) | `supports`; `decides` only for a source that decides (GBIF for a taxon, `step.py:101, 475`) |
| A candidate the writer refused (a lookup of "Mt. McKinley" that returned Denali) | the same stored response | `contradicts`. A convention proposed here; section 8 asks the harness to confirm |
| A fixed check | kind `derived`, locator `check:<tool>` (`step.py:364-391`) | `supports` |
| A rule applied | new kind `rule`, locator `rule:<id>@<version>`, the excerpt states the entry | `decides` |
| Reasoning | new kind `reasoning`, the excerpt is the statement, at most 600 characters, one per `inferred` part | `supports` |
| A person's decision | not an Evidence row: the `decision` member and the audit event | none |

Rows of kind `rule` and `reasoning` leave `raw_ref` and `digest` unset. Then
they stay in the snapshot and are never projected to Data Connect
(`projection.py:484-489`), and no new operation is needed.

A constraint that this file does not change: for a v1 mirror key, clearance
accepts a `parsed`, `normalized` or `authority_id` that differs from the
literal only when a cited row of kind `authority`, `authority_selection` or
`derived` contains it (`policy.py:82-98`). A `rule` or `reasoning` row never
satisfies that check. The proposal plans to change field research's own check
(`step.py:748-772`, proposal G.2); whether `policy.py` changes with it is a
question for section 8.

### 2.7 Order

`parts` is sorted bytewise (UTF-8) by `path`. The model refuses any other
order. Reason: the list feeds a digest (section 3), and a writer that sorted
differently would mint a different digest for the same content. The order is
not the tree's order: `location/place` sorts before `location/province` and is
its child. A reader builds the tree from `parent`.

### 2.8 Bounds

| Bound | Value | Why |
|---|---|---|
| Parts per field | 24 | A deep place tree is about 8 nodes (country, region, island, province, municipality, town, a few named places), and collectors and determiners rarely pass 10 (guess). 24 leaves room and stops a runaway writer. |
| Bytes of `parts` per field | 32 KiB | The largest part the member bounds allow is 5,459 bytes of ASCII (10,739 if every 240-character text were three-byte UTF-8), so six maxed parts reach it. The parts in the examples are 221 to 799 bytes. |
| Parts per record | 64 | The nine values add to about 57 at their deepest (guess: 24 location, 10 collectors, 6 determiners, 5 taxon, 4 elevation, 4 dates, 2 ids, 1 habitat, 1 method). |
| Bytes of `parts` per record | 96 KiB | Equal to the inline threshold below. |
| Text members | 240 characters | The cap the review card already uses (`thread_view.py:26`, `MAX_REVIEW_TEXT`). |
| Cited rows per part | 12; alternatives 4, with 2 rows each; `derived_from` 8 | Largest real case in the examples cites six rows. |
| Reasoning row excerpt | 600 characters | The proposal's bound (section A). |

Size is measured as `active_graph.encoded` measures it: compact JSON,
`ensure_ascii=False`, UTF-8 (`active_graph.py:21-24`). The per-field limits
belong in the model; the per-record limits in a validator on `Run`. A writer
that would exceed a bound writes no `parts` for that field, keeps the v1 keys,
and says so with an operational reason (section 8). It never truncates.

What the limits are measured against. These are the limits that exist for
data in a specimen record; the first two rows are where `parts` is stored.

| Limit | Value | Source | Effect on parts |
|---|---|---|---|
| Inline run | 96 KiB | `active_graph.py:6` | Above it the run is stored as a separate blob and the database snapshot keeps `run_summary`, which empties `fields` (`active_graph.py:28-52, 64-100`). The graph path needs a blob store (`active_graph_storage_not_configured`, `active_graph.py:81-82`); `BACKEND_ACTIVE_GRAPH.md` says production supplies one. |
| Complete graph | 16 MiB less 16 KiB | `active_graph.py:7-8` | Not a concern at these sizes. |
| Compact snapshot | 256 KiB | `storage.py:272-276` | Holds the summary. Not a concern once the run is in a blob. |
| Workspace response | 4 MiB | `active_graph.py:9`, `api.py:1691` | The response carries every field twice, in `run.fields` and again in `fields` (`api.py:388, 413-416`), so parts count twice. At the record cap that is 192 KiB, 4.6% of the limit. |
| Old research state | 1.5 MB, one run reached 873 KB | `persistence.py:35`, `FIELD_RESEARCH.md:52` | Not the specimen snapshot. Parts must not be copied into it (section 8). |

Measured on a throwaway prototype of this contract (not committed), with
36-character ids: the four-node place tree of 105526321 is 1,902 bytes; all of
that specimen's parts across three carriers are 3,204 bytes; 105526322's
elevation parts are 1,566 bytes. A whole record is a few kilobytes, under 4% of
the 96 KiB inline threshold. I did not measure a real field-research run: the
harness session has the ten simulated runs and should measure with parts added.

## 3. Backward compatibility

### 3.1 What must not move

Published pilot records and their digests must stay as they are. A digest
moves only when something re-serializes a model, so the table lists each place
that does.

| Digest | Where | Hashes | Safe when |
|---|---|---|---|
| Candidate id | `projection.py:647, 653-654` | `value.model_dump(mode="json")` of each `FieldValue` | A value with no parts dumps byte for byte as before. This is the digest that moves if any new member is dumped at its default. |
| Human-carry proofs | `human_field_carry.py:263, 338, 356` | a re-dump of a carry that embeds a `FieldValue`, compared with a digest an audit event stored earlier | Same. A changed re-dump makes `_transition` fail (`human_field_carry.py:356`), so old carried decisions would stop verifying. |
| Stored snapshot hash | `storage.py:569-570, 589-590, 664-665` | the stored JSON text as loaded | A stored revision is never re-serialized from the model, so its hash cannot move. A new revision is serialized from the model, and with parts omitted at their default its bytes for an unchanged field are unchanged. |
| Run hash for history links | `active_graph.py:153-157` | the stored run JSON | Same. |
| Source pins | `native_canonical.py:69-73`; `tests/research_harness/test_organiser_handover.py:924` | sha256 of `domain.py`, `storage.py`, `active_graph.py`; `native_canonical.py:51` pins `projection.py` | Editing `domain.py` needs both of its pins updated in the same pull request. This contract needs no edit to `projection.py`, `storage.py` or `active_graph.py`. |

So every new member is optional and omitted at its default: `FieldValue.parts`,
`basis`, `review`, and every optional member inside a part. The snapshot's
`contractVersion` (`production.py:611`, `"0.1"`) stays as it is.

Checked on a throwaway subclass of today's `FieldValue` (not committed):

- the default value dumps identically, by `model_dump`, `model_dump_json`,
  canonical JSON and digest;
- a stored v1 value loads into the subclass and dumps back byte for byte;
- today's `FieldValue` refuses a value with `parts` (`extra_forbidden`), which
  is the rollback boundary in section 3.4;
- the JSON schema gains `parts` and keeps `additionalProperties` false.

Tests to add with the writer: the first two as goldens on a pinned v1 value and
on a stored pilot snapshot; a projection test that a parts-free run yields the
same write ids as before; the existing embedded-schema test
(`test_thread_embedded_schema.py:31-33`).

A consequence to accept: when parts change, `projection.py:647` digests the
whole `FieldValue`, so a part decision mints a new candidate id for the carrier
even though its literal, parsed and normalized columns are unchanged. Any edit
to a value already does this today. Excluding `parts` from the digest would
avoid it but edits `projection.py` and moves its pin. Recommendation: do not.
Section 8 asks the harness to confirm.

### 3.2 Which path carries parts to the app

The workspace path. `workspace()` dumps `run` and also `fields` as
`dict(v.model_dump(mode="json"), value_state=...)` (`api.py:379-425`, lines 388
and 413-416). It has no response model, so `parts` passes through. The app
spreads each field map (`api_repository.dart:984`), so the specimen data tab
sees `field['parts']`, and the evidence list arrives beside it
(`api.py:417`). The run is stored in the snapshot (`SpecimenSnapshot.snapshot`,
`dataconnect/schema/schema.gql:49-59`) or, when it is over 96 KiB, in the blob
the snapshot points to (`active_graph.py:64-100`). The app does not read Data
Connect directly (`pubspec.yaml:38-41`).

Not carried: the candidate rows. `AppendFieldCandidateV2` has no member for
parts (`projection.py:658-679`), and no operation is added: a new Data Connect
operation is permanent and ships with its caller (PRD, rollout step 4). Parts
publish as rows only with the v2 key set, later.

Not the thread. The research thread (`research-thread-v1`) is built from the
old harness's journal (`thread_view.py:411-470`), and `FIELD_RESEARCH.md` step
7 says field research writes one save through the existing record writer. I
believe parts never reach the thread in the first release (guess). It still
matters, because the thread's embedded copy of `FieldValue` has
`additionalProperties` false (`research_models.dart:1099`) and a test fails when
the copy differs from the server's schema (section 3.3).

### 3.3 Who must accept `parts` before any writer emits it

| Reader | Accepts today | What must change | Ships with |
|---|---|---|---|
| Every Python process that loads a snapshot: API, worker, history, reprocess, the human-carry proofs | No. `Record` forbids extras (`domain.py:23-24`); `unpack` validates the stored JSON (`active_graph.py:144-150`) | `FieldValue` gains the members; `FieldPart`, `ReviewNeed`, `PartAlternative`, `PartDecision` are new models | The reader release, step 1 below |
| The app's research thread reader and its embedded schema | No. `FieldValue` there has `additionalProperties` false (`research_models.dart:1099`) | Regenerate `_threadSchemaJson` (`research_models.dart:1180`) from `ResearchThread.model_json_schema()`; the test at `test_thread_embedded_schema.py:31-33` fails until it matches | The same pull request as the Python change, because that test ties them |
| The app's workspace reader | Yes. It spreads the field map (`api_repository.dart:984`); old builds ignore a key they do not read | New code to show parts | The app release, any time after step 1 |
| The app's review list | Partly. A code it does not know shows one generic line (`blockers.dart:327`) | Part reason codes (section 5) | The app release |
| The source pins | Not applicable | `native_canonical.py:70` and `test_organiser_handover.py:924` get the new `domain.py` hash | The same pull request |

### 3.4 Release order, reader first

The runtime release deploys the API, the worker job and SAM from one commit
(`runtime-release.yml:42-126`), but they are separate Cloud Run units, so a
short skew is possible. An old image cannot read a snapshot that holds `parts`.
So the writer must not be turned on in the same release that adds the reader.

1. **Reader release.** One pull request: the Python models, the regenerated
   embedded schema, the two source pins. No writer. Merge, wait for the three
   `main` workflows, and check the Hosting `deployment.json` marker and the API
   `/version` source SHA (AGENTS.md, "Deployment rules"). No stored record
   changes.
2. **Server capability.** The `field_part` decision (section 6) and its entry in
   `available_actions`, so the app shows part actions only when the server
   offers them (`workbench.dart:430-433` and `models.dart:363-364` already
   gate actions on that list).
3. **Writer release.** Field research writes the place tree on `precise_location`
   behind a profile flag (proposal G.2). It writes `part_*` reason codes only in
   an image that also serves `field_part`, so a reviewer always has an action.
4. **Later steps**, one per carrier, each with its own carrier row, labels and
   tests.

After the first write, the runtime cannot be rolled back past step 1: an older
image refuses those snapshots. Old app builds keep working at every step,
including a browser tab opened before the Hosting release: it ignores parts
(section 3.3).

### 3.5 Adding a member later, and values a reader does not know

Every later member costs another reader-first release, because `Record` forbids
extras and the thread schema is compared with the server's (section 3.3). The
workspace path alone would tolerate it; the other two paths do not. That is why
this file includes `authority_id`, `derived_from`, `decision` and the value-level
`basis` and `review` now, though the first writer uses few of them. A closed
vocabulary (`basis`, `review.code`, `decision.action`, `relation`) is a Python
`Literal` and a schema `enum`, so a new word is such a release too.

A reader that meets something it does not know degrades and never fails: an
unknown `basis` shows no chip (`ValueBasis.fromWire` returns null on #286); an
unknown `review.code` is read as `doubt`; an unknown evidence kind shows as a
plain source line; an unknown path prefix is ignored (section 2.1); an unknown
`decision.action` still shows "Checked by a person". Those are the app's
behaviours to build. The wire promises only the vocabularies in this file.

## 4. Worked examples

The ids are symbolic ("ev-2A-locality"); real ids are UUIDs (`domain.py:15-16`).
The rows, rules, source names and the Philippines record id are illustrative
and not taken from a run. Only members that matter are shown on the carrier;
its other members are unchanged. Each block was validated against a throwaway
model of section 2 (not committed), with `parse_part_path` of PR #285 for every
path.

### 4.1 Subject 105526321

The label text is the one the PRD's worked example uses: locality "E. slope Mt.
McKinley / Davao Prov. / Mindanao, P.I.", "Mossy forest 6400'", "F.G. Werner".

Evidence rows the parts cite:

| id | kind | What it holds |
|---|---|---|
| ev-2A-locality, ev-2B-locality | `literal` | reading 2A's and 2B's text of the locality |
| ev-rule-notation | `rule` | the abbreviation "P.I." stands for Philippine Islands, the country's name before independence |
| ev-tgn-philippines | `authority` | a Getty TGN answer: Philippines, also named Philippine Islands |
| ev-wikidata-davao | `lookup` | a Wikidata answer for Davao, the former province |
| ev-geolocate-mckinley | `lookup` | a place lookup of "Mt. McKinley" that returned Denali, whose parents do not include Davao |
| ev-2A-elevation | `literal` | reading 2A's "Mossy forest 6400'" |
| ev-rule-feet-to-metres | `rule` | 1 ft = 0.3048 m (G41) |
| ev-2A-collector, ev-2B-collector | `literal` | "F.G. Werner" and "F.G. Wermer" |

The place tree, on `precise_location` (the first release). The v1 keys carry
copies: `country` is "Philippines" (normalized), `province_state` is "Davao";
`county` and `city` are not on the label.

```json
{
  "state": "supported",
  "literal": "E. slope Mt. McKinley / Davao Prov. / Mindanao, P.I.",
  "layer": "verbatim",
  "evidence_ids": ["ev-2A-locality", "ev-2B-locality"],
  "evidence_relations": {"ev-2A-locality": "supports", "ev-2B-locality": "supports"},
  "parts": [
    {
      "path": "location/country",
      "state": "supported",
      "value": "Philippines",
      "basis": "derived",
      "wording": "P.I.",
      "parent": "location/verbatim",
      "authority_id": "tgn:RECORD-ID",
      "evidence_ids": ["ev-2A-locality", "ev-2B-locality", "ev-rule-notation", "ev-tgn-philippines"],
      "evidence_relations": {
        "ev-2A-locality": "supports",
        "ev-2B-locality": "supports",
        "ev-rule-notation": "decides",
        "ev-tgn-philippines": "supports"
      }
    },
    {
      "path": "location/island",
      "state": "supported",
      "value": "Mindanao",
      "basis": "label",
      "parent": "location/country",
      "evidence_ids": ["ev-2A-locality", "ev-2B-locality"],
      "evidence_relations": {"ev-2A-locality": "supports", "ev-2B-locality": "supports"}
    },
    {
      "path": "location/place",
      "state": "supported",
      "value": "E. slope Mt. McKinley",
      "basis": "label",
      "parent": "location/province",
      "evidence_ids": ["ev-2A-locality", "ev-2B-locality", "ev-geolocate-mckinley"],
      "evidence_relations": {
        "ev-2A-locality": "supports",
        "ev-2B-locality": "supports",
        "ev-geolocate-mckinley": "contradicts"
      },
      "review": {
        "code": "doubt",
        "reason": "No approved source holds this mountain. A lookup of Mt. McKinley returns Denali, which is not in Davao."
      }
    },
    {
      "path": "location/province",
      "state": "supported",
      "value": "Davao",
      "basis": "label",
      "wording": "Davao Prov.",
      "parent": "location/island",
      "evidence_ids": ["ev-2A-locality", "ev-2B-locality", "ev-wikidata-davao"],
      "evidence_relations": {
        "ev-2A-locality": "supports",
        "ev-2B-locality": "supports",
        "ev-wikidata-davao": "supports"
      }
    }
  ]
}
```

The named place is the only flagged part: only a curator-confirmed entry (G36,
`PLAN.md:94`) settles it. The country is `derived`, with the label's "P.I."
kept as the wording. The sort order puts `location/place` before
`location/province`, its parent.

Elevation, on `elevation_from_m` (a later step; the carrier is a guess). 6400 ft
is stored as 1950.72 m, kind `point`; the unit is the one the label stated.

```json
{
  "state": "supported",
  "normalized": "1950.72",
  "layer": "derived",
  "basis": "derived",
  "evidence_ids": ["ev-2A-elevation", "ev-rule-feet-to-metres"],
  "evidence_relations": {"ev-2A-elevation": "supports", "ev-rule-feet-to-metres": "decides"},
  "parts": [
    {
      "path": "elevation/from",
      "state": "supported",
      "value": "1950.72",
      "basis": "derived",
      "wording": "6400'",
      "evidence_ids": ["ev-2A-elevation", "ev-rule-feet-to-metres"],
      "evidence_relations": {"ev-2A-elevation": "supports", "ev-rule-feet-to-metres": "decides"}
    },
    {
      "path": "elevation/kind",
      "state": "supported",
      "value": "point",
      "basis": "label",
      "wording": "6400'",
      "evidence_ids": ["ev-2A-elevation"],
      "evidence_relations": {"ev-2A-elevation": "supports"}
    },
    {
      "path": "elevation/unit",
      "state": "supported",
      "value": "ft",
      "basis": "label",
      "wording": "6400'",
      "evidence_ids": ["ev-2A-elevation"],
      "evidence_relations": {"ev-2A-elevation": "supports"}
    }
  ]
}
```

Collectors, on `collectors` (a later step). One reader wrote "Wermer". The best
supported value is filled and only this part goes to a person (PRD rule 3).

```json
{
  "state": "supported",
  "literal": "F.G. Werner",
  "layer": "settled",
  "evidence_ids": ["ev-2A-collector", "ev-2B-collector"],
  "evidence_relations": {"ev-2A-collector": "supports", "ev-2B-collector": "contradicts"},
  "parts": [
    {
      "path": "collectors/1",
      "state": "supported",
      "value": "F.G. Werner",
      "basis": "label",
      "evidence_ids": ["ev-2A-collector", "ev-2B-collector"],
      "evidence_relations": {"ev-2A-collector": "supports", "ev-2B-collector": "contradicts"},
      "alternatives": [{"value": "F.G. Wermer", "basis": "label", "evidence_ids": ["ev-2B-collector"]}],
      "review": {
        "code": "conflict",
        "reason": "The two readings differ: Werner or Wermer. No source checks a collector's name."
      }
    }
  ]
}
```

### 4.2 Subject 105526322

Both readers dropped the foot mark and wrote "Elev. 6400". Metres is
implausible, because 6400 m exceeds the highest point in the Philippines
(PRD: Mt. Apo, about 2,954 m). The unit is `inferred`, with the reasoning row
and the check that found the unit missing. The metres follow from it and take
its basis (proposal B, "basis cap"), so they need no review of their own.

New evidence rows: ev-A-elevation and ev-B-elevation (`literal`),
ev-check-unit-not-written (`derived`, `check:elevation_parser`: no unit written),
ev-rule-unit-from-highest-point (`rule`), ev-highest-point-philippines
(`lookup`) and ev-reasoning-unit (`reasoning`: "6400 m would be higher than the
highest point in the Philippines, so the unit is taken as feet").

```json
{
  "state": "supported",
  "normalized": "1950.72",
  "layer": "derived",
  "basis": "inferred",
  "evidence_ids": ["ev-A-elevation", "ev-B-elevation", "ev-rule-feet-to-metres"],
  "evidence_relations": {
    "ev-A-elevation": "supports",
    "ev-B-elevation": "supports",
    "ev-rule-feet-to-metres": "decides"
  },
  "parts": [
    {
      "path": "elevation/from",
      "state": "supported",
      "value": "1950.72",
      "basis": "inferred",
      "wording": "Elev. 6400",
      "derived_from": ["elevation/unit"],
      "evidence_ids": ["ev-A-elevation", "ev-B-elevation", "ev-rule-feet-to-metres"],
      "evidence_relations": {
        "ev-A-elevation": "supports",
        "ev-B-elevation": "supports",
        "ev-rule-feet-to-metres": "decides"
      }
    },
    {
      "path": "elevation/kind",
      "state": "supported",
      "value": "point",
      "basis": "label",
      "wording": "Elev. 6400",
      "evidence_ids": ["ev-A-elevation", "ev-B-elevation"],
      "evidence_relations": {"ev-A-elevation": "supports", "ev-B-elevation": "supports"}
    },
    {
      "path": "elevation/unit",
      "state": "supported",
      "value": "ft",
      "basis": "inferred",
      "derived_from": ["location/country"],
      "evidence_ids": [
        "ev-A-elevation",
        "ev-B-elevation",
        "ev-check-unit-not-written",
        "ev-rule-unit-from-highest-point",
        "ev-highest-point-philippines",
        "ev-reasoning-unit"
      ],
      "evidence_relations": {
        "ev-A-elevation": "supports",
        "ev-B-elevation": "supports",
        "ev-check-unit-not-written": "supports",
        "ev-rule-unit-from-highest-point": "decides",
        "ev-highest-point-philippines": "supports",
        "ev-reasoning-unit": "supports"
      },
      "review": {
        "code": "doubt",
        "reason": "Feet is inferred: 6400 m would be higher than any point in the Philippines."
      }
    }
  ]
}
```

Whether the four v1 elevation keys are filled when the unit is inferred is open:
the proposal fills 1950.72 m as inferred (section F), and `v1_mirror` of #285
withholds all four (`field_model.py`, `_elevation`, "unit_inferred"). The block
follows the proposal. Section 8 asks.

## 5. Part reason codes

A reason names a part as `<rule>:<path>`, one code per part that has a `review`
and none for any other part. The rule is one of:

| Code | `review.code` | Meaning |
|---|---|---|
| `part_conflict:<path>` | `conflict` | Readings or sources disagree and the writer filled the best-supported value or none |
| `part_doubt:<path>` | `doubt` | The part is filled and a step in it is in doubt, an inference included; also a part the budget stopped |
| `part_no_support:<path>` | `no_support` | Nothing supports even an inference |

The codes sit in `run.reasons` beside `mandatory_unresolved:<key>`
(`step.py:860` on #284), and so reach the API as `reason_codes`
(`api.py:330`) and as validations (`api.py:418-423`). The path has no colon: the
parser accepts only ASCII letters, digits, underscores and slashes, so the first
colon splits a code, as `projection.py:752` and `blockers.dart:237` already do.
The set of part codes equals the set of reviewed parts, and a test should
assert it. The subject is always a valid part path. A value absent altogether
(105526327's elevation) has no part, so it has no part code: the v1 keys'
`not_present` states say it (section 8).

What each reader does with a code today:

- Data Connect: `AppendValidationFindingV2` gets rule `part_conflict`, the whole
  string as `reasonCode`, and a null `fieldKey`, because the path is not a field
  key (`projection.py:752, 773`).
- An old app: `_issueFor` matches none of the known bases, so the review list
  shows the generic line "A specimen check needs review before approval"
  (`blockers.dart:231-330`). It does not fail.
- A new app: maps the path to its carrier (section 2.1), opens the part, and
  writes its own sentence from the code. Strings follow
  `design/02-ux-writing-guidelines.md` (sentence case; no dash; one idea per
  sentence; no "error", "failed" or "invalid"; a data ambiguity has the
  readings as its subject, guidelines section 2.3; a caveat over 40 characters
  sits behind "Why", guidelines section 6 rule 13). Proposed, for the app session to adopt:

| Code | Headline (visible) | Detail (behind "Why") |
|---|---|---|
| `part_conflict` | "Readings differ for {part}." | "{value} or {alternative}. Choose one." The app cuts each value to 40 characters. |
| `part_doubt` | "Check {part}." | the `review.reason`, as written |
| `part_no_support` | "No source supports {part}." | the `review.reason`, as written |

`{part}` is the app's plain label for the path, in lowercase inside a sentence:
`location/country` "country", `location/island` "island", `location/province`
"province", `location/place` "named place", `location/place/2` "named place 2",
`elevation/unit` "elevation unit", `collectors/1` "collector 1",
`when/collected/start` "collection start date". A level the app does not know
goes through `vocabularyLabel` (rule 17), so an unlisted level is shown, not
hidden. A part that a person decided shows the chip "Checked by a person"
(19 characters, under the chip maximum of 20). The basis chip is the existing
"As written", "Derived" or "Inferred" (`value_basis.dart`, #286).

## 6. A person's decision on a part

Today the `field` decision builds a new `FieldValue` from the request and
replaces the whole field (`api.py:1920-1928`). A part needs a smaller action
that keeps what the harness found (PRD rule 5).

**Request.** A new kind `field_part` on the existing `DecisionInput`
(`api.py:126-132`), which already has a free `kind`, `target_id`, `after` and
`evidence_ids`. An older server answers "Unsupported review decision"
(`api.py:2151`) and changes nothing. `target_id` is the carrier's field key.

```json
{
  "expected_revision": 7,
  "base_record_version_id": "<run id>:7",
  "reason": "Both readings checked against the image: the label reads Werner.",
  "kind": "field_part",
  "target_id": "collectors",
  "after": {"path": "collectors/1", "action": "choose", "option": 0},
  "evidence_ids": []
}
```

| Action | Request `after` | Effect on the part |
|---|---|---|
| `accept` | `path`, `action` | `review` removed, `alternatives` removed, `decision` set. Value, basis and support unchanged, so a derived or inferred part never silently becomes `label` (PRD rule 6). Allowed only where `review` is present. |
| `choose` | `path`, `action`, `option` (an index into `alternatives`) | The alternative's value, wording, basis and rows replace the part's. Rows that supported only the old value become `contradicts`. `alternatives` and `review` removed, `decision` set. |
| `edit` | `path`, `action`, `value`, `basis`, optional `wording` | The person's value, with the basis the request names (one of the three; section 8 asks whether that is right). Rows that supported the old value are dropped from the part (they stay in `run.evidence` and in `before_part`); rows the request cites are added as `supports`. `decision` set. A `supported` part with a decision may cite no rows. |

The handler:

1. Applies the usual checks: reviewer role, a non-empty reason
   (`api.py:1900`), the base record version, cited evidence exists
   (`api.py:1924`).
2. Finds the carrier and the part, and rejects an unknown path.
3. Applies the action, then re-derives what depends on the part: the v1 mirror
   keys that copy it, and `run.reasons` (section 8, question 10, asks which code
   does this). The mirror rule is that for every part
   that fills a v1 key (by role, `field_model.py` on #285), the v1 field's
   resolved value, `normalized` else `parsed` else `literal`
   (`api_repository.dart:997`), equals the part's `value`. The writer checks the
   rule at save; the handler keeps it.
4. Clears `human_approved`, as every other kind does.
5. Appends an audit event `review_field_part` whose `after` holds the field
   key, the path, the action, the new part and `before_part`, the part as it was.
   The earlier basis and support therefore stay in the record's history, in this
   event and in the prior revision, which the event's `before` points to.
   Decisions already project as free JSON (`projection.py:836`, the
   `correction` member), so no connector changes.
6. The server lists `field_part` in `available_actions` for the roles that may
   decide (`api.py:335-359`); the app offers part actions only then.

**Other decision kinds.** A whole-field `field` decision on a carrier keeps
working and drops that carrier's `parts` with their decisions, because the
tree no longer matches the text. The audit event records the count and a
digest of what was dropped, as `superseded_human_carry_digest` does for a
carry (`api.py:1932-1934`). A reprocess carries a person's decisions by field
key today (`human_field_carry.py:19`); a part decision must be carried by
carrier key and path, or one part's decision is lost or widened to the whole
field (proposal C). How the harness merges a carried part into a new tree is its
design; section 8 asks.

## 7. What the first release carries

Names follow the harness's staging decision (proposal G.4): field research goes
live as built, then Step 0, then Step 1.

| Release | Carries | Needs first |
|---|---|---|
| This file | Documentation only | Nothing |
| Reader (section 3.4 step 1) | The models and members of section 2, the regenerated embedded schema, the source pins. The app reads and shows parts when present. No writer | PR #285 (the path parser), PR #283 (the PRD) |
| Server capability | `field_part`, `available_actions`, the reason-code handling in the app | The reader release live |
| Step 0 (harness) | `basis` on label and derived values by today's mechanics; reasoning, rule and check rows; reason codes that may carry a path. Nothing infers | The reader release live (proposal G.4: "the app's reader must ship first") |
| Step 1 (harness) | The place tree on `precise_location.parts`, with inference and part review, behind a profile flag. The v1 place keys are copies, checked equal at save. Pilot proof: two country trees across the ten labels, the Denali refusal, Davao | The server capability live |

What waits:

- elevation as one value with the unit rule, one "when", people, taxon and
  identifiers (proposal Step 2), each with its carrier row, labels and tests;
- the v2 key set, the new publish operation and publishing parts as rows
  (proposal Step 3; PRD rollout steps 2 to 4);
- removal of the v1 keys (needs the owner);
- whether an inferred value clears on its own (owner-only decision 1 of the
  shared plan). This file carries `inferred` and says nothing about clearing it.

## 8. Open questions for the harness session

1. **Grammar and root.** Do you adopt PR #285's grammar: `location/verbatim` as
   the root and as the `parent` of the broadest node, no bare-value subject such
   as `part_no_support:elevation`, and `when/collected/start` rather than
   `when/start`?
2. **Dropped members.** Section 2.3 drops `level`, `name`, `reading_names`,
   `reasoning` (kept as a row) and renames `options` and `inputs`. Does your
   validator need any of them stored? Section 2.2 also adds the value-level
   `basis` and `review` that your proposal asks for; say if you will not use
   `review`, and it goes.
3. **Carriers.** Section 2.1 guesses a carrier for every value except the
   place tree. Which do you want for elevation, "when", people, taxon and ids,
   before each step?
4. **The named place.** The PRD's table gives one node whose value is "E. slope
   Mt. McKinley". The proposal (section F) gives "Mt. McKinley" with "E. slope"
   as a qualifier. One node, or two (`location/place`, `location/place/2`)?
5. **The inferred unit and the v1 elevation keys.** `v1_mirror` of #285
   withholds all four keys when `elevation/unit` is inferred; the proposal
   fills 1950.72 m as inferred. Which? And does `policy.py:82-98` change, or
   does a mirror key that rests on a rule also carry a `derived` row?
6. **Relations and projection.** Do you accept `contradicts` for a refused
   candidate, `decides` for a rule row and `supports` for a reasoning row, and
   `raw_ref` and `digest` unset on rule and reasoning rows so they are never
   projected?
7. **The candidate digest.** Leave `projection.py:647` hashing the whole
   `FieldValue`, so a part decision mints a new candidate id (recommended; it
   needs no `projection.py` edit), or exclude `parts`?
8. **Bounds and failure.** Do 24 parts and 32 KiB per field, 64 parts and 96 KiB
   per record, 240-character text and 600-character reasoning fit your tree?
   When a bound would be exceeded, do you write no parts for that field and add
   an operational reason, and what is its code? Please confirm field research
   never copies parts into the old research aggregate (1.5 MB), and that no
   field-research value passes through the research journal that feeds the
   thread (section 3.2 guesses it does not).
9. **Clearance.** Do `part_*` codes block clearance (shared plan H1, open), and do
   you accept writing them only in an image that serves `field_part`?
10. **After a decision.** Which code re-derives the v1 mirror keys and
    `run.reasons` after `field_part`: the handler, or your recheck step? Do you
    accept that a whole-field `field` decision drops the carrier's parts? How
    does a reprocess carry a decided part into a new tree?
11. **A person's edit.** Must the request name a basis for `edit`, as section 6
    says, or does an edited part get a fixed basis? PRD rule 5 is silent, so
    this may also need the owner.
