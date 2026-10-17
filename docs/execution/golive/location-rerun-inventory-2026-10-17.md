# Location rerun inventory, 2026-10-17

Task: `LOCATION-RERUN-INVENTORY-20261017`. Branch `claude/location-rerun-inventory`.
Read-only: no production write, no paid model call, no source request.
Observed 2026-10-17 between 12:50 and 13:20 UTC, against `origin/main` at `7f0447c3`.

## In short

- Production holds **24 specimens**, all in the Insects collection. None of the
  other 17 collections has a specimen yet, so this list is the whole queue.
- **4 records have a location value in the wrong place.** Three of them ran before
  any of the location fixes. The fourth (`ebfc6171`) came out wrong again on its
  fourth live attempt at 05:50 UTC today. It saved a village in Mexico as its city,
  then derived the Philippines as that city's country.
- **4 more are incomplete** in shapes the fixes address. **3 never finished field
  research or are blocked.** **1** is an old run whose values look right but were
  never checked against a source. The other **12 need no rerun**.
- A batch "Start new run" of the 11 records outside `ebfc6171` needs **about
  $5 to $11** of room under the program allowance, at what past runs were charged.
  The allowance has **$0.84** left. Raising it is the owner's decision (G30).

## Method

1. `executeGraphqlRead` on the Data Connect service (read-only; the API refuses
   mutations): every `Specimen` row, then each one's `SpecimenSnapshot` at its
   current revision.
2. For snapshots with an `active_graph`, the generation-pinned run graph
   `application/sha256/<digest>` from the Storage bucket (GET only, digest checked).
   Older snapshots keep the run inline.
3. The five location fields of each run (`country`, `province_state`, `county`,
   `city`, `precise_location`), with their literal, saved value, authority, recorded
   reason and the source excerpts in the run's evidence.
4. The program allowance ledger (`worker_cursor` document named by
   `ProgramLedger.ident`), read for its totals and per-run entries.

## Records

The Insects collection is `200d7057-23fa-41ab-875b-682c8ba218c9`. "Last research"
is the time of the run's last field research call.

### Wrong value saved (4)

| Record | Saved now | Last research | Read |
|---|---|---|---|
| `ebfc6171` | City "Illinois" with authority `nga:16400756`, which the run's own NGA excerpt lists as "P.PPL, in Coahuila, MX". Country "PH", derived "from city = nga:16400756", a parent that excerpt does not give it. (The Philippine "Illinois" hits in the same excerpt are other ids, all streets.) State and county unresolved ("Getty TGN could not be reached"). | 2026-10-17 05:50, attempt 4 of the same run | 25 minutes after #355 merged; the build that served it is not recorded in the run. Open PR #360 describes this record's case ("retains the old PH country and Illinois city"). Its description does not mention the country derived from a Mexican village. |
| `f35af3a5` | "Davao Prov." split: county "Davao", province "Prov." unresolved; country ambiguous | 2026-10-11 14:11 | Before every location fix. `test_a_philippine_province_with_its_unit_word_is_never_a_county` (added 2026-10-12) covers this shape. |
| `48a71d53` | City "Mindanao" (an island); country "Philippine Islands", no authority | None (run of 2026-10-03, before field research existed) | Needs a new run to be checked at all. |
| `cb903c0e` | County "Mindanao"; country "Philippine Islands", no authority | None (run of 2026-10-03) | Same as above. |

### Incomplete, in a shape the fixes address (4)

| Record | Saved now | Last research | Read |
|---|---|---|---|
| `d10333ff` | State Illinois and Edgar County supported; country unresolved because reader 3A wrote "Panama" and 3B "Panorpa sp." | 2026-10-12 22:01 | Before #335 and #339 (#339 lets a supported Illinois field derive Country "United States" when Country is blank). This country is not blank: it holds a reader's literal, so whether #339 applies is **not confirmed**. Inference: "Panama" is a misreading of the genus *Panorpa*. |
| `3781e440` | Country USA supported; province "Ill." unresolved (TGN 403); county "Coles Co." unresolved because the province is not settled (Wikidata did confirm Coles County) | 2026-10-12 20:40 | Before #331. The same "Ill. / Macoupin Co." shape settled live on `a1efc490` on 2026-10-16. No test names Coles County. |
| `2b02009d` | Country ambiguous between Mindanao island and island group; "P.I." on the label | 2026-10-12 21:18 | No fix targets this; a rerun may still end in review. |
| `93e61763` | Province "Chimaltenago" refused as "not in the country the label gives", although its sibling `d3fb389f` settled Chimaltenango Department | 2026-10-11 16:33 | The one-letter test predates this run, so it failed by another path. Not confirmed that main fixes it. |

### Research not finished, or blocked (3)

