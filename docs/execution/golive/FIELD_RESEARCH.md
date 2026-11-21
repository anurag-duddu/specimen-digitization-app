# Field research: one expert per field (takeover, 2026-10-08)

This note records why the six-specialist research harness could not finish a
specimen, what replaces its runtime path, and how the replacement meets the
owner's harness design of 2026-10-03. It is written for the owner first and
for engineers second.

## The owner's design (2026-10-03, the spec)

1. The harness never invents what the label does not say. Several image
   readers transcribe each label; one model (the organiser) reads every
   transcription and arranges the text into field-value pairs. The owner's
   correction in the schema session, 2026-10-08, refines this: deriving and
   inferring are the point, so the rule is "never a value without recorded
   support" (PRD.md section "Field model v2: four groups", its decision
   record and rules 1 to 3; in progress). This first version settles what the label states, what an
   approved source confirms (for example "P.I." settled as the Philippines
   from a cited place lookup) and the arithmetic derivations below. Supported
   inference beyond that is the next step: an engineering staging decision of
   the harness session, not an owner decision
   (`~/specimen-golive/status/harness-derivation-proposal.md`).
2. The harness receives those pairs together with every raw transcription,
   because a model can make mistakes and evidence is always needed.
3. It works field by field: one expert resolver per field, each with its own
   instructions, visible as its own agent in Logfire.
4. A field that is already an accurate read is simply finalized. A field with
   confusion is checked against the approved sources, and the expert keeps
   trying them until the field is settled or shown not to settle.
5. Unrelated work runs in parallel. Each record starts with fresh context.
6. What cannot be settled (the label lacks it, the sources cannot settle it,
   or several possibilities remain) goes to Needs human review. A settled
   field is cleared. The owner's decisions of 2026-10-09 clear two such
   cases: listed fields the label does not state, and a taxon with no genus
   (see "Fields the label does not state" below).
7. USD 1 per run is a hard ceiling, configurable per institution, and each
   run should cost as little as possible.
8. Failures are graceful: "no data found", "an error occurred, retry".

## What the code did on 2026-10-08 (main cb38a8be5)

| Spec point | Today | Gap |
|---|---|---|
| 1, 2 Pairs plus raw text | Met. The organiser call reads every reading of every label and stores quoted candidates; each specialist receives every reading. | None. |
| 3 One expert per field | Six topic specialists own the 20 fields (geography owns five, collection five, measurement four). | Real gap. |
| 4 Keep trying sources | Each specialist has a 240-second limit that its own record keeping uses up. Only geography is pushed to try more sources. | Real gap. |
| 5 Parallel | Two specialists at a time, in three windows one after another; tool calls one at a time. | Real gap. |
| 6 Unresolved to review | Several unresolved states block the record instead of sending it to review. | Real gap. |
| 7 USD 1 ceiling | Enforced per collection profile. Each request re-sends up to 500 KB. | Partly met. |
| 8 Graceful failures | Several failure reasons show no message in the app. | Real gap. |

## Why one specimen took so long and then failed

