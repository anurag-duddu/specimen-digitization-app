# First-ten cohort reservations and reader deadlines

The evidence-only worker may opt into `cohort_allocation_mode: "actual-regions-v1"`
in its immutable `PilotLaunch`. This requires the complete stage cost map and the
existing exact ten source bindings. `per_specimen_cost_limit_micros` remains a
ceiling for every specimen; `total_cost_limit_micros` is the fixed cohort ceiling.
This mode is useful when segmentation produces different region counts.

Before the first SAM effect, one document compare-and-swap validates all ten
bindings and execution policies and reserves each specimen's SAM price times its
maximum attempts. If any baseline or their sum cannot fit, no effect starts.
The same write binds a digest of all ten baseline rows. Every later admission
checks the complete baseline or expanded row set, so changing another specimen
cannot leave the current specimen admissible. Partial, changed, or previously
used initial allocations cannot be recreated.

After all ten segmentations are positively retained, the existing reader barrier
computes the cost and capacity of every region, both pinned readers, and every
permitted workflow attempt. One compare-and-swap expands all ten run holds and
writes the complete reading reservation together. It preserves the initial SAM
holds, including unused retry allowances, and every consumed or unknown cost.
If any specimen or the combined cost, token, call, step, or original time budget
fails, all readers remain blocked and every region remains available for review.

Admission after expansion recomputes the expected hold from the pinned policy and
retained regions. Restarts cannot grow the reservation again, reset the launch
identity or deadline, release an unknown result, or replay a dispatched reader.
The immutable provider/SAM allocation in protected runtime admission still bounds
the launch total. This feature creates no extra execution or cost authority.

For example, with fixture prices of 17 microdollars for SAM and 59 plus 89 for a
reader pair, ten SAM stages and eleven retained regions need 1,798 microdollars.
A common per-specimen ceiling of 1,000 can remain in place without reserving
10,000. These are synthetic test values, not production prices or a live quote.
Actual region counts and native model performance remain unknown until measured.

`ExecutionPolicy.reader_timeout_seconds` optionally shortens transcription only.
It must be finite, positive, and no greater than `external_timeout_seconds`.
Segmentation, classification, extraction and other stages retain their existing
timeouts. The resolved reader deadline is used for workflow active-time checks,
reservation, late-result handling and release; the cohort's full reading time;
the isolated child process; the agent; and half that duration for each of the two
possible HTTP requests. Existing output and request limits remain unchanged.
With the optional timeout, admission uses the next workflow step's deadline.
The evidence-only local review transition and completed review rows retain the
existing five-second safety margin without requiring another model timeout.
All-ten snapshots still check every row; SAM retains its full admission window.

At a one-second polling interval and one workflow attempt, a cohort of R regions
reserves `15 + 2 * R * (reader_timeout_seconds + 1)` seconds for readings. A
30-second reader bound reserves 697 seconds at eleven regions, leaving at most
803 seconds for all prior work in the original 1,500-second worker window.
Segmentation can retain its 120-second per-effect ceiling. These limits do not
prove that actual models finish in time. An infeasible cohort remains incomplete;
no specimen or region may be removed to change that result.

Both additions are omitted from serialized values when absent. Existing launch,
policy, profile and ledger digests retain their legacy values and behavior.
Changing either field on an already pinned launch/run requires the existing
reconciliation process; this does not migrate or reprice prior work silently.
The lane still ends in human evidence review, without classification, institutional
clearance, or an automatic finalized record.