| Record | State | Read |
|---|---|---|
| `19f0f1f6` | All location fields unresolved: "The run reached one of its processing limits". No field research call. | First pass was booked at $0.64; a new run is needed. |
| `1d842828` | All location fields unresolved: "The run's cost limit was reached". One research attempt began (2026-10-12 20:38) and was stopped before any location field was checked. | First pass was booked at $0.64; a new run is needed. |
| `e98a924c` | `processing_blocked`, blocker `external_outcome_unknown`, since 2026-10-09 | Needs an operator to start a new run. |

### Old run, plausible but unchecked (1)

`9cc24b07`: Guatemala and Yepocapa from the 2026-10-03 run, no authority, state
and county unknown. Rerunning it is optional.

### No rerun needed (12)

`01b79931`, `13c99e90`, `2c6ef7b0`, `2cd0f1ed`, `636865d4`, `66a72095`, `74efda01`,
`8562ded0`, `a1efc490`, `b191ed67`, `d3fb389f`, `f9d55015`. No value is saved in the
wrong place. A city or locality is left unresolved where no source has the place
(for example "Rock Island" in St. Clair County, "Beaver Dam S.P.", "Tanac").
`d3fb389f` also flags its county ambiguous, because the department name the
readers spell two ways was weighed as a county; the label names no county.
`13c99e90` and `636865d4` carry no location on the label.

## Offline replay: not run

The plan was to replay each record's recorded source answers through current main
offline. That was dropped because the method has already failed once. On
2026-10-16 the captured-source replay of `ebfc6171` (`.context/ebfc-captured-source-replay.py`
in the Conductor worktree) predicted United States / Illinois / Clark County. The
fix it checked was released by 02:27 UTC on 2026-10-17, by the Codex session's
public-marker check. The live fourth attempt at 05:50 UTC then saved PH with
Illinois as the city again. The replay rebuilds the experts' outcomes from trace
codes and reuses old source answers, so it cannot show what live experts and live
sources will do. The tables above cite the regression tests that cover each shape
instead.

## What a batch rerun costs

The ledger counts what each step was charged: the computed cost once a step
settles, or its full reservation when no cost was computed.

| | USD |
|---|---|
| Program allowance (`allowance_micros` on the newest ledger entries; older entries carry 15 and 5) | 16.000 |
| Charged so far (`reserved_total_micros`, ledger revision 1006, 05:50:51 UTC) | 15.161 |
| Left | 0.839 |
| Of the charge: ordinary steps settled at a computed cost | 1.867 |
| Of the charge: research effects (97 settled 0.519, 2 held 0.212) | 0.731 |
| Of the charge: 123 ordinary steps booked at full reservation (segment 4.558 across 25, first pass 4.780 across 15, parse 1.745 across 30, transcribe 1.060 across 53) | 12.143 |

These three parts sum to 14.741. The other 0.420 of the total matches no entry in
the ledger document.

Across the 26 runs in the ledger, a run was charged $0.20 to $0.99 (median $0.49).
25 of the 26 paid $0.18 for segmentation, and most paid $0.06 or $0.12 for parsing,
both at reservation. 10 of the 26 also carry $0.32 to $0.64 for a first pass whose
cost was never settled, booked at reservation.

Batch of the 11 records outside `ebfc6171`, at the median: about $5.40. At the
observed maximum: about $10.95. Adding `ebfc6171` adds one more run.

## Batch rerun, 2026-10-17

This section is not read-only. It records the owner-approved "Start new run" on the 11
records outside `ebfc6171`, observed with the same read-only queries. Times are UTC.

### What ran

- 16:10: PR #365 merged (`4894bf2e`). It raised the program allowance to USD 28 (G30)
  and the G9 ceiling to USD 30. Both public markers later reported `ee727747`, which
  contains it, and every new run below pins `allowance_micros` 28000000.
- 16:27 to 16:40: "Start new run" on the 10 records other than `e98a924c`.
- 16:31 to 16:42: five `handwriting-muse` readings ended `provider_request_failed`
  after 60 s each, the client timeout (`reader_timeout_seconds` 120, halved for the
  Hugging Face gateway). The runs waited for a retry.
- 16:45:10: worker execution `specimen-worker-4fk49` exited 1 on a
  `requests.ConnectionError` (RemoteDisconnected) from a SQL Connect request made by
  `settle_step`. Nothing restarts the worker job (`maxRetries` 0; Cloud Scheduler and Cloud
  Tasks are disabled), so the due retries waited. `2b02009d` was in flight and stayed `running` with
  `external_outcome_unknown`.
- 17:52: Resume on `48a71d53` started execution `specimen-worker-plm6x` (succeeded,
  18:39). It handed over to `specimen-worker-zv22t` (succeeded, 18:48). `2b02009d`
  moved from `running` to `retry_scheduled` at 18:16 with no action, then completed.
