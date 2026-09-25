# Go-live program: the full pipeline on the first ten specimens, one at a time

Status: active, started 2026-09-23, corrected the same day after the PR
steward's reviews of #72 and #74, both merged by auto-merge before their
reviews finished. Coordinator: the Claude session titled "App production launch plan";
its topic branches are `golive/plan-*`.
This page is the program's master plan. Workstream briefs are in
[`briefs/`](briefs/). Live status, research reports and the owner-actions
queue live outside the repository in `~/specimen-golive/` (section 7.6).

## 1. Goal and definition of done

The owner's goal, stated in chat on 2026-09-23: take the app live with the ten
pilot specimens and run the whole pipeline end to end, one specimen at a time.
The pipeline, in the owner's words, is: "images in storage - label
segmentation - VLMs - raw transcript back to sql connect against original image
with tracking back to which VLM gave what - scoring for level of disagreement -
LLM does first pass at which final RAW transcript should run against (it should
also give at a VLM level what was returned to the harness) agentic harness takes
the finally decided raw transcript runs lookups (can rely on raw for a final
check if LLM decided transcript output fails, if both fail send to relevant
queue) with databases identified, (function call tool call etc this can be
dependent on collection/subcollection, mandatory vs optional) - mandatory fields
if cleared then cleared, and once harness returns decide queue (human,
deferred, cleared) obviously everything should link back to the specimen
record/id." Every stage's system prompts, at every VLM, LLM and SAM 3 level, and
the harness tracing must be visible in Pydantic Logfire. Storage, the SQL
database and the backend compute must run in production, and the front end must
reflect each record's whole thread. After the ten, the owner runs a new record
and checks that it goes end to end.

Done means all of the following hold, each with recorded evidence:

| ID | Condition | Evidence |
|---|---|---|
| DoD-1 | The public site serves the merged `main` commit and is connected to the production API | `deployment.json` marker, smoke result, a signed-in session resolving the collection |
| DoD-2 | Cloud SQL carries the schema the pipeline needs; the connector is deployed; the collection tree and administrator are bootstrapped | data release run and its checks |
| DoD-3 | The API service, the worker job and the SAM 3 service run from attested images built from `main` | runtime release run and readiness checks |
| DoD-4 | `subject_105526321` to `subject_105526330` were processed one at a time in production, in order, each end to end through every stage in section 4.1, with every artifact in SQL keyed to the specimen and run | SQL rows, thread API output, run reports |
| DoD-5 | Each run is one Logfire trace, linked from the record in the app, that shows SAM 3's parameters, every model call's system prompt and text input and output, the LLM first pass, the harness's tool calls and the queue decision | trace links in the run reports |
| DoD-6 | The owner's own new record runs end to end with no intervention | owner confirmation, run report |
| DoD-7 | Every change reached `main` through a pull request with green required checks and a fresh-swarm review by the PR steward, merged by the steward (G17), and every session appended its closeout to `docs/SESSION_LEARNINGS.md` | PR links, closeout entries |

## 2. Decisions

### 2.1 Owner decisions, 2026-09-23 (chat with the coordinator)

These are the authority for this program. Where they differ from an earlier
approval, they supersede it for this program, and the release workstream's
first pull request records that in each affected document with a dated entry.