Every step of every specialist was saved by rewriting the whole run record,
which had grown to 873 KB against a 1.5 MB cap. Two specialists wrote that
same record at once, so their writes collided and were retried (93 rejected
writes in eight minutes of the live run). Counting the code paths, one
specimen made roughly 4,000 sequential database and storage round trips:
about 36 per model call, 9 per tool call, and about 140 to publish each field.
Offline, with an instant scripted model and an in-memory database, one
specimen still took 59 s of pure record keeping (59% publication, 25% the
whole-record store). The live traces (Logfire, 2026-10-08 22:08-22:20Z) add
the model side: the six specialists ran in three pairs one after another,
about 9 minutes before publication began; model calls, with the effect
record keeping wrapped around each, were 56% of specialist time, and one
taxonomy call took 99 s, because every request re-sent the whole research
input (taxonomy's first message alone was about 118 KB).

The live run on 2026-10-08 (specimen 105526321) failed four ways, all
confirmed from its recorded state, journal and worker log:

1. Taxonomy asked for a procedure by a prompt's version name; the tool refused
   it without a retry.
2. Geography spent 132.9 s on five calls of a tool that makes no outside
   request, almost all of it saving, and hit its 240 s limit.
3. Collectors and catalogue number: a helper built the complete answer with
   its lineage, the model dropped the lineage when retyping it, and the
   validator refused the answer.
4. Publishing `identified_by_irn` timed out twice reading the oversized record
   (30 s each), before anything was written.

## PR #282

Not merged. It fixes cause 1 at its root but works around causes 2 and 3
(one batched geography tool, longer prompts asking the model to copy text
exactly), does not speed up the read behind cause 4, removes a check on which
date reading is chosen, and makes one publication timeout stop the whole
queue. The record keeping that causes the failures stays.

## The replacement: field research

For a run whose profile names a harness route, the workflow hands over at the
`plan` step, as it does today. With `SPECIMEN_RESEARCH_HARNESS=fields` the
handover runs field research instead of the six specialists:

1. **Inputs.** Every reading of every label (named 1A, 1B, 2A as the organiser
   names them), the organiser's candidates and settled value for each field
   (a keyed line the parser read is a candidate of each reading that writes
   it), and the profile's field list.
2. **Every field gets its expert.** A field whose organiser value is
   supported is researched like any other, whether or not an approved source
   or check covers it: its expert may confirm the organiser's value or find
   that it is not this field's text; an accurate read (spec point 4) is
   finalized when its expert confirms it. (Until 2026-10-09 a field with no
   source or check whose organiser value was supported was finalized as
   written with no model call. In the real run of 2026-10-09 that cleared
   105526328's habitat as "trap", the end of its collecting-method line "lot
   #2 cut branch / trap".) Only the identified-by IRN, which no approved
   source supplies, gets no expert (its nonblocking exception). A value
   settled for a field with no source or check is the verbatim layer, any
   other the settled layer. In that run the expert of a field with no source
   or check made one request (once two), of about USD 0.0007 each; in this
   change's real runs of 105526321, 105526326 and 105526327 the experts of
   such fields whose organiser value was supported added USD 0.0014 to
   0.0021 per specimen. The
   briefs of those fields (collectors, collection code, habitat, collection
   method, verbatim D/T/S) say, since WP 1.8, that the expert resolves with
   the text the readings write also where the readers write it differently,
   answering the reader's text the units support, and answers
   several_possibilities only where it finds no text to answer (habitat.txt;
   before 2026-10-25 they said a decided transcript decided its label, and
   until WP 1.8 they followed the old first pass's preferred reader), as the
   agreement rules of step 5 let it: in this change's first real runs the verbatim D/T/S
   experts of 105526321 and 105526326 answered several_possibilities
   between their decided reading's text and the other reader's ("3 sept.
   '46" and "3 Sept. '46"; "IX - 14 - 46" and "IX-14-46"). The habitat
   brief says a collecting method or device (a trap, a net, beating, cut
   branch and the like) is the collection method, never the habitat, and
   that when the only text offered for the habitat is a method the label
   lacks one: in the real run of 529f8033c 105526328's habitat expert still
   confirmed the organiser's "trap". Since lane H4 (2026-11-21) the habitat
   brief also says that a host the label writes is the Habitat, as written
   ("A host the label writes is the Habitat", below).
3. **One expert per field.** Every field gets its own Pydantic AI agent
   (`field_<key>`), its own instructions (shared rules plus the field's brief)
   and only its approved tools. All experts run at once. After the step has
   decided (steps 5 to 7), each field of the attempt is one
   `field_research.field` span inside the step's `field_research` span
   (`step.trace_fields`): the expert's outcome, its failure and fallback,
   the value's state and layer, the run's reason codes for the field, the
   check that refused a resolved answer (or "admin_marker_only": a precise
   location's answer that gives only an administrative marker, or
   "place_text_only": one settled on only a settled place's text, see
   "Fields the label does not state") and the rule that decided the field (rule A
   or B, a derivation, an unreachable source or a timeout on the last
   attempt), and each lookup as source and status. These are codes; the literal,
   value, authority id and reason are added only when the worker captures
   approved content.

   **Each expert's budget.** An expert has 6 model requests ("turns") and 12
   tool calls (`experts.REQUEST_LIMIT`, `experts.TOOL_CALLS_LIMIT`). Once a
   third of its tool calls or fewer are left (four of twelve), or its next
   turn is its last, each tool result tells it to answer now
   (`experts.ANSWER_NOW_NOTE`). A tool call identical to one the same expert
   made before (the same tool and arguments) gets that call's answer,
   marked as a repeat, and runs nothing again; a lookup whose source could
   not be reached is the exception and is asked again (the record's sources
   then answer it from their own cache). An expert that still runs out (a
   turn that asks for more tool calls than are left, or a turn past its
   last) is asked once more for its answer from the readings and the
   answers it has (`_Expert.answer_now`): one request on the same meter,
   under the same run ceiling, with its tools withheld and each tool call
   the limit stopped answered "Not run". That answer is checked like any
   other and is the expert's own. Only when its answer breaks its checks
   does the resolver's fallback take its place: sources_cannot_resolve,
   "The expert used all its attempts without settling this field." When the
   run's ceiling or the input bound refuses that request, the field fails as
   for any refused request (budget_exhausted, input_too_large) and goes to
   review, its reason saying so. The shared brief has
   the expert ask about the label's own text first, then, when no source
   knows it, an abbreviation written out or another reading's variant, and
   then stop: a place no gazetteer holds is not found by asking again with
   other larger units after its name. (In the real run of 2026-10-09 on the
   ten pilot specimens, twelve fields on seven specimens ran out, and the
   fallback replaced their experts' answers. In this change's real runs of
   105526321, 105526326 and 105526327, live and with Getty TGN down, no
   expert ran out: eight tool results told an expert to answer now, and no
   answer-now request was needed.) The briefs' examples are patterns
   ("<Genus> sp. 1", "<Name> Prov.", "<n> ft"), never a real taxon, place,
   person, year or slide code, and the shared brief says examples are never
   text to look up or copy: in one of those runs 105526321's taxon expert
   looked up "Epipsocus", the taxon brief's example genus, which no label
   of that specimen writes. The notation table's line (step 5, P4) is a
   rule, not an example, and keeps its names.
4. **Sources.** GBIF (with Catalogue of Life and Global Names Verifier
   alongside), GEOLocate, Getty TGN, Wikidata and NGA, plus deterministic date,
   elevation and catalogue-number checks. One request per distinct query per
   record (shared cache), retries with backoff (three attempts, a Retry-After
   of at most 10 s honoured, a redirect never followed), GEOLocate spacing
   kept, and at most two requests at a time to each of Getty TGN, Wikidata
   and NGA across the worker process (`sources.SOURCE_SLOTS`). A request
   that waits 30 s for one of those slots is not sent: its lookup gives up
   at once as a timeout ("Getty TGN was busy; this lookup was not sent"),
   logged like any unanswered request (`error=slot_busy`), so the expert
   goes on with its other sources. Like any unanswered request, that answer
   is kept for the rest of the record's research: the same lookup, asked
   again, is answered from the record's cache and not sent. A GEOLocate
   request whose turn under the
   3 s spacing is more than 30 s off is busy the same way ("GEOLocate was
   busy; this lookup was not sent"), and it takes no turn, so the requests
   after it are not spaced behind it. Each source
   response is stored once as evidence. Each request a source leaves
   unanswered (a final status other than 200, or retries that ran out) is
   logged in one WARNING line with the source, the host, the HTTP status or
   the error's class, whether a Retry-After came back and the attempt it
   ended on, never the query; for GBIF, the status its verification ended on.
   The line also says who sent the last response that was no answer: its
   Server and Via headers, with every word of the request's query and path
   replaced by "[query]", whether its body is an HTML page, and the first
   200 characters of its body (`sources._sender`). The body is logged only
   when none of the query's words is in it, compared with letter case,
   accents and every space aside, as written and with its percent-encoding
   read up to three times; a body that is not UTF-8 is never logged. Any
   other body is logged as "[body withheld]" (`sources._body_excerpt`), so
   a short word run into others ("sanjose" for "San Jose", "lima2") is not
   logged either (the review of #303, note 2). For a query `georef_tgn`
   writes to Getty TGN's SPARQL endpoint the query's words are only those
   of its quoted string (the place name searched) and its TGN ids, not the
   query's fixed text (`sources._query_words`; note 3), so a vocab.getty.edu
   refusal stays readable. For any other request every word of its
   parameters and path counts, a fixed one too (Wikidata's "json" and
   "en"), so a body that repeats one is withheld.

   **Getty TGN's search** goes through Getty's SPARQL endpoint
   (vocab.getty.edu, already approved for TGN) when the reconciliation
   service (services.getty.edu) answers 401 or 403, or times out, cannot be
   connected to or keeps failing with HTTP 5xx; on 2026-10-10 it answered
   every request from Cloud Run with 403. The search reads Getty's full-text
   index (`luc:term`) for the place name, ranks places with a term in the
   same words first, and reads the records of at most ten, so the candidates
   have the reconciliation path's shape, and the chain keeps its cap of
   three responses (`historical_gazetteers.MAX_CALLS`, `_tgn_search`). The
   evidence record lists the refused response with its HTTP status and no
   stored body, then the two stored SPARQL responses. The note starts with
   "Getty TGN's search refused the request (HTTP 403); searched Getty's
   SPARQL endpoint instead, whose search does not match accents or word
   stems." If the SPARQL endpoint fails too, the lookup is an outage as
   before.

   That index matches a name's words as written (the review of #303, note
   1; probed 2026-10-11): "Solola" finds a Somali Solola and a Solola Valley
   in North Carolina, not the Guatemalan city and department whose names
   end in an accented a, and "Chimaltenangos" finds nothing. So the answer
   of a search through it never claims the reconciliation service's
   certainty: one place it finds is ambiguous, not success, and its
   evidence names no deciding candidate (`sources._gazetteer`); the place
   rules of step 5 still take the one candidate at a field's level, as for
   any ambiguous answer. A search through it that finds no place is
   ambiguous too, never no match, its note ending "Getty TGN cannot settle
   '<name>': the SPARQL search found no place, which rules nothing out"
   (`historical_gazetteers.SPARQL_FOUND_NOTHING`), so it rules no reader's
   text out. A search with an accent-tolerant term (`luc:term "solola~"`)
   was probed and not added: it took 8.9 s against 0.5 s and returned 50
   places, the two Guatemalan ones 14th and 15th.

   **GEOLocate's answer that it found nothing.** A GEOLocate answer (HTTP
   200) that the parser cannot read is no match, not an outage, only when
   it says it found nothing: its count of results is 0 and it has no
   result set, or one with no features (`sources._geolocate_found_nothing`).
   Asked about a country it does not know ("Central America"), GEOLocate
   answers `{"numResults": 0}` with no result set; in the real run of
   2026-10-09 that answer was classed unreadable, an outage, and blocked
   105526329 for a retry. Any other answer that cannot be read is still
   unreadable, an outage: a body that is not GEOLocate's answer (an HTML
   page, a cut body), and an answer that reports a match the parser cannot
   read (a count above 0, or a feature of the wrong shape). So a reader's
   text GEOLocate found is never ruled out as no match under the readers'
   rule of step 5 (G20, G32; the review of #299, whose probe had readers
   "Yepocapa" and "Yepocapo" settle on an unreadable match for "Yepocapo";
   it now goes to review). Either is logged in one
   WARNING line ("Field research lookup unreadable") with the source, the
   host, the status it was read as and the error's class, never the query.
   An unreadable answer of GBIF (with Catalogue of Life and Global Names
   Verifier alongside), or an unreadable answer to any request of a Getty
   TGN, Wikidata or NGA lookup, stays an outage: a body that is not the
   source's answer or breaks its shape, not an answer about the query; a
   later attempt may read one. For the gazetteers' search requests these
   answers that report a hit the parser cannot read are unreadable too,
   never no match (the second review of #299: readers "Yepocapa" and
   "Yepocapo" settled on such a Getty TGN answer for "Yepocapo"; the field
   now goes to review): a Getty TGN reconciliation answer with a hit that
   is not an object, has an id other than `tgn/<digits>` or has no name,
   even beside hits that can be read (`georef_tgn.parse_reconcile`); an NGA
   name search with a row that has no integer feature id (`ufi`) or no
   termination field (`georef_nga.parse_search`; the feature read after it
   checks the same, `parse_features`); and a Wikidata search none of whose
   items can be read (`georef_wikidata.parse_search`). A TGN hit of
   another Getty vocabulary (AAT, ULAN, CONA or IA: a concept, a person, a
   work or a subject) is no place and is skipped, so an answer of such hits
   only is no match.

   **The later requests of a Getty TGN, Wikidata or NGA lookup** never
   answer no match: only the search request can. Once the search has found
   something, a later reply with no body, no row, or no row its parser can
   use makes the lookup malformed_response, an outage, stored as evidence
   with a note that names the reply ("Getty TGN found places but its record
   reply could not be read"; `historical_gazetteers._later`), so the
   readers' rule of step 5 never rules a reader's text out on it (the
   review of #299's probes S1 to S3). The later requests are Getty TGN's
   records and names (on the SPARQL path, its records), Wikidata's entities
   and the labels of the items they point to, and NGA's features and their
   first-order units. A row the parser cannot read makes the reply
   malformed even beside rows it can read, as for the search: a records row
   whose place is not a TGN id or a record with no name
   (`georef_tgn.parse_records`), a names row with no TGN place or no name
   (`parse_names`), an entity not filed under its own item id or with no
   label (`georef_wikidata.parse_entities`; for labels, an entity not filed
   under its own id, `parse_labels`), a current NGA feature with no name
   (`georef_nga.parse_features`) and a unit row with no first-order code
   (`parse_units`). What a source does not return at all is left out, as
   before: an id with no rows, a Wikidata item reported missing, a
   referenced item with no label, a unit with no name. A records,
   entities, labels, features or units reply that leaves out some of what
   was asked keeps the lookup ambiguous, as before ("requested TGN records
   were incomplete"); a names reply that leaves out a place leaves it its
   GVP name, as before; a reply that leaves out all of it is malformed, as
   above.

   **A county's Wikidata lookup reads its places' classes** (the owner's
   ruling below, "County: the country's second-level unit"). After the
   search, the entities and their labels, it reads the subclass-of (P279)
   statements of its places' instance-of (P31) classes, then of the
   classes those name, in at most two more requests of up to 50 classes
   each, each sent once and never retried (`sources.CLASS_READS`,
   `CLASS_READ_ATTEMPTS`, `ApprovedSources._levels`; a refused read was
   sent three times before Codex's review of 9f5319ca;
   `georef_wikidata.classes_params`, `parse_superclasses`,
   `unread_classes`, `levels_reached`). A chain ends at Wikidata's
   first-level (Q10864048) or second-level (Q12357832) administrative
   division; Q13220204, the second-level class's former id, redirects to
   Q12357832, and `wbgetentities` files the target under the id asked,
   which is read as that class. A place whose chains reach the second-level
   division and not the first-level one has "second-level administrative
   division" among its kinds (`sources._place`). One whose chains reach the
   first-level division, alone or with the second, has "first-level
   administrative division" among its kinds instead, and is at no county's
   level whatever its other kinds say (`agreement.at_level`; a place
   labelled "county" whose class reaches the first level settled County
   before Codex's review of 9f5319ca); a province stays at a province's
   level. Probed on 2026-10-12:
   Yepocapa's "municipality of Guatemala" reaches it in one read; Cook
   County's "county of Illinois", through "county of the United States",
   in two; the Philippines' "province of the Philippines" reaches the
   first-level division. A longer chain is not followed. Each response read
   is stored with the lookup's others, and one evidence record names them
   all. A read with no usable answer (a refusal, a body that is not the
   classes asked) ends the reading: the lookup stands on its other
   responses and no place gets a level from it. Only the county's lookup
   reads classes; its answer is cached apart from another field's answer
   to the same query, whose responses it shares.

   **A source that cannot be reached** (a lookup whose last attempt was rate
   limited, timed out, was refused or redirected, failed on the server or
   came back unreadable, as above; a refused query is not one) does not
   void the field when another of its expert's lookups answered. The
   expert's answer then stands and is checked under the rules of step 5
   like any other, and
   the field's reason ends by naming the source ("Getty TGN could not be
   reached; settled from Wikidata."). A place settles on a cited answer of
   any place source, so no Getty TGN answer is needed. Only when every
   lookup the expert made failed, at least one because its source could not
   be reached, does an unresolved answer leave the field for a retry
   (`source_unavailable`; see step 7). The place briefs tell the expert to
   decide with the sources that answered and to say which did not.
5. **Checked answers.** The expert's answer check (an answer that breaks it
   is sent back for correction) and, again, the step before a resolved answer
   becomes a value apply these rules (`field_research/agreement.py`, on the
   source answers the field received):
   - The literal appears exactly in each reading the answer names.
   - **A whole candidate.** The literal is one of the field's candidate
     literals, whole, for each reading the answer names, whichever reader
     that is: the organiser's candidates,
     and each keyed line the parser read ("taxon: Danaus plexippus") on each
     reading that writes the line. Literals are compared after NFC and
     whitespace collapse only, so "E. slope" and "E.slope" differ. An answer
     that takes a piece of a reading's candidate ("Danaus plexippus" where
     the candidate is "Danaus plexippus megalippe", "Sept. '46" where it is
     "3 Sept. '46", "San Pedro" where it is "San Pedro Sacatepequez") is
     refused. A candidate can itself be a piece of its reading, since the
     organiser's candidate need only lie inside its quote; for the taxon,
     the scientific-name parser reads the candidate's quote from the literal
     on, and, for a literal in which it reads no genus, with the word the
     quote writes immediately before the literal when that word may be a
     genus (`checks.longer_name`). A candidate whose quote writes a longer
     name there ("Danaus plexippus" quoting "Danaus plexippus megalippe",
     "sp. 1" quoting "Epipsocus sp. 1") never settles the taxon: it goes to
     review ("The label writes a longer scientific name than this value.").
     A keyed line's "taxon:", an author and year, a sex sign or "sp. 1" are
     no longer name. Other fields' candidates are not checked against their
     quotes. For a place field (country, province or state, county, city), a
     candidate or a reader's verbatim that names no place, nothing but unit
     words and punctuation by the place comparison key ("Prov.", "Co."), is
     no literal of the field (`agreement.names_no_place`): it is neither cut
     nor extended by an answer and is no reader's text in the agreement
     rules below. It still shows that its reading writes the field, for the
     parents check of step 5 (`step._place_texts`): a county or a city under
     a province written "Davao, Prov." settles only inside that province once
     it settles (NO_PROVINCE). And it still counts as text the organiser
     found for rule A's condition 5. The second rerun of 2026-10-18 had f35af3a5's
     organiser give the province "Prov.", cut from "Davao, Prov.": the
     answer "Davao, Prov." was refused as extending it and "Prov." as no
     place asked of it, so the field fell back; "Davao, Prov." now settles
     as text read from the transcript.
   - **Or text read from the transcript** (the coordinator's ruling of
     2026-10-09, after the real runs of that day: 105526328's collecting
     date "IV-24-48", which both readers of its label write and parse_date
     reads as 1948-04-24, could not settle because the organiser offered no
     candidate; nor could its collection method "trap", or 105526329's and
     105526330's precise location). When the literal is no whole candidate,
     it may be text the expert read in the readings itself
     (`agreement.literal_basis`, TRANSCRIPT): each reading the answer names
     writes it as a run of whole words within one line, or that whole line
     (`agreement.verbatim_runs`). Words are split at spaces, and after a
     comma or a semicolon that does not stand between two digits
     ("Yepocapa,4800 ft." is two words, "1,200 m" is not); a run starts and
     ends at a word's edge, or past any characters other than letters and
     digits at its edge, which may be left off: punctuation, quotes,
     brackets, a foot or minute mark or a "#" ("Yepocapa" of "Yepocapa,",
     "Mindanao" of "(Mindanao)", "46" of "'46", "6400" of "6400'", "2" of
     "#2"). It never starts or ends between two letters or digits of one
     word ("24-48" is no run of "IV-24-48", nor "30" of "Sp.30", nor "200 m"
     of "1,200 m"), and never crosses a line break. A unit left off is
     still refused where a written rule reads it (`extraction_refusal`:
     "6400" of "6400'" as metres). It may cut or extend no candidate of
     that reading ("Sept. '46" beside the candidate "3 Sept. '46", "San
     Pedro Sacatepequez" beside the candidate "San Pedro"): the answer is
     then refused as above.
     Precise location, the label's verbatim locality, is one of two exceptions
     (`agreement.ACROSS_LINES`; the coordinator's request of 2026-10-18,
     after the third rerun, where two of its experts fell back; the other
     exception, since lane H4, is the habitat, for a host's name written over
     two lines: "A host the label writes is the Habitat", below). Labels
     often write a locality over consecutive lines, and then its literal
     may run over them: a run of whole words over consecutive lines of
     each reading the answer names, starting at a word's edge on its first
     line and ending at one on its last, with no blank line
     (`agreement.runs_across_lines`, `agreement.written_runs`). Its value
     keeps the line breaks as the readings write them. An answer that
     gives a space for a line break (or a line break for a space) is read
     as the text every reading it names writes so (`agreement.across_lines`,
     in the expert's check and in the step): e98a924c's both readers write
     "CNHM. E Slope Mt." over "McKinley, Davao Prov.", and the answer "E
     Slope Mt. McKinley, Davao Prov." is their "E Slope Mt.\nMcKinley,
     Davao Prov.". Readers that break the lines at different words write no
     one text, and the answer is sent back. Such a literal may hold whole
     candidates, the organiser's lines of one locality joined in their order
     on the label (2b02009d's decided reading writes "Seliban Riv." over
     "Mt. Apo", given as two candidates), but it still cuts none: it is no
     piece of a candidate, and no place of a candidate in the reading lies
     partly inside it (`agreement._cut_candidate`). Nor does it extend one
     (round 1 of #379's review, finding 3): a line of it that holds a
     candidate holds no other letter or digit, only punctuation and spaces
     between its candidates, so "Seliban Riv." over "near Mt. Apo" beside
     the candidate "Mt. Apo" is refused, as "near Mt. Apo" on one line is. A
     line holding no candidate may join them. Those candidates are
     then parts of it, not rival texts of the label (`agreement.labels`). Every other check holds
     as on one line: it holds no date, elevation or range of them
     (`_holds_another_kind`), and every reading it names writes it. Every
     field but these two, the place fields among them, keeps its literal on
     one line. A date or an elevation so read is never one end
     of a range (`agreement._part_of_range`, PR #300's review and finding 1
     of its review of 6fd595b3b): where a reading it is read from writes
     it, the comma- or semicolon-separated part of the line holding it may
     write no range (`written.ranges`) unless the literal holds both its
     ends, the whole range ("The label writes this value as one end of a
     range."). That part's words are the line's words cut at its comma or
     semicolon, so the word the comma ends stays in it: "V-2-48" and
     "IV-24-48" of "IV-24-48 to V-2-48, Yepocapa" go to review (before the
     follow-up to the review of #305 that word was left out, and both ends
     settled). A range is two ends, each a word holding a digit, joined by
     a run of joiners: a dash of any form, standing as a word of its own,
     alone or in a run of any length ("1200 --- 1500 m"), or touching one
     end ("1200- 1500 m", "IV-24-48 -V-2-48"); a sign "&", "/" or "~"
     standing alone; or a word of `written.RANGE_WORDS`, compared with
     letter case and accents aside: English "to", "till", "until", "thru",
     "through", "and"; Spanish "a", "al", "hasta", "hasta el", "y";
     Portuguese "a", "ao", "ate" (with its acute accent), "e"; French "a"
     (with its grave accent), "au", "jusqu'a", "jusqu'au", "et"; German
     "bis", "bis zum", "und"; Italian "a", "al", "fino", "e"; Dutch "tot",
     "tot en met", "en", "t/m"; Latin "ad", "usque" (a run of them, such as
     "fino a", is one joiner; the later word of a joiner of several, "el",
     "zum" or "met", joins only right after another joiner's word,
     `written.CONTINUATIONS`). The dashes are every character of Unicode's
     dash punctuation category, which `written.PD_DASHES` pins by name
     (the same 26 in Unicode 14.0, 15.0 and 15.1: a hyphen, an en or em
     dash, a figure dash, the Armenian hyphen, the Hebrew maqaf, the two-
     and three-em dashes, a full-width hyphen, a wave dash and the others;
     a later Unicode's new dash is not added by reading the category), and
     the minus sign, the swung dash, the full-width tilde, the hyphen
     bullet and the tilde operator (`written.DASHES`). Up to four pieces
     (words, or dashes split from a word's edge) that may stand beside a
     number (`written.BESIDE_A_NUMBER`) may come between an end and the
     joiner, as the window of `written.BESIDE_WORDS` is five pieces and
     counts the end's own: a unit's words ("1200 m to 1500 m", "1200 m a.
     s. l. to 1500 m"), a month in English, Spanish, Portuguese, French,
     German, Italian or Dutch, a Roman numeral I to XII in capitals
     ("April 24 to May 2, 1948", "24 avril au 2 mai 1948"), or an
     approximate marker ("ca."); with a fifth ("1200 m a. s. l. ca. to 1500
     m") the first end is outside the window and the joiner joins no
     range. The two ends are written alike, of one kind (`written._kind`,
     `written._alike`; the review of #305, note 1): in one unit, or both
     dates (an end that writes letters, or has a month or a Roman month
     beside it or as the next word: "24 IV", "2 V 1948"), or both of
     another kind (`written.OTHER_UNITS`, written right after the end's
     number, glued to it or as the next word: a distance "km" or "mi", a
     count "ex." or "others", the male or female sign, an hour "h"), or a
     bare number beside any of these ("1200 to 1500 m", "24 al 30-IV-1948",
     "5 to 7 May 1948"). Ends in different units are one elevation written in both, no range
     ("4800 ft. / 1463 m": each settles its own unit's field); a unit
     beside a date is two fields ("Guatemala / 1200 m / 24.IV.1948"); and
     an elevation or a date beside a distance or a count is no range
     either, so "1500 m" of "1500 m - 5 km W of Coban" (with its accent),
     of "1500 m and 5 km W" or of "Berg 1200 m und 3 km N" settles, as
     does "24.IV.1948" of "24.IV.1948 en 2 ex." or "IV-24-48" of "IV-24-48
     and 2 others". A word of two numbers joined by a dash or a "/"
     ("1200-1500 m", "10-12") is one word, which no run cuts; its kind is
     read as an end's, from its unit or the word after it. A range in the
     clause, or such a word standing right before or after the literal,
     makes the literal part of a range only when it is written alike with
     the literal (`written.part_of_a_range`): "Sept. 1946" of "10-12
     Sept. 1946", "IV 1948" of "24/30 IV 1948" and "24.IV.1948" of
     "24.IV.1948 10-12" (a bare word of two numbers) go to review, while
     "24.IV.1948" of "24.IV.1948 10-12 h" (hours), "IV-24-48" of "IV-24-48
     1200-1500 m" or of "IV-24-48 1200 to 1500 m" (an elevation range) and
     "1200 m" of "1200 m 10-12 Sept. 1946" (a day range) settle. So "1500
     m" of "1200 bis 1500 m", "entre 1200 y 1500 msnm", "1200 - 1500 m"
     with an em dash, "1200- 1500 m" or "1200 m to 1500 m", "V-2-48" of
     "IV-24-48 au V-2-48", "2.V.1948" of "vom 24.IV.1948 bis zum 2.V.1948"
     and "May 2, 1948" of "April 24 to May 2, 1948" go to review; "1200 to
     1500 m" whole keeps the rules a candidate has. Every other rule
     applies to it as to a candidate: the readers' rules below, the place checks (the lookup of the label's own text, the
     level, the parents, the near spelling) and the doubtful genus. For the taxon, the
     reading's text from the line above the literal on stands in for a
     candidate's quote (`agreement._longer_written`, `checks.longer_name`),
     so "Danaus plexippus" on a line that writes "Danaus plexippus
     megalippe", or "sp. 1" below "Epipsocus", never settles it. A label's
     readers settle on it by step 5's rule, over the label's units (since WP
     1.8; until then, on a label whose old first pass preferred no reader,
     every reader had to write the text and its clause alike: 105526328's
     "Yepocapa, Mun.", which its other reader writes "Mum.", and 1A "trap"
     beside 1B "light trap"). A decided reading that
     writes the text beside another candidate of the organiser's for the
     field writes two texts and settles neither. Such a value is marked:
     the label rows field research writes for it cite the literal's first
     run of whole words and carry `"basis": "transcript"` in their stored
     records, an info finding
     `transcript_literal:<field>` beside the record cites them (it never
     routes the record), and one Logfire event, "field_research literal
     read from the transcript", names the field and the readings, never
     their text (`step._from_the_transcript`). A place settled so is
     written, for the parents check below, by each reading that writes its
     literal as whole words (`step._misfit`).
   - **Text another field holds** (the step only, `step._taken`). A
     literal read from the transcript never settles when the same text,
     overlapping in the same reading, is claimed for a field of another
     kind. Only a settled value claims text (round 2 of the production
     test, 2026-10-11): another field's value this attempt's answers
     settle, wherever its literal stands in the readings of the labels its
     answer names; or another field's value settled before this attempt or
     by a person (supported, in the verbatim or settled layer, or a
     person's value that is not derived: `step._claims_text`), in the
     readings of its labels. What this attempt settles is found by applying
     every answer once, before the guard, on a copy of the run
     (`step._first_pass`: no blob is written, no Logfire event is made, and
     the run is left as it was); the answers are then applied for real
     with the guard. An organiser candidate (or keyed line the parser read),
     an answer that settles nothing (refused, unsettled or failed) and a
     value no one settled claim no text: 105526328's collecting method
     "trap", read from the transcript, settles although the organiser
     offered "trap" as the habitat, whose expert found no habitat. (Before
     this, from PR #300's review, an organiser candidate claimed its text
     whatever its expert did. The case that review raised, the locality
     "Yepocapa, 4800ft." beside an elevation candidate "4800ft." whose
     expert failed, still goes to review, as text that plainly holds an
     elevation, below.) A settled value's literal claims only where it
     stands as whole tokens:
     each occurrence that neither starts nor ends between two letters or
     between two digits (`step._occurrences`; finding 2 of the review of
     6fd595b3b), so a collection code settled as "2" claims the "2" of "lot
     #2" but not the "2" of "IV-24-48", and the date read from the
     transcript settles; a code settled as "IV-24-48" still claims the
     date's whole text. The field
     goes to review with the reason "This text, read from the transcript,
     is also the value found for <field>." The kinds are
     `agreement.FIELD_KINDS`: the place fields (precise location among
     them) are one kind, so a town inside the locality is no conflict; the
     dates are one, the elevations one, collectors and determiner one; any
     other field is a kind of its own; and verbatim D/T/S shares text with
     any field; the museum has set no validation rule for it yet. So
     105526329's precise location "Yepocapa, 4800ft.", read from the
     transcript, goes to review beside the elevation "4800ft." (the brief
     leaves elevations out of the locality), while "Volcan Barva" beside
     "2000 msnm" settles. An organiser's candidate is never refused here
     (but for the one case below), and two fields that both settle the same text from the transcript
     (105526328's "trap" as the habitat and as the method) both go to
     review. A field whose answer is refused on its own does not claim:
     a date and a collection code that both read "IV-24-48" settle the
     date, since the code holds a date (below) and settles nothing, and
     the code goes to review as text the date holds.
     One overlap goes the other way (the live rerun on 616ae010 of
     2026-10-18): a place read from the transcript whose text another
     field's value, settled in the same attempt, overlaps only partly (at
     each overlap neither text holds the other: `step._partly`) settles,
     and that other field goes to review, whether its answer gave a
     candidate or text read from the transcript, with a reason of its own
     naming the place: "This text runs into the value found for <field>."
     (`step.RUNS_INTO`; until round 1 of #380's review it was given the
     reason above, which says its text was read from the transcript and is
     the place's value, neither of which need be true). A label line often
     begins with another field's text and runs on into the locality. Then
     the place's expert leaves that text
     out, while the other field's answer runs on into the locality's words.
     e98a924c's label 2 begins "CNHM. E Slope Mt." over "McKinley, Davao
     Prov.". The organiser filed the whole first line as the collection
     code, whose expert kept it, and the precise location's expert read
     "E Slope Mt." / "McKinley, Davao Prov.". The locality went to review
     until then; now it settles, and the collection code, which holds the
     locality's words (its brief says a place is no code), goes to review.
     A place that holds another field's whole text ("CNHM. E Slope Mt." /
     "McKinley, Davao Prov." beside the code "CNHM."), or lies wholly
     inside it, still goes to review, as does one beside a value settled
     before this attempt or by a person, which is not researched again.
   - **Text plainly of another kind** (the answer check and the step,
     `agreement._holds_another_kind`; finding 2 of the review of
     6fd595b3b). A place field (country, province or state, county, city,
     precise location) or the collection code read from the transcript
     never holds text that is plainly another kind of field's, whether or
     not any field claims it (`written.other_kind`): an elevation, a number
     with an elevation unit after it or before it ("4800ft.", "m 1200"; the
     units below), unless the words after its unit, in its own clause, make
     it a distance (`written._distance`; the review of #305, notes 2 and 5):
     a compass point ("500 m N of the church", "Yepocapa, 500 m N") that no
     word of a mountain's side follows (`written.ASPECTS`: "1500 m N slope"
     and, with its accent, "Volcan Barva 2600 m S ladera" are elevations);
     or a word of `written.RELATIONS` ("of", "from", "de", "von", "al" and
     the like; "along", "above", "below", "past", "beyond", "before",
     "after", "upstream", "downstream", "inland"; Spanish "arriba",
     "abajo", Portuguese "acima", "abaixo", German "oberhalb",
     "unterhalb": "500 m along road to Coban", "Rio Negro, 200 m upstream
     of ford", "100 m above the bridge" are locality text) with a word
     after it in its clause, the place it is measured from (only "inland",
     "upstream" and "downstream" may stand alone: "Rio Negro, 500 m
     upstream"; "Finca Moca, 1500 m above" holds an elevation), and no word
     of sea level or altitude within three words after it
     (`written.ELEVATION_WORDS`: "1500 m above sea level", "1500 m de
     altitud", "900 m acima do nivel do mar" with its accent are
     elevations). A word that is also a joiner, before a number, makes no
     distance ("Serra, 1200 m e 2 ex." holds an elevation: Portuguese "e"
     is "and", not east; Codex's review of 77fdaeba). A comma or a
     semicolon after the unit ends its clause,
     so "Finca Moca, 1500 m, N slope" holds an elevation, and a heading
     right before the number (`written.HEADINGS`: "alt.", "elev.", "Hohe"
     with its umlaut, "cota", and "el." with its period) makes it an
     elevation whatever follows ("Finca Moca, alt. 1500 m E side"). A
     number with no unit is an elevation here too when a heading stands
     right before it ("Coban, alt. 1200", "Finca Moca, elev. 1200",
     "Coban, alt. 1800", which was read as a year before) or a capital "M"
     that may be a person's initial follows it ("Trap 4800 M. Smith"),
     though it settles no elevation field (below). A capital "M" alone
     before a number is no unit, so "M 12" and "M. 12" settle as a code;
     in a place field's text it may still be metres, and the place is
     refused ("Alpi Apuane, M 1200"). Nor is a capital "M" a unit in a
     count of males and females ("Finca Moca, 3 M. 2 F." settles), also
     with a joiner word between or a sex word ("Finca Moca, 3 M. and 5
     females" and "Finca Moca, 5 females y 3 M." settle; Codex's review of
     77fdaeba).
     A date: any run of up to five whole words the date parser reads as a
     date or as several, with Roman months read and no century rule
     ("IV-24-48", "24.VI.1952", "24 Apr 1948", a year from 1750 on such as
     "1948"; a slide code is none); in a place field's text, not the
     collection code's, a run that starts right after a road, km, hill,
     farm or estate word (`written.PLACE_WORDS`, by language), with no
     comma or semicolon between them and no period after a whole word
     (closing quotes or brackets aside), is part of the place when it is a
     bare number or a month and a day with no year (`written._a_place_number`:
     "Hill 1800", "FM 1960, Harris Co.", "BR-116 km 1850", "Hwy I-5",
     "Calle 5 de Mayo", and after an abbreviation's period,
     `written.PLACE_ABBREVIATIONS`, "Hwy. 1960" or "km. 1850"; "Ruta,
     1960", "Hill; 1800", "Fazenda, 1948", "Route, IV-1948", "Fazenda.
     1948", "Ruta. 1960", '"Fazenda." 1948', "Hwy. 24.IV.1948" and "Route
     IV-1948" hold a date: Codex's reviews of 77fdaeba, b9f42db6 and
     1b997582), unless initials or a collector's or
     determiner's mark stand before that word, which makes it a surname
     (`written.PERSON_MARKS`: "J. Hill 1948", "leg. Berg 1948" hold a
     date); a date with any other word before it still holds one ("Finca
     Moca 1948" may be the farm and the year collected; "Route 66 1948",
     "May 5 Camp", and the codes "FM 1960", "X-12" and "IV-1948" are
     refused as before). Or a range of dates or
     elevations (`written.ranges` with a unit, a month, a Roman month or
     letters at an end: "24 IV a 2 V"; a range of bare numbers, "km 12 a
     15", or of distances, "2 to 5 km N", is none). Such an answer is
     sent back, telling the expert to leave that text out, and the step
     sends the field to review ("This text holds an elevation, which is
     another field's.", "...holds a date...", "...holds a range of dates or
     elevations..."). So with no elevation candidate and the elevation's
     expert failing, "Yepocapa, 4800ft." no longer settles as the locality
     while "Yepocapa" does, and with no date candidate "IV-24-48" no longer
     settles as the collection code; "Volcan Barva" beside "2000 msnm"
     still settles. An organiser's candidate is not checked here.
   - **The elevation's unit** (the answer check and the step,
     `agreement._unit_refusal`, for an organiser's candidate and for text
     read from the transcript alike; finding 5 of the review of 6fd595b3b,
     pre-existing on main: "1500 m" from "alt. 1500 m" settled
     elevation_from_ft as 1500). Each elevation field holds the unit
     `application.derivations.UNITS` gives it (metres for elevation_from_m
     and elevation_to_m, feet for elevation_from_ft and elevation_to_ft).
     Wherever a reading the answer names (its label's decided reading, on a
     label with one) writes the literal as whole numbers, the unit of each
     of the literal's numbers is read on that line (`written.units_of`,
     `written.numbers`): the unit written right after the number, glued or
     after spaces, in any spelling of `written.ELEVATION_UNITS` (metres "m",
     "mts", "metres", "meters", "metros", "metri", "msnm", "msm", "m.s.n.m.",
     "m a.s.l.", "masl", "msl", "m s.l.m.", "m u. M." with its umlaut, "m
     NN", "m alt."; feet "ft", "feet", "foot", a foot mark straight, curly
     or a prime, "pies", "p.s.n.m.", "pes" with its accent, "Fuss" with or
     without its sharp s, "pieds", "piedi", "voet"; letter case, accents,
     periods and the spaces inside a unit aside), or right before it as
     Italian labels write it ("m 1200", never a capital "M" alone: "M
     1200" and "M. 1200" are a code's letter or a person's initial); or,
     for an end of a range that writes none, the other end's unit ("1200"
     of "1200 to 1500 m" or of "1200-1500 m"). "mt" may be Mount and is no
     unit, nor is "mm", and a foot mark after a degree sign is a minute of
     arc. A capital "M" alone after a number is no unit when a person's
     name or initial follows it, in capitals too ("1200" of "lot 1200 M.
     Smith" or "lot 1200 M. SMITH" and "4800" of "Trap 4800 M. Smith" have
     none; before the review of #305's follow-up the first settled
     elevation_from_m, and before Codex's review of 77fdaeba the second)
     or when it counts males beside a count of another sex ("3 M. 2 F.",
     "3 M. and 5 females"); "ALT. 1500 M" is still metres. A number the
     reading writes as a distance, by the rule for place text above
     (`written.written_as_a_distance`: "1200 m" of "Finca Moca, 1200 m
     along road", "300 m" of "Rio Negro, 300 m arriba del puente", "500 m"
     of "Yepocapa, 500 m E of the bridge", "1500 ft" of "Trail, 1500 ft
     past the bridge"), settles no elevation field ("The label writes this
     number as a distance, not an elevation."; on main before this PR and
     at 77fdaeba each settled); "1500 m" of "Finca Moca, 1500 m above sea
     level", "Finca Moca, 1500 m above" or "Finca Moca, 1500 m, N slope"
     still settles. When any of those
     units is the other unit the answer is refused ("The label writes this
     elevation in the other unit.": "1500 m" or "1500" of "alt. 1500 m" as
     feet, "6400'" or "6400 pies" as metres, "4800 ft. (1463 m)" as either);
     when the reading writes none of its numbers with a unit, it is refused
     too ("The label writes no elevation unit with this number.": "1500" of
     "Elev. 1500", "1200 mt"), as a unit is never guessed (G41). Sent back,
     the expert's brief has it answer label_lacks_value when the label
     states the elevation only in the other unit, and the derivations
     below then convert the settled one; refused at the step, the
     field goes to review, and no elevation is derived while one is
     unresolved (`derive._elevations`). The answer check's written rule
     (`extraction_refusal`, a unit after a bare number) still applies
     before this one. The experts' shared brief renders its range and
     elevation-unit lines from the tables these rules read
     (`written.range_line`, `written.unit_line`, folded to ASCII), as it
     renders the place notations.
   - **A doubtful genus (taxon only).** The literal never settles the taxon
     when the label marks its genus as doubtful (`checks.genus_in_doubt`,
     through `agreement._genus_in_doubt`): wherever the quote of a candidate
     of that literal, the text of a reading the answer names, or, unless
     the answer names the label's decided transcript (its readers' one
     text, or a person's), the text of any of its readers writes the
     literal (every reader is then the label's text: 1A's "cf. Epipsocus
     sp. 1" holds back an answer that names only 1B's "Epipsocus sp. 1"):
     - a qualifier of the doubt signs' list (below, under B), in any case
       except "vic", with or without its periods, stands in the
       whitespace-separated part holding the literal's first word
       ("cfr.Epipsocus"), in the part just before it on its line ("cfr.
       Epipsocus", "nr. Epipsocus", "NR Epipsocus", "C.F Epipsocus"), or
       alone on the line above, the only part of that line ("cf." on a
       line of its own above "Epipsocus sp. 1"). A person's initials with
       the final period ("C.F.") are none. The doubt signs' other
       exceptions under B (a nature reserve's "NR", "Nr." before a number,
       "conf." before a person, initials without the final period, a
       settled place beside "near", "nr." or "vic.") do not apply here; or
     - a question mark ("?", the full-width one, U+FF1F, or the inverted
       one, U+00BF: `checks.QUESTION_MARKS`) is on that word itself ("Epipsocus?",
       "?Epipsocus", "Epipsocus(?)"), or stands alone, a part with no letter
       or digit, just before or just after it on its line ("? Epipsocus",
       "(?) Epipsocus", "Epipsocus ?", "Epipsocus ? sp. 1", "Epipsocus
       (?)").

     A question mark on or beside another word ("Davao? Epipsocus",
     "Epipsocus sp. 1 ?"), any on the line above ("1946?" above "Epipsocus
     sp. 1") or below ("?" under "Epipsocus"), a qualifier that ends a
     longer line above ("Sabah, Danum Valley NR" or "Mindanao, Davao vic."
     above "Epipsocus sp. 1": it belongs to that line; N2 of #289's sixth
     review), and a qualifier after the genus ("Epipsocus cf. sp. 1", G25)
     are none. The value goes to review ("The label marks this
     name's genus as doubtful."): GBIF may decide the bare genus the taxon
     brief has the expert look up, and an expert that then resolves the
     taxon as that genus ("Epipsocus" quoting "cfr. Epipsocus", or quoting
     "Epipsocus" on a reading line that writes "Epipsocus?") is refused.
   - A value that differs from the literal is a source candidate the expert
     was given, or a deterministic check's settled parse of that literal (an
     ambiguous check's readings are only options for a person). An elevation
     candidate that writes more than its number ("ca. 1200 m", "300-450 m")
     is the literal, and a number the elevation check returned for exactly
     that literal is the value (the briefs name which end).
   - **No reader is preferred (owner, 2026-10-25; WP 1.8).** The first pass
     names no reading (the units path, since WP 1.8 the only one:
     `docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md`),
     and a label's decided transcript (`input_source` decided_transcript on
     the wire) is its readers' one text when they all agree, or a person's.
     The owner's words: "I wouldn't call it as evidence. It's
     raw transcription per model that can be leveraged if harness wants to
     think of possibilities LLM may have missed on its interpretation.
     Evidence is settlement which can be actual match from the lookups raw
     transcription itself being very clear and so on. It's a fine
     distinction"; "There an LLM opinion that's put in front along with
     actual Raw transcription per model to the harness if needed as then
     harness does its thing per field and settles as written or derived and
     so on"; "Harness can decide as it goes out and learns more than what the
     raw transcriptions are capable of"; asked "Should the harness be free to
     settle a field on any model's raw transcription when evidence supports
     it, even if the LLM pass picked a different one?": "This is exactly what
     should have been happening"; "Not just transcription the harness when
     it goes and does lookups will settle it. As matches could be close to
     raw but not exact. Or it might be something else in context and
     corroborated with other fields etc. so many possibilities". Every rule
     here reads the readings the answer names, whichever reader wrote them. Each expert's request carries each label's reading units,
     with the text the image shows at each unit where the first pass named
     one (`Reading.units`), and the labels whose transcript a person decided
     (`person_decided`). Another reader's text is a possibility, or raw
     transcription; evidence is what settles a field. The old first pass,
     which preferred a reader as advice to the experts, its request key
     `first_pass` and its findings were removed in WP 1.8.
   - **Readers and labels that disagree (G20, G27, G32).** Whatever state the
     organiser gave the field, each label that writes it settles on its own
     (`agreement.labels`), by the settlement rule of the spec's section 4
     (`agreement.labels_by_rule`). A label whose transcript a person decided
     (`Transcript.actor`) settles on the person's text, cleared, with no
     other reader's text overriding it, not even on a source's exact match,
     because the person saw the image (the coordinator's ruling of
     2026-10-25; lookups still work on the person's text; an answer naming
     another reader of such a label is sent back naming the person's
     reading, `PERSON_DECIDED`). Any other label's candidates are its
     readers' texts for the field, grouped letter case and spacing aside
     (the coordinator's ruling of 2026-10-09: texts compare after NFC,
     casefolding and removing every space and line break,
     `agreement.agreement_key`, so "shrubs" and "Shrubs", "sp. 30" and
     "Sp.30", "Mt." and "MT." agree, while "Mun." and "Mum." or "1200 m"
     and "1200 m." do not). A candidate is backed by the image (IMAGE: the
     first pass's units name its text), by the field's approved sources
     (SOURCE) or by readers that agree on it, on this label or another
     (TEXT). A source backs a text when the expert asked the field's
     approved sources about every distinct text the label's readers write,
     exactly one is confirmed by an answer about it, and every other has a
     captured no_match answer about it and no success or ambiguous one.
     An error, a timeout or a text
     never asked about is not a no-match; a later gazetteer reply that step
     4 says is still read as no match is one. For a place field, a text its
     gazetteers found only as another kind of place than the field's counts
     as found by none too (`agreement.found_only_elsewhere`; the batch
     rerun of 2026-10-17, where 48a71d53's and cb903c0e's province went to
     review beside "Mindanao,", an island): every Getty TGN, Wikidata or NGA
     success or ambiguous answer about it lists candidates, those of two or
     more of these gazetteers hold one of its name (one answer's list may be
     cut short: Wikidata's holds at most seven), each of those has a kind,
     and none of that name or one letter from it is at the field's level.
     GEOLocate's answers count
     only for a city, where any candidate keeps the text; an abbreviated
     text ("Ill.") never counts so, as it may stand for a name no source was
     asked. For a place field (country,
     province or state, county, city) such a label also settles when every
     text its readers write is confirmed and one authority_id confirms them
     all: the readers name that place ("Yepocapa," and "Yepocapa", both
     confirmed by one GEOLocate answer as the same town). That rests on the
     source's evidence, and each reader's text must match the candidate's
     name by the place comparison key (case, accents, punctuation, unit
     words), so texts that differ in those settle together ("Yepocapa," and
     "Yepocapa", "Chimaltenango Dept." and "Chimaltenango"); readers confirmed as
     different places, or not all confirmed, still go to review, and every
     other field keeps the one-confirmed rule. The answer then gives one
     reader's text as its literal with that authority_id and cites the
     answer that confirms it, and each reader's text stays in the value's
     lineage. Another label of the specimen backs a text (TEXT) when two or
     more of its readers agree on it (`agreement.MIN_BACKING_READERS`: a
     label one reader read backs nothing). Exactly one backed candidate settles the label: cleared
     with an IMAGE or a SOURCE backing, else marked for a person
     (`text_only`); among rival backed candidates the best backed settles,
     marked (`conflict`), and when none of them has an IMAGE or a SOURCE
     backing, or two rank first alike, the label does not settle and their
     texts are a person's options. For each label that settles, the step
     records a finding, rule `field_settlement`: an info finding
     `cleared:<field>:<label>`, or a warning `marked:<field>:<label>:<why>`
     whose code is one of the run's reasons too (`step._settlement`,
     `step.marked_reasons`). The old first pass's findings
     (`first_pass_<followed|overridden|absent|conflict>`) were removed in
     WP 1.8. An answer confirms a text as
     GBIF's decided candidate for the whole name it writes (a success
     answer), as the one candidate at a place field's level when it has that
     name (a success or ambiguous answer; see Places), or, for precise
     location, as a success answer's candidate of that name. A place text
     written as an abbreviation is also confirmed as the one candidate at
     the field's level of an answer asked an expansion its letters fit
     (P4 below, the rule a value settles on such an expansion by), whatever
     that candidate's name: 3781e440's reader 2B writes "USA: Ill. Coles
     Co." and 2A "U.S.B.I.L.: Coles Co.,", and Wikidata's answers for
     "United States of America" and "Illinois" confirm 2B's "USA" and
     "Ill." (the third rerun of 2026-10-18; until then only a candidate of
     the text's own name did, and the state went to review, `DIFFER`).
     Initials so confirmed still settle only with another place inside them
     (Initials, below). An answer that cites only the lookup of "USA" itself,
     whose one nation is "United States", is sent back to cite the answer
     asked the expansion. A place source
     was asked about a text when the text is the query's first
     comma-separated part: the only name a gazetteer searches (the part
     before the first comma) and the place GEOLocate looks for. The rest of
     the query is larger units, so "San Pedro, Sacatepequez" asks about
     "San Pedro", never about "San Pedro Sacatepequez". A place query or
     candidate name is compared
     with a reader's text by the place tool's comparison key
     (`application/georef_locality.py` `comparison_key`: casefolded, accents
     and marks dropped, anything but letters and digits a single space, "Mt."
     read as "mount", unit words such as "Prov." or "Dept." dropped), so
     "Yepocapa," and "chimaltenango," were asked about by the queries
     "Yepocapa" and "Chimaltenango"; the literal itself stays as written, and
     a near spelling is never the same name here, with one exception: when
     the sources confirm none of a label's texts by its own name, a place
     text one letter from the one candidate at the field's level of an answer
     asked that candidate's name is confirmed (`agreement._by_source`,
     identities' `near`; the one-letter bound of G34 is unchanged), every
     other text still ruled out. The field settles
     when every label settles on the same literal, which is then the answer's literal
     (citing the confirming answer when a source settled a label), or, for
     labels (or a place's readers, above) that settle on different literals,
     when a source confirms each of those literals as the answer's
     authority_id (the same place ID or GBIF usage), the answer's literal is
     one of them and it cites the answer confirming it. Anything else goes
     to review, with each reader's candidate row still cited. So a field with no approved source (collectors,
     habitat, collection method, collection code, verbatim D/T/S), or only
     deterministic checks, settles a label whose readers differ on the text
     the image names (cleared) or on the one text readers or another label
     back (marked), rival backings as above. This
     follows the native harness's G20 and G32 rules
     (`research_harness/evidence.py`); it is stricter than
     `application/field_resolution.py`, which clears readers that differ when
     every success names one value, unless they are a place's readers whose
     texts one candidate confirms (above).
   - **Places.** A place field (country, province or state, county, city)
     settles only on a cited success or ambiguous answer of a place source
     with exactly one candidate at the field's level, and that candidate is
     the value, with its authority_id; with none or several at the level the
     field goes to review. The levels are by each source's kinds, kept in
     `agreement.PLACE_LEVELS`: Getty TGN's place types ("nations"; "first
     level subdivisions (political entities)"; "second level subdivisions
     (political entities)" or "counties"; "inhabited places", "cities",
     "towns" or "villages"), Wikidata's instance-of labels ("country",
     "sovereign state"; "province", "former province", "department", "state";
     "county", "second-level administrative division"; "city", "town",
     "village", "human settlement", "municipality", each also as "... of
     ..."), NGA's feature codes ("A.PCL..."; "A.ADM1"; "A.ADM2"; "P....").
     A county's or a province's Wikidata lookup (`sources.LEVEL_FIELDS`)
     names "second-level administrative division" among a place's kinds
     when its classes reach that class, and "first-level administrative
     division" when they reach that one (step 4), so Wikidata's municipio
     Yepocapa, "municipality of Guatemala", is at a city's level and, for a
     county, at a county's level too, and Bahia, "federative unit of
     Brazil", is at a province's level for a province (until the second
     rerun of 2026-10-18 only a county's lookup read the classes, and
     19f0f1f6's province "Bahia" fell back). GEOLocate settles only a
     city, with all its candidates at a city's level: for a country, a
     province or state, or a county its candidate is a part of the query
     itself (its country, its state or county part, or else its place part),
     which it only repeats, so it confirms nothing there (asked "Yepocapa,
     Chimaltenango, Guatemala" for a province
     "Yepocapa", its candidate is "Chimaltenango", a province inferred from a
     locality). The country and county experts therefore do not have
     GEOLocate among their tools, only Getty TGN, Wikidata and NGA
     (`contracts.GAZETTEERS`; in the real runs of 2026-10-09 all 22 of the
     county experts' GEOLocate lookups were refused before they were sent,
     and the country experts spent 51 lookups on it). So TGN's ambiguous
     answer for "Philippine Islands" (a ridge, the nation, a Dutch village, a
     sea, an island group) settles the country "P.I." as Philippines (on the
     abbreviation rule below, when another place of the label lies in the
     Philippines), and its answer for "Chimaltenango"
     (the department and its town) settles the province as the department
     and a city only as the town. Precise location stays the verbatim text.
   - **The label's own text (P3).** The answer that decides a place value
     was asked the label's own text: the query's first comma-separated part,
     the name the source searches, has the literal's comparison key (as
     above, case, accents, punctuation and notations such as "Prov." aside).
     For GEOLocate that part is the city it settles. There are two
     exceptions. An abbreviation (P4): when the literal is written as an
     abbreviation, the query's first part may be an expansion its letters
     fit ("Philippine Islands" for "P.I.", "New South Wales" for "N.S.W.",
     "Guatemala" for "Guat."). No table lists abbreviations: one letter
     rule decides, for any place field and any language
     (`field_research/abbreviations.py`, `fit`; the owner, 2026-10-09: "make
     resolving and lasting changes that can handle big variance especially
     as specimens can be anywhere not just insect parasites"):
     - The literal is written as an abbreviation: it has a period, or its
       letters are all capitals and at most four ("NSW", "UK"), or one of
       its groups is one of the forms written without a period in
       `abbreviations.PERIOD_FREE` (Mt, Mts, Mtn, Mtns, St, Ste, Sta, Sto,
       Ft, Pt, Co, Is: "Mt Apo", "Falkland Is"). "Lima" is none, so
       "Limassol" asked for it settles nothing.
     - The expansion has more letters than the literal.
     - The literal splits into letter groups at periods, spaces and
       hyphens, and the expansion into words at the same. Letters and
       digits compare casefolded with accents dropped ("GUAT." fits
       "Guatemala", and "Mex." written with an acute accent on the e fits
       "Mexico"); any other character is left out.
     - The groups map in order onto consecutive words of the expansion,
       which may skip only its minor words (of, the, and, de, del, la, le,
       da, do, dos, das, van, von, y, et: "Edo. Mex." fits "Estado de
       Mexico"). Every group maps onto one word, and every word left over is
       minor, so "Mex." does not fit "Mexico City", nor "P.I." "Peru" or
       "Philippines".
     - Each group is its word written in full, or one of the two forms an
       abbreviation takes, with at most 60% of the word's letters
       (`abbreviations._form`, `MAX_SHARE`): a truncation, the word's first
       letters ("Guat" for "Guatemala", "Prov" for "Province", "Ill" for
       "Illinois", "P" for "Philippine"), or a contraction, the word's first
       and last letters with letters of the word between them in order
       ("Sta" for "Santa", "Ft" for "Fort", "Mts" for "Mountains", "Dpto"
       for "Departamento", "Qld" for "Queensland", "Edo" for "Estado").
       "Ill." does not fit "Iowa", nor "Mts." "Mount". A name with a letter
       or two dropped is no abbreviation, period or not: "Chimaltenago."
       (12 of 13 letters), "Chimaltango.", "Guatmala.", "Mindano." and
       "Philipines." fit nothing, and each is a near spelling (below) or
       nothing, as without the period.
     - At least one group is a truncation or a contraction: "Rio Janeiro."
       does not fit "Rio de Janeiro".
     - A literal of four capitals or fewer with no period ("UK", "USA",
       "NSW", "MALI") is read only as initials, one letter for each word of
       an expansion of two or more words: "UK" fits "United Kingdom", never
       "Ukraine"; "MALI" fits no "Malawi" and "IRAN" no "Ireland"; one
       capital alone fits nothing.

     An expansion may write out a unit word the label abbreviates after or
     before the name ("Davao Province" for "Davao, Prov.", "Cook County" for
     "Cook Co.", "Estado de Mexico" for "Edo. de Mexico", "Departamento
     Cusco" for "Dpto. Cusco"). A query that fits is taken as an expansion
     even when it also has the literal's comparison key, as a unit word
     written out does ("Davao Province" and "Davao, Prov." are both
     "davao"), so it gets the row and the rival check below; the literal
     asked as written ("Davao Prov."), or the name before its comma
     ("Davao"), is the label's own text. The province and county briefs
     have the expert search with the unit word written out. In the parent
     session's run of the pilots on 2026-10-09, Getty TGN's answer for
     "Davao, Philippines" held two first-level units (Davao del Norte and
     the special city of Davao), which settles nothing, and Wikidata's
     answer for "Davao Province, Philippines" held one, the former province
     of Davao.

     The letters only allow an expansion; they do not choose one ("S.A."
     fits "South Australia", "South Africa" and "Saudi Arabia", and a short
     word with a trailing period reads as a truncation, so "Lima." fits
     "Limassol"). Everything
     else above still holds: the cited answer has exactly one candidate at
     the field's level, and the place must fit the label's other place
     fields (below). Two more checks stand behind the letters:
     - **A rival** (`agreement.rival_expansion`, in the expert's check and
       in the step). The field settles nothing and is ambiguous, for review
       ("The sources found different places for the label's
       abbreviation."), when one of the field's place sources (a success or
       ambiguous answer, its evidence stored) was asked another name than
       the settling expansion (compared folded: case, accents and
       punctuation aside) and found another place at the field's level:
       another expansion the literal fits, with any candidate at the level
       that is another place; or the label's own text, with exactly one
       candidate at the level, another place. Another place has another
       record and another name: the same nation in two gazetteers (TGN's
       and Wikidata's Philippines) is one place. So "S.A." looked up as
       "South Africa" and as "Saudi Arabia", two nations, leaves the country
       ambiguous, as does "Ga." looked up as "Georgia" when its own text was
       found as one other nation; "South Australia", a state, is no rival
       for a country, and an own text found as several nations, or as none,
       is none either.
     - **Initials** (`abbreviations.initialism`: every group one letter or
       a minor word, as "P.I.", "S.A.", "N.S.W.", "B.C.", "UK"). The letters
       of initials allow many places ("P.I." fits "Philippine Islands",
       "Pacific Islands" and "Pitcairn Islands"), so a place settled on
       initials stays settled only when a place field below it, settled in
       the same attempt on its own evidence (anything but initials), lies
       inside it: that field's settling candidate names it among its
       parents, by record, or by its text, value or expansion
       (`step._corroborate`, once every place is in, from the city up).
       Or else when another place the label writes below it (the
       organiser's text for a province, county, city or precise location)
       lies inside it by the attempt's answers about that text: among the
       Getty TGN, Wikidata and NGA answers about it, those of two or more
       of these gazetteers hold candidates of its name that name a parent
       (one answer's list may be cut short: Wikidata's holds at most
       seven), and every such candidate in those answers lies inside it
       (`step._placed_inside`; a candidate that names no parent, a ship or
       a film, is left aside, and GEOLocate's parents come from the query,
       so its answers count for nothing). The value then also cites those
       answers and its reason ends 'The initials "P.I." read as "Philippine
       Islands" because the label's "Mt. Apo" lies inside it: each place of
       that name that the Wikidata and NGA GEOnet Names Server answers
       about it put somewhere is there.' (2b02009d, whose only places below
       "P.I." were the island "Mindanao", which NGA also holds as villages
       in Honduras and Guatemala, and "Mt. Apo", each of whose namesakes
       with a parent in the Wikidata and NGA answers is in the
       Philippines.)
       Otherwise the field is ambiguous, for review, with a reason naming
       the initials ('The initials "P.I." fit "Philippine Islands", but no
       other place on the label was found inside it, so the initials alone
       do not decide.'), and the rows its settling wrote are dropped. Only
       the step checks this. So "Mindanao, P.I." keeps the Philippines when
       its province "Davao, Prov." settles on Wikidata's former province of
       Davao, whose parent is the Philippines; with no other place on the
       label, with a province that settles outside the Philippines, or with
       a province written as initials itself ("D.P."), it goes to review. A
       city is the lowest place field, so a city on initials always does.
       Truncations and contractions need no such place.

     When the value
     settles, the step writes one evidence row of kind "rule" (locator
     `abbreviation:<field>:<expansion>`, no stored record, so it is never
     projected) naming the abbreviation, the expansion, the source asked
     and how the letters fit (`country: "P.I." abbreviates "Philippine
     Islands", the name tgn was asked: its letters fit the words in order
     (P = Philippine, I = Islands; field_research.abbreviations)`), and the
     value cites it as support. The shared brief has the expert look up an
     abbreviation's expansion, with each abbreviated word written out, when
     it knows what it stands for, and name the abbreviation it expanded in
     its explanation. A near spelling: the
     query is the chosen candidate's own
     name, and that name is one letter from the literal
     (`georef_locality.one_letter_apart`: both full names, their comparison
     keys one insertion, deletion or substitution apart). That is the
     one-letter half of G34; the value settles only when the rest of G34
     holds too (below), and the step then records a `near_spelling:<field>`
     warning finding beside the record, naming the deciding answer, which
     never routes it. Any other lookup settles nothing, for decided and contested labels
     alike, in the expert's check and in the step: "Escuintla" asked for a
     label's "Chimaltenago", "Philippines" for "P.I." (a lookup of the modern
     name is context only), a name the literal's letters do not spell
     ("Peru" for "P.I."), or a name two letters away ("Chimaltenango" for
     "Chimaltango", with or without a period after it). So "P.I." settles
     its country on Getty TGN's answer to "Philippine Islands", whose one
     nation is the Philippines, when another place on its label lies in the
     Philippines, as 105526326's province "Davao, Prov." does; TGN and NGA
     have no match for "P.I." itself (the coordinator's lookup of
     2026-10-09).
   - **The label's other place fields (B3, N1).** A place below the
     country settles only when its source names, among the places it lies
     in, the country (and province) settled from the reading the answer
     names. This is a check by name and by record on those readings, not
     proof that the place lies inside the label's country and province
     (limits below). Only the step checks this (the brief tells
     the expert): it does so once every field's
     outcome is in, the country first, then the province, county and city,
     since the experts run at once and the country must be known
     (`step._misfit`, `agreement.parents_refusal`). Each source names the
     places a candidate lies in (`SourceCandidate.parents`): Getty TGN and
     Wikidata name each parent by its own record, so TGN's "Pilipinas" is
     the record tgn:1000135 it calls "Philippines" when searched; NGA names a
     first-order unit and a two-letter country code ("GT"), which a
     country's name does not match but its record's ISO code may (the
     country code paragraph below); a GEOLocate match lies in its admin unit (the
     first-level unit outside the USA, the county inside it), the queried
     state inside the USA, and the queried country, the only one GEOLocate
     searches. For each reading the answer names (its label's decided
     reading, on a label with one), another place field is written by the
     reading when the reading has text for it, and settled for it when its
     value is supported, the step has done with it, and the reading writes
     its literal (compared as place names). A parent is that field when it
     is the field's settled record (its authority_id), or when its name has
     the comparison key of one of the field's texts, of the value the field
     settled on, or of the expansion it settled through (the one its
     abbreviation row names: a GEOLocate city asked with the country
     "Philippine Islands" lies in the country "Phil. Is." settled through
     that expansion, `step._expansions`). Then:
     - a province, county or city settles only when its candidate has
       parents and one is the country settled for the reading, and, for a
       county or a city, one is also the province settled for it when one
       is. With no country settled for the reading, no parents, or none
       that is that country or province, the field goes to review with the
       reason ("The place found is not in the country the label gives.").
       So a Philippine label (P.I. settled as the Philippines, Davao, Mati)
       never settles its province on TGN's department of Guatemala, and
       Wikidata's one department for "San Pedro", in Paraguay, never settles
       a Guatemalan province. A country needs no parent. A place that waits
       for a country whose research failed is researched again with it on
       the retry. A country that no answer settled holds no place back when
       the reading writes none, writes the place's own misfiled text there,
       or when the Getty TGN, Wikidata and NGA answers of any field confirm
       every country text of every reading of the record as one nation
       (`agreement.confirmed_place`: each text confirmed as above, of its own
       name or through an expansion, and every candidate at a nation's level
       of an answer about it or its expansion that same nation), and the
       place lies in that nation (`step._confirmed_country`). A country
       field left with no value and no text is then derived from the place
       (`derive.fill`, as for a label that writes no country), and one left
       ambiguous may be (the country derivation below); the text never
       supplies the value. 3781e440's country expert never cited Wikidata's
       answer for "United States of America" (only its answer for "USA"
       itself and the no-match answers for "U.S.B.I.L."), every one of its
       answers was refused, and its county was refused `NO_COUNTRY`; "USA" is confirmed as the
       United States, so Illinois and Coles County settle and derive it.
       Two readers who write "USA" and "Canada" leave the places for review,
       whether or not the organiser filed "Canada" (round 1 of #379's
       review, finding 2). The step reads each line of any reading that
       writes a country, province or county text of the record, and, on
       a label whose readers all have the same number of lines, the line at
       the same place (by its index) of every other reader of that label,
       so reader 1B's "Canada" over "Ill." over "Coles Co.", beside 1A's
       filed "USA" over the same two lines, is read too (round 1 of #380's
       review, finding 3). Readers whose line counts differ (one reads a
       printed header the other skips, or joins two lines) would pair the
       wrong lines, so each then has only its own place lines read (round
       1 of #381's review, finding 2). On each, it sets aside
       what the fields hold, where the line writes it: every field's
       organiser candidates, and the literals and verbatims of every
       supported value, never of a value left unsettled, so the country
       expert's own unresolved "Canada" holds nothing (finding 2). It then
       weighs what is left group by group, split at commas, semicolons,
       colons, brackets and slashes, after setting aside each date,
       elevation or range a group holds ("1948" of "Canada 1948", "1200 ft"
       of "Canada 1200 ft"; finding 4). A group keeps the country check in
       force unless what is left of it holds no letter, is only unit words,
       is only words that name no place (`step._residue_words`: what the
       elevation and date tables read around a number, their headings,
       approximate words, elevation words, units, months and range
       joiners, and a collector's or a determiner's mark, so "alt." of
       "alt. 1200 m", "coll." of "coll. 12.vi.1948" and "leg." beside a
       collector's name hold nothing back; round 1 of #381's review,
       finding 1), was found by none of the sources asked (3781e440's
       "U.S.B.I.L."), names that same nation by one of its names or an
       abbreviation of one by the letter rule ("United States", "U.S.",
       "US"; finding 3), or is confirmed as that nation
       (`step._unplaced_text`);
     - a county also needs the province its reading writes to have a
       settled value ("The province the label gives is not settled, so
       this county cannot be confirmed inside it.", `agreement.NO_PROVINCE`;
       the step passes the place fields the reading writes whose field has
       no supported value as `unsettled`), and is never that settled
       province itself: not its record, and its literal is none of the
       province's texts, values or expansions compared with letter case,
       accents and punctuation aside and unit words kept
       (`georef_locality.fold`; "The label gives this place as the
       province, and a province is never also the county.",
       `agreement.IS_THE_PROVINCE`). So "Chimaltenango" written once as the
       department, or "Davao Prov." as the province, is no county, while
       "Iowa Co." in the state Iowa may be. A province settled from another
       reader's spelling of the same label is settled, and is not checked
       as that reading's province, as before;
     - a near spelling, of any place field, settles only on G34's whole
       condition, read on the larger places (the coordinator's ruling of
       2026-10-09): every place field the reading writes above the field
       (`agreement.PLACE_ORDER`: a province's country; a county's province
       and country; a city's county, province and country), all of them and
       at least one, is one of the candidate's parents. A place's parents
       are only larger places, so a county or a city the reading writes
       below a near-spelled province is never checked as its parent
       (105526330's province, below). A country has no place field above
       it, so a near-spelled country always goes to review, even beside a
       province or a city of the nation's own name ("Guatamala" beside the
       province "Guatemala", "Mexco" beside the city "Mexico"), which
       settled it before.

     The check's limits (the fourth review's NB1): a parent counts by name
     even when it is another place of that name. Getty TGN names a US
     county without "County" (its live answers of 2026-10-09), so a
     Graniteville in Nevada County, California, lies "in Nevada" and
     settles on a label whose state is Nevada, and a town in the US state
     of Georgia settles under the nation Georgia. Only the readings the
     answer names are read, so a province that only another reader of the
     label writes is not checked. A city is checked against the country and
     the province, never the county.

     A country named only by its code (round 4 of the production test,
     2026-10-11). 105526329's country settled on Wikidata's Guatemala
     (Q774), and its province's expert cited NGA's department
     Chimaltenango, one letter from the label's "Chimaltenago", which NGA
     puts "in GT": the code matched neither the name nor the record, so the
     province went to review. NGA's country parent now carries its code
     (`PlaceRef.iso_code`, `sources._parent`), and a candidate carries the
     ISO 3166-1 alpha-2 code its own record carries
     (`SourceCandidate.iso_code`: Wikidata's P297 on any item, NGA's code on
     any PCL feature; Getty TGN gives none), except a record that names an
     end date, a dissolved state or a former colony, whose code ISO may
     since have given to another country (`sources._place`). A code is
     matched only against the record the country field settled on, and the
     country settles only on a record at a nation's level
     (`agreement.placed`): a colony's record settles no country and supplies
     no code, and a province's record supplies none either. A parent is the
     settled country when its code is that record's code, compared exactly
     (`agreement.lies_in`, `agreement.country_code`): two capital letters,
     never one of ISO's user-assigned codes (AA, QM to QZ, XA to XZ, ZZ),
     never a code read from a name. The step takes the record's code from
     the answers the country field received in this attempt
     (`step._record_code`); a country settled in an earlier attempt or by a
     person has none there, so a place below it is compared by name and
     record only, as before. For a country settled on initials it takes the
     settling candidate's code (`step._corroborate`). Both checks
     read the code (the country a place lies in, and the places above a
     near spelling), so 329's
     province settles one letter off with its `near_spelling` warning,
     and NGA's town Yepocapa settles inside it, while NGA's department in
     "GT" still does not settle on a label whose country settled as the
     Philippines ("PH"). GNS writes ISO codes, not FIPS 10-4, in the
     recorded capture: Costa Rica's Limon "CR-L", Honduras's Yoro "HN-YO",
     the Philippines' Davao "PH-DVC", each feature under them inside that
     country (`test_ngas_unit_codes_start_with_the_iso_country_code`).
   - **105526330's province.** Reader 1A writes "Chimaltenago", 1B
     "Chimaltenango", and Getty TGN knows only "Chimaltenango". Until
     2026-10-25 an answer that took 1B's "Chimaltenango" as its literal was
     refused (G19). In the real-run measurement of 2026-10-25 (t1-329) the
     first pass saw "Chimaltenago" in the image. By the settlement rule
     (`agreement.labels_by_rule`, points 1 and 4), where the first pass's
     units name 1A's "Chimaltenago" and TGN confirms 1B's "Chimaltenango",
     one letter from it, by its own name, the two texts are one candidate:
     the label settles cleared on the image's spelling as the literal, with
     the department as its value through that near spelling (`Label.matched`;
     a `near_spelling` warning; the value's reason names reader 1B's
     "Chimaltenango"), and an answer with 1B's text is sent back to give
     "Chimaltenago" (`test_first_pass_advice.py`,
     `test_a_source_confirming_the_other_readers_one_letter_correction_keeps_the_images_spelling`).
     A county is never another reader's spelling of
     the settled province (`step._province_spelling`), nor any field
     another reader's spelling, one letter off on the same label, of text a
     field of another kind settled (`step._spelled_alike` in `_taken`).
     Where both readers write "Chimaltenago", or the image names it and
     nothing backs the other reader's text, an answer that
     keeps "Chimaltenago" as the literal, as written (G27), and takes TGN's
     department Chimaltenango, one letter from it, as the value, passes the
     expert's check, and the step settles it with a `near_spelling`
     warning: the one field the reading writes above the province, its
     country Guatemala, is the department's parent (G34's whole condition).
     The city Yepocapa the reading also writes lies below the province and
     is not checked as its parent. Until 2026-10-09 it was, and the real run
     of that day left the province for review.
   - **County: the country's second-level unit (owner, 2026-10-11).** Asked
     whether County should hold the municipio for Latin American labels
     (Yepocapa, Guatemala), the owner answered: "however the local
     government does it so if that is the equivalent then yes"
     (schema-harness-plan.md, "What the owner has said"). A county is the
     place a source puts at its country's second level, whatever the
     country calls it: Getty TGN's "second level subdivisions (political
     entities)" or "counties", NGA's A.ADM2, Wikidata's "county" or
     "second-level administrative division" (step 4). No table of
     countries says which unit that is. The county brief says so, and that
     a town and the second-level unit around it often share a name: the
     county settles on that unit when a source confirms it inside the
     label's province and country, and the city still settles on the town
     (the city brief says so too). Before, the brief said "A
     municipality, a city, an island or a province is not a county", and
     105526329's county ("Yepocapa, 4800ft / Chimaltenago, / Guatemala")
     was absent while its city settled as Yepocapa. On the recorded
     answers that label's county settles on Wikidata's municipio Yepocapa
     (Q1523937) or NGA's (A.ADM2), and its city on NGA's town (P.PPLA2):
     one text, two places at two levels; two place fields may share text
     (`agreement.may_share_text`, unchanged). The rules that keep a county
     from being invented:
     - its place settles only as any place does (above): one candidate at
       a county's level in a cited answer about the label's own text, with
       the parents rule, which for a county also needs the province its
       reading writes settled and never takes that province itself;
     - a literal for which an answer of one of the county's sources, asked
       about it, has a candidate of its name at a province's level settles
       no county, unless the literal writes a county or municipality unit
       word ("<Name> Co.", "Mun. <Name>"; `agreement.writes_county_unit`,
       the words of `admin_markers.ADMIN_MARKERS` that mark a county): the
       label may name that first-level unit, and the sources cannot tell
       which ("The sources also find this name as a province or state, so
       they cannot tell which the label means.",
       `agreement.first_level_namesake`, `FIRST_LEVEL_TOO`, ambiguous). NGA
       holds Chimaltenango as a department (A.ADM1) and as a municipio
       (A.ADM2), so on a label that writes only the department a county
       answer that cites NGA's municipio is refused;
     - a Philippine "Davao Prov." stays the province: NGA's recorded answer
       for "Davao Province" is Davao del Norte at the first level (A.ADM1),
       Getty TGN's recorded record of it types it "provinces, first level
       subdivisions (political entities)", and Wikidata's class "province
       of the Philippines" is a first-level administrative division, so in
       NGA's and Wikidata's recorded answers for "Davao Province" no
       candidate is at a county's level; an answer that held it at the
       second level too would still meet the province's own text
       (`IS_THE_PROVINCE`).
   - **The taxon.** A taxon is GBIF's decision for the whole name its
     candidate literal writes: the cited success answer's query is the
     scientific-name parser's query for that literal (the genus, any
     subgenus, the species epithet and any infraspecific epithet with its
     marker, as written, with or without the author and year written), or the
     genus alone for a "sp." identification (G25). A query for part of the
     name or for another name on the line grounds nothing, and a label with no
     genus ("sp. 30") has no groundable query: such a taxon clears as
     written, unmatched, on the owner's decision B (see "Fields the label
     does not state" below). The value and identifier are
     the candidate GBIF decided, never one of its alternatives. The clearance
     rules check the stored taxon the same way.

   An expert whose answer still fails the checks after its retries sends the
   field to review, never to a retry. At the step, an answer that breaks the
   rules is ambiguous (readers or labels disagree) or unresolved, never
   settled.
6. **Derived values** (G37, G41, G44) are filled deterministically afterwards
   from settled fields only: elevation copies and exact unit conversion, and
   the collection date's end from its start (G44: only for a single date; the
   start of a written range is never copied, `derive.fill` through
   `field_validators.written_range`, see "How dates are read" below). An elevation settled on a
   candidate that writes more than its number is read as its parsed value,
   the check's number. Then the listed fields the label does not state are
   marked so (see "Fields the label does not state" below).
7. **One save.** Field values, evidence and reasons are written in one save
   at the end, through the existing record writer. Clearance uses the existing
   scientific rules without blanket human approval (G1). Anything unresolved
   sends the record to Needs human review with a plain reason. A field whose
   expert reached no source (step 4), a model failure and a field's timeout
   leave the record blocked with a retry, every settled field kept. A
   field's timeout is its expert's own 150 s deadline, the step's deadline
   (step 9), or a model request that ran out of time (`experts.timed_out`):
   the gateway's own bound on one request (120 s,
   `step.MODEL_TIMEOUT_SECONDS`), which the inference client raises as an
   httpx timeout (connect, read, write or pool) and `experts.ClientTimeouts`
   keeps a `TimeoutError`; a `TimeoutError` from the client (asyncio's or
   huggingface_hub's `InferenceTimeoutError`); or a provider's answer with
   HTTP 408 (Request Timeout) or 504 (Gateway Timeout). Nothing else is a
   timeout: an auth error, any other HTTP status, a connection that failed,
   an answer that is no completion and any defect are model failures. The
   workflow allows the run's `max_attempts` attempts (its execution policy,
   3 by default). On
   the step's last attempt a field whose sources still could not be reached
   goes to Needs human review instead, unresolved, its reason naming them
   ("Getty TGN could not be reached after 3 attempts."), and so does a field
   that ran out of time ("Research on this field ran out of time after 3
   attempts."), whichever of those timeouts it was; the record finalizes
   with its other fields. A model failure on the last attempt still stops
   the automatic retries (`retry_budget_exhausted:<code>`). The app reads a
   blocker by its exact code, from a table (`lib/src/blocker_words.dart` and the vocabulary table),
   and never shows the code. A word inside a code decides nothing: the "budget"
   in `retry_budget_exhausted:` says retries ran out, and a step limit, a
   request limit and a time limit also say "budget" on the wire and are no cost
   limit. A code the app has no name for reads "Needs an operator check".

   For a run whose retries ran out, the app reads the cause after the colon:

   | Cause after the colon | Name | Sentences |
   | --- | --- | --- |
   | `lookup_operational_failure` | Retries stopped, source not reachable | An approved source could not be reached after repeated attempts. Retry later, or ask an administrator. |
   | `field_research_timeout` | Retries stopped, ran out of time | Field research ran out of time after repeated attempts. Retry later, or ask an administrator. |
   | `field_research_model_error` | Retries stopped, no usable model answer | The model gave no usable answer after repeated attempts. Retry later, or ask an administrator. |
   | any other cause | Automatic retries stopped | Processing stopped after repeated attempts. Retry later, or ask an administrator. |

   A run stopped by a limit, or by the settings that carry one, reads by its
   own code. Only a limit on money is called a cost limit or a spending
   allowance:

   | Code | Name | What the app says |
   | --- | --- | --- |
   | `step_budget_exhausted` | Step limit reached | The run reached its limit on processing steps. |
   | `external_call_budget_exhausted` | External request limit reached | The run reached its limit on external requests. |
   | `token_budget_exhausted` | Model unit limit reached | The run reached its limit on model units. |
   | `active_time_budget_exhausted` | Active time limit reached | The run reached its limit on active processing time. |
   | `evidence_harness_blocked:elapsed_budget_exhausted` | Evidence check time limit reached | An evidence check reached its time limit. |
   | `cost_budget_exhausted` | Cost limit reached | Processing stopped at a cost limit. |
   | `program_allowance_exhausted` | Spending allowance reached | Processing stopped at the program's spending allowance. |
   | `tenant_budget_exhausted` | Monthly cost limit reached | Processing stopped at a monthly cost limit set for the organization or a collection. |
   | `pilot_launch_budget_exhausted` | Pilot cost limit reached | The pilot's cost limit would be crossed. |
   | `pilot_cohort_reading_budget_insufficient` | Reading cost limit too low | The cost limit does not cover the planned readings. |
   | `approved_cost_budget_unavailable` | Cost settings not available | The approved cost settings for this run are not available. |
   | `research_budget_state_unavailable` | Saved cost totals not readable | The saved cost totals for this record could not be read. |
   | `program_allowance_ledger_unavailable` | Allowance totals not readable | The program's spending totals could not be read. |
   | `tenant_budget_unavailable` | Monthly totals not readable | The monthly spending limits or totals could not be read. |
   | `program_allowance_unavailable` | Spending allowance not set up | The program's spending allowance is not set up for this collection. |
   | `pilot_run_budget_not_approved` | Run limits do not fit the pilot | The run's approved limits do not fit the pilot launch. |
   | `pilot_stage_cost_reservations_mismatch` | Stage cost settings differ | The run's stage cost settings differ from the pilot launch. |
   | `pilot_cohort_reader_cost_unknown` | Reading cost not set | The cost of a reading step is not set. |

   Each limit's sentence is followed by what to do: an administrator must
   review the approved limit, the allowance or the cost settings, or an
   operator must check the totals. A test in the app reads the server source
   files that set a run's limit blockers and fails when a quoted code it finds
   there with "budget", "cost" or "allowance" in it is not in these tables. It
   does not see a code passed on indirectly, nor the pilot launch's capacity
   and time codes (for example `pilot_cohort_reading_capacity_insufficient` and
   `pilot_cohort_reading_time_insufficient`); those are not in the tables and
   read "Needs an operator check".

   The processing panel's "Blocked:" line shows the name and a passage shows
   the sentences. The workbench issue list shows the same sentence and next
   step for every code in the two tables above. For a code the app has no
   name for, the panel shows "Processing needs an operator check before it can
   continue. Ask an administrator to review it." and the issue list shows the
   first sentence with "Open processing details for the current state and
   permitted actions." For a code in the two tables, the queue row, the
   history, the blocker filter menu and the reason chips show the name alone
   (the reason chips read a code whole before they split it at a colon). For a
   code the app has no name for, the queue row, the history and the filter menu
   read "Needs an operator check", and two such codes stay two entries in the
   filter menu, numbered; the reason chips, which this change leaves alone for
   other codes, read its plain-English words. The raw code stays in the
   workbench's "Technical review details" drawer (inside the closed "Review
   details" disclosure), which lists each issue's `reason_code`, and in the
   history's "Retained version data" drawer, which holds a past version's raw
   record. No line, sentence, row or menu above shows it.
8. **Budget.** Before every model call the step reserves that call's worst
   case (its input, the provider's chat template and the output cap) from
   what remains of the run's ceiling (the profile's `run_cost_limit_micros`,
   USD 1 for the pilot), and settles to the real usage after. A request the
   provider refuses with HTTP 429 generated nothing and settles to nothing;
   one sent that fails any other way keeps its worst case
   (`budget.MeteredModel`). A call that
   would cross the ceiling is not sent: while other calls' reservations are
   held it waits for them to settle, each to its real cost (about a tenth
   of its worst case or less), and tries again; only when no other
   reservation is held and it still does not fit is it refused, and its
   field goes to review (`budget.CostMeter.reserve`). So every expert can
   run under a cap its real spend fits, though the worst cases of all
   experts' requests at once do not (in this branch's real runs, two of
   105526321's fields were refused under a USD 0.080 cap its real spend of
   about USD 0.035 fitted); the ceiling is never raised or crossed. The step
   holds no more of the shared program allowance than it has left: when that
   is less than the run's headroom, the meter's cap is what is left, and a
   field that does not fit goes to review. Only when the program allowance
   cannot pay for one expert request is the record blocked, as before. Field
   research the run's own limits other than money (steps, external requests,
   model units, active time) leave no room for is not blocked: the step is
   given up on unsent and the record goes to review, its unchecked fields
   for a person (HARNESS.md, "Field research at a run limit"). A setup
   error before any request settles to nothing; research cut short by an
   error, or a step that overran its deadline, settles to what the meter spent.
9. **Time.** Research stops a minute before the step's deadline (210 s of the
   pilot's 270 s): a field still being researched becomes a timeout for the
   retry (on the last attempt, a field for review; step 7), and every settled
   field is kept. Inside it, each expert has 150 s and each of its model
   requests 120 s (the gateway's bound); running out of either is the
   field's timeout too. The work after research measured
   4.3 s on a slide-sized record with a 50 ms storage round trip per blob, most
   of it the integrity check, so the minute is more than three times it. The
   record's sources close when research ends, so a GBIF check still running
   cannot hold the step.

At the harness route's prices (USD 0.20 per million input tokens, USD 0.60
per million output), a typical record is expected to cost a few cents for
field research. The ceiling cannot be crossed.

## How dates are read (G24, G29, G44; 2026-10-09)

The experts' `parse_date` is `field_research/checks.parse_date`, which wraps
`application/field_validators.date_parser` (tool version `date-parser-v2`;
the notations are `application/date_notations.py`, the month words
`application/date_months.py`). It is deterministic and reads only by the
named rules below. It never guesses beyond them: a form no rule reads is
`no_match`, and a date a rule leaves open is `ambiguous` and goes to review.
Each reading records the rule that matched (`order`), how a missing year was
found (`via`) and the century rule it used (`century_rule`), so the check
row the settled value cites shows them.

- **Months.** A Roman numeral I to XII, when the profile enables Roman
  months (G29), in any position: month first (`IX-14-46`, `IV-24-48`),
  between day and year (`14.IX.1946`, `14 IX 1946`, `3.iv.1948`), year first
  (`1946.IX.14`, `1946-IX-14`), month and year (`IX.1946`, `XI .46`), and
  day and month with no year (`14.IX`). A lowercase numeral is read only
  in three shapes, each joined by `.` or `-` (spaces around them allowed): after
  a day and before a year of two or four digits (`3.iv.1948`, `3.ix.46`,
  `3-ix-46`), after a four-digit year and before a day (`1946.ix.14`), and
  after a day with no year (`3.iv`). It is never read month-first (`iv-23-48`),
  as a month and year (`iv.1948`, `1946.ix`) or joined by spaces alone
  (`12 vi 1946`, `12 x 46`). A month written by name in English, Spanish,
  French, German, Portuguese, Italian or Latin, in full or abbreviated, with or
  without its period and accents (`sept.`, `Sept`, `ene.`, `janv.`, `Mai`,
  `mars`, `Okt.`, `agosto`, `Septembris`). A word two languages share means
  the same month in both, and the table refuses to load otherwise
  (`date_months`). A day may carry an ordinal (`3rd`, `1er`, `1o`), and `de`,
  `del`, `of`, `di`, `da` or `do` may stand between a day and its month and
  between a month and its year (`14 de septiembre de 1946`); a month name and
  its year may be joined by a comma (`September, 1946` is September 1946). A
  numeral is written in ASCII letters only: the dotless i (U+0131) and the
  dotted capital I (U+0130) match `I` under Unicode's case rules, and neither
  reads as `I` (`3.` U+0131 `x.1946` is no date; `date_notations.month_of`).
- **Years.** Four digits, or two digits after an apostrophe (`'46`) or bare
  after a month or inside a date (`Sept. 46`, `14.IX.46`, `4-5-48`). The profile's
  century rule reads a two-digit year as 19xx and the reading records it as
  its `century_rule` (`date-rules-v1:two_digit_year_century=1900`); without
  the rule the year stays open (`century_unresolved`) and the date goes to
  review. The record's own mark of an inferred century is
  `FieldValue.century_rule` (with `precision`), which field research does not
  set today: the century rule is kept in the reading of the check row the
  value cites (locator `check:date_parser`), as it was before this change.
  A year alone is a date at year precision, four digits or `'46`.
- **Numeric dates** (`4-5-48`, `3.9.1946`, `5/13/1948`, and with the year
  written first `1946-04-05`). They are settled only when a part over 12 fixes
  which number is the day (`13-5-48` is 13 May 1948); a written four-digit
  year fixes the year. Otherwise both readings are returned and the check
  names the ambiguity (the note `day_month_order_ambiguous`, after
  `several_readings`), so the review reason can say that the label does not
  say which number is the month. A year written first is not read as the ISO
  order: `1946-04-05` is April 5 or May 4 until a part over 12 decides.
- **A year literal.** A month and day alone take a year the same reading
  writes elsewhere, when the expert passes it as `year_literal`. They are then
  that date only: `IV-25` beside `1948` is 25 April 1948, no longer also April
  1925 (the reading a bare two-digit number after a month would otherwise
  take under the century rule). The reading's `via` is `year_literal`. Field
  research asks the parser for this (`date_parser(..., year_literal_decides=True)`);
  the parser's default still leaves both readings, because the six-specialist
  harness's hash-pinned explicit-event rules (`research_harness/temporal_context.py`)
  read the second one to refuse a year that "alone chooses" between a day and a
  short year (`test_temporal_event_links.py`). The step never settles a value on
  a year literal: `step._check_row` runs the check again on the literal alone,
  without it, so a date only a year literal completes stays unsupported and goes
  to review. A date settles with its year only when the literal quotes both, on
  two lines or on one (the next two rules).
- **A date split over two lines of one label** (`date_lines`; pilot
  105526330: "Guatemala, IV-25" above "1948, R.D. Mitchell"). The date and the
  year are one date only under all of these rules, none a guess: the two lines
  are adjacent, with nothing between them but the line break (the date ends its
  line and the year starts the next, or the year ends a line and the date
  starts the next); nothing else on either line could be a date (no other year,
  numeric date, Roman numeral beside a number, or month word of any language: a
  wide test, `date_lines.could_be_a_date`); the date states no year of its own;
  and the year is bare, never a measurement or a determination's year. Two
  forms, with a different bareness rule because they have different authors:
  - the literal is both lines, as the organiser quotes it (`"IV-25\n1948"`, or
    the year first). A year below the date may carry the period, comma or
    semicolon a sentence leaves (`1948.`, `1948,`, `1948;`): it is the year
    alone, every rule below applies to it, and the mark the literal quotes
    counts as following the year (`"3 Sept.\n1948."` in a reading that goes on
    `1948.5 m` is refused). A colon after it is no such mark:
    `"3 Sept.\n1948:"` is `split_lines_year_not_alone`. A year above the date
    may end in any of the four, colon included (`"1948:\nIX-3"` over
    `IX-3 Guatemala` reads), because it must stand alone on its line. Lines
    with a blank line between them are `no_match` with
    `split_lines_not_adjacent`. The organiser has named the year, so it may be followed by
    a comma, semicolon or period and then other text (`1948, R.D. Mitchell`),
    but never by a unit (`1948 m`, `1948 ft.`, `1948 msnm`), an apostrophe
    (`1948'`), a dash and a number (`1948-49`), a decimal or second number
    (`1948.5`, `1948 5`) or a word (`1948 det. J. Smith`); a year that ends the
    line above the date must stand alone on its line (`det. J. Smith 1950`
    and `El. 1948` do not). `parse_date` then reads one date (`via`
    `split_lines`). Another date on the lines is `no_match` with the note
    `split_lines_hold_another_date`; a year that is marked or does not stand
    alone is `no_match` with `split_lines_year_not_alone`; a date that already
    states a year is `no_match` with `split_lines_state_two_years`; a line the
    parser does not read with the year is `no_match` with the parser's own note
    (`"28.XII-3.I\n1947"` is `range_end_before_start`) or, when it has none,
    `split_lines_date_not_read` (`"Davao\n1948"`, `"3.9-5.10\n1946"`);
  - the literal is the day and month alone (`IV-25`): nobody has named a year,
    so it takes one only from a line that holds nothing but a four-digit year,
    optionally followed by a period or a comma, directly below it or directly
    above it (`via` `year_on_next_line` or `year_on_previous_line`). A year with
    any other text on its line (`1948, R.D. Mitchell`, `1948 m`, `1948'`,
    `1948-49`, `1948-2`, `El. 1948`, `alt. 1948`, `det. J. Smith 1950`) is not
    borrowed, nor is `'48`, a bare two-digit number or `4800`; and when the lines
    above and below give two different years, neither is. In every such case the
    date stays open (`year_missing`) and goes to review.

  In both forms, and on one line (below), **a number with a measurement marker
  attached is no year** (`date_lines._year_marker`; review 297, rounds 2 and 3:
  `Alt.` ending the line above `1900` lent 1900 to the date below it; the
  coordinator's ruling of 2026-10-10 on #306 narrowed the rule to markers
  attached to the year). The markers, matched without accents and in any case,
  in the languages of the month tables:
  - an elevation or depth word, which stands before its number: `alt.`, `alt`,
    `altitude` (English, French, Portuguese), `altitud`, `altura` (Spanish,
    Portuguese), `altitudine`, `quota` (Italian), `altitudo` (Latin), `elev.`,
    `elevation` and the Spanish, Portuguese and French spellings, `Hoehe`,
    `Seehoehe`, `Meereshoehe` (German, written with the umlaut too), `depth`,
    `profundidad`, `profundidade`, `profondeur`, `profondita`, `Tiefe`; `El.` with
    its period (`El` alone is the Spanish article: `El Salvador` above `1948`
    still lends it);
  - a unit or a height above sea level, which stands after its number: `m`,
    `mt`, `mts`, `metros`, `metres`, `meters`, `metri`, `ft`, `feet`, `pies`,
    `pes` (with or without its accent), `pieds`, `piedi`, `Fuss`, `msnm`, `m.s.n.m.`, `snm`,
    `s.l.m.`, `a.s.l.`, `m.a.s.l.`, in any case and with or without its periods
    (`Metros`, `FT.`, `MTS.`, `MSNM`, `M.S.N.M.`), or a tick (`4800'`). A
    distance is no marker (`5 mi W`).

  A unit belongs to a number before it only when it is attached to it
  (`date_lines._unit_here`; the reviews of #306 at d305db77e and f89292766, and the
  coordinator's rulings). It does not when a number of its own follows it
  (`m 1200`, `m. 1200`, `M 1200`, `M. 1200`, `mt 1800`: the unit written before its
  number, as Italian labels do). One waiver: a Title-case `Mt.`, `Mts.`, `Ft.`,
  `Mte.` or `Pto.` (with or without its period), or the initial `M.`, before a
  capitalised name is a place or a person: `Mt. Apo`, `Mt Apo`, `Mt. Rainier`,
  `Ft. Collins`, `Ft. Sherman`, `Mts. Rwenzori` and `M. Smith` are names, as in the
  pilot's `E. slope Mt. McKinley`. The waiver is for names, never for marker words
  (the review of d0707cca and the coordinator's ruling): a capitalised collector or
  determination word, elevation word, lot or number mark (`Lot`, `No.`, `Nr.`,
  `Cat.`, `Num.`) or `Ex.` after the abbreviation is no name, and the unit stays a
  unit (`1900 Ft. Coll. Smith`, `1900 M. Leg. Smith`, `1900 M. Det. Smith`,
  `1900 Mts. Col. J. Perez`, `1900 Mts. Alt.`, `1900 Mt. Lot 5`, `1900 M. No. 12`,
  and `1900` above `Ft. Coll. Smith`). A unit in lower case or in capitals stays a unit
  whatever follows it (`1900 m R.D. Mitchell`, `1900 ft. Coll. Smith`,
  `1900 msnm Guatemala`, `1900 metros San Pedro`, `1900 FT. COLL. SMITH`,
  `1900 MT. APO`, `1900 M LEG. SMITH`), and so does a Title-case unit word that is
  no listed abbreviation (`1900 Metro Manila`): a collector or a place written after
  the elevation is the usual layout.

  A year on a line of its own (split lines, or a year a day and month borrow) is
  no year when a unit is attached right after it: after nothing but spaces,
  periods, a comma or an opening bracket, with no number of its own between
  (`1948. m`, `1948.m`, `1948.ft`, `1948, m`), or at the start of the nearest
  line below that is not blank (`1900` above `m`, `msnm`, `metros`, `Metros`,
  `meters`, `feet`, `pies`, `FT.`, `MTS.`, `MSNM`, `M.S.N.M.`, `M` or `M.`, or above
  `m R.D. Mitchell`, `m Yepocapa`, `ft. Clayton`, `mt. Apo` or `m. Smith leg.`;
  `1948` above `M. Smith`, `Mt. Apo`, `m 1200` or `M 1200` still reads); or when the nearest line
  above it that is not blank is only a marker waiting for its number: it ends in
  an elevation or depth word (`Alt.` or `Guatemala, Alt.` above `1900`) or holds
  no digit and a marker (`m.s.n.m.` or `Metros` above `1900`). A measurement with
  its own number elsewhere does not count, after a comma on the year's line, on
  the line above or on the line below: `"IV-25\n1948, 1,900 m"`,
  `"IV-25\n1948, 1900m"`, `"IV-25\n1948, Alt. 1500 m"`,
  `"VI-25\n1948, m 1200"`, `"4800 ft. IV-25\n1948"`, `Alt. 1500 m` above `1948`
  above `IV-25`, and `1948` above `m 1200` read. A unit or an elevation word
  written against the year on its own line (`1948 m`, `El. 1948`) already leaves
  the year not alone. A determination (`det.`, `determ.`, `determinavit`,
  `determined`, `identified`, and the Spanish, Portuguese and French
  `determino`, `determinou`, `determine`, `identificado`, `identifie`, accents
  dropped; `ident.` only before `by`, `por`, `par`, `von` or a capitalised name that
  is no marker word, so `Ident. No. 5` is none) before a year on a line of its own,
  on the nearest line above it that does not hold the date, makes it the
  determination's year: `det. J. Smith` or `Ident. by J. Smith` above `1950` above
  `IV-25` is refused, while `Ident. No. 5` above `1948` above `IV-25` reads
  1948-04-25. A determination after the year
  (`"IV-25\n1948, det. R.D. Mitchell"`) does not. A two-line literal is then `no_match` with
  `split_lines_year_may_be_a_measurement` or
  `split_lines_year_may_be_a_determination`; a day and month alone borrow no
  year and stay open (`year_missing`).

  On one line, whatever notation reads the date (`date_lines.one_line_year_problem`),
  the year the literal ends with is no year when a unit is attached right after
  it as above (`25.IV 1900 m`, `25.IV 1900. m`, `25 IV 1900 M.`, `25 IV 1900 (m)`,
  `3 Sept. 1900 msnm`, `25.IV.1900 m`, `IV-25-1900 ft.`, or `25 IV 1900` above
  `m` or `metros`), and the year a literal starts with is no year when an
  elevation or depth word stands right before it (`Alt. 1948`,
  `Elev.: 1948 IV 25`): `no_match` with `one_line_year_may_be_a_measurement`. The
  line above is not asked for a one-line date (`Alt. 1500 m` above `25 IV 1948`
  reads 1948-04-25), nor does a measurement with its own number on the line
  count (`25 IV 1948, 1900 m`, `25.IV 1948 1900 m`, `25.VI.1948 m 1200`,
  `25 giugno 1948, m 1800`, `3-IX-1946, m 1200`, and the pilot's
  `IX-14-46 3300'` read), nor a name (`3.IX.1946 Mt. Apo`,
  `Aug. 3, 1948 Mt. Rainier Nat. Pk.`, `VII-3-1948 Ft. Collins, Colo.`,
  `25 IV 1948, Ft. Sherman, Canal Zone` read).

  **A determination before the date makes it the determination's date**
  (`date_lines.determination_date`, `checks.parse_date(..., field=...)`, which the
  experts and `step._check_row` pass; the reviews of f89292766, d0707cca and
  04bbe6936 and the coordinator's rulings). A date that a determination stands
  before on its own line, with no collector and no complete date (one with its
  year) between them (`det. J. Smith 1950`, `det. 25.IV.1950`,
  `det. J. Smith, IV-25 1950`, `"det. J. Smith IV-25\n1950"`, and `1950` alone in
  either; `Ident. by J. Smith 1952`, `leg. Rossi det. Bianchi 1950`), settles only
  Date Identified; for Date Visited From and To, or with no field, it is `no_match`
  with `date_follows_a_determination`. A determination claims the first complete
  date after it only: in `det. J. Smith 1952 / Guatemala IV-25-1948` and
  `det. J. Smith 1952 25.IV.1948`, 1952 is the determination's date and 1948 the
  collecting date; in `det. Bianchi leg. Rossi 1950` the collector stands between,
  and 1950 is the collecting date.

  A date alone on its line, with nothing else on it but punctuation or a
  collection mark (below), takes the first line above it that is not blank, under
  the same rule. Only a bare year passes over more: the lines just above it that
  hold the parts of its date without a year (`IV-25`, `Sept.`, `3`). So
  `det. J. Smith` above `25.IV.1952`, `(25.IV.1952)` or `IV-25 1952`,
  `det. J. Smith` above a blank line above `25.IV.1952`, `J. Smith det.` above
  `1952`, `Det. by H. Dybas` above `Sept. 3, 1952`, `Ident. J. Smith` above
  `25.IV.1952`, `leg. Rossi det. Bianchi` above `1950`, `det. J. Smith` above
  `IV-25` above `1952` (as a literal over both lines, `IV-25` alone or `1952`
  alone), and `det. J. Smith` above `3` above `Sept.` above `1952` give Date
  Identified's date. A line that holds a complete date of its own stops the search
  (the coordinator's ruling on the review of 04bbe6936: a date inherits only across
  its own parts): `det. J. Smith` above `1952` above `25.IV.1948` (with or without a
  blank line between), `Det. J. Smith` above `25.IV.1952` above `IV-25-1948`,
  `det. J. Smith` above `1952` above `IV-25` above `1948` (as a literal over the two
  lines, `IV-25` alone or `1948` alone), and `det. J. Smith` above `IV-25` above
  `25.IV.1948` leave 1948 a collecting date; in the first three, 1952 is the
  determination's date.
  `det. J. Smith 1950` above `25.IV.1948` does not give Date Identified's date
  either (the determination's first date is 1950), nor `det. J. Smith` above
  `leg. Rossi` above `25.IV.1948`, nor `Guatemala` above `25.IV.1948`. A date whose
  line holds other text decides from its own line only: `det. J. Smith` above
  `Guatemala 25.IV.1948` or `25.IV.1948 Guatemala` is the collecting date.

  A collector after the date on its line keeps the collecting date, whatever stands
  before it (`det. J. Smith` above `25.IV.1948 leg. Hoogstraal`, and `det. J. Smith
  25.IV.1948 leg. Hoogstraal` on one line). `leg.`, `legit`, `colr.`, `collector`,
  `colector` and `coletor` always name a collector; `coll.` and `col.` only before a
  person's name, perhaps after a determination joined to them (`25.IV.1948 coll. J.
  Smith`, `coll. R.D. Mitchell`, `Coll. Jones`, `coll. & det. J. Jones`, `col. y
  det. J. Perez`). A name may begin with initials or lower-case particles, and after
  them its surname may be written in capitals (`coll. van Dyke`, `coll. de la Cruz`,
  `coll. J. van Dyke`, `coll. H. DYBAS`); a surname with a second capital after a
  lower-case letter, or a word in capitals longer than six letters, is a name too
  (`coll. McRae`, `coll. HOOGSTRAAL`). After `ex` or a museum or collection word,
  before a museum or collection word (`Mus.`, `Museum`, `Musee` with or without its
  accent, `Museo`, `Museu`, `Collection`, `Coll.`) or an acronym written with a
  lower-case letter (two to six letters without periods, beginning with two
  capitals: `IAvH`, `INBio`), or with no name after them, they are a collection or
  provenance mark and no collector (the coordinator's ruling on the review of
  04bbe6936): `det. J. Smith 1950, coll. Mus. Paris`, `det. J. Smith 1950 ex coll.
  Jones`, `Det. J. Perez 1950, Col. IAvH`, `det. J. Smith 1950 coll. INBio`,
  `det. J. Smith 1950 coll. Coll. Oberthur`, `det. J. Smith 1950 coll.` and `det.
  Bianchi ex coll. Rossi 1950` are Date Identified's, and so are `25.IV.1950 Col.
  IAvH` and `25.IV.1950 ex coll. Jones` alone on their line under `det. J. Smith`.
  An acronym in capitals only (`FMNH`, `MCZ`) is no certain mark: it may be a
  surname (below).
  A museum or collection word after the date is a mark too, with `coll.` or `col.`
  after it or not (Codex's review of 8a742bb6): under `det. J. Smith`,
  `25.IV.1950 Mus. coll. Jones`, `Museum coll. Jones`, `Collection col. Jones`,
  `ex Mus. coll. Jones`, `Mus. Paris` and `, Collection Oberthur` are Date
  Identified's.

  Some words after `coll.` or `col.` may name a person or a collection: two to six
  capitals (a surname or an acronym: `JONES`, `NG`, `USNM`, `FMNH`, `MCZ`), another
  lower-case word (`smith`), or initials with no name after them (`U.S.N.M.`). When
  the date is the determination's only if those words name a collection, no field
  takes it (Codex's reviews of 8a742bb6 and 7f27908a): `det. J. Smith 25.IV.1950
  coll. JONES`, `det. J. Smith` above `25.IV.1950 coll. JONES`, `coll. NG` or
  `coll. FMNH`, `det. J. Smith 25.IV.1950 coll. USNM`, `det. J. Smith 25.IV.1950
  Coll. FMNH`, `det. J. Smith 1950 coll. MCZ`, `det. J. Smith` above `25.IV.1950
  coll. smith`, `det. J. Smith 25.IV.1948 coll. U.S.N.M.` and `det. Bianchi coll.
  JONES 1950` are `no_match` with
  `coll_may_name_a_collector_or_a_collection` for every field and for no field
  (`date_lines.determination_date` answers both ways and finds they differ). A
  collector beside them decides (`det. J. Smith` above `25.IV.1948 coll. JONES,
  leg. Rossi` is a collecting date), and without a determination they change
  nothing (`Guatemala 25.IV.1948 coll. JONES` and `25.IV.1948 coll. smith` are
  collecting dates).

  `Ident.` is a determination only before
  `by`, `por`, `par`, `von` or a capitalised name that is no marker word:
  `Ident. No. 5, Davao, 25.IV.1948`, and `Ident. No. 5` or `Ident. Nr. 12` above
  `25.IV.1948`, are collecting dates.

  Date Identified settles only from a determination's date: any other date is
  `no_match` with `date_follows_no_determination` for it. A
  determination after the date, joined to the collector or not, leaves the
  collecting date: `25.IV.1948 leg. et det. J. Smith`, `leg. & det.`, `leg./det.`,
  `leg. u. det.`, `3-IX-1946, col. y det. J. Perez`, `25.VI.1948, leg. Rossi det.
  Bianchi`, `25.IV.1948 J. Smith leg. et det.`, `25 IV 1948 det. Smith` and
  `IV-25 1948 det. Smith` read for Date Visited From and To.
- **A day and month, then their year, on one line** (`date_lines.one_line_literal`,
  `one_line_problem`; review 297c, note 5). When no notation reads a one-line
  literal whole and it ends in a year (four digits, or two after an
  apostrophe) joined to what comes before it only by spaces, a comma or a
  period, `parse_date` reads what comes before with that year, if the parser
  reads it as a day and month (or a range) with no year of its own:
  `IV-25 1948`, `IV-25, 1948`, `IV.25 1948`, `25.IV, 1948`, `25 IV, 1948`,
  `25.iv 1948`, `IV-25 '48` (`via` `one_line`; `IV-25` beside 1948 is April 25,
  1948 only). The rules are a year on the line below its date's, with the
  one-line marker rule above: nothing else on the line could be a date
  (`one_line_holds_another_date`); the year may be followed by a comma,
  semicolon or period and other text, or by a collector or a determination
  (`leg.`, `leg`, `legit`, `coll.`, `col.`, `colr.`, `collector`, and the Spanish and
  Portuguese `colector` and `coletor`; `det.`, `identified` and the other
  determination words: `IV-25 1948 leg. R.D. Mitchell` and `IV-25 1948 det. Smith`
  read), never by a unit, an apostrophe, a dash and a number, a second number, any
  other word or a colon (`one_line_year_not_alone`); no unit attached right after
  the year (`one_line_year_may_be_a_measurement`: `IV-25 1948. m`,
  `IV-25, 1948, m`); readers that disagree leave it ambiguous. Which field the date
  belongs to, collecting or determination, is the rule above. A collector after the
  year is allowed on one line only: a year on the line below its date followed
  by `leg.` is still `split_lines_year_not_alone`. A date part the calendar refuses
  says so (`31.IV, 1948` is `invalid_calendar_date`). Not read this way: a
  semicolon or colon between the date and the year (`IV-25; 1948`), a bare
  two-digit number (`IV-25 48`), `IV 25 1948`, a lowercase numeral month-first
  (`iv-25 1948`), and every all-numeric date (`4-25 1948`, `25.4 1948`): which
  number is the month is never picked. A form a notation reads whole is read
  by its notation, under the one-line marker rule only (`25 IV 1948`,
  `25.IV 1948`, `3 Sept. 1948`, `25.4. 1948`, where 25 is no month).
- **A literal that spans a line break is judged only by those rules.** For the
  date check (the date parser and `date_lines`), a line is what
  `str.splitlines()` gives: a break is `\n`, `\r\n`, `\r`, VT, FF, NEL (U+0085),
  U+2028, U+2029 or the file, group and record separators. (`step._excerpt_span`,
  which cuts the excerpt a label row shows, and the taxon helpers
  `checks.word_before`, `token_before` and `token_after` find a quote's own line
  by `\n` alone; none of them reads a date.) The parser reads no
  notation across one: any such literal that is not a date and its year as
  above (`3\nSept.\n1946`, `3 Sept.\n1946 leg.`, `1948-\nIX-3`, `3 Sept.`
  U+2028 `1946`) is `no_match` with the note `literal_spans_a_line_break`, so
  a notation's whitespace never joins two lines past the rules above, and
  `date_lines` finds a literal's line, and the lines beside it, by the same
  breaks.
- **A literal inside a longer token is no date.** A reading counts only where the
  literal stands as a token of its own, not glued to a letter or a digit before
  its first character or after its last when that character is one
  (`date_lines.places`): `III-25 1948` in `VIII-25 1948`, `IV-25-1948` in
  `Lot XIV-25-1948`, `25.IV.1948` in `125.IV.1948` or `25.IV.19489`, and
  `25 IV 1900` in `25 IV 1900m` are `no_match` with
  `literal_inside_a_longer_token`; `IV-25-1948` in `Lot IV-25-1948` and
  `25.IV.1948` in `Davao (25.IV.1948)` read. A reader that writes the literal only
  inside a longer token is not asked, as a reader without it is not.
- **Readings of one label that disagree.** The check reads the literal in each
  reading's own text. When those results are not all the same (one reader's
  adjacent year is 1948 and the other's 1949; one has the year line and one has
  dropped it; one year is marked and the other bare), the check is `ambiguous`
  with the notes `readers_disagree_on_date` and one naming each reading and
  its result (`1A: 1948-04-25; 1B: 1949-04-25`), whichever reading is listed
  first. The first reading's result is never taken for the others, and
  `step._check_row` keeps no row for it. `reading_names` must name every
  reading (a mismatch is a `ValueError`, never a silently shorter list). A reading that shows the literal inside
  a slide code or a hyphen-joined token still makes it no date, as before.
- **Ranges** (`3-5.IX.1946`, `VIII-IX.46`, `3.IX-5.X.1946`, `10-12 Sept.
  1946`, `Sept. 3-5, 1946`, `3 Sept.-5 Oct. 1946`, `Sept.-Oct. 1946`,
  `3.IX.1946-5.X.1946`). The text is split at a dash (hyphen, en dash or em
  dash) into two ends; each end must read as a date by itself, and the first
  borrows only what it leaves out (the month, the year) from the second. The
  reading has the start as `iso` and `precision` and the end as `end` and
  `end_precision`; the rule is `range:<start kind>..<end kind>`. An end
  before its start is no range (`range_end_before_start`), and a numeric
  range is not read. Two Roman months and a bare two-digit number all joined
  by hyphens (`III-V-46`, `I-II-46`, `VIII-IX-46`) are no date
  (`range_shaped_like_a_code`): the shape is also the slide codes'
  (`IV-29-68-4`), and nothing in it says which; the same months with the year
  marked by a period, an apostrophe or four digits read (`VIII-IX.46`,
  `III-V-'46`, `III-V-1946`). A range written apart from its year takes it
  under the rules above, on the line beside it (`"3-5.IX\n1946"`,
  `"3.IX-5.X.\n1946"`, `"VIII-IX\n1946"`, `"10.-12. Mai\n1946"`, via
  `split_lines`) or after a comma on its line (`3-5.IX, 1946`,
  `VIII-IX, 1946`, via `one_line`), when neither end states a year of its own
  (`date_notations.ranges(text, year)`; the parser does this only with
  `year_literal_decides`, so other callers read ranges as before). Date
  Visited From takes the start; Date Visited To takes
  the end (`checks.DATE_PART`: the check returns the end as that field's
  value, and a single date is its own end, so an explicit end date written
  whole still works). The literal for both fields is the whole range, one of
  the organiser's candidates. The G44 copy never fills Date Visited To from a
  range's start (`derive.fill`, which asks `date_lines.written_range`: a range
  whose year is beside it is a range too).

Not read at all, each left for a person: a numeric range (`3.9-5.10.1946`), a
year range (`1946-48`), a bare two-digit year alone (`46`), a lowercase
Roman numeral beside spaces (`12 vi 1946`), a month range shaped like a code
(`III-V-46`) and an all-numeric day and month followed by their year after
another separator (`4-25 1948`, `25.4 1948`). The tests
are `tests/test_date_forms.py` (a table of more than 60 forms in seven
languages, with start, end, precision and rule, and every date and code the ten
pilot labels write), `tests/test_date_months.py`,
`tests/field_research/test_date_split_lines.py`,
`tests/field_research/test_date_one_line.py`,
`tests/field_research/test_date_lines.py` and the three date tests at the end
of `tests/field_research/test_experts.py`.

## The catalogue number and the slide's QR code (2026-11-17)

An engineering change of the autonomy program (lane V2b); the owner has not
ruled on the barcode. It serves his words of 2026-11-17, "it is important to
not make mistakes because people wont trust it", and of 2026-10-09, "I think
our harness is not about only being strict, its about the process of
figuring it out given the data at hand."

The barcode label prints the catalogue number twice: as digits after
"FMNHINS" and as a QR code (Model 2, version 1, numeric; the payload is the
seven digits alone). The readers read the digits, about 12 pixels high on a
scan, and misread them: in the last full test (`units-wp26-20261115`) two
runs cleared 105526487 as 4486518 where its code says 4486618, and
`marked:fmnh_ins_number:*:text_only` held 6 to 10 of 30 specimens a run.
Lane V2 measured a decoder on the 100 slides of the truth set (off-repo
notes, 2026-11-17): zxing-cpp 3.1.1 asked for QR Code Model 2 decoded 98, all
equal to the truth, none wrong, and none wrong in 300,000 damaged synthetic
codes once anything but QR Code Model 2 with exactly seven digits is refused
(a looser setting found Micro QR codes in the damage). The repository's
wrapper, whose resize differs from the one V2 used, decodes 97 of the 100,
all equal to the truth.

1. **Decoded once, in the segment step** (`application/barcode.py`,
   `record`), on the specimen's canonical pixels: the whole image and a
   grey, lightly stretched copy, each at its size and at twice and three
   times it (a rung over 24 million pixels is skipped). A decode is accepted
   only when every symbol of every rung is a valid QR Code Model 2 whose
   text is exactly seven digits, all of them the same text, and one and the
   same label region of the slide holds every symbol's centre (a code on no
   label, such as a neighbouring slide's in the scan, is no decode). An
   accepted decode is one evidence row on the run (kind `derived`, source
   `barcode`, locator `check:barcode_decode`, on that label); its excerpt
   names the number, the decoder and its version and the first rung that
   decoded it, and its stored record every symbol found, with its box,
   version, error-correction level and the share of its error correction
   left unused. Anything else, a decoder failure included, stores nothing
   and never fails the step: the run goes on as it would have without a
   decoder. No network, no model. A missing decoder is logged once a process
   at warning level, and the application images' package check
   (`research_harness/package_qualification.qualify_packages`, run by
   `scripts/ci/build_runtime_image.sh` for the API and worker images)
   refuses an image without the pinned zxing-cpp. A run started on a
   person's regions keeps them and skips the segment step
   (`human_field_carry.py`, `completed_steps = ["segment"]`), so it is never
   decoded and its catalogue number is settled as before.
2. **Field research settles the catalogue number on it, and no other
   field** (`field_research/catalogue_code.py`, called by
   `step.apply_outcomes` after the field's expert answer and its labels'
   settlement). The expert is not told the decode. Since 2026-11-20 (lane
   V3; "The code gives the number" below) the catalogue number is the
   code's number whenever the run holds a stored decode whose payload is
   itself a well-formed catalogue number. The code is compared with, and
   gives, whole values only: the rule reads no number out of the readers'
   texts and breaks no tie among readings.
   - Rule 1, no value settled: the field is ambiguous, unresolved, not
     present or blank, or its settled text fails the identifier format.
     The field is settled with the code's number: supported, on the settled
     layer, its literal and parsed text the code's digits, on the code's
     label, the code row its one citation and deciding it. Its reason says
     no reading settled the number and the code gives it, and quotes what
     the readers read where the organiser gave the field candidates (whole
     candidates, quoted and never compared). The field's marked findings go
     and one `cleared:fmnh_ins_number:<label>` finding cites the code row.
   - Rule 2, a value settled whose literal does not write the code whole,
     whatever its parsed layer reads: the field takes the code's number in
     the same way. The readers' number is kept in the reason and by an info
     finding, `barcode_readers_differ:fmnh_ins_number`, that cites the code
     row and the rows that backed the readers' value; it is never a reason
     and never holds. No `barcode_differs` mark is made.
   - Rule 3, confirm, when all three hold: the settled value's literal
     writes the code whole (in the literal's letters and numbers alone,
     spaces, punctuation, marks and invisible characters dropped, the code's
     seven digits have no numeric character right before or after them); a
     reading of the code's label holds that literal at an occurrence with no
     number right before or after it (the same projection, applied to the
     text on either side); and the value's parsed and normalized layers are
     supported without the code. The code is then a source-class backing:
     the field's text_only or conflict mark becomes a cleared finding, the
     code row is cited as deciding it, and the reason says the code confirms
     the number. If the literal writes the code whole but another condition
     fails, nothing changes (an `unsupported_parsed` hold stays as with no
     code). Unchanged since 2026-11-17.
   - Rule 4, otherwise nothing changes: no stored decode; a payload that is
     no well-formed catalogue number, whole (`barcode.stored_code` already
     refuses anything but seven digits); for rules 1 and 2, a row that lies
     on no label of this run's image; a run not on the units path; a run
     with a transcript a person decided on any of its labels; or, for every
     part of the rule, a field a person holds authority over. In the
     transcript's case, where a settled value's number is not the code's,
     the value's reason says so and an info finding
     `barcode_person_differs:fmnh_ins_number` cites the code; a field no
     reading settled stays open.
   A person's authority over the field is read from the run's durable state
   through one function, the one the second opinion reads it through
   (`second_opinion.authority`): a decision made at the decision endpoint
   (`Run.person_decided_fields`), a decision a move or a new run carried
   (`step.human_keys`), a research selection a person locked, a field a
   location reassessment protects. No part of the rule acts on such a
   field: every part enters through one function (`catalogue_code._entry`),
   which stands aside for it, so the code neither confirms the field (its
   reason, citations and findings stay as research left them), nor gives
   it a number, nor replaces its value, nor notes a difference. The fifth
   record of authority, a transcript a person decided, is rule 4's own
   case: there the rule does nothing but its note. Research itself may ask
   the field's expert again on a Retry (main's task selection, unchanged
   here: it reads the carry alone); whatever that leaves is left. Codex
   round 2 found the confirmation still acting on a number a person had
   saved that equals the code's. That is all this rule promises: research's own answer on such a Retry can still replace
   what the person saved (a person's number by an open field when the expert
   names several), as on main. Codex round 1 and the sign-off review of
   PR #458 found the earlier head reading the carry alone, so that a number
   a person had saved at the endpoint was replaced by the code's on a Retry,
   and a later approval cleared the record by a person with the code's
   number.
   The rule's two info notes (`barcode_readers_differ`,
   `barcode_person_differs`) are replaced, never accumulated: a field
   researched again loses both before the rule acts, and at every finalize
   `barcode_readers_differ` goes once the field is no longer the number the
   code gave (`catalogue_code.forget_stale`, called by
   `step.finalize_fields`; a blocked run is not finalized, so there the note
   waits for the field's next research).
   Until 2026-11-20 the code confirmed or held and gave no value: rule 2's
   case was "contradict" (the value stayed, marked
   `marked:fmnh_ins_number:<label>:barcode_differs` and held for a person),
   and rule 1's case changed nothing. No run makes that mark now. A record
   finalized before keeps the mark until a new run (a settled field is not
   researched again), and the app still words it ("The catalog number read
   from the label and the number in the slide's QR code differ. Compare
   them."). A record finalized before with an open number does not need a
   new run: while it is in review with no blocker and attempts left, Retry
   researches its open fields again (a paid research pass for each of them,
   the number's expert included), and the code gives the number at the end
   of that pass.
   Order: `step.apply_outcomes` calls the rule in two parts. The
   confirmation (rule 3, and the note beside a person's transcript) runs
   where the rule always ran, after the field's settlement. Rules 1 and 2
   run as the function's last act, after the check stage. So on the attempt
   that researches the catalogue number no other field's check sees a
   number the code gives, and neither does the re-ask's trial, which
   applies the same outcomes on a copy of the run: every other field's
   value, state, reason and findings, and the number of expert requests,
   are those of the same run with no code row. Codex round 1 found the
   earlier head giving the number before the check stage: with the code
   0010001 and both readers writing "E. slope Mt. McKinley" over "Davao
   Prov. 0010001", the extent check counted the given digits as a settled
   field's text, marked the precise location and asked its expert again.
   A later research attempt of the same run, a stated residual (the
   coordinator's ruling of 2026-11-20, not the owner's words; proposals to
   give the number only in an attempt that completes research, or to keep
   and restore the value research left, were put to the coordinator and
   ruled out: the first does not remove the case for an operator's Retry,
   the second carries state). The coordinator's reasoning: within one
   research attempt the code's number is given last, so every other field's
   checks and the re-ask's trial see exactly what they see on main with the
   same inputs, which is what the review's findings required. On a later
   attempt of the same run (a blocked attempt and its retry or a Resume, an
   operator's Retry of a held record, a location reassessment) the catalogue
   number is a settled value of the run like any other, and other fields'
   checks count it as they do on main whenever a reading settled the number:
   the extent check no longer abstains for a number it can now account for,
   may mark `precise_location_extent`, and the existing re-ask rule may send
   its one request. That is the checks working on truer state, not a side
   effect of the order. It needs a label that writes the catalogue number on
   a locality line. A second research attempt was measured on 0 of the 151
   base and live runs and on 5 of the 100 r3 runs. A reviewer of such a
   record sees a flag on Precise Location with its extent reason
   (`marked:precise_location:<label>:precise_location_extent`: the locality
   is cut short before the higher place on its next line), as on any record
   whose readers settled the number. Also on a later attempt, the number's
   expert is not asked again, where on main the expert of an open number is.
   Residual risks: a code that is not this slide's catalogue number (a
   sticker that belongs to another specimen) now gives that number and the
   record clears with it, whatever the readers read; and such a code whose
   digits the readers also wrote confirms that number. None of the 97 truth
   slides that decode carries such a code.
   The rule builds no evidence row, and `step.apply_outcomes` calls each
   part of it inside a guard that logs any exception and puts the field,
   its findings and its decision back as the rules above left them. No
   other field changes on that attempt. The barcode label's own `unresolved_transcription` follows the
   existing rule (`step.scientific_reasons`): for a label whose transcript
   is unresolved it is raised when no field is drawn from the label, or a
   drawn field is not supported or not grounded in the raw readings, unless
   S1's duplicate-label rule sets it aside because each drawn field has a
   reason of its own; so it comes back where the catalogue number's mark
   goes and the label's readers still differ (105526522), and where the
   code gives the number. It does not hold the record then:
   `step.code_confirmed` reads a number the code gave as one the code
   confirms.
3. **On the last full test, replayed, under the rule of 2026-11-17** (R0's
   method over the stored runs, the decode attached as the segment step
   would store it; the replay of the rule of 2026-11-20 is below):
   `marked:fmnh_ins_number` falls from 6, 6, 10 and 9 specimens a run to
   1, 2, 2 and 0 (the 2s are 105526487's new `barcode_differs`; the 1 is
   105526446, which does not decode). 104 settled values are confirmed and
   2 held: the two wrong clearances of 105526487 (4486518, the code's
   4486618) now go to a person with the wrong value kept. Open fields stay
   open as on main (105526330, 105526617, 105526487, 105526335). No
   catalogue number is newly cleared wrong, and no specimen finished before
   or after.
4. **Breaking a tie on the code is not shipped.** Earlier heads of PR #452
   settled an open field on the candidate equal to the code. Review found a
   new way through it each round: a candidate clipped from a longer number
   ("0010001" of "10010001"), a digit of another script or a superscript
   beside the code, an invisible separator between them, a date joined to
   the number across a line break, and a spaced number that made research
   fail. A later attempt must hold all of these, and should compare the
   code with the first pass's reading units for the catalogue number (a
   whole unit's text), not search the raw text. The rule of 2026-11-20
   breaks no tie either: it picks no reader's text, and gives the code's
   own number whole; each of those cases is a test of it.

### The code gives the number (2026-11-20, lane V3)

**Authority.** The rule is the coordinator's ruling of 2026-11-20, not the
owner's own words. It is made under the owner's ruling of 2026-11-18, typed
after the coordinator reported the barcode rules holding records for a
person (quoted exactly in `docs/execution/autonomy/PLAN.md` section 4):
"rather than holding for a person, I'd like you to figure out how to resolve
these simpler things. I dont see a huge confluct there honestly. When we
have multiple readers etc it is natural to see different values, we shouldnt
be paralysed by it, our harness helps in clarifying anyway so the goal is to
self resolve." His words of 2026-11-17 bind it too: "it is important to not
make mistakes because people wont trust it"; so it was measured before it
was built.

The owner's words of 2026-10-26 bear on it as well. They are recorded in
`docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md`,
section 1 ("The pipeline, in the owner's words", line 32; that document says
its quotations are copied as typed), and read, exactly as that line has
them: "Finally first pass never settles, it has to go to harness(QR is a straight pass, ignore that, I’m talking about specimens data)".
Reading "a straight pass" as "the code's number is the catalogue number
without the harness settling it" is the coordinator's reading, not his
words.

**Why.** On the released code (e83c36fd) a record clears when its catalogue
number is settled. In the live confirmation run of that code, of the 52
records finalized when its rows were last read (2026-11-20, the run still
in progress), 12 were held: 4 with no number settled, 4 as
`barcode_differs` and 4 over label coverage. The slide's QR code had been
decoded on all 8 held over the number.

**Measured first** (free, before any code; the 100 truth slides):

| | Slides |
|---|---|
| The released segment step stores a decode | 97 |
| The decode equals the truth's catalogue number | 97 |
| The decode differs from the truth | 0 |
| No decode stored (105526336, 105526446, 105526715) | 3 |

In the stored base runs field research settled a number on 91 slides: equal
to the truth on 88, wrong on 3 (105526356 "4486748" for 4486749, 105526771
"448634" for 4486334, 105527231 "4465874" for 4485874; each already held as
`barcode_differs`), and none on 9, of which 8 decode.

**Replayed with the real code** (K1's replay, the decode attached; before is
e83c36fd, after is this change, replayed again after the review's changes
with the same figures; the second opinion fed its 95
stored answers on both sides):

| Stored runs of the 100 truth slides | Clear before | Clear after | Wrong catalogue numbers among cleared, before / after |
|---|---|---|---|
| Base (wp26 r1/pair 30 + base70 r1/pair 70) | 83 | 94 | 0 / 0 |
| r3 (reader A Kimi) | 71 | 83 | 0 / 0 |

Every record that moves goes from needs review to cleared, with the truth's
number. Base, 11: rule 1 on 105526455, 105526487, 105526563, 105526658,
105526686, 105526854, 105527051 and 105527241 (no number settled); rule 2
on 105526356, 105526771 and 105527231 (the three wrong numbers above, each
replaced by the code's). r3, 12: rule 1 on 105526322, 105526326, 105526330,
105526455, 105526523, 105526658, 105527144, 105527218 and 105527285; rule 2
on 105526356, 105526686 ("4456419" for 4486419) and 105527231. Still held
after, base: label coverage unconfirmed 4; `text_only` on 105526446, which
does not decode; one run that never finalized.

Nothing else moves, on all 200 replayed runs: every other field's whole
value is identical (0 differ), every finding that is not the catalogue
number's is identical, the second opinion's stored result is identical, and
a second finalize reads the same record. The check stage, run again on
each of the 189 finalized runs with the number as the code left it and as
research left it, makes the same marks and leaves the same reasons on all
189, so the given number would put no field back to its expert on these
slides. A replay researches nothing, so the expert requests are the stored
ones on both sides (base 4,142, r3 3,957). The reasons that differ are the
catalogue number's own, gone (base 16 `mandatory_unresolved` and
`identifier_format`, 3 `barcode_differs`; r3 18 and 3), and two open
reasons, new, that hold nothing: `label_unsettled:fmnh_ins_number` (base
10, r3 9) and the code's label's `unresolved_transcription` (base 2, r3 1).
They come from the field now being drawn from the code's label: an open
catalogue number cites no row, so no label counted it.

The records that newly clear bring their other fields' values into the
cleared set, unchanged. Scored as K1 scored them (`score_k1c.py`, the
product view, values shown as settled with no mark inside cleared records):
base 429 right and 5 wrong before, 505 right and 6 wrong after; r3 399 and
3 before, 477 and 4 after. The one more wrong value is on 105526455, which
clears on rule 1: Province/State "Utah" where the truth is "Idaho" (the
second opinion agrees with "Utah", from the printed heading "Siphonaptera
of Utah"). The value is the same before and after; before, the record that
carries it was held for its catalogue number. In the base run the app flags
it (`label_unsettled:province_state`: its label has one reader); in the r3
run it carries no flag.

On the live rows of the released code read on 2026-11-20 (52 rows, the run
still in progress; the rule's real function on each row's stored value,
readings and decode, the finalize predicted from the row's reasons): 40
clear before, 48 after, 0 wrong catalogue numbers before and after; the
decode equals the truth on 51 of 51; the 4 records still held are all label
coverage unconfirmed.

**What the stored rows prove, and what they cannot.** They prove the rule's
decision and the finalize on real stored fields, readings, regions and
images: `catalogue_code.settle` and `step.finalize_fields` are the real
code. They cannot prove: the path through `step.apply_outcomes` (its guard
and its order after the expert's answer), which the unit tests take; the
segment step's own decode on the released regions (the replay attaches a
decode made from the truth set's copy of the image and the stored run's
regions: 96 base runs and 87 r3 runs, against 97 on the released code's own
build); the reason's quotation of what the readers read (a stored open
number cites no organiser row, so no replayed reason quotes any; the live
rows, which keep the organiser's candidates, do); a field whose research
failed, and a person's decisions (none in the stored runs); the 1 base and
10 r3 runs that never finalized, left as stored.

**What follows from it.**
- The three slides with no decode are unchanged: two clear on their
  readings as before, and 105526446 stays held by `text_only`. The
  identifier-format hold stays for a number neither a reading nor the code
  settles.
- The value is on the settled layer with the code's digits as its literal,
  so the app shows it with the basis it shows for every catalogue number
  ("As written": the label carries the code and the code writes the number)
  and its cleared finding reads "Confirmed on Label N by the image, a
  source or a person"; the reason names the QR code. No app change.
- Nothing is stored beyond the field's value, its findings and its citation
  of the code row. A settled field is not researched again
  (`step.build_tasks`), so Retry and Resume keep it; a re-finalize, and so a
  history restore or a person's decision elsewhere, reads the same record;
  a person's later decision on the field replaces it, and from then on no
  part of the code's rule changes that field, its reason, its citations or
  its settlement findings (`catalogue_code._entry`, reading
  `second_opinion.authority`); the rule only removes its own earlier info
  notes from the run.
- A field whose expert failed with a retryable failure takes the code's
  number in that attempt; the attempt is blocked for its retry as before,
  and the retry does not ask the expert again (a later attempt of the run:
  "Order" above says what else it sees).
- A person's correction of a number the code gave, saved on the app's
  prefilled evidence, stays held after the person approves. The app prefills
  a correction with the field's own rows, and for a code-given number that
  is the code's own row, which does not hold the person's number: the record
  is held by `evidence_does_not_support_value:fmnh_ins_number`, where main,
  whose field cites the readers' rows, clears it by a person. It holds and
  never overrides: the value is the person's throughout. After a Retry
  research settles the readers' number on the readers' rows and the record
  is cleared by a person with the person's number (measured by the sign-off
  review of ccb026f9 beside origin/main, and by
  `test_a_correction_on_the_prefilled_evidence_stays_held_after_approval_until_a_retry`).
  A correction that cites a reader's row is not held.
- A person's approval given while the number was open is withdrawn when the
  code gives the number, as for any value research changes after an
  approval (#450's digest): the record clears by the system's rules and is
  not shown as approved by a person.
- A cleared record whose barcode label's readers differ carries
  `label_unsettled:fmnh_ins_number` among its open reasons (13 of the 94
  base records that clear; 3 of them already today, where the code
  confirms), so the app flags the field although the code decides it.
  `step.label_attention` is unchanged here; lifting that flag is a separate
  decision.

Tests: `tests/test_barcode.py` (codes made by zxing-cpp's encoder in the
test; no museum image is committed) and
`tests/field_research/test_catalogue_code.py` (115 cases: each rule and each
exclusion, the earlier reviews' cases, and that a run with no code row, and
every other field, settle exactly as before; every record of a person's
authority; and Codex's locality case, with the expert requests counted) and
`tests/field_research/test_catalogue_code_person.py` (17 cases: on the
published profile through the real decision endpoint, Retry and Resume, the
sign-off review's person sequences, and a person saving the code's own
number, after research and before it, compared with a record with no code
row; the rule's notes; and that the one call
in `finalize_fields` leaves a run with no code row equal in every stored
value). Sixteen earlier cases changed
expectation with the rule: each is kept and says what e83c36fd did.

## The second opinion (2026-11-18)

An engineering change of the autonomy program (lane F1). It serves the
owner's goal for the session, set with /goal on 2026-11-18: "take the
specimen digitization to full autonomy but ensuring that records are ever
cleared wrong and aren't unnecessarily waiting for a human review. It is a
human in the loop system but for areas that have failed to be resolved by
the autonomous system." The owner has not ruled on this mechanism or its
model; the coordinator's bar of at most 1 wrong value in 100 shown as
settled is the coordinator's proposal, not his. The structure below is the
coordinator's ruling after two review rounds on an earlier one that ran
inside field research (PR #456).

**How a value becomes settled now.** Field research settles a value as
before (its expert, its sources, the settlement rule, the checks); its code
is main's. A value it settled with text and no mark is then shown as settled
only when an independent strong model, filling the record on its own,
agrees with it. Otherwise the field is marked for a person on its own field;
no value, state, layer or reason text changes.

**Its own workflow step** (`field_second_opinion`;
`application/second_opinion_step.py`, `field_research/second_opinion.py`).
When field research's step, or its recheck, leaves the run finalized (no
retryable research failure pending, nothing further to ask) and a value the
second opinion answers for has no recorded verdict for its current value,
the workflow does not finalize the record yet: in the same save the run's
stage becomes `field_second_opinion` and its disposition none. The next
workflow step runs it with a paid step's lifecycle, and obeys every guard a
mandatory paid step obeys: its attempts, the run's limits on steps, external
calls (two, since a retry is possible), reserved tokens (16,000, as a mandatory paid step reserves) and
active time, a price row, and the cost ceiling with retained research
liabilities; then its reservation (two requests' worst case, USD 0.12 at
list, since a malformed answer is asked again once) on the retained research
cost, any monthly cap and the program's allowance, all inside one handler.
An intent is saved before the request: the stored result's status `asking`,
the attempt, a lease, the reserved cost, tokens and time, and no blocker, so
an open intent is never an unknown external outcome that blocks. The step's
deadline is the profile's external timeout, at most 90 s, and the worker's
deadline less research's margin; reading the crops runs in a worker thread
waited for until it; the request is bounded as the experts' are
(`asyncio.timeout`, over the gateway client's own timeout), and the client's
closing is cut at it too: a valid answer received before it stands even if
the closing then times out (logged). Its paid call is recorded under its own route and settled to what the
provider reported, or held in full when that is not known; the reported
tokens count in the run's tokens. The step then finalizes the record. Field
research never calls it and never reads its result.

**How its failure differs from a mandatory step's.** The step is optional.
A mandatory paid step that cannot be afforded, fails, times out or loses its
outcome blocks the run (processing blocked, a retry scheduled, or a
person's attention). This step never does. Whatever stops it ends it "not
obtained" with a code, and the record is finalized with the stage and
blocker field research gave it (finalized, none) and the not-checked marks
derived from the current values. Refusals before any reservation (switched
off, its attempts used, a run limit, no price row, money) reserve nothing; a
refusal or an error while reserving releases what a monthly cap held, at
zero, and is not retried. After the intent, a provider error (HTTP 402
included), a timeout, a second malformed answer, a request dearer than what
is left of its reservation or any exception is recorded and finalized at
once. The record's size limit: the stored answer is the 20 values and
their texts, each cut at 300 characters; with less than twice 16 KiB below
the record's limit nothing is reserved, saved or sent ("not obtained:
record_too_large"); a result that would leave less than 16 KiB, or whose
save is refused for size, is not stored ("result_too_large"), so a later
ordinary write is never the one to cross it; when nothing of the step can
be saved at all, it writes nothing of its own and the record is finalized
exactly as research left it, as main would save it (the marks not checked),
never left pending at an unchanged revision. Residual risk, accepted by the
coordinator: within a few bytes of the limit (0 to 4 bytes of graph headroom)
that finalized record is five bytes longer than the pending one (its
disposition) and the size-limit recovery blocks the run; a run that close is
blocked by its next write on main too. A person's decision while the intent is open
abandons it at the decision endpoint, and anything else that finalizes the
run abandons it first (`second_opinion.abandon`, from `finalize_fields`):
"not obtained: abandoned", its whole reservation held on the run and on
the ledgers alike; the step's own result then loses its save and settles
nothing, and the record stays as that decision or finalize left it. The
shared ledgers are settled only after the result's save succeeds. Every
outcome of a call that was sent (a timeout, a provider error after sending,
a second malformed answer, an answer too large to store, an abandoned or
lost call) is final for the values it asked about, and an outcome that sent
nothing never removes or replaces that coverage: Retry, Resume or a recheck asks again only for a
field it answers for now whose value was never asked or has changed since;
a field that left that set (a person took it) never causes it; a new run
asks afresh. A lost outcome (the
worker's deadline, a crash, the result's save failing) is found by the next
workflow step once the lease ends (the queue waits for the lease):
"not obtained: outcome_unknown", its whole reservation held, and finalized.
Each attempt sends one request, or two when the first answer is malformed;
a lost one is not repeated.

**One stored result** (`Run.second_opinion`, an optional key omitted while
unset): the status (`obtained`, `not_obtained` with its code,
`switched_off`), the attempt and route, and for each judged field (every
field but the catalogue number and the determiner's IRN that holds a
settled value when the step runs) the value it was compared with as the app
shows it (`compared`), the second opinion's value and the label text it
rests on, and the verdict (`agrees` or `differs`). The model's answer is
stored inline (a few kilobytes) with its labels and the padded labels.
Nothing else is written: no finding, no mark, no evidence row or blob, no
field. So evidence verification cannot fail because of it, and nothing
research reads (its findings, its fields) carries anything of it. A not
obtained result keeps the verdicts an earlier answer gave; they derive marks
only while the values they were given on are current.

**Marks are derived at finalize, never stored** (`second_opinion.reasons`,
added by `step.finalize_fields`, which every finalize runs: research's, its
recheck, the give-up, a person's decision, the approval). For a field
settled with a value, over which no person holds authority and which no
other rule's mark already holds:
`marked:<field>:<label>:second_opinion_differs` when the recorded verdict
for its current shown value is "differs";
`marked:<field>:<label>:second_opinion_not_checked` when there is no
recorded verdict for its current shown value (not obtained, switched off,
not run yet, or the value changed since it was judged); nothing when it is
"agrees", and nothing for the catalogue number or the IRN. A judged field
shown blank (not present, "not on the label" among them, not applicable,
or supported with no text; an open field's state already flags it) gets
`marked:<field>::second_opinion_differs`, with no label, when the obtained
and current answer gives it a value (lane H3, below). Because each mark is derived from the current value it cannot go
stale: a value research changes on a retry is "not checked" until the step
runs again, which it does when the recorded verdicts no longer cover the
settled values. A person's authority is one function
(`second_opinion.authority`): the fields a person decided at the decision
endpoint (`Run.person_decided_fields`, written there for every field,
research-candidate, authority and taxonomy decision whatever its payload,
the app's own included), carried decisions, research-selection locks, a
person's transcript binding the field's label, and a location
reassessment's protected fields.

**Records stored before this change.** The specimen's review audit names
each decision on a field (`review_field`, `review_research_candidate`,
`review_authority_resolution`, `review_taxonomy_resolution`, the run's id in
`before`, the field in `after`). Where a record is loaded
(`active_graph.unpack`), those of its current run that the endpoint did not
record on the run are adopted into `Run.person_decided_fields`, once: the
endpoint now marks its own event `person_decided_field`, and such an event
is never adopted. A record with nothing to adopt loads exactly as stored.
Residual risk: a legacy decision followed by a history restore to a
revision before it is adopted again at the next load (its event carries no
mark); production's 33 records carry no person's decisions or approvals, by
the coordinator's read-only check of 2026-11-18, so none is affected today.

**A history restore** returns the run to the restored revision's own state,
including that revision's stored result and its person-decided list. A
decision a person made after that revision is undone by the restore itself:
this is what a restore is, not a defect. The restored reasons are what the
derivation gives on the restored run.

**A person's approval is the person's.** As main skips its own marks once a
person approved (`scientific_reasons`, `human_approved`), the second opinion
contributes no code to an approved run and is not due on it (no paid call);
an approval withdrawn or superseded by a later value change
(`lane.settle_approval`) brings the marks back by the same condition. A
person's decision while the record waits at `field_second_opinion` is
handled as main handles it on a record whose research is complete: an open
intent is abandoned, and the same whole `refinalize` decides the record;
the step's own finish also runs that whole finalize, never only its codes.
The one family research adds after its own finalize
(`location_reassessment_unconfirmed:*`) is kept because PR #455 records it
durably (`run.pending_review`, by `_retained_reassessment`) and every
finalize derives it; the finish carries no reason across, so the durable
state decides (no duplicate; nothing stale once a reassessment that settles
the family or a person's approval has cleared it). A record resumed or retried while it waited
for the step goes through research's recheck as on main (the same refinalize), then to the step if
it is still due: at most one paid call for values it has not asked about.

**Runs classified before this change** have no price row for the second
opinion in their pinned profile: on Resume or Retry the step ends
`unconfigured` and their settled fields read "not checked" until a new run
(an approved record stays cleared). HTTP 402 counts as a sent call, final
for its values, and is costed at the request's worst case by main's meter
rule for non-429 errors (`budget.py:264`).

**On the published profile a mark is a flag on its field, not a hold.** The
second opinion ships with the clearing rule (work package K1, the same pull
request): on the published profile only the catalogue number is mandatory and the second opinion never judges it, so
its marks are optional fields' doubts (`step.split_reasons`, at
`finalize_fields`, which the step's own finish reaches through `refinalize`).
An agreed value is shown as settled; a differing or unchecked value is
settled and flagged on its field (`open_reasons`, the API's
`open_reason_codes`, which the app reads for a field's attention); the
record clears on its catalogue number. Not obtained or switched off, every
settled value it answers for is flagged "not checked" and the record still
clears. A run is judged by its own pinned profile: on a run whose profile makes a field mandatory, any mark on that field holds the record, the second opinion's included; a new run (Reprocess, the app's "Start new run") takes the published skeletal profile, where only the catalogue number is mandatory and no second-opinion mark can hold. A record stored before this change keeps its old mandatory set on Resume or Retry: the second opinion ends `unconfigured`, its settled fields read "not checked", and those marks hold under the old profile; it clears by the new rule only on a new run, or by a person's approval. A record held for another reason (its catalogue number unsettled,
marked or of the wrong format; label coverage unconfirmed; research given
up; a person's pending approval or another standing hold) stays held
whatever the second opinion says (`tests/field_research/test_second_opinion_skeletal.py`).

**An agreed value and an agreed blank carry no flag (2026-11-19, work package F2).**
The name is the work package's; what the rules do is remove named reason
codes, and a field another open reason still names stays flagged.
Two rules, the coordinator's rulings on lane H1's measurement over the 100 truth
slides (not the owner's words; `docs/execution/autonomy/PLAN.md`, F2), derived
at every finalize from the stored result and the run as it is now
(`second_opinion.unflagged`, called by `step.finalize_fields` once the reasons
are split and `label_attention` and `incomplete_reasons` have added theirs).
Nothing is stored or carried; only the optional fields' doubts
(`run.open_reasons`) are shortened, so no reason that holds a record, no
value, state, reason text, mark, finding or evidence row changes, and no
record clears or holds differently.
- Rule A, an agreed value: `label_unsettled:<field>` is not an open reason
  for a field settled with a value whose recorded verdict for its current
  shown value is "agrees" (the same currency test the marks use: a value
  changed since it was judged is not agreed). The three date fields are
  excepted and keep the code. Every other code naming the field stays, a
  mark among them, so a field another reason still names stays flagged.
  Rule A is skipped on a run any label of which one reader read (a reason
  of that finalize, holding or open, is
  `independent_observations_missing:<label>`: `second_opinion.one_reader`,
  record level, with no tracing of which field is drawn from which label):
  every agreed value of such a run keeps its flag. For Habitat alone
  (`second_opinion.READERS_MUST_WRITE`, lane H4) rule A needs more: every
  reader of the labels the value rests on writes the value's text, letter
  case and spacing aside (`agreement.reader_writes`); where a reader writes
  another text there, the Habitat keeps the code ("A host the label writes
  is the Habitat", below).
- Rule B, an agreed blank: `mandatory_unresolved:<field>` and
  `label_unsettled:<field>` are not open reasons for a field that is blank
  (`not_present`, nothing shown) where the second opinion's own answer for
  the field is blank too: the stored `answer` keeps every one of the 20
  fields as `{value, evidence}`, and a blank is a null value whose text does
  not start with UNSURE (`read_answer`'s rule). Verbatim D/T/S and Habitat
  are excepted and keep their codes whatever the second opinion says.
  `research_incomplete:<field>`, `taxonomy_unresolved` and every mark stay,
  so a blank field one of them names stays flagged: a blank Taxon the second
  opinion also leaves blank loses these two codes and keeps
  `taxonomy_unresolved`, and the app still flags it.
  A blank where the second opinion reads a value keeps its codes (a
  missed-value signal). A one-reader label does not stop rule B.
- Neither rule applies: to the catalogue number or the determiner's IRN
  (never judged); to a field the run's own pinned profile makes mandatory
  (there the code holds the record as before, on the published profile and
  on an older pinned one alike); to a field a person holds authority over
  (`second_opinion.authority`); on a run a person approved; on a run not on
  the units path; while the stored result is not obtained, switched off or
  unconfigured, or its intent was open (an open intent is abandoned first:
  not obtained); or while a value the step answers for has no verdict for
  its current value (`second_opinion.due`: the record's flags are then as
  without the rules until the step has run again).
- Rule B also needs the answer current for the run
  (`second_opinion.answer_current`), by what the stored result and the run
  record: the labels it was asked on (`labels`) are the run's labels in the
  step's order; no label's transcript is a person's (`Transcript.actor`: the
  request reads the two readers' texts only); and no reading is newer than
  the request (each `Observation.created_at` against the stored `at`, both
  read as ISO times with an offset). What it cannot establish is not
  current, and the flags stay. A correction of regions and a Reprocess start
  a new run, which holds no stored result.
Two conditions are the coordinator's rulings of 2026-11-20 on the live
confirmation rows, which held what the replay did not. The one-reader
condition on rule A: an agreed value needs two independent readings behind
it. Slide 105526455 settled Province/State "Utah" for Idaho from a label one
reader read (a printed "Siphonaptera of Utah" form with "Ida" written on
it); the second opinion, given that one reader's text, agreed, and rule A as
first ruled would have lifted the value's only flag. Rule B does not take
the condition: a blank is no wrong value shown as settled, the second
opinion reads the crops itself, and the 63 blanks it agreed on the replay's
one-reader records were all truly absent. Habitat as rule B's exception: a
bare host name is a known miss of field research and of the second opinion
alike (lane H1: 48 blank Habitats where the truth has a host; slide
105526418, "CALLOSPERMOPHILUS", blank, agreed blank and missed), so their
agreement on a blank Habitat proves nothing until hosts are filled.
Measured on the 100 truth slides (the stored runs replayed on this code with
the stored second-opinion answers, each run finalized with and without the
rules: `~/specimen-golive/autonomy-program/F2/`): of 200 runs none differs in
anything but its open reasons; on the 83 records that clear, rule A removes
146 flags, all on right values, and rule B 125, all on truly absent values;
a cleared record's flagged fields go from 11.16 to 7.89 on average. Known
limits: small samples per field type; the second opinion sees both readers'
texts, so a misreading both readers share can be agreed. Tests:
`tests/field_research/test_agreed_no_flag.py`; the two cases at the end of
`tests/fixtures/field_attention.json` (no code, no attention; no change in
the app).

**A blank the second opinion fills is flagged** (`second_opinion.filled`,
called by `step.finalize_fields` on every finalize after the reasons are
split and the holds derived; lane H3, the coordinator's ruling of
2026-11-21 on lane H2's measurement, an engineering fix, not the owner's
words). A judged field the record shows blank (not present, "not on the
label" among them, not applicable, or supported with no text; an open field
is skipped, as its state already flags it) for which the second opinion's own answer gives a
value gains the open reason `marked:<field>::second_opinion_differs` (no
label: a blank has no value to rest on one), so the app flags the field.
Only a flag: the value stays blank (the second opinion's value is a
possibility, never evidence), nothing is held, `cleared_by` and the
disposition do not change, and the field's state, reason and evidence stay
research's. The field's stored reason and its check row
(`check:not_on_label`) still say "Not on the label": they record what
research's expert answered and what the readings were checked for, and a
rule derived at finalize does not rewrite them (rewriting would carry state
from one finalize to the next). The mark beside them says that an
independent reading gives a value, and the app's field row shows the mark's
words ("An independent reading of the labels gives a different value. Check
this value against the image."). On a blank its first sentence is true (the
reading gives a value where the record shows none); the second asks a
person to check "this value" on a field that shows none, which states nothing
false but reads oddly; no app wording changed. The conditions are rule B's and the marks': the run is on the
units path and no person approved it; the result is obtained and current
(`answer_current`) and the step is not due; never the catalogue number or
the IRN, a field the run's own profile makes mandatory (so it never holds),
a field a person holds authority over, or a field that already needs
attention by `review_summary.attention_fields` over this finalize's reasons
and the fields' states (a field is flagged once). This reverses, for this
one case, the limit PR #455 wrote (marks only on a field settled with a
value); PR #457's test already called such a blank "a missed-value signal",
but a blank `step.mark_not_on_label` marks has no flag to keep. Measured
free (`~/specimen-golive/autonomy-program/H3/replay_h3.txt`, the stored runs
of the 100 truth slides finalized again by this code with their stored
answers, `H3/scripts/replay_h3.py` and `compare_h3.py`): 53 flags gained,
all Habitat, all on cleared records, all where the truth has a value (the
second opinion's value right by `second_opinion.same` on 46, wrong on 7),
none where the truth is blank; dispositions and `cleared_by` unchanged on
100 of 100 and every part of the stored run but its open reasons equal on
100 of 100; flagged fields per cleared record 7.55 to 8.08 (the app's
mapping, the IRN left out). Residual: 5 cleared records whose truth has a
Habitat keep it blank with no flag, as the second opinion gave no value
there (105526348, 105526356, 105526392, 105526468, 105527285). Tests:
`tests/field_research/test_blank_second_opinion_fills.py`; one case in
`tests/fixtures/field_attention.json` and one in the app's
`second_opinion_test.dart` (no change in the app's code).

When the mark is current. The mark is derived at finalize, as every open
reason is. Guaranteed: a save that follows a finalize of the run as saved
carries what a fresh finalize of that state gives (the G51 reviewer, round 2: of the 249 finalized states of his round-2 sequences, 247 equal a fresh finalize; the
other two are the restore window's, below). Not guaranteed: a save that does
not follow a finalize keeps the open reasons of an earlier finalize, on
origin/main and on this branch alike and for every open reason, until the
next finalize, which recomputes the mark from the record as it then is and
may give it or give none. The guarantee holds one way only: a save with no
finalize can still equal a fresh finalize (after Retry with no decision, or
a restore to a revision no person approved: the G51 reviewer, round 3). The
worker ends some such windows when it reaches a finalize; a run it blocks
first keeps the stored open reasons while it is blocked, and some windows
last until a person acts, which may be never.

Known examples, found in the reviews of this PR; the list is not claimed
complete:

- a history restore (`history_restore.py:62`, `api.py:1573-1580`): the
  record is held for review, or blocked when the restored run had a blocker,
  and then stays blocked until the Retry or Resume after the repair (a decision does not end that window; an approval ends it only when the blocker was a lost blob's `evidence_integrity_failure`);
- a decision other than an approval or a capability deferral that arrives on
  a run whose stage is not `finalized` (`api.py:2423`; an approval reaches the finalize at any stage, where `step.refinalize` still returns early on a blocker other than a repaired `evidence_integrity_failure`, and a decision arriving at `field_second_opinion` is moved
  to `finalized` first, `api.py:2092`): after a transcript decision (stage
  `parse`); after Retry or Resume before any worker step (stage `pending`);
  on a paused or cancelled run, at rest, possibly indefinitely (the worker
  returns at `workflow.py:726`; a person resumes, retries or approves it,
  and reprocess is named here from the code only: it was not run); on a
  blocked run, until the Retry or Resume after the repair (`step.refinalize`
  returns early on a run with a blocker, `step.py:4846`);
- a field decision on the taxon or another looked-up field after a
  transcript decision removed field research from the completed steps
  (`api.py:2247`, then `api.py:2163` sets stage `lookup`), found by Codex in
  round 3; the saved revision keeps the mark beside the stored second
  opinion, and the worker's finalize removes it (tested);
- graph-limit recovery (`active_graph.py:237-264`, used by
  `save_recoverably`): when a save exceeds the record's graph or snapshot limit, the working copy is discarded, the prior snapshot is reloaded, its approval withdrawn, and it is saved `processing_blocked` with the limit as its blocker and no finalize, found by Codex in round 3; run by the G51 reviewer in round 4: an oversized decision returns 200, is discarded, the prior snapshot is saved blocked and its approval withdrawn; Retry ends it;
- a worker block the worker does not end by itself, for example
  `step_budget_exhausted` after a decision on a pending run
  (`workflow.py:921`, `workflow.py:978`; later steps return at
  `workflow.py:726`; automatic recovery does not take a completed-research recheck, `workflow.py:2141-2147`), found by Codex in round 3; run by the G51 reviewer in round 4: with the step allowance used up (set by a direct save standing in for repeated rechecks), Resume, a Habitat decision and a worker step left the run blocked with the mark on the person's field; Retry, Resume and an approval did not end it.

When a finalize ends a window it recomputes the mark. Tested here: after a
restore to an approved revision, Resume gives the mark, and approving again
gives none (an approved run gets no mark) while the record clears by that
person's approval; after a transcript decision the worker's finalize removes
it (the answer is no longer current); after a decision on the marked field
(on a paused or cancelled run, after Retry or Resume, while a blob is lost),
the finalize that follows gives no mark on that person's field, and the
record then waits for that person's approval
(`standing_holds.person_acted`). The G51 reviewer's notes add (rounds 2 and
3): after a restore, a decision on another field also gives the mark, and a
decision on the field itself gives no mark and does not clear the record,
which stays `needs_human_review`, held by `history_restored_requires_review`
and `human_approval_required`; an approval inside the transcript window ends
it through the ordinary policy's finalize, as on origin/main; after a lost
blob, a field decision after the repair does not end it (the run is still
blocked), an approval does.

Measured, not proven: in the G51 reviewer's round-4 sequences (`reviews/verdict_463_g51_r4.md`: 86 sequences per tree through the API and workflow, 249 noted states) no state was `cleared` with a stale or missing mark, and Codex's
static trace of round 3 found no counterexample. origin/main's own open
reasons wait the same way (the G51 reviewer's probes of origin/main,
`codex_seq_main.txt` and `windows_main.txt`: after the restore, 12
`label_unsettled` codes a fresh finalize lifts and PR #455's
`marked:city:<label>:second_opinion_differs` missing; after the transcript
decision, 8 stale codes, #455's mark among them; after Retry and a decision,
#455's mark on a person's City). Making these saves recompute the open
reasons is a change to origin/main's mechanism for every reason, ruled out
of this PR by the coordinator (a recorded follow-up). The windows section of
`tests/field_research/test_blank_second_opinion_fills.py` pins several of
these windows through the real API.

**The request.** Route `second-opinion-muse-spark` (Muse Spark Open 816B on
Baseten through the Hugging Face router; tool choice required, 8,000 output
tokens, no request options: the fields benchmark's pins; USD 1.25 in and
4.25 out per million tokens at list, a row of the published price list,
whose version is now `pilot-prices-2026-11-18`). The system message is
`field_research/prompts/second_opinion.txt`, the benchmark's instruction
byte for byte (sha256 `842a498c...`, pinned in code; it is not yet mirrored
in Logfire, which needs the owner's variables key). The user message holds
every label crop in label order, then each label's reader A and reader B
texts. The answer is one forced call of `record_fields`, which must satisfy
the tool schema field by field: all 20 fields, each an object with exactly
`value` (a string or null) and `evidence` (a string); anything else (a
missing field, the catalogue number or the IRN included, a null entry, a
bare value, an extra key) is "not obtained: malformed", with no verdicts.
The request carries nothing of the pipeline's fields. A crop longer than
40 times its width (or the reverse) is padded with a white border, centred,
to exactly 40:1 (Baseten refused 3 of the benchmark's 70 requests for it);
the same crop always gives the same bytes and the result lists the padded
labels. Not measured: those three slides were never answered.

**The comparison**, one strict rule per kind of field, between the value
the app shows (normalized, else parsed, else literal) and the second
opinion's: dates (Date Visited From and To, Date Identified) as ISO dates
the calendar accepts, equal at the same precision; numbers (the four
elevations) as plain decimals, equal once rounded to the hundredth; text
(every other field) equal once accents are removed, case is folded and
every character that is not a letter or a digit is dropped, except a "." or
"," between two digits and a "-" or "+" directly before a digit, which are
kept ("1.5 km" is not "15 km", "14,5 km" is not "14.5 km", "-80" is not
"80"); Province/State and County set aside one trailing unit word ("prov",
"province", "department"; "county", "co"). A second opinion that gives no
value (the label does not carry the field, or it is unsure) differs. Where
it differs from the benchmark's "agree" (`analyse_fields.py`): no 0.85
similarity on Precise Location, no country alias table, dates and numbers
must be well-formed.

**Measured basis** (the fields benchmark, 2026-11-18, free analysis of
paid answers, `~/specimen-golive/runs/autonomy-fields-20261118/`; cleared
records of the K1 replay with the QR code, locality compared as K1 does):
with Muse Spark's second opinion on the 67 slides it answered, the base
pipeline's 355 unmarked values held 39 wrong; the 299 the benchmark counts
as agreed held 5. With the stronger reader (r3): 336 and 33; agreed 280 and
2. This code's replay over the same stored answers (lane F1's notes,
`replay_f1b.py`: the step's `obtain`, `record` and `derived`): base
pipeline 273 values still shown as settled, 4 wrong (9 with the locality
compared exactly; judged fields only, without the 55 never-judged catalogue
numbers, 4 of 218, 1.8 %, 95 % upper bound 4.2 %); 60 newly marked differs
(35 wrong); 22 not checked (four
stored answers refused as malformed, all 22 values right). r3 pipeline: 265
shown, 2 wrong (6 exact; judged only 2 of 217, upper bound 2.9 %); 58 differs (31 wrong); 13 not checked. Small
samples: 2 wrong in 265 has a 95 % upper bound near 3 %. Against the first
structure's replay, 11 base cells moved from shown to not checked: the
strict answer rule refuses two more stored answers (105526322 has null
entries; 105526459 omits the catalogue number).

Known limits: a misreading both readers share and the second opinion copies
stays agreed (two dates of two slides in the replay). Cost: about USD 0.012
a specimen at list on the benchmark (0.038 at most), one more provider
dependency per specimen; while the provider's credit is spent every record
ends "not obtained" and holds.

Tests: `tests/field_research/test_second_opinion.py` (the comparison's
table, the strict answer, the route and price; through the workflow: the
step after research and before the record is finalized, research's result
equal to main's with the step present, the request's content, the stored
key's shape, derived marks, a value changed after it was judged, another
rule's mark, the units path only; every way of not obtaining it, each
leaving the stage and blocker research gave the run; a worker deadline in
the request and the result's save failing, each found after the lease; a
refusal on money, a request dearer than its cap, the attempts used; no step
while research has a retry pending; the feet inference on a retry equal to
main's; a person's field with the app's payload across a retry; a person's
transcript; carried decisions, locks and protected fields; a legacy record
adopted at load; a history restore; a recheck that asks nothing; a result
over the size limit at its boundary; an approval while the intent is open;
a reservation that raises; a crop read and a client close that hang; the
token budget; a malformed answer asked again once). Every
other test runs with no derived mark (`tests/conftest.py`).

## A host the label writes is the Habitat (2026-11-21, lane H4)

Two rulings of the coordinator's (not the owner's words; `docs/execution/autonomy/PLAN.md`, "H4", has the authority,
the measurements with their sources and what is left open): the habitat expert answers a label's host as the Habitat
value, as written, by a change confined to its own instructions and the habitat field's acceptance code; and one
condition inside rule A of "The second opinion". The ontology's `host_marker` notation still says a host has no field
("[no field]", in every expert's instructions and the first pass's) and its comment that none of the 20 fields holds a
host stands; the museum's published records hold hosts as associated taxa. Where a host belongs is an open point for
the owner, not a ruling of his.

**The brief** (`prompts/habitat.txt`, its lines 6 to 10; no other prompt text changed: 33 of the 34 rendered texts are
byte-identical to origin/main 3eb37c11's). A host is this field's value, and the notation's "[no field]" and "never
its taxon" mean only that a host is never the specimen's taxon. A host is the name after a host marker, on its line
or the lines right below it. A host needs no marker: the specimens are insects, so a name the expert knows for a
mammal's, a bird's or another non-insect animal's is the host wherever it stands, and a missing marker, a place where
an identification would stand, or the units', the organiser's or `other_fields`' taxon advice is no reason to answer
`label_lacks_value`; a name it cannot place (an abbreviated genus it cannot expand, a word it does not know) is not
guessed: `sources_cannot_resolve`. The name is copied whole, a written "Ex.", "Ex:", "ex" or "On" kept, a heading
"Host" or "Host:" left out; it ends before another field's text; `value` and `authority_id` stay empty, the literal
being the value. A host or a habitat the label writes over consecutive lines may run over them, whatever the shared
rules say of two lines.

**The acceptance check, for the habitat alone** (`field_research/agreement.py`; the expert's check and the step
repeat it as for every field).

- `ACROSS_LINES` holds `habitat` beside `precise_location`: a habitat literal that holds a line break is a run of
  whole words over consecutive lines of each reading it names (`written_runs`, `runs_across_lines`), an answer that
  gives a space for a line break is read as the text every reading it names writes so (`across_lines`), and a
  literal over lines holds whole organiser candidates in their order and cuts none (`_cut_candidate`, the precise
  location's code path, which no test here exercises with habitat candidates). The value
  keeps the line break as the readings write it, as a precise location's does. A word the label breaks with a hyphen
  keeps its hyphen. Readers that write the lines differently write no one text, and an answer naming both is sent
  back. The first line alone of a two-line name, and a name with the next line added, still pass this check: only
  the brief tells the expert otherwise, and the guard on text another field holds (`step._taken`) refused the one
  such answer of the measured run that ran on to a state's name.
- `literal_refusal` refuses a habitat literal that starts with the heading "Host" (`HOST_HEADING`,
  `host_heading`: the whole word, letter case and the punctuation around it aside; "Hosts" and "on host" are not it):
  the expert is sent back with the reason, and where the step applies such an answer the Habitat stays unresolved.
  Never rewritten. The check runs where an answer is applied; a stored value is not checked again by a finalize.

**The condition inside rule A** (`second_opinion.agreed`, `READERS_MUST_WRITE`). An agreed Habitat loses
`label_unsettled:habitat` only where every reader of the labels the value rests on writes the value's text, letter
case and spacing aside (`agreement.reader_writes`: whole words, so "Mus" is not written in "Museum", and a letter or
a punctuation mark more or less is another text). The case it answers: the two readers write a host's species
differently, the first pass's unit names one reader's text so the label settles cleared, and the second opinion
gives that same text; the label's doubt is then about the value itself. It does not catch a Habitat every reader and
the second opinion read alike and wrongly.

**Measured** (PLAN.md "H4" has the tables). Two paid habitat-only reruns on the 99 cleared records of the 100 truth
slides, launched by the coordinator: f54e941d (USD 0.2034 at list) and a28cf3f5, which ships (USD 0.2076;
`~/specimen-golive/runs/autonomy-habitat3-20261121/logs/analysis.txt`): Habitat right on 49 (10 on the stored
records), wrong on 6 (6), every wrong or partial one flagged, missing on 37 (76), of which 35 flagged, right blank on
7 of 7; no record's disposition, `cleared_by`, holding reasons or other field differs from the same record finalized
with nothing researched. In both runs the second
opinion's judgement of a new Habitat was taken from the answer the stored run already holds, through the released
step: by its contract its request holds none of the pipeline's fields (`second_opinion.py:26-27`), so that answer is
an answer to the same request; it is one stored sample, not a new call. Free: the real finalize replayed on the stored runs of the
100 truth slides gives origin/main's record on 100 of 100
(`~/specimen-golive/autonomy-program/H4/replay_h4_v2.txt`); the rule A condition adds one flag on that run's answers,
on its one wrong Habitat that would have had none, and none on its 49 right ones (`H4/flag_rule_run3.txt`).

**Known limits.** 22 of the 37 missing are names the expert still answers `label_lacks_value` for; 10 of those
explanations say that no host marker stands before the name (a rough keyword count,
`~/specimen-golive/autonomy-program/H4/lacks_explanations.txt`), which the brief says is no reason. The same printed
label went both ways within a run, and 2 Habitats that were right in the first of the two runs were missing, and
flagged, in the second. 10 are `one_reader` refusals (one reader's text that nothing else backs; the rule is
unchanged). Three of the six wrong values are partial names. A stored Habitat
can hold a line break; the app's field row shows every line when open and at most two lines when collapsed
(`fields_panel.dart:488`; `specimen_ui`'s `UiDisclosureStyle.summaryMaxLines`), as for a precise location (read from
the code, not run for this change). `prompts/precise_location.txt` still says a locality may run over lines "unlike
any other field"; it was not edited, so that every other prompt text stays byte-identical. A record researched
before this change keeps its Habitat until research asks the habitat expert again: a new run (unless a person
decided the field), or a Retry that requeues field research on a record in review
(`workflow.requeue_completed_field_research`), and on a Retry only where the stored Habitat is not a settled value
(`step.build_tasks`). Tests:
`tests/field_research/test_host_is_the_habitat.py`, `tests/field_research/test_agreed_habitat_readers.py`.

## Fields the label does not state (owner, 2026-10-09)

The owner decided two cases in the schema session on 2026-10-09. On whether
a required field the label doesn't state should keep going to review or
clear as "not on the label": "clearing as not on the label is fine" (A). On
whether a taxon with no genus should clear as written, marked "unmatched":
"ok" (B). The list below is the schema session's engineering reading of A
(`~/specimen-golive/status/schema-harness-plan.md`, H6 item 5); the owner
may narrow it.

**The list (A).** It is kept in `field_research/contracts.py`
(`NOT_ON_LABEL`), keyed by the collection profile's id and version
(`zoology_insects_slides` 1.0.0), and the step reads it through the run's
own pinned profile. A Retry keeps the run's profile snapshot, so a key added
to the published profile would never reach it; the published profile, its
digest and its byte pins are unchanged. Another profile, or a new version of
this one, gets its own entry.
- On the list: county, city, collection code, collection method, date
  identified, habitat, the four elevations and precise location.
- Never on it, whatever a profile lists, because their absence usually
  means a reading failed: catalogue number, country, the two collecting
  dates and collectors; and the taxon, which follows B. Province or state,
  verbatim D/T/S and identified-by IRN keep today's behaviour.
- WP 2.R of the reading-units program (2026-11-15) checked each field the
  list leaves out against its sources and added none
  (`tests/field_research/test_review_rules.py` pins them). The owner's answer
  named no fields (the schema session's record of it, the same file). The
  catalogue number is one a person finds on the label and its barcode (PRD.md
  12.4, "How a person resolves each group today": "The label and its
  barcode"), a barcode label each drawn slide of the reference set holds
  (`docs/execution/units/PLAN.md` section 1). PRD.md
  12.4's table of v1 keys from v2 parts fills a country and a province with
  no condition, a county only "where the country has one" and a city "when
  there is one"; a country or a province the label does not write is filled
  by derivation from settled fields (`prompts/country.txt:9`,
  `prompts/province_state.txt:11`; G37), as Date Visited To is from Date
  Visited From (G44). Verbatim D/T/S
  holds a date with no exact day or a time of day (PRD.md 12.4, the
  collection manager's answer of 2026-10-07), and the row's checks find its
  text only through what the organiser found for it (`step._organiser_texts`):
  in units-wp15c's four runs that was nothing on 105526327, whose label
  writes the month "XI.46". For the collecting date and the
  collectors no source settles that their absence clears, so they keep
  today's result.

**When a listed field clears as not on the label.** Only when all of these
hold (`step.mark_not_on_label`, after the derived values, so a derivable
elevation is derived first, and only for a field a person has not decided):
1. Its expert itself answered that no reading states it
   (label_lacks_value), with no failure, in this attempt; or, for a precise
   location, its expert's answer gives only an administrative marker
   beside the places settled (below, "An administrative marker is no
   precise location"); or, for a county or a city, its every text is a
   settled place's above it (below, "A county or a city that is only a
   settled place's text"). Every field but
   the identified-by IRN gets its expert (step 2), so the answer is the
   model's; no lookup is required, since a field such as the habitat has no
   source to search. The shared brief has the expert answer
   label_lacks_value for a value the labels do not write, a value it could
   only infer or look up included (a town for labels that name only a
   province or a mountain, an identification date for labels whose only
   date is the collecting date), and never sources_cannot_resolve; the city
   and date-identified briefs say so for their fields. (In the real run of
   2026-10-09 105526326's city and 105526329's date identified were answered
   sources_cannot_resolve where the labels lack them.)
   The resolver's fallback qualifies only for a county or a city whose
   every text is a settled place's above it (below), where the names the
   expert's lookups asked about stand for what it tried. Its reason, when every answer the
   expert gave failed its checks, is "None of the expert's answers passed
   the checks against the readings and the sources' answers.", and no
   fallback's reason ends with a note of a source the expert could not
   reach, as it is no answer of the expert's (the second rerun of
   2026-10-18 read such notes as Getty TGN's fault). Otherwise the resolver's fallback, put in place of an answer the expert never gave
   (out of attempts with no checked answer when asked once more, or answers
   that failed their checks), is sources_cannot_resolve, so it never
   qualifies. An expert's answer when asked once more is its own and
   qualifies.
2. Its value is still not present.
3. Label coverage is confirmed, every label has two or more readings, and
   every reading has text.
4. No part of any label is unreadable: no reader's unreadable span, no
   transcript marked unreadable, and no placeholder for an unread word
   anywhere in a reader's, a reading's or a transcript's text
   (`checks.shows_placeholder`, the one test rule B reads too). The
   placeholders are "[unreadable]" (the marker the reader prompt asks for
   in place of each unreadable span), "(unreadable)", "[illegible]",
   "(illegible)", "[illeg.]", "[illeg]", "(illeg.)", "[unclear]",
   "(unclear)", "[?]", "???", "[...]" and the ellipsis character, anywhere
   in a text, in any case (`checks.DOUBT_PLACEHOLDERS`); the words
   "illegible" and "unreadable" standing alone, in any case
   (`checks.PLACEHOLDER_WORDS`; never "illegibly"); exactly three periods,
   with no period right before or after them ("Mossy ...", "Mossy...",
   "(...)"), unless right after the word "etc", in any case ("etc...");
   and three or more periods in square or round brackets ("[....]").
   Four or more periods outside brackets are a printed form's dot leader
   ("Det. ..........", "Loc. ......"), never a placeholder (N3 of #289's
   sixth review).
5. The organiser found no text for it: no candidate, no literal, no
   reader's verbatim. This is judged after every value of the attempt is
   made, so against what settled (`step._organiser_texts`, each text with
   where it stands in the readings). A text counts as absent when it is
   the literal a field of another kind (`agreement.FIELD_KINDS`) settled,
   in this attempt, an earlier one or by a person, letter case and the
   punctuation around it aside, and stands, less that punctuation, where
   that literal stands (`step._held_by_another_kind`, `step._bare`;
   settled as `step._claims_text` says): 105526328's "trap", which the
   organiser offered as the habitat, once the collecting method settles
   on "trap"; "IV-24-48" offered as the collection code once the date
   settles on it; "trampa de luz" (or "Trampa de luz." beside the settled
   "Trampa de luz") offered as the habitat once the method settles on it.
   The mirror case clears the same way, and this is accepted behaviour
   (the coordinator's ruling on PR #309's review): the organiser offers
   "trap" as the collecting method, the habitat's expert settles "trap",
   and the method's expert finds no method, so the method clears as not
   on the label beside the habitat "trap" (on 5332ce4e3 both went to
   review). A text no other field settled still counts, and so does one
   only inside a longer settled literal: "trap, cloud forest" beside the
   method "trap", or the organiser's precise location "nr. Finca Moca"
   beside a habitat settled as the whole line "cloud forest nr. Finca
   Moca" (PR #309's review, finding 3). For a county, a city
   or a precise location, a text also counts as absent when its whole
   words, compared by the place comparison key (case, accents and
   punctuation aside, "Mt." read as "mount"), are a run of the words of
   another settled place field's literal, and it writes no unit word of
   its own (County, Co., Prov., Dept., Mun. and the others the place tool
   knows): the organiser's "Mt. McKinley" as a city, inside the settled
   precise location "E. slope Mt. McKinley", or the town "Yepocapa" as a
   precise location beside the settled city "Yepocapa". "Lee" beside the
   city "Leesburg", or "Cook County" inside the precise location "Cook
   County Forest Preserve", does not count. For a county or a city, a
   text also counts as absent when every place it stands, less the
   punctuation around it, lies inside where a settled place above it
   stands, each of that place's texts only in a reading that writes it once,
   and a reader's verbatim it keeps only when it names that place
   (`step._places_above`, `step._within`): 48a71d53's "Davao Prov.",
   which the organiser offered as the county, under its settled province
   "Davao Prov.". For a precise location, the
   texts still left count as absent when, beside the places settled, they
   write only an administrative marker next to the settled place of its
   level, or readers differ only in one (below): the organiser's
   "Yepocapa, Mun. Chimaltenango" beside the settled city and province,
   or "Kreis Ahrweiler" or "Cook Co." beside the settled county. The
   organiser's "Ionia Twp." beside the settled county "Ionia" counts (a
   township is a place inside the county), as do "Dist. Turrialba" beside
   the settled canton "Turrialba" (a Costa Rican district lies inside its
   canton) and "Distr. Kandy" beside the settled county "Kandy": with the
   precise location's expert finding none, each stays in review (for
   "Distr. Kandy", the conservative outcome the coordinator accepted).
6. For an elevation, no reading writes an elevation
   (`step._elevation_written`, on every reading's and every reader's text).
   That is, none of:
   - an elevation as the place tool reads one
     (`georef_locality.read_locality`, on each whole text and on each of its
     lines; the tool is unchanged);
   - a number in metres above sea level, however the unit is spaced or
     dotted: "msnm", "m snm", "m.s.n.m.", "masl", "m a.s.l." ("2000 msnm",
     "1200 masl", `step.SEA_LEVEL_METRES`);
   - a number, then one of the units "m", "mt", "mts", "mtr", "mtrs",
     "metro", "metros", "msm", "pies" or "p.s.n.m." (its letters dotted or
     not, spaced or not: "psnm", "p s n m"), with an optional final period
     and in any case ("1200 mts.", "1200 mts", "1200 metros", "1200 msm",
     "6400 pies", "6400 p.s.n.m.", "1200 m.", "1200 m",
     `step.NUMBER_AND_UNIT`). The number never follows a letter, a digit, a
     "-" or a "/", so it is never the end of a date or a code
     ("V-4-67-1"), and it may be a range ("1200-1500 mts."); the unit is a
     whole word on the number's line ("1200 mm" is none). "1200 m" and
     "1200 m." are read by the place tool too.
7. For a precise location, a city or a county is settled: the readings
   then carry nothing finer than the places settled (the town-only labels
   of 105526328 to 105526330).

The value keeps the state "not present", which the app shows as "This field
is not present on the label", and its reason starts "Not on the label:". It
cites one check row (kind "derived", locator `check:not_on_label`) whose
excerpt and stored record name every reading of the run, by name and
observation. The row lists no observation ids itself: one evidence row may
cite readings of one label only (`integrity.verify_evidence`). The clearance
rules (`step.not_on_label`) then skip mandatory_unresolved for the field,
only while the value cites that row, the row names the run's current
readings, and, for a precise location, a city or county is still settled.
So catalogue number, country, the collecting dates and collectors still go
to review when the label lacks them, as does any listed field a reading
writes, a label with an unreadable part, and a label whose coverage is not
confirmed.

**An administrative marker is no precise location (round 2 of the
production test, 2026-10-11).** 105526328's precise location was left
ambiguous between "Yepocapa, Mun." (3A) and "Yepocapa, Mum." (3B). The
label writes no place finer than the town, which settled as the city, and
the readers differ only inside "Mun." (municipio). Once every place is in
(after the initials check, `step._no_finer_place`), a precise location
researched in this attempt is not present when all of these hold:
- the profile lists the precise location among the fields that may clear
  as not on the label (`zoology_insects_slides` 1.0.0 does); otherwise the
  answer is applied as before this check: a resolved answer settles as its
  text and the record may clear, and an unsettled one stays for review;
- its expert answered resolved, several_possibilities or
  sources_cannot_resolve, with no failure, not as the resolver's fallback
  and not finalized without a model call;
- every text the answer cites (its literal and its options) is written by
  a reading;
- those texts give nothing beyond the settled places but an
  administrative marker next to the settled place of its level
  (`step._admin_markers`): each text's words, folded as the place tool
  folds them (letter case, accents and punctuation aside), less every run
  of words that is the whole text of a settled country, province or
  state, county or city (its literal, its value and each reader's
  verbatim it keeps). What is left of at least one text is markers only,
  each with the settled place of the level it marks right before or right
  after it (`step._marks_a_settled_place`), and what is left of every
  other text is nothing, markers only, or the same words with, in a
  marker's place, a word that may be a misreading of it
  (`step._misread_marker`: letters only, as long as the marker, one
  letter different, and no word or abbreviation for a place's feature).
  So 3B's "Mum." beside 3A's "Mun." is taken as the marker, but "Mtn." (a
  mountain), "Run" (a stream), "Cr." or "Ck." (a creek), "Cv." (a cove),
  "Min." (a mine) or "Mt." beside "Kt." is not: the check gives no marker,
  and the answer is applied as it is (105526328's options "Yepocapa, Mun."
  and "Yepocapa, Mtn." leave the precise location ambiguous, for review).
The markers are a data list (`field_research/admin_markers.py`), each with
the fields of the level it marks: a municipality marker ("Mun.", "Mpio.",
"Municipio", "Comune", "Gemeinde", "Commune", "Kommune") the city or the
county, which hold the municipio; a county marker ("Co.", "County",
"Kreis", "Landkreis", "Powiat", "Okres") the county; a province
marker ("Prov.", "Dept.", "Depto.", "Departamento", "State", "Estado",
"Edo.", "Pref.", "Region", "Oblast", "Kanton", "Kt.") the province or
state. "Boulder, Co." beside the settled city "Boulder", "Kreis Ahrweiler"
beside a settled city only, or "Mun. Cuenca" beside a settled province
only, marks no settled level and gives no marker. These words are not
markers, because in at least one country each names a unit below the county
or the municipio, a place of its own inside it: "Twp." (township),
"Parr."/"Parroquia", "Freguesia", "Socken", "Sogn", "Corregimiento",
"Gmina", "Dist.", "Distr.", "District", "Distrito" and "Raion" (a Costa
Rican district lies inside its canton, a Peruvian one inside its
province), "Taluk", "Tehsil", "Bezirk", "Arrondissement", "Comuna" and
"Parish". So "Dist. Turrialba", "Distr. Turrialba", "Turrialba District",
"Dist. Chanchamayo", "Distr. Kandy" and "Bila Tserkva Raion" beside a
settled county of that name give no marker. Resolved by the precise
location's expert, each settles as the precise location, as on 5332ce4e3.
Offered by the organiser, with the expert finding none, "Dist. Turrialba"
and "Distr. Kandy" stay in review. Nor are words that are part of a
place's name or name a feature ("St.", "Mt.", "Lk.", "Arr.", "Brgy.",
"Frazione"), words whose level differs between countries ("Cant.", "Amt",
"Fylke", "Okrug"), "Canton" and words a label uses for something else.
"Co." counts only right after a settled name ("Cook Co."): before a name
it is also the Spanish "Cerro", a hill ("Co. Chirripo"). The feature words
are a second data list (`admin_markers.PLACE_FEATURE_WORDS`): Mt, Mtn,
Mte, Mts, Cr, Ck, Cerro, Run, R, Rio, L, Lago, Lac, Is, Isla, Pt, Pta,
Punta, Pk, Peak, Vol, Volcan, Fca, Finca, Hda, Hacienda, Sta, Sto, San, B,
Bay, Kt, Cv, Cove, Min, Mina, Mine and others, compared folded ("Rio" and
"Volcan" with or without their accents). Any other word keeps the text a
place: "E. slope Mt.
McKinley, Davao Prov." beside the settled province "Davao, Prov." still
settles as the precise location; "Ionia Twp." beside the settled county
"Ionia" settles when its expert resolves it and stays in review when its
expert finds none (as on 5332ce4e3); "5 km N of Yepocapa" and "Finca
Moca, Mun. Yepocapa" beside the settled town give no marker; and the
organiser's "5 km N of Kandy" or "Co. Chirripo" beside the settled county
keeps the precise location in review.
When the conditions hold, the value is not present, its reason "The
readings give no place finer than the places settled: beside them, they
write only the administrative marker "Mun."." followed by the expert's
explanation, and the rows a settled answer added, with its
transcript_literal finding, are dropped; its trace names "admin_marker_only". Rule A then judges it as a
field whose expert found no value (condition 1). When it clears, its
reason starts "Not on the label: beside the places settled, the readings
write only the administrative marker "Mun.", no finer place.", and its
check row's excerpt says the readings write only an administrative marker
(its record names the marker); the clearance rules accept that excerpt for
a precise location. When rule A declines (a label not read whole, no city
or county settled), the record goes to review. A precise location that
named only the town and its marker therefore no longer settles as that
text: it clears as not on the label, or waits for a person.

**A precise location that is only a settled place's text (round 4 of the
production test, 2026-10-11).** 105526329's precise location settled as
"Yepocapa", the text of its settled city on the same reading, though its
brief asks label_lacks_value when no reading writes a locality finer than
the other place fields. Once every place is in (after
`step._no_finer_place`), a precise location settled on its expert's
resolved answer whose literal, folded (`georef_locality.fold`: case,
accents, punctuation and spacing aside, every word kept), is only the text
of a settled city, county, province or state, or country on a reading the
answer names (that field's literal standing there as whole tokens, or the
verbatim it keeps of that reading) is made what label_lacks_value makes
it: not present, citing the answer's sources, its reason "The readings
give no place finer than the places settled: "Yepocapa" is the text of
the City field." followed by the expert's explanation; the rows its
settling added and its transcript_literal finding are dropped, and its
trace names "place_text_only" (`step._repeats_a_place`). This holds
whatever the profile's not-on-the-label list says, as for
label_lacks_value. Rule A then judges it as a field whose expert found
none: when it clears, its reason starts "Not on the label: beside the
places settled, the readings write no finer place;", its check row's
excerpt says the readings write no finer place (its record names the
field), and the clearance rules accept that excerpt; when rule A declines
(a label not read whole) or the profile does not list the precise
location, the record goes to review. A literal that adds any word to the
place's text still settles: "nr. Yepocapa", "5 km N of Yepocapa", "E.
slope Mt. McKinley", "Yepocapa region", and "Co. Chirripo", a hill beside
the county Chirripo (the review of #312 found that a comparison by place
name, which drops unit words, took the last two for the place). A marker
beside a settled place is the marker check's alone: "Yepocapa, Mun." is
not present where the profile lists the precise location
(`_no_finer_place`) and settles as its text where it does not, as above.
"Yepocapa" also settles when the city did not settle.

**A county or a city that is only a settled place's text (the batch rerun
of 2026-10-17).** 93e61763's, 9cc24b07's, d3fb389f's and f35af3a5's
county went to review although their labels name no county: the county's
expert answered the province line ("Chimaltenango,", "Davao, Prov."),
whose name its sources also hold at the second level, as several
possibilities. A written place is one field's: a province is never also
the county (`agreement.IS_THE_PROVINCE`). Once every place is in (after
`step._repeats_a_place`), a county, then a city, researched in this
attempt whose expert's answer left it ambiguous or unresolved (an answer
and no failure, not label_lacks_value, not finalized without a model call; the resolver's
fallback too, when its expert asked at least one source and every name its
lookups asked about, the query's first comma-separated part, is taken as an
option of its answer: f35af3a5's city in the second rerun of 2026-10-18 asked
about "Davao", cut from the settled province "Davao, Prov.", and "Davao
City", a name the label does not write, while a fallback that asked about a
town the label writes, "Tagum", keeps the field) is made what
label_lacks_value makes it
when every text the label gives it is the text of a settled place above it
(`step._only_a_place_above`, `step._held_above`): not present, citing the
answer's sources, its reason 'The readings write no county of their own:
"Chimaltenango," is the text of the Province/State field.' followed by the
expert's explanation; the rows its value added and its transcript_literal
finding are dropped. This holds whether or not every source the expert
asked answered, since the text is the settled place's either way. Its
trace keeps the code of a step check that refused the expert's resolved
answer first (`first_level_too`, `is_the_province`), and otherwise names
"place_above_text_only". The texts are the organiser's and the answer's
literal and options. One that stands in the readings is the place's text
where every place it stands, less the punctuation around it, lies inside
where that place's text stands: its literal, and each reader's verbatim it
keeps when that verbatim names the place (by the place comparison key the
literal, value or an expansion, or one letter from one: 93e61763's
"Chimaltenago"; never another reader's other text the field keeps, as
48a71d53's province keeps 1B's "Mindanao" beside its literal "Davao
Prov."), each only in a reading that writes it once, so the second
"Chimaltenango" of "Chimaltenango, Chimaltenango" is no province's. An option no reading
writes is the place's when it is one of the place's names, or one letter
from one (9cc24b07's "Chimaltenango Department" for the province written
"Chimaltenago"); one whose words a reading writes otherwise is a text of
the label no place above holds, which keeps the field; and any other is a
source's name for a place the label does not write (f35af3a5's "Davao
City"), which is left aside. At least one text must be the place's. Rule
A then judges it as a field whose expert found none: when it clears, its
reason starts 'Not on the label: the readings write no county of their
own;', its check row's excerpt says the readings write only the text of a
settled place above it (its record names that place's field), and the
clearance rules accept that excerpt for a county or a city. A county or a
city with a text no settled place above holds, or with no place above
settled, keeps its expert's answer.

**A taxon with no genus (B).** A taxon whose label names no genus for its
morphocode ("sp. 30" with a sex sign, and no genus written beside it)
clears as written, marked unmatched (`step._unmatched_taxon`), only when
all of these hold:
- its expert itself answered that GBIF cannot resolve it
  (sources_cannot_resolve), with no failure, not finalized without a model
  call, and not as the resolver's fallback (`FieldOutcome.fallback`: an expert out of
  attempts with no checked answer when asked once more, or whose answers
  kept failing their checks); its answer's
  literal is the code itself, compared with the organiser's literal as
  the GBIF query guard below compares a query (case, spaces, punctuation
  and sex signs aside), whether or not it asked GBIF, so an answer quoting
  "Epipsocus", the slide number, another code or nothing never qualifies;
  and it answered after a GBIF lookup attempt for the field, or quoting
  as its literal the morphocode a reading it names writes
  (`step._expert_found_no_genus`);
- no GBIF answer the expert received for the field shows a genus
  (`step._answer_found_a_genus`): none has candidates (105526328's
  "Epipsocus" homonym has two), none has the status success or ambiguous
  (a name the GBIF tool withholds unsent is ambiguous), and no query the
  expert asked GBIF names a genus (`checks.query_names_a_genus`). A query
  names a genus when the scientific-name parser reads a name in it as
  written ("Epipsocus", "Epipsocus sp. 1", "Epipsocus prob. sp. 1"), with
  the emphasis marks "*" and "_" dropped and its first letter a capital
  ("epipsocus", "*Epipsocus*", "epipsocus sp. 1"), or as its tokens (the
  label check's tokens, below) with the first letter a capital
  ("Epipsocus(?)"); or when, its morphocodes aside, any of its tokens may
  be a genus by the label check's test below ("EPIPSOCUS", "ep1psocus",
  "Epipsocu5", "(epipsocus)", "E. sp. 1", "E.?", an "Epipsocus" with an
  accented capital). The taxon brief has the
  expert look up the genus a label writes, so such a lookup is its own
  finding that the label writes one, wherever on the label the genus
  stands. The brief has it look up alone, before it answers for a
  morphocode, any genus any label writes anywhere (on another line or
  another label, with a qualifier or without), and a genus in doubt too:
  a genus, or a word that may be one, behind a qualifier of any spelling
  ("cf.", "cfr.", "c.f.", "aff.", "nr.", "conf.", "poss.", "prob.") or
  with "?" is looked up as the bare genus word, with no qualifier and no
  epithet, and the expert then answers sources_cannot_resolve whatever
  GBIF says (`prompts/taxon.txt`). GBIF's no-name answer for a morphocode (no match, no candidates,
  "sp. 30" asked) shows none, so the pilots' codes still clear with no
  GBIF lookup or after that answer;
- the expert asked GBIF, for the field, no query but the code itself
  (`step._gbif_asked_another_name`, `checks.query_is_the_code`): each
  query is compared with the organiser's literal once case, spaces,
  punctuation and sex signs are stripped from both. So "Sp.30" or "SP 30"
  asked for "sp. 30" qualifies, and any other query holds the taxon back:
  a misread genus the test above does not count ("Epipsocu55"), a slide
  number, another code, or an empty query. The taxon brief never has the
  expert send GBIF a name no reading prints. GBIF's no-name lookup that the
  step adds itself is no query;
- the organiser's literal is a morphocode (`checks.names_no_genus`: the
  scientific-name parser reads no name in it, it has no whole-name GBIF
  query, and it is "sp.", then a number with an optional letter, or a
  short lower-case code after a space or a period, then optional sex
  signs; "spp", "sp. nov.", "sp. n.", "sp. aff." and "sp. cf." are none);
- every taxon candidate is the same morphocode (`checks.morphocode`: the
  same number or code, case, spacing, punctuation and sex signs aside, so a
  reader's "Sp.30" beside "sp. 30", never "sp. 39"). This compares the
  organiser's candidates. Readers of a label with no decided transcript
  whose codes differ never settle (the readers' rule below), unless they
  differ only in letter case or spacing (until WP 1.8, a label whose old
  first pass preferred a reader cleared that reader's code alone where
  nothing backed another reader's);
- the label names no genus for that code (`checks.label_names_no_genus`):
  this is judged on every reading's text, not on the organiser's literal.
  Wherever any reading writes the code, no token beside it may be a genus
  (`checks.genus_beside`). A token is a whitespace-separated word with
  "?", "*", "_", straight and curly quotes, backticks, brackets, ",", ";"
  and ":" shed at either end, and a qualifier of the doubt signs' list
  (below) with its final period shed at the start, or at the end with no
  letter right before it, written against the word or as a word of its
  own ("cf.Epipsocus", "c.f.Epipsocus" and "Conf.Epipsocus" are
  "Epipsocus"; a person's initials such as "C.F." keep their letters;
  `checks._token`); what then holds no letter or digit (a sex
  sign, a "+", a lone "?" or "cf.") is no token. Two tokens are read
  (`checks.genus_beside`), and words of `checks.NOT_GENERA` are passed
  over on both sides (the real-model run of the ten pilots, 2026-10-09):
  - before the code, the last token on its line that is not one of them;
    when its line has none, the last such token of the nearest line above
    that has any token; when every token of that line is one of them, none
    ("Epipsocus" in "Epipsocus legs sp. 1" and above "<female sign> legs
    Sp.#1"; none for "legs sp. 1" or for "wings + head" above "sp. 30");
  - after the code, the first token on its line that is not one of them,
    and none when every token there is one ("Epipsocus" in "sp. 1
    <female sign> legs Epipsocus"; none for "sp. 1 legs").

  `checks.NOT_GENERA` is the one list of such words, compared as written
  (Unicode NFC): the parts a slide mounts, the slide or mount and the sex,
  in English (head, leg, legs, wing, wings, abdomen, antenna, antennae,
  genitalia, terminalia, slide, mount, male, males, female, females),
  Spanish (cabeza, pata, patas, ala, alas, antena, antenas, lamina,
  montaje, macho, machos, hembra, hembras), French (tete, patte, pattes,
  aile, ailes, antenne, antennes, lame, montage, male, males, femelle,
  femelles), German (Kopf, Bein, Beine, Fluegel, Fuehler, Praeparat,
  Maennchen, Weibchen) and Portuguese (cabeca, pernas, asa, asas, lamina,
  montagem, femea, femeas), and the two sex signs. This note is plain
  ASCII: the list holds each word with its accents (the Spanish lamina
  with an acute a, the Portuguese one with a circumflex a; tete, femea and
  femeas with a circumflex e; the French male and males with a circumflex
  a; cabeca with a c cedilla) and the German words with an umlaut (u
  umlaut for "ue", a umlaut for "ae"); their ASCII spellings are not
  listed, but for the English male and males. A genus is
  written with a capital, so the lower-case words are listed only in lower
  case ("Legs" and "Ala" may still be a genus), and "perna" is not
  listed (Perna is a mussel genus). A token is none either when a
  person's name written with initials ends with it (before the code) or
  starts with it (after the code) (`checks._PERSON`): initials run into
  the surname ("R.D.mitchell"), initials then a capitalised surname ("R.
  D. Mitchell", "1948, R.D. Mitchell", "H. Hoogstraal"), a surname, a
  comma and initials ("Mitchell, R.D.", "Mitchell, R. D."), or two or more
  initials alone ("R.D."), unless the initials spell a qualifier of the
  doubt signs' list ("C.F. Epipsocus" and "N.R. Epipsocus" may be "cf."
  and "nr."). One capital and a period ("E.") abbreviates a genus.

  The token read may be a genus (`checks.may_be_genus`), judged with its
  first letter made a capital, as the query check above judges a token:
  when it holds a letter and no digit ("Epipsocus", "epipsocus?", "E.?",
  "cf.Epipsocus", "Mitchell", the reader's "[unreadable]"); when it is
  then a capital followed by letters and digits ending in a letter, with
  an optional final period ("Ep1psocus", "ep1psocus"); or when it holds
  three letters or more and one digit at most, a genus misread with a
  digit ("Epipsocu5", "3pipsocus"; with one digit, no date or number
  punctuation stands between digits). Any other token is none:
  "V-4-67-1", "6400'", "IX-14-46", "Epipsocu55". On the taxon's keyed line
  ("taxon: sp. 30", as `Workflow.parse` reads key: value text) the key is
  no token; when the nearest line above with a token is itself a keyed
  line ("verbatim_dts: ..."), it is another field's, and no token before
  the code is read. So "Epipsocus sp. 1", "Epipsocus", "Epipsocus?" or
  "[unreadable]" with "sp. 1" on the next line (as on 105526328), "E.?
  sp. 1", "Epipsocu5 sp. 1", "C.F. Epipsocus" above "sp. 1" and "Legs sp.
  1" never clear as unmatched, whatever the organiser's candidate is; the
  pilot's 105526321 ("Mossy forest 6400'" above "sp. 30"), 105526326
  ("Sp. 22" on a label of its own), 105526327 ("V-4-67-1" above "sp 22",
  "legs" on the line below), 105526322 ("wings + head" above "sp. 30"),
  105526323 ("genitalia + legs" above "Sp 30"), 105526329 ("R.D.mitchell"
  above "sp #1") and 105526330 ("1948, R.D. Mitchell" above
  "<female sign> legs Sp.#1") pass this check. 105526322 and 105526329
  still go to review on the readers' rule below: their readers write
  "sp. 30" and "Sp.30", "sp #1" and "Sp #1", and their labels have no
  decided transcript;
- no part of a label that writes the code is unreadable
  (`step._code_label_unreadable`): rule A's test (no reader's unreadable
  span, no transcript marked unreadable, no placeholder of rule A's list
  in a reader's, a reading's or a transcript's text,
  `checks.shows_placeholder`), applied to each label any of whose texts
  writes the code. An unreadable word there may be the genus;
- no sign of a doubtful or unreadable name shows anywhere on the specimen
  (`step._doubt_on_the_labels`): none in any reading's, reader's or
  transcript's text of any label, whether or not that label writes the
  code. The signs are one list, `checks.DOUBT_SIGNS`:
  - a question mark ("?", the full-width one, U+FF1F, or the inverted
    one, U+00BF: `checks.QUESTION_MARKS`) in a whitespace-separated part
    that holds a letter ("Epipsocus?", "?Epipsocus", "Epipsocus(?)",
    "E.?"), or in the part just before or just after one, across a line
    break too ("Epipsocus ?", "(?) Epipsocus", "Epipsocus" with "?" on the
    next line);
  - a qualifier (`checks.DOUBT_QUALIFIERS`): cf, cfr, aff, affin,
    affinis, nr, near, prob, probably, poss, possibly, conf, vic or prope,
    each a whole word, in any case except vic, which counts in lower case
    only (`checks.LOWER_CASE_QUALIFIERS`: "vic." and "v.i.c.", never "Vic."
    or "VIC", Victoria), and with or without its periods (a period may
    follow each of its letters, so "c.f.", "Cf.", "CF." and "n.r." are
    "cf" and "nr"), with no letter right before or after it: apart or
    against a word ("cf. Epipsocus", "CF.Epipsocus", "(cf) Epipsocus",
    "cfr. Epipsocus", "Epipsocus nr", "possibly Epipsocus"), never inside a
    longer word ("Nearctic", "Staff", "Victoria", "Proper"). These
    ordinary label words, which say nothing about a name, are no sign
    (`checks._qualifier_sign`; N3 of #289's sixth review):
    - capitals with a period between each two, with or without the final
      period: a person's initials ("C.F." in "leg. C.F. Baker", "Baker,
      C.F", "C.F Baker", "N.R. Smith");
    - "NR", all capitals with no period after it: a nature reserve
      ("Sabah, Danum Valley NR");
    - "Nr" or "NR", with or without its period, before a number on its
      line: German "Nummer" ("Praep. Nr. 1234");
    - "conf", in any case, with or without its period, before the word
      "by" in any case, or before a person's initials (capitals each
      followed by a period) and a capitalised surname, or two or more
      initials alone, after spaces or a line break: "confirmed by"
      ("conf. by J. Smith", "conf. K. Yoshizawa", "conf. E.L. Mockford",
      "Conf. E.L.M."). A surname with no initials ("conf. Yoshizawa")
      cannot be told from a genus and stays a sign;
    - "near" or "nr" right before a place the label's place fields
      settled, or "vic" right before or right after one, on its line:
      the rest of the line after it (and its period) starts with that
      place's whole name, or, for "vic", the line up to it ends with that
      name, compared by the place comparison key ("5 mi near Chicago",
      "nr. Chicago", "Chicago vic.", "Chicago, vic." beside the settled
      city "Chicago"). The places are the country, province or state,
      county and city settled on a place source's record (supported, with
      a literal and an authority_id: `step._settled_places`).
      `apply_outcomes` settles the places before the taxon, so the step
      and the later re-check (`step.taxon_unmatched`) read the same
      places. "near", "nr." and "vic." beside any other word, or beside a
      place no place field settled ("5 km nr. Davao" when no place field
      settled Davao, or "5 mi near Chicago" when the city did not settle),
      stay signs;
  - a placeholder for an unread word, by rule A's own test
    (`checks.shows_placeholder`, item 4 of rule A above): its listed
    placeholders, the words "illegible" and "unreadable" standing alone,
    exactly three periods (never after "etc"), and three or more periods in
    brackets; never a dot leader of four or more periods;
  - a reader's unreadable span, or a transcript marked unreadable, on any
    label.

  These sit on top of the label check, which reads only the two tokens
  beside the code. The taxon brief has the expert look a doubtful genus up
  alone, a query the GBIF guard above refuses; the signs hold the taxon
  back when the expert makes no such lookup. So "Epipsocus?" above
  "V-4-67-1" above the code, on the line after the code or on another
  label, and "cf. Epipsocus", "cfr. Epipsocus" or "c.f. Epipsocus"
  anywhere, a determination label of its own included, keep the taxon in
  review, as do "nr. Epipsocus", "NR. Epipsocus", "Nr. Epipsocus", "conf.
  Epipsocus", a locality's "near", "nr." or "vic." beside a place no place
  field settled, a "?" beside any word, "Mossy ..." and "[...]". A
  collector's "C.F. Baker" or "Baker, C.F", a locality's "Melbourne,
  Vic.", "Sabah, Danum Valley NR" or "5 mi near Chicago" beside the
  settled city Chicago, "Praep. Nr. 1234", "conf. K. Yoshizawa" and a
  printed form's "Loc. ........" do not. No reading of 105526321,
  105526326 or 105526327 shows a sign.
  105526324's unreadable label, whose readers list the span and write
  "[unreadable]", holds back the "sp 22" another of its labels writes;
- the readers settle on the literal by the rule for readers that disagree
  (step 5 above: the settlement rule, `agreement.labels_by_rule`);
- the value meets the agreement rules every resolved answer meets
  (`agreement.refusal`): among them, no candidate of it may quote a longer
  name around it, and no text may mark the literal's first word as a
  doubtful genus (step 5 above).

The value is supported, with the literal as written, no authority, the
settled layer and the reason "Unmatched: the label names no genus, so GBIF
has nothing to match". It cites one check row (locator
`check:taxon_no_genus`) naming the literal and GBIF's no-match, which the
run keeps among its lookups (`lookup.no_name_lookup`: no match, and no
request made; the step adds it when the expert never asked GBIF that
literal). The clearance rules do not give such a taxon taxonomy_unresolved
(`step.taxon_unmatched`) while it cites that row, the run's readings still
name no genus beside its code, no part of a label that writes the code is
unreadable, no sign of a doubtful or unreadable name shows on any label,
and no GBIF lookup the run stores shows a genus
(`step._lookup_found_a_genus`: the same test, on the query sent or asked
and the name GBIF could not read) or asked anything but the code itself
(`step._lookup_asked_another_name`, on the same texts; the step's own
no-name lookup aside). A taxon with a genus that GBIF cannot
decide, such as 105526328's "Epipsocus", still goes to review, whether the
organiser's candidate is "Epipsocus sp. 1" or only "sp. 1": when the label
writes the genus, or any word that may be one, as a token beside the code,
by the label check; when a label that writes the code has an unreadable
part; when any label shows a sign of a doubtful or unreadable name; and,
wherever the label writes the genus, when the expert asked GBIF anything
but the code; and when the expert's answer quotes anything but the code.
Two cases remain, each only when the expert makes no lookup of a genus
its brief has it look up (alone, any genus a label writes, doubtful or
not, before it answers for a morphocode):
- a genus written with no doubt sign where the label check does not count
  it (away from the code, as "Epipsocus" above "V-4-67-1" above the code,
  on the line after the code's or on another label; behind a line of
  `checks.NOT_GENERA` words, as "Epipsocus" above "wings + head" or
  "legs" above the code; right after a person's initials, as "R.D.
  Epipsocus" above the code, read as a name; or misread beside it into a
  token the label check's test does not count, as "Epipsocu55"), when the
  expert makes no GBIF lookup but of the code itself;
- a genus marked doubtful in a way the doubt signs do not read (a doubt
  word outside the qualifier list, as "sim. Epipsocus" above "V-4-67-1"
  above the code; or a qualifier the signs read as an ordinary label word,
  as "NR Epipsocus", a nature reserve to them, or "C.F Epipsocus",
  initials to them), when the expert likewise makes no GBIF lookup but of
  the code itself.

Until WP 1.8 each still cleared as unmatched on the old path. Since WP 2.T
neither clears on the units path, since WP 1.8 the only one. There, rule B, by either of its branches, declines while any label of the
specimen writes a word that may be a genus. Such a word is any run of
letters, of any case, other than a `checks.NOT_GENERA` word or a Roman
numeral I to XII, that no single span holds whole. The spans are a
settled field's occurrence where its provenance places it, a whole
notation token, a code with no genus, a catalogue number with its prefix,
or a keyed line's key; a unit's span carries to another reader there only
when that reader writes the same words, each at most one character apart
(`step._genus_on_a_label`; the same test on the units path, and
`tests/field_research/test_taxon_scope.py`). Where the expert does look the genus up, as its brief says,
the GBIF guard refuses rule B, since that query is not the code
(`step._gbif_asked_another_name`;
`test_the_real_resolver_looking_the_genus_up_as_its_brief_says_keeps_the_taxon_in_review`
for the same three and "Epipsocus" above "V-4-67-1").

**Known limitation.** The canonical projection skips a field with no literal
(`application/projection.py`, `_fields`), so the record in Data Connect does
not link a not-on-the-label value to its check row; the row itself is kept
with the run's evidence.

## After field research: a reviewer's decisions

Field research runs once per run. When it has completed, a later pass (an
operator's retry or resume, or a reviewer's decision) researches nothing and
pays nothing: the clearance rules are applied again to the fields exactly as
they are. As on the native path, a reviewer's correction is kept exactly as
made and the record waits in review for that reviewer's approval; an approval
clears the record when the rules clear it, and a correction the rules refuse
stays in review. A taxon GBIF could not settle is cleared the way the ordinary
policy clears one: the reviewer chooses one of the candidates of the run's
last stored lookup (the taxonomy resolution decision reads only that one).
Field research therefore stores its GBIF lookups so that the last is the
last success or ambiguous one with candidates whose query is the whole name
the label writes, else the last such one with candidates; a lookup with none
(a failure, no match) is never last while one with candidates exists. Field research leaves such a taxon
ambiguous or unresolved, so a correction first records the name the label
writes. A name that lookup never returned cannot be chosen, and a value typed
in without that choice stays in review.
A corrected transcription is the one exception: its fields
are parsed again from the new text, and field research runs on them again.
On a label with no decided transcript, a reviewer's field correction leaves
`unresolved_transcription:<region>` in place, even after approval (the
corrected value has no raw reading behind it): the way out is a transcription
decision, which reruns field research and pays for it again.

WP 2.R of the reading-units program (2026-11-15) tried narrowing
`unresolved_transcription` on the units path and removed it: first for a
label whose readers' differences no field's rows or text touched, then for one
whose readers differ only in letter case or spacing. Review found a difference
of each kind that decides a field: a year on the next line decides the date
"IV-25" ("1948" against "1949"), and "Mt. Apo" against "MT. APO" below it
changes whether that year is read with the date (`date_lines`). Main's rule
in `step.scientific_reasons` stands on both paths: a label with no transcript,
or one unresolved or without text, is `unresolved_transcription` when no field
is drawn from it, or a field drawn from it, its work done, is not supported, or
is neither grounded in a reader's raw reading nor derived; and a label the
first pass gave up on is so however its fields settle.

Amended 2026-11-17 (the autonomy program's work package S1, C3;
[`docs/execution/autonomy/PLAN.md`](../autonomy/PLAN.md) section 4): a
label with fields drawn from it is not also `unresolved_transcription` when
every one of those fields already has a review reason of its own (held or
marked), since a person is sent to each of them anyway. Any drawn field
without one, a field cleared as not on the label or one waiting for its
source among them, keeps the label's reason, and a label no field is drawn
from keeps it as before. A record whose fields that describe the specimen
are all settled with no value (the catalogue number and the collection code
aside) is `no_specimen_value` until a person approves it.

Amended 2026-11-18 (the autonomy program's work package K1,
[`docs/execution/autonomy/PLAN.md`](../autonomy/PLAN.md) section 4; the
owner's words of that date in [`PLAN.md`](PLAN.md) section 2.1, "Skeletal
records"): the `no_specimen_value` reason is removed, and only the catalogue
number is mandatory. `step.scientific_reasons` still gives every reason above,
for every field a label writes; `step.split_reasons` then decides which hold
the record, and every other reason is kept in `run.open_reasons`. The classification is the coordinator's rulings of 2026-11-18 (the coordinator's words, not the owner's): an optional field the system failed to resolve is that field's doubt, it is the field that waits for a person, not the record; a label no field is drawn from holds nothing, except the label the catalogue number is drawn from; and only these hold: the catalogue number not settled, marked, failing its format, or drawn from a label whose reading is in doubt that the slide's QR code does not confirm; label coverage; missing provenance or evidence for the record as a whole; a run that did not finish; and a person's pending decision or approval.
Research given up for the run as a whole is the step's `give_up` (every field
it would research fails as `run_limit`, the run's own limits leaving no room for
another attempt): it holds as `field_research_given_up`. A field's own failure
or fallback, a spent per-field or per-specimen meter among them, is that field's
`research_incomplete:<field>`. No field's state, value, marks or findings change.

| Reason code | Holds the record? |
|---|---|
| `label_coverage_unconfirmed` | holds |
| `mandatory_unresolved:fmnh_ins_number` (no settled catalogue number, its research failed included) | holds |
| `marked:fmnh_ins_number:<label>:<why>` (`text_only`, `conflict`, `parts_on_labels`, `barcode_differs`, a check-stage rule) | holds |
| `identifier_format` | holds |
| `unsupported_parsed`, `unsupported_normalized`, `unsupported_authority_id`, `evidence_missing`, `evidence_does_not_support_value`, `raw_reading_grounding_unproved`, `pixel_lineage_missing` on `fmnh_ins_number` | holds |
| `unresolved_transcription:<label>`, `independent_observations_missing:<label>`, a label's language rule `<reason>:<label>` | holds when the catalogue number is drawn from the label and the slide's QR code does not confirm it; otherwise (a label only optional fields are drawn from, a label no field is drawn from, a label whose first pass was given up) an optional field's doubt |
| `raw_provenance_missing:<label>` | holds when the catalogue number is drawn from the label (the code does not stand in for a missing raw reading); otherwise an optional field's doubt |
| the field codes above on an optional field (`mandatory_unresolved`, `unsupported_*`, `evidence_missing`, `evidence_does_not_support_value`, `raw_reading_grounding_unproved`, `pixel_lineage_missing`, `marked`) | an optional field's doubt. Since work package F2, `mandatory_unresolved:<field>` is not given for a blank (`not_present`) optional field, Verbatim D/T/S and Habitat excepted, that the obtained, current second opinion also leaves blank ("The second opinion", rule B); on a run whose pinned profile makes the field mandatory it is given and holds as before |
| `research_incomplete:<optional field>` (new: a failure, a limit, a spent per-field or per-specimen meter, a request too large, an outage or deadline on the last attempt, or the expert's fallback) | an optional field's doubt; the field keeps its own reason (`FIELD_REASONS`) |
| `taxonomy_unresolved`, `identified_by_irn_identity_unproved` | an optional field's doubt |
| `elevation_invalid`, `elevation_range`, `elevation_units_conflict`, `date_precision_requires_review`, `date_order` | an optional field's doubt |
| `field_research_given_up` (new: research given up for the run as a whole) | holds; derived on every finalize from the give-up's finding on the run, which the next research attempt removes |
| `preserved_human_decision:<field>` | holds (recomputed from a person's decisions on every finalize) |
| `human_approval_required`, `history_restored_requires_review`, `location_reassessment_unconfirmed:<field>` | holds; derived on every finalize from `run.pending_review` (`application/standing_holds.py`), recorded when a person decides, a history is restored or a reassessment leaves a field unproved, and cleared by a person's approval (the reassessment's entries also by the reassessment that settles them) |
| `label_unsettled:<field>` (new: a field drawn from a label whose doubt is open, `step.label_attention`) | never holds: the field's attention only. Since work package F2 it is not given for an optional field settled with a value the second opinion agrees with (the three date fields excepted, and not on a run with a label one reader read), nor for an agreed blank field ("The second opinion", rules A and B); a field another open reason still names stays flagged |
| an operational failure (`lookup_operational_failure`, `field_research_model_error`, `field_research_timeout` `:<field>`, the blocker) | holds: the run is blocked, as before |
| `evidence_integrity_failure` | never a reason: the step blocks, as before |
| ordinary path: `institutional_policy_unapproved`, `mandatory_semantics_unconfirmed`, `evidence_lineage_invalid:<row>`, its capability reason | holds |
| ordinary path: `taxonomy_lookup_missing` | an optional field's doubt |
| `no_specimen_value` | removed |
| any other code | holds (fail closed; no code produced today falls here) |

A field cleared as not on the label, or a taxon cleared as unmatched, is
reopened like any other field with Correct value: the reviewer's value is
kept as made and the record waits for that reviewer's approval. Every later
pass checks a not-on-the-label value again: it clears only while it cites
its check row and that row names the run's current readings. An unmatched
taxon is checked again too: it clears only while it cites its check row,
the run's readings name no genus beside its code, no part of a label that
writes the code is unreadable, no label shows a sign of a doubtful or
unreadable name, and no GBIF lookup the run stores shows a genus or asked
anything but the code. A not-present
value with no such row, as every record researched before 2026-10-09 has,
never clears on a re-check; only new research writes the row.

A field research run that failed (a field whose expert reached no source, a
model error, a timeout) is retried until its last allowed attempt, on which
a source still unreachable or a timeout (a model request that ran out of
time among them) sends its field to review (step 7 above), and
the retry researches only the fields that did not settle (a
province, county or city that waited for a country that did not settle
is among them). A field marked not on the label is not settled, so the
retry researches it again, and it then cites only the row the retry writes.

An operator can explicitly **Reassess locations** from the Processing panel
when a completed run still has unsettled automatic locations and a research
attempt remains. This researches only country, province/state, county, city
and precise location together, using the existing run and saved readings.
It can reconsider earlier machine assignments when fresh qualified source
evidence supports a different hierarchy. Human selections and independently
source-backed parents remain protected. A partial or unavailable source cannot
replace a supported hierarchy with a mixture of incompatible old and new
values. Parents derived from a human-selected location remain constraints too;
a stale dependent parent may still need separate review. Earlier values and
evidence remain in history. The action records its
reason and scope, consumes an ordinary research attempt and retains all usage,
prices and spending limits; it supplies no geographic values. Ordinary Retry
continues to preserve supported fields.

Location reconciliation shares captured source answers across every grounded
location literal, regardless of which expert requested the lookup. Distinct
source-typed administrative text constrains compatible parent chains; qualified
parents then narrow their children. An ambiguous town cannot choose a county,
and conflicting written administrative places or distinct authority matches
remain unresolved. This uses the answers already captured during the attempt;
it makes no additional lookup and does not reopen an exhausted attempt.

A blank ambiguous country can be derived from qualified administrative parents
when every retained country alternative (including other labels and readers)
has a fresh, directly matching gazetteer record at a recognized lower level,
and no matching record has a recognized country level. Unmodeled source kinds
provide neither level proof nor country counterproof; an alternative with no
recognized lower-level proof stays ambiguous. Human decisions, actual country
disputes, unknown alternatives and incompatible parent countries still block
replacement. If derivation cannot complete, the original ambiguity is retained.
An explicitly selected authority record supplies its own ancestry; another
same-name record cannot supply parents for it. This changes no attempt or
spending authorization and does not apply archived answers to a live record.

Two kinds of country alternative no longer hold that derivation back (the
third rerun of 2026-10-18, `agreement.set_aside`, `agreement.confirmed_place`):
- text no reading a field may settle on writes. Every reading that writes it
  is either another reader of a label whose decided transcript (its
  readers' one text, or a person's) does not write it, with no reading of
  another label writing it (a possibility nothing backs,
  `agreement.only_a_possibility`; until 2026-10-25 `agreement.evidence_only`,
  G19), or one of the two readers of a label with no decided transcript
  where the
  other reader writes other words at that very point (`agreement.disputed`):
  each run of the text lies wholly inside the token differences of the two
  readings (`application.first_pass.reading_differences`, the differences
  the label's first pass judges), each with text on the other side; that
  text is neither the text's place name nor one letter from it; it is
  written, as whole words, in one of the other reader's texts for a field
  of another kind than a place (the organiser's candidates and those
  fields' literals, `step._claimed_texts`): a taxon, a collector ("Chas."),
  a date ("1945"); and the other reader writes the text nowhere. Another
  place field's text there is never such text (round 1 of #379's review,
  finding 1): "Mexico" where the other reader writes "Texas", that
  reader's province, is two readings of one place, and the country stays
  for review. Words of another kind are not a place's reading of that ink,
  so they leave the country text one reader's word, uncorroborated, while
  the country itself is derived from places settled on their own.
  d10333ff's determination label had no decided transcript in three runs
  (its first pass reached its token cap once and chose no reading twice):
  reader 3A writes "Panama" where 3B writes "Panorpa", 3B's taxon. Its label
  1 settles Edgar County (and, in two of the runs, Illinois), and the
  country is derived as the United States. A reader that writes the text too, writes it with other
  accents or one letter off, leaves the line out, or writes there words no
  field holds keeps the country for review, as do both readers writing
  "Panama";
- text the gazetteers confirm as the very nation every newly settled child
  lies in ("USA" beside Coles County).

Such text still counts as its label's text everywhere else (G20 and G32).

On 2026-10-16 the owner authorized one additional same-run location reassessment
for specimen `ebfc6171-bf2f-56b8-a35b-442798810461`, run
`e7b00556-f006-4be7-9bd8-82ebf41173be`, in organization
`e4b2a17f-c28b-4e13-8273-c8297083d215` and collection
`200d7057-23fa-41ab-875b-682c8ba218c9`. The earlier third attempt exposed the
shared-source reconciliation defect fixed by PR349. The reviewed server
exception admits only the existing explicit action from count three to count
four for this exact identity. Its authorization identifier is
`owner-2026-10-16-ebfc-location-attempt-4`, recorded with the existing action
audit and location-only queue marker. The original execution policy remains
pinned at three attempts, with USD1 per run and USD16 shared; earlier attempts,
usage, prices, readings, checkpoints and reviewer decisions remain retained.

The worker validates the exact prospective fourth marker before reserving or
sending work. Exhausted field research without that authorization is given up
unsent, including ordinary Retry/Resume after the fourth. The normal intent
save counts the fourth before dispatch; failure or history restore cannot
replenish it. Source protection, final-attempt handling and all money limits
continue to apply. This exception provides no fifth attempt or additional
attempt for another record or processing stage.

If `SPECIMEN_RESEARCH_HARNESS` is rolled back to "on", a run field research
left `retry_scheduled` (`field_research_timeout`, `field_research_model_error`,
`lookup_operational_failure`) is refused by native provisioning when its retry
comes due (`research_provision_run_unavailable`: native provisioning does
not accept a run at that stage), and each such run needs a manual Resume
(or Retry), which returns it to `plan`.

The worker check behind G38 derivation and the per-field research retry
(application.derivation_readiness) reports those native-only features as
unavailable when the worker runs with `SPECIMEN_RESEARCH_HARNESS=fields`. That
is intended: field research has neither.

The six-specialist code stays in the repository, unused by production, until
field research is proven live; a later pull request deletes it with its tests.