- 17:56 to 17:58: on `e98a924c`, Pause, then Reconcile, then Start new run. The owner
  approved the three first-hand. A paused run's Reconcile clears the blocker and lease
  and queues nothing, so no more of the old run was sent.
- PR #369 (open when this was written) resends a dropped SQL Connect request and hands
  over after a drain crash.

### Outcome

All 11 new runs ended `completed` / `needs_human_review`, between 17:58 and 18:48.
Their usage records USD 5.459 reserved in total (USD 0.289 to 0.996 per run), with
`actual_cost_micros` null on every run. The ledger total rose from 15,161,257 to
20,620,245 micro-units (revision 1006 to 1265), by the same 5,458,988. USD 7.38 of the
USD 28 allowance is left. The inventory estimated USD 5.40 to 10.95.

By the inventory's groups:

- **Wrong value saved.** None of the three batch records saves its wrong value now.
  - `f35af3a5`: "Davao" is no longer its county (now ambiguous); its province is Davao
    (`wikidata:Q15095071`) and its country Philippines (`wikidata:Q928`).
  - `48a71d53`: city "Mindanao" is now not present, and its country is Philippines
    (`wikidata:Q928`). Its province "Davao Prov.", supported with no authority before,
    is now ambiguous.
  - `cb903c0e`: county "Mindanao" is now not present, and its country is Philippines
    (`wikidata:Q928`). Its province "Davao", supported with no authority before, is
    now ambiguous.
- **Incomplete.**
  - `d10333ff`: city Kansas settled (GEOLocate), and its locality now reads "4mi SSE
    Kansas" (was "4mi 8SE Kansas"). Its country is still not settled (unresolved, now
    ambiguous), although Illinois and Edgar County are supported.
  - `3781e440`: Illinois (`wikidata:Q1204`) and Coles County (`wikidata:Q112137`)
    settled. Its locality now reads "Fox Ridge State Park" (was "Forbidge State Park").
  - `2b02009d`: locality Mt. Apo settled. Its country is still ambiguous, and its
    province went from not present to unresolved.
  - `93e61763`: province Chimaltenango Department (`wikidata:Q765975`) settled. Its
    county went from not present to ambiguous, and its locality "Yepocapa" is now not
    present, with Yepocapa kept as its city.
- **Research not finished, or blocked.**
  - `19f0f1f6`: all five fields are unresolved again: "The run's cost limit was reached
    before this field could be checked", at USD 0.996 reserved of the USD 1 run limit
    (32 steps, 52 external calls). A rerun did not fix it.
  - `1d842828`: country United States (`wikidata:Q30`) and locality Fox Ridge State Park
    settled. Its province and county are ambiguous; its two readers disagree on that
    line ("Coles Co." and "USAI.C. Coleco.").
  - `e98a924c`: country Philippines, province Davao (`wikidata:Q15095071`) and county not
    present settled. Its city is unresolved; its locality reads "McKinley, Davao Prov.".
- **Old run.** `9cc24b07`: country Guatemala (`wikidata:Q774`), province Chimaltenango
  Department and city Yepocapa (GEOLocate) settled. Its county is ambiguous.

### Shapes still open

Not fixed here. Each record above is in human review.

1. County ambiguous where the label names only a first-level unit: `93e61763`,
   `9cc24b07`, `f35af3a5` and `48a71d53` (as `d3fb389f` in the inventory).
2. "Davao Prov." settles as the province on `f35af3a5` and `e98a924c`, but is ambiguous
   on `48a71d53` and `cb903c0e`, whose labels also name Mindanao.
3. Country not settled although lower units are: `d10333ff` (Illinois, Edgar County)
   and `2b02009d` ("P.I.").
4. `19f0f1f6` reaches its USD 1 run limit before field research checks a location. Its
   cause is not confirmed here.

### Per record

"Before" is the value the inventory read (run graph, or the inline run of an older
snapshot). Settled means supported or not present. "Lost" means a settled field is now
open; "changed" means a settled value or authority differs. "Ledger remaining" is
what was left of the USD 28 allowance just after that run's last charge.

#### `19f0f1f6`: completed / needs_human_review, run ecf0c26f, reserved 0.996 USD, ledger remaining 7.38 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | unresolved | unresolved | same |
| province_state | unresolved | unresolved | same |
| county | unresolved | unresolved | same |
| city | unresolved | unresolved | same |
| precise_location | unresolved | unresolved | same |

#### `1d842828`: completed / needs_human_review, run e94d6c04, reserved 0.333 USD, ledger remaining 9.17 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | unresolved | supported: United States [wikidata:Q30] | settled |
| province_state | unresolved | ambiguous | still open |
| county | unresolved | ambiguous | still open |
| city | unresolved | unresolved | same |
| precise_location | unresolved | supported: Fox Ridge State Park | settled |