| ID | Decision (owner's words in quotes) | Supersedes |
|---|---|---|
| G1 | The pipeline in section 1 is the scope. "When I say something that harness was able to resolve is cleared it is cleared." | `HUMAN_REVIEW_RELEASE.md` (automated clearance deferred), `GO_LIVE_RUNBOOK.md` ("not full-pipeline acceptance"; GBIF lookups and automated clearance out of scope), `RELEASE_RUNTIME.md` 454-457 and 464-478, the `automated_clearance: deferred` scope artifact |
| G2 | One specimen at a time, on demand, including new uploads, "instead of doing batch 10". The ten are the acceptance cohort, processed in order | `RELEASE_AUTHORIZATION.md` single worker execution with zero retries and exactly ten; `APPROVED_WORKER_TIMING.md`; `COHORT_READING_ADMISSION.md` all-ten barrier; `APPROVED_RELEASE_BUDGET.md` 75-76 |
| G3 | System prompts at every VLM, LLM and SAM 3 level, and the harness tracing, are visible in Logfire, linked to the specimen record | `APPROVED_LOGFIRE_TRACING.md` metadata-only scope; `RELEASE_AUTHORIZATION.md` 245-256; `OBSERVABILITY_AND_EVALUATION.md` (content mode for synthetic data only) |
| G4 | Spec-driven and test-driven. Multiple branches with a worktree per branch, in parallel sessions. A separate PR steward session reviews every pull request with a new agent swarm each time, babysits CI/CD until green, merges, and pushes big fixes back to the owning session to fix and resubmit. Never work on `main` directly. "Managing context is key for all sessions" | extends `AGENTS.md` |
| G5 | "I dont want you to make new design decisions like building a new adjudication layer or changing queue logic." Build the stated pipeline and the existing specification. Where the specification is silent or cannot be met as written, ask the owner through the coordinator | nothing |
| G6 | "graceful failures are important. no data found, an error occurred, retry and so on. I am aware there is not always available data and thats when it goes to the need a human queue. As long as agentic harness is able to resolve it will and it can. We need to have a strong harness layer that will be improved but we need to first have a fully functional one" | nothing |
| G7 | The LLM first pass and the agentic harness run on a Hugging Face model, through the existing gateway and token | open item in `PRD.md`; no adjudication model was named anywhere |
| G8 | Mandatory and optional fields for the slide pilot: the owner will supply the list. Until it arrives, the profile is configuration-driven and carries the specification's list (all 20 mandatory, `PRD.md` 12.4) | answered by G42 (2026-09-24) |
| G9 | Spending ceiling USD 25, cumulative, infrastructure and models together | `APPROVED_RELEASE_BUDGET.md` USD 12 |
| G10 | Geography lookups use Google Maps as `PRD.md` 12.4 specifies; the owner creates the Maps Platform key | nothing |
| G11 | Data and runtime releases deploy automatically on merge, like Hosting: once the required checks pass and the PR steward approves, a merge to `main` deploys runtime code and additive schema changes. Branch protection, the required checks, keyless identities and main-only environments stay. Envelopes, cost ledgers, independent-review reports and authorization artifacts retire for this program | `AGENTS.md` deployment paragraph (envelope, independent review), `DEPLOYMENT.md`, `RELEASING.md`, `RELEASE_AUTHORIZATION.md`, `RELEASE_DATA.md`, `RELEASE_RUNTIME.md`, `PROTECTED_RELEASE_HARNESS.md` |
| G12 | "for location parts in the harness a different approach might be needed, spin this off as a new task". A research session (S8) produces a retrospective georeferencing plan from the owner's charter for the owner to review. Until the owner accepts a plan, the harness keeps geography behind its typed tool interface with the Google Maps tool of G10 as the initial version | nothing; G10 stands until the owner accepts S8's plan |
| G13 | Chosen option "Queue it" (asked by S3): a request to process a specimen while another run in the same collection is active waits, and runs go one at a time in request order | nothing; the per-specimen limit of `CONTRACTS.md` 219 stays |
| G14 | Chosen option "Use intake collection" (asked by S3): the profile comes from the collection a specimen was uploaded or imported into, resolved down the collection tree; a reviewer can correct the collection; there is no classification stage | `PRD.md` 9.2 steps 1-2 (186-187), collection prediction |
| G15 | Chosen option "Automatic coverage check": the lane checks the segmentation result itself with the specification's region-count and full-image cross-checks, and sends the record to the human queue when the check fails | nothing; QUE-002's coverage requirement stands and is now met automatically |
| G16 | Chosen option "Optional for now": `identified_by_irn` is recorded as not resolved and does not block clearance until EMu Parties is connected | its mandatory status in `PRD.md` 12.4, for the slide pilot |
| G17 | Chosen option "Steward merges": auto-merge stays off on go-live pull requests; the PR steward merges after its swarm approves | nothing; restates G4 and DoD-7 |
| G18 | Chosen option "Full swarm every time": the PR steward reviews every new head with a fresh four-reviewer swarm, including a head that differs from an approved one only by a merge from `main` | nothing |
| G19 | Chosen option "Harness tries raw readings" (asked by S4): when the LLM first pass picks no reading for a label, the harness runs its lookups on each reader's raw reading; fields that resolve clear on their own evidence, and a field still left with conflicting readings goes to needs human review | the first-pass prompt's "route material ambiguity to human review", which now means the first pass returns no reading |
| G20 | Chosen option "Yes, the lookup settles it" (asked by S4): when the readers disagree and a lookup confirms exactly one reader's literal, that literal is used with its provenance and the field can clear under G1; it counts as a resolved critical disagreement for QUE-002 | nothing |
| G21 | Chosen option "Turn off repo auto-merge": the owner switches off the repository's "Allow auto-merge", so that G17 holds for every session. Done 2026-09-23 and standing: the steward reports any auto-merge it finds and never changes the setting | nothing |
| G22 | Chosen option "Keep all four mandatory": the four elevation fields stay mandatory and nothing is derived, neither a conversion nor a filled-in endpoint; a label without all four values goes to human review, which is every pilot label. Revised on 2026-09-24: a missing elevation may be derived from the settled location with an elevation dataset (G37), and a single stated value fills From and To with the other unit converted (G41) | nothing; settles the "pending policy" of `CONTRACTS.md` 234-235 and `PRD.md` 569 (elevation conversion) |
| G23 | Chosen option "GBIF decides, others support" (asked by S4): GBIF species match v2 against the pinned COL XR checklist decides a taxonomy outcome; Global Names Verifier and Catalogue of Life are also queried and recorded as evidence; in the chosen option's words, "a disagreement is flagged but GBIF's result stands" and "BugGuide isn't used (North American only)". The flag is a warning finding, never a reason for review (section 4.1, stage 8) | settles `PRD.md` 571 (source precedence) |
| G24 | Chosen option "As written, '46 means 1946": a date clears at the precision written, and a two-digit year reads as 19xx for Insects, recorded as that rule. An uncertain date (a written "?") is outside G24 and keeps the existing date gate | settles the precision part of `PRD.md` 570; G29 settles its Roman-numeral months |
| G25 | Chosen option "Yes, at the label's rank": when a label identifies only to genus, a confirmed, accepted genus satisfies the taxon field | settles `GBIF.md` 126's "expected rank" for genus-only labels |
| G26 | Chosen option "Place ID only": from Google geocoding the pipeline keeps only the place ID, its own outcome and a fingerprint of the response; Google's names, address parts and coordinates are dropped everywhere, including Logfire traces | settles the storage and caching part of `PRD.md` 572; narrows `PRD.md` 547 (Google as a source of names and coordinates) and 550 (what an adapter keeps) for Google |
| G27 | Asked by the coordinator from S8's finding on 105526329 and 105526330: the label reads "Chimaltenago", one reader wrote that and the other silently wrote "Chimaltenango", and a place lookup matches the second exactly and the first only approximately. The owner chose neither offered option ("Exact match settles it", "Place yes, spelling to review") and answered: "raw transcript anyway will have exactly as written, for verbatim field it will be as written but final location will be exact actual as settled by harness. we are always capturing both so there isn't an issue if people want to change later". So the lookup settles the final value and the field clears; the verbatim is never replaced, neither by a lookup result nor by the spelling a lookup matched; when the first pass picked no reading and the readers' literals differ, each reader's reading is kept as captured and none is chosen; both are stored, linked to the specimen (the shape is in S5's data contract) | G20's "that literal is used" for the verbatim; S8's proposal D14 (#94) |
| G28 | Chosen option "Yes, same as places": taxon names follow G27; the taxon field keeps the label's spelling as its verbatim text, GBIF's settled name is the final value, and both are stored | nothing |
| G29 | Chosen option "Yes, read it as the month", with the owner's addition: "yes, read as month + this should be part of system prompt too, all permutations combinatinos. thats the whole point of the harness, we figure out all possible cases and try to get to final records that need to be ingested. this should be the prinnciple of th harness essentially. theres a broad range possible per collection/subcollection each subcollection will have its own harness, right now were on insects". So a Roman numeral I to XII in the month position is that month; the harness works through every reading a notation allows, for dates and for every other field, and settles the one the evidence supports; what it cannot settle goes to needs human review with the candidates (G1, G6); each subcollection's profile carries its own harness knowledge, and the pilot's is Insects | settles the Roman-numeral months of `PRD.md` 570; states `PRD.md` 44 and HAR-013 as the harness's principle |
| G30 | Chosen option "USD 5" (the coordinator's recommendation): production model calls may spend USD 5 of G9's USD 25, across every paid step (readers, SAM 3, first pass, harness): each call reserves its worst-case cost before it starts, so no call can cross the allowance, and is settled to its cost once the provider reports its usage or returns a billed amount (SAM 3, priced by its measured seconds, settles as `computed`), while any other outcome stays reserved in full (coordinator ruling on the mechanism, section 4.3); the acceptance lab's USD 5 share is separate, and infrastructure takes the rest; when the allowance is spent, paid steps block as `program_allowance_exhausted`, an operational block (QUE-005), until the owner raises it | sets section 4.3's "configured model allowance" |
| G31 | Chosen option "Not sensitive": the owner checked the ten pilot slides against `PRD.md` 724's criteria and classified them not sensitive on 2026-09-23, recorded in `~/specimen-golive/OWNER_ACTIONS.md`; their import declares them not sensitive on that verified classification | meets `CONTRACTS.md` 169-170 ("actual source classification must be verified") and closes `RELEASE_RUNTIME.md` 558-560's open item for these ten |
| G32 | Chosen option "Same settled value" (asked by S4): "The harness settles each label separately and clears the field when both settle to the same value, for example two spellings of one place. Otherwise it goes to review." So a field found on two labels of one slide is settled per label on its own evidence and clears when every label settles to the same value: the same place ID or GBIF usage, or, for a field without a lookup, the same text; otherwise it goes to needs human review with each label's reading kept, and every verbatim stays as written (G27) | the specification is silent on a field found on two labels (G5) |
| G33 | Chosen option "Every reading" (asked by S4): "Dates in every model's reading count, not only the chosen transcript. If they disagree on the order, the date goes to review. A misread can block a choice but never make one." So the numeric dates of every reading, the decided transcript's and the raw readings', are the evidence that fixes an all-numeric date's day and month order (a component over 12), and any disagreement among them fixes no order | settles what "the one the evidence supports" (G29) means for an all-numeric date |
| G34 | Answer to S8's D15 for the Google tool, asked with S4's regression case: "clear with place ID byt I want the harness for location retrospective georeferencing fully implemented". The option it takes: "The field clears with Google's place ID and no name; the label's spelling stays as the verbatim. Only when Google's name is one letter off and fits the other place fields, since a real test sends a Philippine label to Denali, Alaska." Engineering reading (coordinator): a place field whose literal matches no component by fold or alias clears with the place ID and no name only when the long name of Google's component at the field's levels, never a short name or code, is within one edit of the folded literal, it is the only such component, and every other admin field of the same reading, all of them and at least one, matches Google's result by fold or alias; the field carries a `near_spelling` warning finding that never routes the record; otherwise it goes to needs human review with the candidate. The retrospective georeferencing tool of S8's plan (#94) is to be fully implemented: S8 builds it behind S4's geography interface; the owner decided D1, D2, D3, D6, D7 and D9 (G35 to G39), and D4, D5, D8 and D10 to D13 stand as section 2.3 records | decides D15 for the Google tool; makes #94's retrospective tool a build |
| G35 | Answer to S8's D1, asked by the coordinator: the owner's diagram below (tier 1, historical gazetteers, GeoNames, Wikidata and Getty TGN: "Evaluates historical name + date active", "Returns: Modern name equivalents & historical bounding polygons"; tier 2, modern geocoders: "Pipeline sends the *modernized* name + surrounding context"; tier 3, "Spatial Filtering": "Calculates final Point-Radius Uncertainty"), then "Google  should have current day location with coordinate. This will be helpful for future dataviz exercises". Asked next about Google's terms (6.3.1: coordinates cached 30 days at most, place IDs kept), chosen option "Open sources + Google ID": "Store coordinates from openly licensed sources (Wikidata, GeoNames, NGA), credited. Keep Google's place ID, so a dataviz on a Google map can fetch Google's current coordinates live, which the terms allow." Reading (coordinator): the place tool follows the three tiers; Google receives the modernized name with the same reading's place text (section 4.8's sources), in requests section 4.8 governs (coordinator reading), or the literal when tier 1 has nothing to modernize, where G34 applies; stored coordinates come from open sources, credited; from Google only the place ID, the outcome and the fingerprint are kept (G26 stands), and Google's coordinates never feed tier 3 (section 4.8, coordinator ruling); Getty TGN is wanted now; Mapbox is not used | decides D1 and D2 (#94); keeps G26 |
| G36 | Answer to S8's D3: "McKinley I think is denali. That's what google search returned. I wonder how they arrived and the conclusions. We cant make wrong conclusions". Asked next, chosen option "Curator confirms": "The Insects collection manager, or a curator they name, confirms each place and itinerary entry S8 drafts with its sources. Confirmed entries settle a field; unconfirmed ones never do." Reading (coordinator): no conclusion without evidence; the Davao "Mt. McKinley" is not Denali, since the labels read "Davao Prov., Mindanao, P.I.", and S8's Mount Talomo is unconfirmed, so the six McKinley slides go to needs human review until a curator confirms an entry; a confirmed itinerary match on collector, place and date settles too (the Apo slide); the repository records the confirming role and date, never a personal identity | decides D3 (#94) |
| G37 | Answer to S8's D7: "these can be derived if other location related fields have returned a final value. If even those are unclear then it will wait for human review. I dont think every single field will always be on the label. thats not the intent, the harness should be able to check available information and fill in the rest with authority and evidence. Pass this along to overall harness goals and sessions and agents". Asked next about G22, chosen option "Derive elevation": "Elevation may be derived from the settled location with an elevation dataset, with that evidence recorded, like other fields." Reading (coordinator), for the whole harness: a field the label does not state may be derived from fields with final values, with its authority and evidence recorded, and it fills the field, mandatory ones included; with unsettled inputs it waits for review. County and city are derived when the whole uncertainty circle lies inside one unit. For elevation, a missing elevation may be derived from the settled location with an elevation dataset (D11), and the verbatim stays as written; converting a stated value and filling its endpoints came later, as G41 | decides D7 (#94); revises G22 for a missing elevation |
| G38 | Answer to S8's D6: "Image - transcription - verbatim as per transcription(matching to field) - harness settled answers - derived from other fields. Essentially this is the hierarchy. Harness is operating after VLM transcription to the very end. whatever is human needed, if they fill one field, rest can be autofilled(button click for fill the rest or something)". Reading (coordinator): every field value records its layer, verbatim, settled or derived, and a reviewer's value is the review decision; the thread shows every layer, and a later layer never erases an earlier one; for "Jones Farm, Cook Co." the county settles and the location is derived from it at county precision; in review, "fill the rest" derives the remaining fields from a reviewer's value, with evidence, and the reviewer can edit each before approving | decides D6 (#94); adds the review action "fill the rest" |
| G39 | Chosen option "Result, fields later" (S8's D9): "In the tool result and the trace now; record fields after the pilot. S8's proposal." | decides D9 (#94) |
| G40 | In chat, after the owner asked "but mindanao is in the phillippines?" and the coordinator confirmed it: "Yes pretty much. Hence the harness is looking at everything transcribed for context, the system prompt should factor in all possibilities and the agents search and try to figure out what it could be. That's pretty much the job continuous lookups and discernment". Reading (coordinator): the harness reads everything transcribed on the specimen, every label and field, as context for each field; its system prompt covers every possibility the profile's knowledge names (G29); the agent keeps looking things up and weighing the evidence until a field settles, is derived (G37) or goes to review (G1, G6), its place lookups going through section 4.8's filter (coordinator ruling) | states the harness's job, with G29 |
| G41 | Asked after #124's review found the coordinator's reading of G37 wider than the owner's answer: "At G22 you declined filling From and To from a single value and converting to the other unit. G37 now lets a missing elevation be derived from map data at the settled place. For a label that reads only "6,400 ft", what should fill the metre fields and the missing end of the range?" Chosen option "Convert and fill": "The label's own number fills both From and To, and the metre fields are converted from it exactly (1 ft = 0.3048 m), each marked as derived with evidence. This is the option you declined at G22." Reading (coordinator): the other unit is converted both ways by the exact factor, as G22's original option read; a stated range keeps its own endpoints; map data fills an elevation only where the label states none (G37). Source: `~/specimen-golive/OWNER_DECISIONS_2026-09-24.md`, G41 | revises G22's ban on conversion and filled endpoints; the four elevation fields stay mandatory |
| G42 | The owner, in chat on 2026-09-24 (04:21Z), answering G8: "The mandatory fields in an entomological database should be:" and the twenty fields listed below, then "Some harness lookups resources I might’ve given this a while back k sharing again location we already have a plan so not sharing that" and the taxonomy resources listed below, BugGuide marked "(North American)". Reading (coordinator): the twenty match `PRD.md` 12.4's table name for name, so the profile's mandatory list stands; `identified_by_irn` stays non-blocking until EMu Parties is connected, which the owner confirmed as G43; `date_identified` is on no pilot label, so all ten still go to review; the taxonomy sources match G23 and `PRD.md` 12.4, and BugGuide stays unused for the pilot, which has no North American material (G23); whether it serves North American material is the owner's decision (G5), since `PRD.md` 12.4's source registry requires each source's terms to be approved; the owner listed no optional fields, so the profile's optional handling stays as it is. Source: `~/specimen-golive/OWNER_DECISIONS_2026-09-24.md`, G42 | answers G8; keeps G16 and G23 for the pilot |
| G43 | Asked after G42, whose list marks Identified by IRN mandatory: "Your field list makes Identified by IRN mandatory. Earlier (G16) you chose "Optional for now": it doesn't block clearance until EMu Parties is connected, because the app can't look up EMu's person records yet. Which holds for the pilot?" Chosen option "Keep G16 for now": "Identified by IRN is recorded as not resolved and doesn't block clearance until EMu Parties is connected. After that it's mandatory like the other nineteen." Source: `~/specimen-golive/OWNER_DECISIONS_2026-09-24.md`, G43 | confirms G16 for the pilot |
| G44 | Asked from S4's real runs: "A label gives one collecting date, for example "3 Sept. '46". Date Visited From takes it as written. Should Date Visited To be filled with the same date, marked as derived with its evidence, the way a single elevation fills both ends under G41?" Chosen option "Fill To, derived": "Date Visited To gets the same date, marked as derived from Date Visited From, so the record can clear on it." Reading (coordinator): a written range keeps both ends as written; the derived value names Date Visited From, its rule and the rules version (section 4.8). Source: that file, G44 | settles a single date's To end |
| G45 | Asked from S4's real runs: "In S4's real test runs, the agent sometimes put slide-preparation codes like "VI-24-68-7" into fields no lookup checks, such as Collectors or Habitat. Nothing wrongly cleared, because other fields failed. On an otherwise complete label, though, such a code could clear as the collector. Should the queue decision send a field to review when its value doesn't look like its kind, e.g. a code in Collectors?" Chosen option "Yes, check the kind": "In fields no lookup checks, a value that doesn't look like its field's kind goes to review with a reason." Reading (coordinator): S4 builds it in the queue decision (T4), each field's shape rule in the Insects knowledge; for `verbatim_dts`, whose meaning `PRD.md` leaves unconfirmed (its open question 3), the owner's answer is pending (section 2.3), and until then a mismatch there is recorded as a finding (coordinator hold). Source: that file, G45 | adds a review reason for fields no lookup checks |

G35 to G45 are recorded verbatim, with each question as asked, in
`~/specimen-golive/OWNER_DECISIONS_2026-09-24.md`. G35's diagram, as the
owner wrote it:

```
[Legacy Text String]
       │
       ▼
[Tier 1: Historical Gazetteers] (GeoNames / Wikidata / Getty TGN)
       │
       ├─► Evaluates historical name + date active
       └─► Returns: Modern name equivalents & historical bounding polygons
       │
       ▼
[Tier 2: Modern Geocoders] (Google Maps API / Mapbox Geocoding)
       │
       ├─► Pipeline sends the *modernized* name + surrounding context
       └─► Returns: Highly accurate, precise modern coordinates
       │
       ▼
[Tier 3: Spatial Filtering] (Calculates final Point-Radius Uncertainty)
```

G42's list and resources, as the owner wrote them:

```
The mandatory fields in an entomological database should be:
 FMNH-INS#
 Collection Code
 Country
 Province/State
 County
 City
 Precise Location
 Elevation From (m)
 Elevation To (m)
 Elevation From (ft)
 Elevation To (ft)
 Habitat
 Collection Method
 Date Visited From
 Date Visited To
 Collectors
 Verbatim D/T/S
 Taxon
 Identified by IRN
 Date Identified

For taxonomy:
https://verifier.globalnames.org/
https://www.catalogueoflife.org/
https://www.gbif.org/
https://www.bugguide.net/node/view/15740 (North American)
```

`AGENTS.md`'s security rules are unchanged: nobody deploys from a workstation
or an agent shell, and nobody weakens branch protection, required checks,
environments, pinned action SHAs or identity conditions.

### 2.2 What the existing documents already fix

Sessions implement these as specified; none is a new decision.

| Topic | Source |
|---|---|
| Backend compute is Cloud Run: `specimen-api` service, `specimen-sam` service, `specimen-worker` job, `us-east4`. There are no Cloud Functions and the Cloud Functions API is not enabled | `scripts/ci/deploy_runtime.py` 31-32, 141-188; `firebase.json` |
| The workflow engine is the application's own SQL-checkpointed `Workflow`, no Temporal | `PROCESSING_ENGINE_COMPARISON.md` 10-15; `HARNESS_OPTIONS.md` 277-290 |
| The harness framework is Pydantic AI; tools are typed, allow-listed adapters with typed outcomes; the harness never invents values | `HARNESS_OPTIONS.md` 277-290; `PRD.md` HAR-001 to HAR-019 (326-344) |
| Readers: two independent readings per label, `handwriting-qwen` and `handwriting-muse`, provider-pinned, no automatic routing | `PRD.md` TRN-001 to TRN-010; `HUGGINGFACE_MODEL_ROUTING.md` |
| Raw reading provenance | `PRD.md` TRN-005; `CONTRACTS.md` 184 |
| Disagreement score `bounded-levenshtein-fraction-v1`, labelled as review priority and uncalibrated | `BACKEND_ADJUDICATION_PROVENANCE.md` 5; `READING_EVIDENCE.md` 70-89; `PRD.md` SCR-004, SCR-005 |
| The LLM first pass prompt is the managed prompt `transcription-disagreement-adjudication` | `src/specimen_digitization/prompts.py` 63-72 |
| Lookup sources: taxonomy through GBIF, which decides, with Global Names Verifier and Catalogue of Life as supporting evidence, and BugGuide isn't used (G23); geography through Google Maps (G10), keeping only the place ID, the outcome and a response fingerprint (G26), until S8's place tool replaces it behind the same interface with the owner's three tiers (G35): historical gazetteers (GeoNames, Wikidata, Getty TGN, NGA), Google given the modernized name, and the point-radius uncertainty, with the outside data of section 4.8. On `PRD.md` 573 (may a Google-only match clear): G10, G20, G27 and G34 let a Google lookup settle a place field, and G35 decided S8's D1 by keeping Google as tier 2, so a Google-only match can support that field's clearance. Fields other than taxonomy, geography and parties resolution are transcribed as seen. Parties resolution (`identified_by_irn`) needs EMu Parties, which is not provisioned, so that field is optional for the slide pilot (G16) | `PRD.md` 12.4 (490-501, 538-550); `GBIF.md` |
| Typed lookup outcomes: the eleven of HAR-008, as `LookupStatus` encodes them; no outcome is added. The failure table: a missing or rejected credential is an authentication error and an operational block | `PRD.md` HAR-008 (333), 682-694; `domain.py` 43-54 |
| Queue definitions: exactly one of cleared, needs human review, deferred; deferred only for documented model-capability limits; missing configuration, rate limits, timeouts, invalid credentials, outages, budget exhaustion and code errors are operational blocks with retry, not a queue | `PRD.md` QUE-001 to QUE-005 (390-394); `CONTRACTS.md` 217-246, as modified by G1 |
| Field value states; only `supported` satisfies a mandatory field | `CONTRACTS.md` 221-237 |
| Collection hierarchy and bootstrap | `COLLECTION_HIERARCHY.md`; `FIRST_COLLECTION_BOOTSTRAP.md` |
| The worker acts as its own operator account with a membership that cannot see sensitive data, never as the administrator, so automated steps are recorded under their own identity. An upload declared Sensitive, which is the intake default, is therefore never processed by this worker (coordinator ruling from these sources); G2 and DoD-6 hold for uploads declared not sensitive. A Sensitive upload is never reclassified (`CONTRACTS.md` 137, 161), so it is not processed; the app says so on the record and where an upload's sensitivity is chosen, with the Sensitive default left preselected (`design/03` §1.7, `design/01` H2.6, in `design/02` §1.8's neutral wording). The ten pilot slides are not sensitive by the owner's verified classification (G31) | `LIVE_PROCESSING.md` 62-63; `BACKEND.md` 169-170; `infra/release/OWNER_INPUTS.md` 288; `CONTRACTS.md` "Explicit intake sensitivity"; `PRD.md` 67, 724 |

### 2.3 Owner inputs still outstanding

| Item | Needed by | How |
|---|---|---|
| The mandatory and optional field list for the slide pilot (G8); `identified_by_irn` is already optional (G16) | first-pass and harness workstream, before acceptance | done 2026-09-24 (G42): the twenty fields of `PRD.md` 12.4, with G16 kept (G43) |
| Google Maps Platform key (G10) | harness geography tool | done 2026-09-23: `specimen-google-maps-key` version 1, a key restricted to the Geocoding API |
| Logfire write token (G3) | tracing in production | done 2026-09-23: the owner's existing token, stored as `specimen-worker-logfire` version 1 and verified for the specimen project |
| Hugging Face token rotation | none | withdrawn by the owner on 2026-09-23; the existing `huggingface-runtime-token` version is used |
| Hugging Face Inference Providers credits: the account's included monthly credits ran out on 2026-09-23 and routed calls return HTTP 402 | every model call: readers, first pass, harness, the acceptance lab | done 2026-09-23: the owner bought pre-paid credits, and routed calls succeed again |
| The repository's "Allow auto-merge" switched off (G21) | G17 for every session | done 2026-09-23 (`allow_auto_merge` is false) |
| A Logfire read token for the acceptance lab (optional) | reading each run's trace back for DoD-5 | owner copies the existing read token, under the owner's 2026-09-23 decision to reuse existing credentials; a separate, revocable lab token can replace it later; the acceptance lab's entry in `~/specimen-golive/OWNER_ACTIONS.md` |
| Standing IAM grants for the release and runtime identities (G11), the one-time, time-bounded grants for initialization and bootstrap that `DEPLOYMENT.md` 924-930 and the setup-window path require, and read access to the secrets `specimen-source-registry`, `specimen-collection-bindings` and `specimen-worker-actor-uid`, which the owner created on 2026-09-23 (version 1 each) | first data and runtime releases | owner runs the exact reviewed list the release workstream prepares (#119); once its part 1 is applied, the next setup window waits for #123 and a fresh window packet |
| S8's D4, the museum's published GBIF points, and D5, the checks' limits (#94) | the checks that compare a place with the label; until decided, D4's occurrence check is off and sends nothing, and D5's checks record findings only and never change an outcome (coordinator rulings) | put to the owner on 2026-09-24 and dismissed, so on hold until the owner takes them up; when D4 is taken up, its `catalogNumber` and `recordedBy` queries go to the owner as an explicit exception to section 4.8; D1, D2, D3, D6, D7 and D9 are decided (G35 to G39), D11 (Copernicus GLO-30 elevation tiles read from the project's storage, credited) and D13 (the in-house point-radius uncertainty engine per the Georeferencing Best Practices and Calculator) are coordinator rulings, and D8, D10 and D12 wait for their phase, except Getty TGN (G35) |
| What `verbatim_dts` holds (`PRD.md`'s open question 3), which G45's kind check needs for that field | G45 for `verbatim_dts` | saved for the owner, with D4 and D5, on 2026-09-24; until the answer, a mismatch there is recorded as a finding (coordinator hold) |
| A curator's confirmation of S8's curated place and itinerary entries (G36): the Insects collection manager, or a curator they name | the six McKinley slides and the Apo slide settling | S8's review sheets, one per entry with its sources, are ready (`~/specimen-golive/research/S8-curator-review-sheets.md`, 2026-09-24). The owner chose not to send them for now: "That’s fine. Human review is ok" (2026-09-24), so the six McKinley slides' places go to human review; Mt. Apo is a mapped peak, so only the itinerary's refinement of slide 327 waits |
| Access to Getty TGN (G35) | tier 1 of the place tool | not needed: S8 found on 2026-09-24 that Getty's reconciliation service and SPARQL endpoint answer anonymously under ODC-By 1.0 (#94, source S32); the gateway that needs a token is not used |
| The reference datasets for the place tool: the GeoNames dumps pinned in `~/specimen-golive/datasets/geonames/2026-09-24/`, the Copernicus GLO-30 tiles and the geoBoundaries files | S8's tool in production | the owner runs S2's checksum-verifying, no-clobber command once S8's manifest PR merges (section 4.8) |
| A Firebase account for the worker, with an operator membership that cannot see sensitive data (section 2.2) | automated steps recorded under their own identity | account done 2026-09-23: disabled, with no email, password, phone or sign-in provider; its UID is `specimen-worker-actor-uid` version 1. Still to run: its membership, applied once, with read-back, by the protected data release, never from an agent shell (S5's document in #96, in S2's T3e, with the UID from a temporary environment secret, after a read-only check that the account exists, is disabled, and has no email, password, phone or sign-in provider; disabled is required because production's email-link sign-in allows sign-up and would reach any enabled account that ever held an address, while the worker never signs in and acts through its service account; coordinator ruling, from #96's security review): an active organization membership and one collection membership on the pilot collection only, resolved from the committed key `insects` against the approved hierarchy artifact, whose approval hash the owner holds and supplies apart from the artifact, never computed from it (#96's `WORKER_MEMBERSHIP.md` rule, which the hierarchy bootstrap follows too), role `operator`, which cannot approve (`api.py` 323-342), with `canViewSensitive: false`. Never the admin membership document of `scripts/data/bootstrap_admin.py`, which hard-codes role `admin` (51, 71) |

## 3. Verified starting state, 2026-09-23

Six read-only research reports are in `~/specimen-golive/research/`. Summary:

| Area | State |
|---|---|
| Hosting | Live at `709ae3c` (run `35777324319`); after sign-in the client shows "Collection connection required" because it was built with no API origin |
| GitHub | `main` protected; repository public; no repository variables; the protected data and runtime workflows fail closed at admission on every push (runs `35777324461`, `35777324525`) |
| Cloud | No Cloud Run services or jobs anywhere; registry empty; Cloud SQL `specimen-digitization-instance` runnable, database and IAM users exist, never migrated; Data Connect placeholder schema, no connector; only the Hugging Face secret exists; all ten images present under `microscopic-slides/` |
| Pilot slides | Four localities from two collecting events (S8's reading, checked by eye; table in `~/specimen-golive/research/S8-pilot-localities.md`). 321-327: Mindanao, Philippines, 1946 (CNHM; F.G. Werner, H. Hoogstraal), written "P.I." or "Philippine Islands". 328-330: Yepocapa, Chimaltenango, Guatemala, 1948 (R.D. Mitchell); the label misspells "Chimaltenago". On 324-328 the locality, date, elevation and collector are on the right-hand label, and the left one holds only determination or preparation notes. Codes on the top edge such as `IX-17-66-2` are slide-preparation codes, not collection dates |
| Stages 1 to 4 | Wired in production only inside the frozen ten-specimen evidence-only lane; readings persist only inside the snapshot JSON |
| Stage 5 | Built, inactive in production; risk registry empty |
| Stage 6, LLM first pass | Absent; the prompt exists and no code calls it; the `adjudicate` step resolves only identical readings |
| Stage 7, harness | Deterministic, no tool calling, no fallback to raw readings, authority registry unconfigured, EMu Parties blocked |
| Stage 8, queue | Built; clearance always needs a human (`policy.py` 138-139), plus institutional-approval and semantics gates (`policy.py` 31-34), `label_coverage_unconfirmed` (`policy.py` 35-36; only a person sets `coverage_confirmed` for real profiles, `api.py` 1990 and 2220) and, in the evidence-only `PilotWorker`, `pilot_clearance_forbidden` (`worker.py` 318-323); deferral is the reviewer's `capability_defer` action (`api.py` 1940-1967) |
| On-demand processing | Impossible in production today: processing is scheduled only in synthetic mode (`api.py` 1292-1293, 2387-2396), the production worker runs only the frozen ten, SAM 3 rejects anything outside the manifest and shuts itself down within an hour, the Insects profile is a draft with no segmentation settings, and real records carry no budget so every paid step blocks |
| Persistence | 27 tables; production writes only the snapshot; the 13 normalized `Append*` mutations are called only by an emulator test; `data-apply/v1` refuses to run once the API or worker exists |
| Profiles | Code only; one Insects profile, all 20 fields mandatory; optional fields dropped at runtime; no inheritance down the collection tree |
| Tracing | Metadata only, worker only, custom allowlist exporter; only reader calls have their own spans; no trace id stored or returned; the standard path already has an `approved-content` mode (`observability.py` 232-276) |
| Client | Shows the image, readings with model and provider, a difference fraction, fields and history; defects: "State unknown" on every record without a disposition, identical readings labelled as differing, the full image re-downloaded every 20 seconds; SAM boxes hidden for the pilot originals |
| Release path | At least four steps fail even for the original scope (research report 02, section 7); retired by G11 |
| Unmerged branches worth reading | `codex/initialize-firebase-placeholder` (initialize from the empty Firebase onboarding schema), `codex/reader-trace-linkage` (link model telemetry to specimen observations) |

## 4. What gets built

Everything here implements section 1 with the sources in section 2.2. A
workstream that finds the specification silent or contradictory stops and asks
the coordinator; it does not decide (G5).

### 4.1 Stages

| Stage | Owner's requirement | Exists | To build |
|---|---|---|---|
| 1 Images in storage | Images in Cloud Storage feed the pipeline; new uploads too | Upload flow; source import from the bucket (not wired in production) | Wire source import in production over `microscopic-slides/`; start processing on intake and on request (G2); a request during an active run in the same collection waits and runs in request order (G13); the intake collection selects the profile (G14) |
| 2 Label segmentation | SAM 3 | Client, server, pinned revision, concept prompt `label` and 0.5 thresholds from the offline preflight | Authorize per run instead of per frozen manifest; stay up while work is due; record parameters and regions; confirm coverage automatically with the region-count and full-image cross-checks and send a failed check to the human queue (G15). Acceptance expects two labels on five pilot slides, and a missed label goes to human review |
| 3 VLMs | Several readers per label | Two provider-pinned routes, independent, raw responses kept | Run both routes in the on-demand lane |
| 4 Raw transcripts to SQL | Linked to the original image, which VLM gave what | Stored in the snapshot JSON only | Write the normalized tables in production (section 4.4) |
| 5 Disagreement score | Scoring for level of disagreement | `bounded-levenshtein-fraction-v1`, risk scores, uncalibrated | Run in the lane and persist per region |
| 6 LLM first pass | Decides which final raw transcript the harness runs against, and gives per VLM what was returned to the harness | Prompt only | A first-pass step on a Hugging Face model (G7) with the existing prompt; records the decision and, per reader, the reading and what was handed to the harness; when it picks no reading, the harness runs on each reader's raw reading (G19) |
| 7 Agentic harness | Runs lookups on the decided transcript through tools that depend on collection and subcollection, mandatory and optional fields; falls back to the raw readings if the decided transcript fails; if both fail, the relevant queue; graceful failures (G6) | Deterministic phases, GBIF adapter, unconfigured authorities | A Pydantic AI agent with the profile's typed tools (section 2.2 sources), its place lookups and the final call's going through section 4.8's filter (coordinator ruling), the HAR-008 outcomes for no data found, errors and retries, the raw-reading fallback, every tool call recorded; GBIF decides taxonomy, with Global Names Verifier and Catalogue of Life as supporting evidence (G23), and a match succeeds as `GBIF.md` 126-130 defines, at the label's own rank for a genus-only label (G25); a lookup that confirms exactly one reader's literal settles a disagreement (G20); for places (G27) and taxon names (G28) the verbatim keeps the text as written and the final value is what the lookup settled, both stored; from Google only the place ID, the outcome and a response fingerprint are kept, everywhere including traces, test fixtures and lab folders, and the geocoding tool hands the agent only those (G26); when no reader's literal matched the settled place exactly, the final value is the place ID and the outcome with no name, because G26 keeps Google's names out; S8's D15 (#94) asks the owner to choose between that, where the field clears (option b), and sending the field to review (option c), and G34 decides it for the Google tool: where no reader's literal matches even after folding or through an alias, the field clears with the place ID and no name only when the long name of Google's component at the field's levels, never a short name or code, is within one edit of the folded literal, the only such component, and every other admin field of the same reading, all of them and at least one, matches by fold or alias, with a `near_spelling` warning finding that never routes the record, and otherwise goes to review with the candidate; S8 builds the retrospective georeferencing tool of #94 behind the same interface (G34), whose D items stand as section 2.3 records; the harness works through every reading a notation allows and settles the one the evidence supports, with the notations in the Insects harness knowledge that S4 writes and the profile names, rendered into the harness's system prompt (G29, section 4.2); a field on two labels is settled per label and clears when every label settles to the same value, or else goes to review with each label's reading (G32); the numeric dates of every reading, decided and raw, are the evidence for an all-numeric date's order, and any disagreement among them fixes no order (G33); the place tool follows the owner's three tiers, historical gazetteers, then Google given the modernized name with its context, then the point-radius uncertainty, and stores only open-source coordinates (G35, G26), and a place only the museum's records know settles through a curator-confirmed entry (G36); a field the label leaves out is derived from settled fields with authority and evidence (G37), each value records its layer (G38), and the agent reads everything transcribed as context and keeps looking things up until a field settles, is derived or goes to review (G40); S8 builds the geographic derivations behind the geography interface, and S4 those that need no outside data (coordinator ruling) |
| 8 Queue decision | Harness-resolved is cleared (G1); otherwise human review or deferred as the spec defines; no data for a mandatory field means the human queue (G1, G6) | Policy engine with human-only clearance; deferral only through the reviewer's action | Apply G1 in the policy: remove the gates that contradict it (`policy.py` 31-34 and 138-139) for runs whose profile names `harness_route`, since G1 covers "something that harness was able to resolve", while every other run keeps them (coordinator reading of G1, #158); keep `label_coverage_unconfirmed` (35-36), which the lane's automatic check satisfies (G15); keep the reviewer's `capability_defer` action (`api.py` 1940-1967) and let the queue decision also return deferred under QUE-004; keep operational blocks with retry; validate the separately parsed date instead of the verbatim text (`policy.py` 119-126), and for a Date Visited To derived under G44 the derived value with its record: a date clears at the precision written, a two-digit year reads as 19xx for Insects (G24), and a Roman numeral in the month position is that month (G29); keep the elevation gate (99-106), which reads `field.literal` today (101-110) and must read a derived elevation's value instead, counting it only with its derivation record (G37 and G41, revising G22; section 4.8); a single written collecting date fills Date Visited To as derived (G44); a field no lookup checks whose value doesn't look like its kind sends the record to review with a reason (G45), except `verbatim_dts`, a finding under the coordinator hold of section 2.3; `unresolved_transcription` (46-48) yields to G19 and G20, so a region whose first pass picked no reading passes when every field drawn from it resolved, on its own evidence or through a lookup that settled the disagreement, and a field still left with conflicting readings sends the record to needs human review; when the first pass picked no reading, the non-empty check reads the settled value with a success outcome, since no single verbatim was chosen (G27, G28), while a field without a lookup whose readers all read the same text takes that text as its verbatim and its value and clears, on one label as on several (coordinator reading of G27 and G32, matching #131), once it passes G45's kind check, which for `verbatim_dts` is a finding under the coordinator hold of section 2.3, and the grounding check (75, `field.literal in excerpt`, which raises on that None literal) tests each reader's reading against its own evidence. The taxonomy gate (140-157) and finalize's operational check (163) read only `run.lookups[-1]`, which is arbitrary once G19 and G20 add a lookup per reader: the taxonomy gate reads the lookup that settled the taxon field, and the operational check catches an operational failure, not recovered by a retry, in any lookup the decision depends on. G23's flag and the readers' spelling difference under G27 are recorded as findings, never reasons for review. `pilot_clearance_forbidden` (`worker.py` 318-323) is off the lane's path and stays |
| 9 Linkage | Everything links to the specimen record | Stable ids throughout | Keep; the normalized rows carry specimen and run |

### 4.2 Profile

The slide pilot profile is configuration: readers, segmentation settings, tools
per field, the mandatory and optional field groups (G8), the risk policy
reference, and the clearance rule (G1). It maps to the `Insects` collection
beneath `Zoology`, and subcollections inherit their nearest ancestor's profile,
as `COLLECTION_HIERARCHY.md` 73-76 describes and the code does not yet do. A
specimen's profile comes from its intake collection, resolved down the tree, and
a reviewer can correct it (G14): the lane sets `run.classification_selection`
from the intake collection, which the `classify` step requires (`workflow.py`
308-331), and a reviewer corrects the profile collection through the existing
classification endpoint (`api.py` 2243); moving a specimen to another
collection stays refused (2262). `identified_by_irn` does not block clearance
for the slide pilot until EMu Parties is connected (G16, G43); the other
nineteen fields are mandatory, as the owner's list confirms (G42), and the four elevation fields stay mandatory, filled with authority and
evidence (G37 and G41, revising G22). The profile carries the Insects date rules as versioned rules, which S3
writes and S4's date tool reads: a two-digit year reads as 19xx (G24), and a
Roman numeral I to XII in the month position is that month (G29). It also
names, by id and version, the Insects harness knowledge under G29: the
notations its labels use and every reading each allows, which S4 writes in a
module it owns and renders into the harness's system prompt, as the owner
asked (coordinator ruling on who writes what). Optional fields must survive at runtime and
be extracted and shown.

### 4.3 Budget

The USD 25 ceiling (G9) covers everything. The pipeline records every paid
call's cost on the run and refuses a paid step whose worst-case reservation
would cross the configured model allowance; a Cloud Billing budget alert
watches the whole project. The production model allowance is USD 5 (G30). By
coordinator ruling on the mechanism:
- Each paid call reserves its worst-case cost before it starts, in one atomic
  check-and-reserve on a shared ledger: S3's `worker_cursor` document, written
  through `SaveDocumentV2` only at the revision the check read.
- Only usage the provider reports, or a billed amount it returns, settles a
  call, which releases the rest of its reservation. A timeout, a transport
  error, a 5xx or a response without usage stays reserved in full, recorded as
  `cost_basis: reserved`. A settled cost above its reservation counts in full,
  never capped, and once the allowance is spent further paid steps block. A
  retry reserves again, and nothing settled or held reserved is given back when
  a run fails or is retried.
- A worst case exists only where a request is bounded: every first-pass and
  harness model request carries a cap on output tokens, and each harness run a
  cap on its model requests, set from the lab's measured runs. A run that
  reaches its cap is a harness failure under G6.
- Every request of a call is bounded, and the call reserves the sum: readers
  and the first pass make up to two requests, the retry resending the crop.
  Per request, the bound is the lesser of the route's context length at the
  pinned input price plus the output cap, and, where the route documents its
  image-token rule and any maximum it downscales to, the crop's tokens under
  that rule plus the prompt and the output cap. A route without that
  documentation takes the context-length bound. 20,000 micro-dollars is the
  floor. The retry's validation feedback is capped at the first 20 errors plus
  a count, and a retry that would not fit is not sent (coordinator rulings for
  S3, 2026-09-24).
- The run's own budget settles like the program ledger: a reservation is
  released to its settled cost, and an unknown outcome stays reserved in full.
  A reader stopped by its token limits or its reservation is a failed
  reading: its step completes without an observation, and the queue decision
  sends the record to review with `independent_observations_missing`
  (coordinator readings of G6 and G30). Exhausting the program allowance or
  the run's budget stays an operational block (G30, QUE-005).
- SAM 3 is priced by its measured seconds, startup included, at the service's
  vCPU and memory rates, and settles as `computed`; its reservation bounds
  startup, the 300-second request timeout and the 10-second shutdown, as
  S3's #132 computes.

Each paid call records its usage, its reservation and a cost computed from a
pinned price list whose version and date are recorded, or the billed amount
where a provider returns one. The acceptance lab's USD 5 share is separate and
runs under the same mechanism with its own ledger. Infrastructure takes the
rest, mostly the always-on database at about USD 10-11 a month.

### 4.4 Data

The existing normalized tables (`dataconnect/schema/schema.gql`) are written in
production for every run, next to the snapshot. The data workstream adds only
what the owner's requirements need and the schema cannot hold today, per
research report 03 section 4: the disagreement score per region; the
transcription's region (required by `CONTRACTS.md` 185) and the first pass's
decision with what each reader handed to the harness; the harness's tool calls;
the mandatory or optional group of each field; the automatic coverage check's
result and evidence (G15); the trace id. Everything is keyed per region, since a
specimen can carry several labels. From Google geocoding only the place ID, the
outcome and a response fingerprint are stored (G26). A place or taxon field
stores both its verbatim text and its settled final value (G27, G28). Its first pull request is the exact GraphQL
and the contract the other workstreams code against. Additive changes only,
meaning expand-only: new tables; new nullable columns; dropping NOT NULL, but
only on columns the data contract names with a reason, and never on a key
column, a column of any unique constraint, or the provenance and idempotency
keys (`ModelObservation.runId`, `regionId`, `provider`, `modelVersion`,
`stepKey`, and the TRN-005 provenance `rawAssetId`, `promptVersion` and
`inputSha256` on every table that carries them, `EvidenceItem`, `PipelineRun`
and `Checkpoint` included), since a nullable column switches a unique constraint off for
every null row; the gate reads a checked-in list of the allowed columns and
refuses all of these even when that list names them;
one closed exception, by coordinator ruling (#88): `SourceAsset`'s
`specimen_unique_1` on (bucket, objectName, generation) is replaced by
`source_asset_specimen_object` on (organizationId, collectionId, specimenId,
bucket, objectName, generation), because the blob store is content-addressed
and identical bytes are one object across specimens; every added column is an
existing NOT NULL column, since PostgreSQL treats NULLs as distinct; it takes
two applies, so that a unique constraint governs the table at every moment
while writers run: the first adds the new constraint beside the old, which
keeps governing; the second runs one fixed, reviewed statement in
`dataconnect/sql/` (S5's T2a) that drops the old, since the migration
allowlist admits no drop, whatever Data Connect's diff carries; the data
release runs it before it computes that diff, and only after its own read-back of the live database at apply time shows
`source_asset_specimen_object` in place, over its six columns and valid,
since the gate compares committed
text only; the gate admits exactly these two steps from its checked-in list, and any other change to a
unique constraint needs its own ruling; new indexes, unique constraints and
foreign keys over new columns only; new connector operations, each `@auth(level: NO_ACCESS)` with the
membership `@check`s (`DATA.md` 73). The data plane's gate refuses everything
else: dropped or renamed tables and columns, type changes, adding NOT NULL, key
changes, new or changed uniqueness over existing columns other than that
exception, changed or removed operations, and
operations at any other auth level. `AppendProfileVersionV2` is open to
operators so that the projection can record the profile snapshot each run
used, but its `approvedBy` stays null unless the caller is a reviewer or above
with sensitive access, which is main's rule for approval claims; the worker
writes null (coordinator ruling on #88's review).

### 4.5 Tracing

The lane uses the standard Logfire path in its existing `approved-content` mode
with binary content off (images stay in Storage). One trace per run with a root
span carrying specimen, run, collection and profile ids; a span per stage; SAM 3
parameters on its span, continued inside the SAM service; Pydantic AI
instrumentation with content on for readers, the first pass and the harness, so
system prompts, messages and tool calls are visible; the queue decision with its
reasons. The geocoding tool hands the agent only the place ID, the outcome and
the response fingerprint, so neither the traces nor the model provider see
Google's response (G26), and no span, log line, exception text, stored error, tool-call result, test fixture or lab folder records the Geocoding
request URL, which carries the key, since the repository is public. The trace id is stored on the run and linked from the record in the
app. Local lab runs use the same instrumentation with `environment=lab`.

### 4.6 Runtime and releases

The existing topology, changed only where G2 and G11 require:

- the API may start executions of the worker job (`run.invoker` on that job
  only), and processing starts on intake and on request;
- the worker drains due work one specimen at a time and exits when none is due;
- SAM 3 serves any run the worker authorizes, scales to zero, and no longer
  shuts itself down after an hour;
- a merge to `main` deploys: Hosting as today; the runtime images, built from
  the merged commit, attested and deployed with readiness checks; additive
  schema changes applied with an automated additive-only check, including while
  the runtime is running.

### 4.7 Client

The record screen shows the thread: the original image with its region
overlays, several on a two-label slide;
per region, each reader's reading with its model, provider and prompt version;
the disagreement score; the first pass's decision and what each reader handed
to the harness; the harness's lookups with their outcomes; the fields, mandatory
and optional, with state and evidence; the queue decision and its reasons; and a
link to the Logfire trace, which opens through `url_launcher`, flutter.dev's
first-party plugin, a new app dependency (coordinator ruling for #122). The
queue shows needs human review, deferred and cleared, plus processing and
blocked. Its reason filter offers the reason codes S3 publishes in the
collection configuration's `reason_codes`, generated from the lane policy's
codes, and S5's T5 search matches a code with its suffixed entries; the new
run states (pending, retry scheduled, paused, cancelled) are picked in the
filter sheet, with no new status chips (coordinator rulings for S6; until S5's T5, the filter offers only codes
stored without a suffix). The thread marks each value's layer, verbatim,
settled or derived, with a derived value's evidence one step away, and in
review "Fill the rest" derives the remaining fields from a reviewer's value,
each editable before approval (G38). Intake starts processing and shows live
status. The client defects in section 3 are fixed first.

### 4.8 Outside data (G35, G38)

The place tool follows these coordinator rulings, from #124's reviews:
- Its requests carry place text only (coordinator rulings of 2026-09-24, from
  the reviews of #124, #174, #180 and #185, including the rulings on S8's
  option (c) and on S4's #183). The agent keeps a place-lookup tool it can
  call mid-run (G40), and the deterministic final call looks places up too.
  Both build requests through S4's single filter, and S8's request builder
  calls that same filter for every request its tiers send. The rule covers
  every value a request takes from the record or from a tier-1 name, in any
  parameter. The filter's output is what leaves, and after it a value is only
  escaped or encoded.
  - Sources, checked first, before any cut or expansion: exact substrings of
    the reading, taken from its place fields
    (`country`, `province_state`, `county`, `city`, `precise_location`) and of
    its unassigned locality text (the part of the lines holding those fields
    that no reading assigns to any field); the names tier 1 returns; and, in
    "fill the rest", the reviewer's value in a place field. A value drawn from
    anything else is refused. A full form written on the label, such as
    "Philippine Islands", is a source like any other place text.
  - Cuts, applied only to those values and by character span over the
    reading, so no character a cut covers can leave however a value is sliced
    (a slice that is not a whole token is cut this way, not refused): every token
    of every literal any reading assigns to a non-place field, and of every
    value a reviewer puts in a non-place field; every token of every clause,
    between commas, semicolons or line breaks, that holds a collector or
    determiner marker the profile's notations name, wherever the marker sits
    in it; every token that carries a digit; the month names and
    abbreviations the profile's date notations list, in any case; and a Roman
    numeral I to XII, in any case, that is a whole token next to a day or a
    year, before or after it, across separators (coordinator ruling on S4's
    #183, 2026-09-24). So "VIII" goes in "3 VIII 1946" and in "Mindanao, VIII,
    1946", while "Camp IV" and "P.I." stay. The readings' non-place literals do
    not cut the reviewer's own place value, since the reviewer's correction is
    the authority there.
  - Expansion, after the cuts: a surviving notation token that the table
    assigns to place fields only, and that appears in an allowed source, may
    be replaced by each full form the table lists for it, so "Davao Prov." is
    sent as "Davao Province". The table carries sendable place words, not
    glosses. Each full form then goes through the same cuts, and an expansion
    never brings back a cut character. A full form with no such notation in a
    source, and not written on the label, is refused (coordinator ruling on
    S4's #183).
  - Identifiers: an identifier a tier-1 source returned, matching that
    source's documented identifier pattern (such as a Wikidata item's
    Q-number, a TGN or GNS numeric identifier, or a GNS first-order unit code
    such as "PH-DVC"), may be sent back to that same source
    unchanged. It carries no label text, so the digit cut does not apply to
    it, and a value that fails the pattern is refused.
  - Fixed parts: query properties such as P625, P582 and P1365, paging, limits
    and headers (a project User-Agent naming no person or email) are reviewed
    constants, not record values, with a test that they carry no label text.
    Every value the filter passes enters a request only escaped or encoded:
    as an escaped literal in SPARQL, or as an encoded parameter in an API
    such as Wikidata's Action API. The key is the Secret Manager credential,
    which the filter leaves untouched; the fixed-parts test uses a fake key,
    and no test or fixture records a key or the URL carrying it.
  - Notations may be read locally in any form, since the rule limits only what
    leaves, and dates and elevations are compared locally and never sent. The
    filter applies to every request the place tool makes, tier 1, tier 2 and
    "fill the rest" alike.
  - Tests show exactly what it guarantees: "H. Hoogstraal leg." and a slice of
    it such as "Hoogstraa"; "3 Sept. '46" and "3 SEPT. '46"; "3 VIII 1946", "3
    viii 1946" and "Mindanao, VIII, 1946"; "Mindanao, P.I. 3 Sept. '46"; "Camp
    IV"; "Davao Prov., leg. Hoogstraal"; "Philippine Islands" written on the
    label and "P.I." expanded to it; every full form the table lists; a
    reviewer's corrected collector spelling that matches no reading literal;
    a reviewer's place value that a reading's non-place literal would
    otherwise cut; tier-1 identifiers passing and other values refused; the
    fixed parts and the User-Agent carrying no label text; and a place value
    with a quote in it reaching the query escaped. No cut character leaves,
    each expansion carries only full forms the table lists, and a value not
    drawn from those sources is refused.
  - Its stated limit: text the filter cannot recognize, such as a name no
    reading assigns to any field and no marker accompanies, can still leave; a
    lone or ranged month numeral in a record value with no day or year beside
    it, such as "VIII/IX", can leave; and the month-position cut can trim a
    tier-1 name whose numeral stands beside a number, such as a region
    written with its code.
- The Maps key, and any credential a later source needs, is kept in Secret
  Manager and follows section 4.5's rule: no span, log line, exception text,
  stored error, tool-call result, test fixture or lab folder records it or the
  URL that carries it. GeoNames is read from its dumps (D12 defers its web
  service), and Getty TGN answers anonymously, so neither needs one today.
- The GeoNames dumps, the GLO-30 tiles and the geoBoundaries files are pinned
  by version and checksum in S8's committed manifest and stored
  content-addressed under `application/sha256/`, which the worker's standing
  read grant covers (#119). The reader verifies each checksum. The owner
  uploads them with a checksum-verifying, no-clobber command that S2 writes
  from the merged manifest; no agent writes storage. GeoNames keeps no archive
  of its daily dumps, so for them the command uploads S8's pinned files from a
  folder outside the repository after checking size and digest, and never
  downloads them again.

The taxonomy tools send the taxon name, never place text (`GBIF.md` 107-114).

| Source | Sent | Kept | Licence and credit |
|---|---|---|---|
| Google Geocoding (place tool, tier 2) | the modernized name, or the literal, with the same reading's place text (this section's sources) | the place ID, the outcome and the response fingerprint only (G26); names and coordinates are read in memory to compute the outcome and never feed a stored or derived value | nothing of Google's is stored |
| GeoNames (place tool, tier 1) | nothing: its dumps are read from the project's storage | GeoNames ids, names, codes and coordinates | CC BY 4.0, credited |
| Wikidata (place tool, tier 1) | the name, with the same reading's place fields | item ids, labels and coordinates | CC0, credited as a courtesy |
| Getty TGN (place tool, tier 1) | the name, with the same reading's place fields | TGN ids, names, dates and coordinates | ODC-By 1.0, credited |
| NGA GNS (place tool, tier 1) | the name, with the same reading's place fields, or nothing when read from its files | feature ids, names and coordinates | credited as "NGA GEOnet Names Server"; NGA's current pages carry only a disclaimer (#94, source S33) |
| Copernicus GLO-30 (place tool, D11) | nothing: tiles are read from the project's storage | where the label states no elevation, the minimum and maximum over the uncertainty circle, with the tile's version | credited to DLR and Airbus, as its licence requires |
| geoBoundaries' open release for the Philippines, and CONRED's COD-AB file via HDX for Guatemala (place tool, containment, G37) | nothing: files are read from the project's storage | the county or city whose unit holds the whole uncertainty circle, widened by the file's stated simplification error for geoBoundaries' simplified Philippine files | per file, as each source's licence states: the Philippine units under CC BY 3.0 IGO (NAMRIA, PSA and OCHA Philippines, via HDX), and Guatemala's departments and municipios from CONRED's own file under the licence its metadata states (CC BY 3.0 IGO, via HDX), never geoBoundaries' ODbL OpenStreetMap file (coordinator rulings, from S8's licence checks of 2026-09-24) |
| GBIF species match v2 (taxonomy, decides, G23) | the scientific name with authorship when present, its rank and higher ranks, and the checklist key (`GBIF.md` 107-114) | the usage key, accepted name, rank, status and match type, with the exact query, retrieval time, identifiers, licence metadata and response digest (`GBIF.md` 31) | COL XR's licence (CC BY 4.0), cited per GBIF's citation guidelines (`GBIF.md` 47) |
| Global Names Verifier and Catalogue of Life (taxonomy evidence, G23) | the scientific name | their match results, as evidence | each source's licence, recorded and credited per source |
| GBIF occurrence search (D4, held) | nothing: the check is off while D4 is held (coordinator ruling) | nothing | its query (`GBIF.md` 183-190, or #94's `locality` and `recordedBy` match), what it keeps, and how CC BY-NC records are handled come with D4's decision |

Each credit goes into the georeference's `georeferenceSources` and into the
dataset metadata, as D2 proposed; S8 writes each source's exact text, taken
from its terms, into the manifest.

GADM is not used, not even as a measurement: its terms bar redistribution and
commercial use (coordinator ruling, with geoBoundaries for containment).

Coordinates (coordinator ruling): tier 3, every derivation (G37, G38, G41) and
the georeference (G39) use open-source coordinates only, never Google's point.
This narrows G35's diagram, whose tier 2 coordinates would feed tier 3, to
what G26 and Google's terms allow: the Maps terms bar content derived from
Google Maps content. A future dataviz fetches Google's current coordinates
live by place ID (G35).

Derived values (coordinator ruling): a derived value counts only when its
record names its settled inputs, the dataset or authority with its version,
and the tool call that produced it. A G41 conversion or endpoint fill, and G44's date fill, call
no outside tool, so each names instead the stated field, its rule (1 ft =
0.3048 m exactly, or one value for both ends) with the rules version, and S4's
`apply_derivations` step (#144, #167).
S4's gate and S5's T6 enforce this, with a test that a value the model asserts
without such a record does not count.

Curated entries (coordinator ruling): an entry becomes curator-confirmed only
in a pull request that cites the confirmation the coordinator records in
`~/specimen-golive/OWNER_ACTIONS.md` when the owner relays it (the confirming
role and date, never a name), with a test that an unconfirmed entry never
settles a field (G36).

The review action "fill the rest" (G38), by coordinator ruling:
- the server refuses it for a record declared Sensitive, on which no automated
  step runs (section 2.2, `PRD.md` 67);
- it requires review rights, like the decision route;
- the API holds no Maps key or source credential and never writes the G30
  ledger, so the route validates the request and enqueues a derivation job,
  and the worker runs S4's `derive_rest` with the tools' credentials,
  reserving each paid call under G30;
- the result is a stored proposal, read when the job ends, which the reviewer
  edits and approves through the existing decision route. S3 hosts the job,
  S5 the route and the proposal, S4 `derive_rest`, and S6 the button.

## 5. Sequencing

Two tracks run at once and meet at the first production run.

**Release track (workstream S2).**
1. Contract amendments recording the owner decisions of section 2.1 in every
   affected document (docs only).
2. Auto-on-merge data and runtime workflows (G11), with the first data
   initialization matching the real state (database exists and is empty).
3. The exact IAM and secret list: standing grants for the release and runtime
   identities, and the one-time, time-bounded grants for initialization and
   bootstrap; the owner runs it.
4. First data release (schema, connector, collection tree, administrator) and
   first runtime deploy on the code then on `main`; repository variables set;
   Hosting rebuilt. The app is connected and visibly live (DoD-1 to DoD-3).
5. From then on, every merge deploys.

**Pipeline track (S3, S4, S5, S6).**
1. The data contract (S5) first, because S3 and S4 write to it.
2. The on-demand lane, SAM 3 per run, profile, budget and tracing (S3).
3. The LLM first pass, the agentic harness and the queue rule (S4).
4. The normalized projection and the thread API (S5).
5. The thread view and queue (S6).

**Acceptance (S7).** Local runs with real models start at once on specimen 1 to
flush out environment and stage failures, and follow the pipeline track as it
lands. Once the release track reaches step 4 and the pipeline track is merged,
production runs begin: specimen 1, fix, rerun until flawless, then specimen 2,
and so on to specimen 10 (section 8). Then the owner's new record.

## 6. Sessions, ownership and branches

Each side session runs in its own worktree, cuts topic branches
`golive/<ws>-<topic>` from a freshly fetched `origin/main`, and opens pull
requests labelled `golive` with the title prefix `[golive:<ws>]`.

| ID | Session title (also its messaging name) | Scope | Owns (writes) | Model and effort |
|---|---|---|---|---|
| S0 | App production launch plan | Plan, decisions, merge order, owner liaison, acceptance sign-off | `docs/execution/golive/PLAN.md`, `briefs/`, `~/specimen-golive/MERGE_ORDER.md`, and the notes in `docs/product-requirements/PRD.md` that record owner decisions | Opus 5.5, max |
| S1 | Steward go-live PRs through review and merge | Review every PR with a fresh swarm, CI to green, merge, post-merge deploy checks, push back | no source; PR comments; reruns; merges (G17) | Opus 5.5, high |
| S2 | Release data and runtime planes on merge | Contract amendments, auto-on-merge planes, IAM and secret lists, first releases, repository variables, deploy health | `AGENTS.md` deployment paragraph, `docs/DEPLOYMENT.md`, release and approval docs, `.github/workflows/`, `scripts/ci/` release and deploy code, `infra/`, `containers/`, `scripts/qa/live/` | Opus 5.5, xhigh |
| S3 | Build the on-demand processing lane | On-demand trigger and source import in production, worker drain, SAM 3 per run, profile configuration and inheritance, optional fields at runtime, budget, tracing | `api.py` processing and source routes, `worker*.py`, `sam3_*.py`, `production.py` adapters (535-910), `workflow.py` step bodies before `adjudicate` (pin_dependencies, classify, quality_check, segment, transcribe), `cli.py`, `transcription.py`, `collection_*.py`, `profile_runtime.py`, `observability.py`, `bounded_telemetry.py`, `tracing.py`, `provider_privacy.py` | Opus 5.5, high |
| S4 | Build the LLM first pass and agentic harness | LLM first pass, agentic harness and tools, fallback, graceful outcomes, queue rule G1 | new first-pass and harness modules, `harness.py`, `evidence_harness.py`, `lookup.py`, `parties.py`, `geography.py`, `policy.py`, `prompts.py`, `model_gateway.py` routes, `workflow.py` step bodies from `adjudicate` to finalize, including `parse` (685-719) and the stage 5 scores (the disagreement ratio in `adjudicate`, the risk score in `finalize`) | Opus 5.5, high |
| S5 | Build the pipeline data model and thread API | Data contract, schema additions, normalized projection, thread API, contract snapshots | `dataconnect/`, `scripts/data/`, `storage.py`, `search.py`, `active_graph.py`, `production.py` `SqlConnectRepository` (80-534), a new thread-route module, `scripts/ci/release_sql_catalog.sql` and the table-count assertion in `scripts/ci/test_data_release.py`, `docs/execution/backend-*.json` | Opus 5.5, high |
| S6 | Build the record thread UI | Client defects, thread view, queue, processing status, trace link | `apps/specimen_digitization/` (sole owner of goldens) | Opus 5.5, high |
| S7 | Run the acceptance lab one specimen at a time | Local and production runs one specimen at a time, run reports, defect routing | new `scripts/lab/`, `~/specimen-golive/runs/`, `~/specimen-golive/reports/`, GitHub issues labelled `golive` | Opus 5.5, high |
| S8 | Research retrospective georeferencing for the harness | The owner's georeferencing charter (G12): historical toponyms, tiered resolution, uncertainty, Darwin Core mapping; a plan for the owner (#94), then the retrospective georeferencing tool behind S4's geography interface (G34) | `docs/product-requirements/GEOREFERENCING.md`, `scripts/research/georeferencing/`, and the tool's modules: `src/specimen_digitization/application/georef_*.py` and `georeferencing_tool.py`, `tests/test_georef_*.py`, `tests/test_georeferencing_tool.py`, `tests/fixtures/georeferencing/` and `docs/execution/golive/GEO.md` | Opus 5.5, high |

Shared files (`domain.py`, `workflow.py`, `api.py`, `production.py`) take
additive, small changes; new behaviour goes in new modules where possible.
`domain.py` has no single owner: changes are additive (new types, new fields
with defaults), each pull request lists its additions in its body, and where
two sessions need the same shape, S5 decides it. A change to a file another
session owns, such as `storage.py` (S5), needs that session's sign-off as a
comment on the pull request before the steward merges it. Only S0 edits this page.
Everyone appends to `docs/SESSION_LEARNINGS.md`.

## 7. Rules for every session

### 7.1 Branches and worktrees
- Work only in your own worktree; never in the root checkout (it is someone
  else's dirty codex branch) and never on `main`.
- One topic per branch and per pull request. Start each topic from a fresh
  `git fetch origin` and `origin/main`.
- Subagents that write code get their own worktree (`isolation: "worktree"`) or
  their own sub-branch; the session integrates.
- Never use bare `git stash`; the stash stack is shared across worktrees.

### 7.2 Spec first, test first
- Each topic starts with the spec delta (a short section in your workstream's
  doc under `docs/execution/golive/`, citing section 2) and failing tests, in
  their own commit, then the implementation. The PR body names both commits.
- Tests use fakes for paid and external calls; recorded real responses from the
  acceptance lab may become fixtures, except that a Google geocoding response is
  first reduced to the place ID, the outcome and the fingerprint (G26), and no
  recorded request keeps its URL, which carries the key.
- Nothing may contradict the owner decisions in section 2.1 or add product
  behaviour the owner did not ask for (G5). Where the specification is silent
  or contradictory, stop and ask the coordinator; do not decide.

### 7.3 Pull requests
- Title `[golive:<ws>] <what>`, label `golive`, body sections: Spec, Tests (red
  and green commits), Gates run locally, Risk, Depends on.
- Keep each PR under about 600 changed lines, excluding generated files and
  goldens, so a fresh review swarm can hold it.
- Include your `docs/SESSION_LEARNINGS.md` closeout entry in the PR.
- When the PR is open, message the PR steward: first line "PR #N ready: <title>".
- When the steward pushes back, fix on the same branch and message it again.
- Open a pull request as a draft and confirm your session's PR panel shows
  auto-merge off before marking it ready (defence in depth after G21).
- Never enable auto-merge (G17); the repository's setting is off (G21, done
  2026-09-23). The steward merges with `gh pr merge N --merge` once its
  swarm approves the current head. Every new head gets a fresh swarm, reverts
  included (G18), so a pull request is brought up to date with `main` only when
  it is next to merge, and by its owning session: GitHub's server-side merge
  ignores the `merge=union` rule for `docs/SESSION_LEARNINGS.md`. When the
  steward says your PR is next, run `git fetch origin && git merge origin/main`
  (a merge, not a rebase), push, and reply "PR #N ready".

### 7.4 Local gates and machine load
- Start every shell with `export DEVELOPER_DIR=/Library/Developer/CommandLineTools LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`.
- Run targeted tests while developing. Before a push, run the gates for what you
  changed, one at a time, never the whole `verify.sh` in one command: pre-commit
  always; `uv run pytest scripts/ -q` and `uv run pytest tests/ -q` for Python;
  the Flutter gates (with `lib/firebase_options.dart` copied from
  `firebase_options.ci.dart` and removed afterwards) only for the app. CI runs
  everything.
- Start a full suite only when `uptime` shows a one-minute load below 12. Never
  run git operations in a worktree while a gate runs there.
- Write long output to a file and read at most 50 lines of it. Never pipe
  `flutter test` progress into a result.

### 7.5 Context
- Your brief and your status file are your memory. After a compaction or
  restart, reread both before acting.
- Send broad reading to Explore subagents and ask for conclusions with
  `file:line`, not dumps. Start a fresh subagent per task.
- Commit at every green step; the branch is the durable record.

### 7.6 Status, owner actions, messages
- `~/specimen-golive/status/<session-id>.md`: at most 30 lines, overwritten at
  every milestone: branch, worktree, open PRs, current step, blockers, next step.
- Anything only the owner can do goes into `~/specimen-golive/OWNER_ACTIONS.md`
  (exact command or console path, why, what it unblocks); then message the
  coordinator. Do not ask the owner directly; the coordinator batches requests.
- Messages go by `SendMessage` to the session title (`ListAgents` shows names).
  The first line is a complete sentence saying what the message is about.
- Research reports are in `~/specimen-golive/research/` (01 pipeline, 02 release
  planes, 03 data, 04 observability and prompts, 05 client, 06 specification).

### 7.7 Security
- Never put secrets, tokens, the administrator's identity, instance addresses,
  billing or organization ids into the repository, a pull request, an issue, a
  log you share, or a message. Private artifacts stay in `~/specimen-release-private/`.
- No deploys from a shell. `gcloud` calls are read-only and always carry
  `--project specimen-digitization`. `gh` writes only what your brief assigns:
  your own pull requests and their comments, GitHub issues (S7), and the
  steward's reviews, reruns and merges. Repository variables and
  settings are owner actions. Never pass `--project` to `gh`.
  `firebase dataconnect:sql:diff` is not read-only (it moves the live schema's
  update time); do not run it.
- Do not read `.logfire/` credential files or `.env` files into context.

### 7.8 Closeout
Append the session's outcome, evidence, learnings, failed approaches and
follow-ups to `docs/SESSION_LEARNINGS.md` before any handoff, merge, branch
deletion or worktree removal (`AGENTS.md`).

## 8. The per-specimen acceptance loop

For each specimen in order, `subject_105526321` first:

1. Run it locally with real models through the latest merged lane (S7); fix
   what fails before touching production.
2. Import and process it in production through the app, declared not
   sensitive on the owner's verified classification (G31), since the worker
   never sees a record declared Sensitive (section 2.2).
3. Check, and record in `~/specimen-golive/reports/<subject>.md`: every stage
   ran; SQL holds the regions, each reader's reading with provenance, the
   disagreement scores, the first pass's decision with what each reader handed
   to the harness, every tool call and outcome, the fields with their groups and
   states, and the queue decision with reasons, all keyed to the specimen and
   run; the Logfire trace shows every stage with its prompts; the app shows the
   whole thread; cost and timings.
4. Any failure: a defect to the owning session, a fix through a pull request,
   an automatic deploy, and a new run of the same specimen until it passes with
   no intervention.
5. Then the next specimen. By the tenth, a run should pass the first time.

A record the harness could not resolve and that went to the human queue with
the right reason is a correct run; correct means the pipeline behaved as
section 4 specifies, not that every record cleared. Under G37 and G41 the harness now fills a missing
elevation, endpoint or unit with evidence, but the six McKinley slides go to
needs human review until a curator confirms their place (G36), and most slides
lack a taxon and a determiner; no label states the determination date, which
nothing can derive, so needs human review with the right reasons remains the
expected outcome for each of the ten.
