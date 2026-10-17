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

## Open decisions for the owner

1. Raise the program allowance enough for the batch (G30 needs the owner).
2. Whether `ebfc6171` joins the batch after PR #360 merges, or goes to human review
   if a fresh run fails again.

Not confirmed: the outcome of any rerun. Only a live run shows that.