#### `2b02009d`: completed / needs_human_review, run 280956be, reserved 0.974 USD, ledger remaining 8.28 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | ambiguous | ambiguous | same |
| province_state | not_present | unresolved | lost |
| county | not_present | not_present | same |
| city | not_present | not_present | same |
| precise_location | ambiguous | supported: Mt. Apo | settled |

#### `3781e440`: completed / needs_human_review, run 77c21030, reserved 0.344 USD, ledger remaining 9.05 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | supported: United States [wikidata:Q30] | supported: United States [wikidata:Q30] | same |
| province_state | unresolved | supported: Illinois [wikidata:Q1204] | settled |
| county | unresolved | supported: Coles County [wikidata:Q112137] | settled |
| city | unresolved | unresolved | same |
| precise_location | supported: Forbidge State Park | supported: Fox Ridge State Park | changed |

#### `48a71d53`: completed / needs_human_review, run 98cde4d2, reserved 0.351 USD, ledger remaining 8.13 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | supported: Philippine Islands | supported: Philippines [wikidata:Q928] | changed |
| province_state | supported: Davao Prov. | ambiguous | lost |
| county | unknown | ambiguous | still open |
| city | supported: Mindanao | not_present | changed |
| precise_location | unknown | supported: E. slope Mt. McKinley | settled |

#### `93e61763`: completed / needs_human_review, run 40d40a71, reserved 0.605 USD, ledger remaining 11.01 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | supported: Guatemala [wikidata:Q774] | supported: Guatemala [wikidata:Q774] | same |
| province_state | unresolved | supported: Chimaltenango Department [wikidata:Q765975] | settled |
| county | not_present | ambiguous | lost |
| city | supported: Yepocapa [geolocate:76853dedbc6ff5ce] | supported: Yepocapa [geolocate:76853dedbc6ff5ce] | same |
| precise_location | supported: Yepocapa | not_present | changed |

#### `9cc24b07`: completed / needs_human_review, run 9a7550cb, reserved 0.289 USD, ledger remaining 10.31 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | supported: Guatemala | supported: Guatemala [wikidata:Q774] | changed |
| province_state | unknown | supported: Chimaltenango Department [wikidata:Q765975] | settled |
| county | unknown | ambiguous | still open |
| city | supported: Yepocapa | supported: Yepocapa [geolocate:76853dedbc6ff5ce] | changed |
| precise_location | unknown | not_present | settled |

#### `cb903c0e`: completed / needs_human_review, run 42812953, reserved 0.315 USD, ledger remaining 10.20 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | supported: Philippine Islands | supported: Philippines [wikidata:Q928] | changed |
| province_state | supported: Davao | ambiguous | lost |
| county | supported: Mindanao | not_present | changed |
| city | unknown | unknown | same |
| precise_location | supported: E. Slope Mt. | supported: E. Slope Mt. | same |

#### `d10333ff`: completed / needs_human_review, run a75b4e51, reserved 0.324 USD, ledger remaining 10.08 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | unresolved | ambiguous | still open |
| province_state | supported: Illinois [wikidata:Q1204] | supported: Illinois [wikidata:Q1204] | same |
| county | supported: Edgar County [wikidata:Q484124] | supported: Edgar County [wikidata:Q484124] | same |
| city | unresolved | supported: Kansas [geolocate:efc839dbe9c3b055] | settled |
| precise_location | supported: 4mi 8SE Kansas | supported: 4mi SSE Kansas | changed |

#### `e98a924c`: completed / needs_human_review, run afaf11bb, reserved 0.615 USD, ledger remaining 9.31 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | unknown | supported: Philippines [wikidata:Q928] | settled |
| province_state | unknown | supported: Davao [wikidata:Q15095071] | settled |
| county | unknown | not_present | settled |
| city | unknown | unresolved | still open |
| precise_location | unknown | supported: McKinley, Davao Prov. | settled |

#### `f35af3a5`: completed / needs_human_review, run dcfcf68a, reserved 0.313 USD, ledger remaining 9.95 USD

| Field | Before | After | Change |
|---|---|---|---|
| country | ambiguous | supported: Philippines [wikidata:Q928] | settled |
| province_state | unresolved | supported: Davao [wikidata:Q15095071] | settled |
| county | unresolved | ambiguous | still open |
| city | not_present | not_present | same |
| precise_location | supported: E. slope Mt. McKinley | supported: E. slope Mt. McKinley | same |

## Open decisions for the owner

1. Raise the program allowance enough for the batch (G30 needs the owner). Done: the
   owner approved USD 28 and G9 USD 30 on 2026-10-17 (PR #365).
2. Whether `ebfc6171` joins the batch after PR #360 merges, or goes to human review
   if a fresh run fails again. PR #360 was still open when the batch ran.

The batch's outcome is in "Batch rerun, 2026-10-17" above.
