# Cost meter reconciliation

Authority: the owner's approval of 2026-10-20, relayed by the coordinator
session (the same words as [COST_METER.md](COST_METER.md)): "Yes, build the
in-app tenant cost meter (option A): per organization and collection totals,
per-tenant budget caps, shared Google costs split by usage, monthly check
against the real bills."

Once a month, compare what the meter says it spent with what Hugging Face and
Google Cloud actually billed, and say where the two differ and why. This is
offline operator tooling. It reads three files that the operator fetches with
read-only commands and writes two report files. It deploys nothing, calls no
API and reads no production data itself.

- Logic: `src/specimen_digitization/application/cost_reconciliation.py`
  (`reconcile`, `render_markdown`), with no I/O.
- Command: `scripts/ops/reconcile_costs.py`.
- Tests: `tests/test_cost_reconciliation.py` and
  `scripts/ops/test_reconcile_costs.py`.

## What is compared

A gap is always `metered - billed`: positive when the meter is above the bill.

| Pair | Billed side | Meter side |
|---|---|---|
| Each Hugging Face model | The usage page's requests and nano-USD for the model, summed over the month's UTC days | The model's paid-call rows, found through the route registry: settled (cost basis not `reserved`) and held (basis `reserved`) |
| Each Google cost family | The family's lines, cost plus the free-allowance credits ("billed after allowance") | The family's rows: before the free allowance (`listCostMicros`) and after it (`costMicros`) |

Google families, by the bill's service and SKU (`google_family`):

| Family | Bill lines | Meter rows |
|---|---|---|
| `specimen-sam` | Cloud Run `Services CPU/Memory (Instance-based billing)` | Direct SAM 3 calls (provider `google_cloud`, resource `sam3`) and allocation rows for `specimen-sam` |
| `specimen-worker` | Cloud Run `Jobs CPU/Memory` | Allocation rows for `specimen-worker` |
| `specimen-api` | Cloud Run `Services CPU/Memory (Request-based billing)` and `Requests` | Allocation rows for `specimen-api` |
| `storage` | Every Cloud Storage line | Allocation rows of stage `storage` |
| `database` | Every Cloud SQL line | Allocation rows for `cloud-sql` or of stage `database` |

The standard export does not name the Cloud Run service, so every
instance-based SKU is taken to be `specimen-sam`, the only instance-based
service the app deploys.

Everything else on the Google bill (Artifact Registry, Logging, Secret Manager,
Firebase Hosting, SQL Connect, Monitoring, BigQuery, network lines of Cloud Run,
and so on), and any `tax` or `rounding_error` row, is listed as **not metered**
with its amount. Tool calls (provider `tool`) and any Google row the check
cannot place are listed beside the comparison and never compared with a bill.

The allocation rows come from the shared-Google-cost change (COST_METER.md,
"What the later changes add"). The check works with or without them: with none,
the Google families compare against direct SAM 3 calls only and say so. It
recognizes an allocation row by source `allocation`, kind `allocation` or an
`allocationMethodId`; places it by its resource (`specimen-sam`,
`specimen-worker`, `specimen-api`, `cloud-sql`) or, failing that, its stage
(`label_finding`, `worker`, `api`, `storage`, `database`); and takes a row
whose method id contains `free-allowance` as a free-allowance credit (negative
`costMicros`, `listCostMicros` 0). If that change writes rows differently,
`meter_family` and its tests change with it.

## The three inputs

Keep every input file private. The meter rows carry organization and collection
UUIDs, which never go into this public repository. `reconcile_costs.py --month
YYYY-MM --print-queries` prints the commands below for the month.

### 1. Meter rows (Data Connect, read-only)

Run as a project owner with Application Default Credentials
(`gcloud auth application-default login`; the caller needs the
`firebasedataconnect.services.executeGraphqlRead` permission, which a project
owner has). The query reads `CostEntry` for the month across every
organization, 1,000 rows a page, ordered by key. Run the printed `curl` loop,
which sends the query to the service's `executeGraphqlRead` endpoint with an
offset of 0, 1000, 2000 and so on until a page holds fewer than 1,000 rows
(at most 100 pages), writing one file per page; a response that is not a page
of rows (an error body) stops the loop and stays in its file. Pass every page
file to `--meter-rows` (repeatable); a row that appears on two pages counts
once. If a file holds a multiple of 1,000 rows, the command warns (on standard
error and under "Warnings" in the report) that the next page may not have been
fetched. The endpoint refuses mutations. The query asks for the columns the
check uses and not `usage`.

The file may be the response (`{"data": {"costEntries": [...]}}`), the list of
rows, or one row per line.

### 2. Hugging Face bill (the usage page)

Sign in at huggingface.co as the account that pays for Inference Providers, open
`https://huggingface.co/settings/inference-providers/overview`, choose the month
on the page, open the browser console and paste the one-line snippet that
`--print-queries` prints. It copies the page's `inferenceUsageMetrics` (from the
`[data-props]` JSON) to the clipboard; paste that into a file and pass it to
`--huggingface`. The snippet reads nothing but `data-props`: no cookie, storage,
header, token or network call. Days on the page are UTC.

Two shapes are accepted: that raw object (a `histogram` of days with one bar per
model carrying `numRequests` and `usedNanoUsd`), or a hand-made file
`{"days": {"YYYY-MM-DD": {"<model id>": {"requests": 3, "nano_usd": 2500000000}}}}`.
The raw reader looks for those two names and a model name under a few likely
keys, and fails with the keys it saw when it cannot place a layout; see "Not
confirmed".

### 3. Google bill

Either of these, or both:

- **The billing export in BigQuery** (best; needs the owner's one-time step
  below). `--print-queries` prints two queries for a dataset table you name with
  `--bq-table PROJECT.DATASET.gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` (the
  account id with underscores for dashes): one by invoice month, as a statement
  groups it, and one by usage time over the month and a day either side, which
  also catches usage invoiced the next month. Save the SQL to a file and run
  `bq query --nouse_legacy_sql --format=json --max_rows=1000000 < query.sql >
  google_export_YYYY-MM.json`. Each row is one hour of one SKU. The report puts
  each row on a day in the billing-day time zone and drops days outside the
  month.
- **Figures read from the console report**, for a month with no export yet:
  Billing, Reports, time range by charge period (usage date) for one day,
  grouped by SKU, with the table set to 50 rows a page (it pages ten). Write one
  line per SKU and day:
  `{"lines": [{"service": "Cloud Run", "sku": "Jobs CPU in us-east4", "day": "2026-10-17", "cost_usd": 0.05, "credits_usd": -0.05}]}`.
  `credits_usd` is zero or negative as the console shows it. The console puts
  every credit in one column, so a promotion credit would be read as the free
  allowance; use the export when the account holds promotion credits.

Pass the file or files to `--google` (repeatable). Giving the hourly export and
the console's daily lines together also runs the billing-day check.
`--project` (default: the committed project) keeps only that project's export
rows; rows of other projects on the billing account are totalled apart and
shown, because the free tier is shared across them.

## The owner's one-time step: turn on the billing export

Only the owner can do this, in the Google Cloud console (a console action on
the billing account, not a deployment). It costs pennies and starts filling a
table the check reads every month.

1. Choose the project that will hold the data (Google recommends a separate
   small project) and check that billing is on for it and that it is linked to
   the same billing account that pays for the app.
2. In BigQuery, open the project's View actions menu and choose Create dataset.
   Choose the data location **US (multiple regions in United
   States)**, and leave "Enable table expiration" cleared: deleted export
   tables cannot be refilled. The location cannot be changed later. A dataset
   in a multi-region (US or EU) is filled backwards from the start of the
   previous month when the export is first enabled, which can take up to five
   days to arrive; a dataset in a single region (us-east4 included) is not, and
   only holds usage from the day it is enabled. That is why US is chosen.
3. In the console go to Billing, pick the billing account, then **Billing
   export**, the **BigQuery export** tab. In the **Standard usage cost**
   section choose Enable (the page's wording is "Enable [data type] export"),
   select the project and dataset, and Save. If asked, enable the BigQuery API.
4. Roles needed: **Billing Account Costs Manager** or **Billing Account
   Administrator** on the billing account, and **BigQuery User** on the project
   that holds the dataset. Google adds `billing-export-bigquery@system.gserviceaccount.com`
   as an owner of the dataset; do not remove it, or the table stops updating.
5. The first rows can take a few hours; there is no delivery guarantee. If the
   export is disabled and re-enabled, usage for the gap may be missing.

The table is `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`. Cost: loading is
free; BigQuery storage in the US multi-region is $0.02 per GiB-month with the
first 10 GiB free, and queries are $6.25 per TiB with the first TiB a month
free (cloud.google.com/bigquery/pricing, researched 2026-10-20). A standard export of
one small project is expected to stay far below either free allowance (an
estimate, not a figure from a Google page).

## How a gap is judged

- The limit is the larger of USD 0.05 and 5% of the billed amount
  (`--abs-usd`, `--relative`). A gap strictly above it is flagged. A flag
  carries the explanations below that the inputs support, or `unexplained`.
- Hugging Face compares the bill with the meter's settled plus held figure. The
  settled-only gap is reported too.
- Google compares billed-after-allowance (cost plus free-allowance credits)
  with the meter after the free allowance, and reports the meter before it
  against the bill's cost as `gap_list_micros`. Credits of the free-allowance
  type are `FREE_TIER` (add others with `--free-credit-type`). Every other
  credit (a promotion, a no-cost trial, a discount) is not subtracted in the
  comparison, because the meter has no counterpart to it, but it is never
  hidden: the headline gives the cost, the free-tier credits, the other credits
  by type and the net charge, the family and unmetered tables carry an "Other
  credits" column naming the types and a "Net charge" column, and the JSON has
  `billed_other_credits_by_type` and `billed_net_micros` for each family and for
  the Google total.
- The total is flagged when both bills were supplied and the whole-month gap
  exceeds the limit; the like-for-like total leaves out the Google lines the
  meter does not cover and the rows that have no bill.

| Code | Where | Shown when |
|---|---|---|
| `held_calls` | Hugging Face, Google SAM | The meter is above the bill and holds calls with unknown spend (a timeout, a server error, no usage reported), counted at their reservation. For Hugging Face it says whether the settled calls alone are within the limit |
| `provider_discount` | Hugging Face | The request counts agree (within the held calls) and the bill is under 97% of the settled figure, as with cached input |
| `billed_above_list` | Hugging Face | The request counts agree and the bill is over 103% of the settled figure; names the price list versions on the rows |
| `requests_outside_meter` | Hugging Face | The bill counts more requests than the meter has calls (refused ones included): calls made outside the app on the same account, or rows the sweep has not written |
| `calls_not_billed` | Hugging Face | The meter settled more calls than the bill has requests |
| `no_meter_rows` | Hugging Face | The bill has a model the meter has no call for; says whether the registry names the model |
| `route_not_in_registry` | Hugging Face | The meter has calls on a route that the registry does not name |
| `day_boundary` | Hugging Face | At least half of the daily gaps (by absolute size, and more than half the limit) sit on the month's first or last UTC day |
| `no_allocation_rows` | Google | The meter is below the bill and holds no allocation rows for the month |
| `missing_allocation_days` | Google | The meter is below the bill and the family has billed days with no allocation row; says if only the bill's latest day is missing |
| `free_allowance` | Google | The free-allowance difference points the same way as the gap and is at least half of it. When the family's lines carry other credit types it names them first, with the `--free-credit-type` re-run to try if one is the free tier, and blames the shared free tier only "otherwise", when the meter allowed more than the bill gave |
| `other_credits` | Google | A flagged family has other credit types and `free_allowance` did not apply: names them and the net charge |
| `intake_jobs` | Google worker | The meter is below the bill: Jobs SKUs also bill the intake jobs |
| `storage_non_bytes` | Google storage | The meter is below the bill and some billed Cloud Storage SKUs are operations or transfer |
| `day_boundary` / `billing_zone` | Google | The billing-day check finds another zone fits the console's days better than the zone in use |
| `unmetered_services`, `tools_without_bill`, `flagged_items` | Total | The total is flagged: what the bill holds that the meter cannot cover, and the items flagged above |

### The billing-day time zone

Google's documentation says a day in the billing report starts at midnight US
Pacific time, with daylight saving (the Cloud Billing reports page, researched
2026-10-20). A hand reading of the console on 2026-10-17 took the day to be
UTC-5 instead; which is right is unverified. The check settles it from data:
given hourly export rows and the console's daily lines together, it cuts the
hourly rows into days in UTC, America/Los_Angeles and UTC-5, and reports which
differs least from the console's figures (the summed difference of the daily
cost per SKU, over the console days the export fully covers). When the
second-best zone is within USD 0.01 of the best, no winner is named and the
zones within USD 0.01 of the best are listed as indistinguishable, since the
console rounds to cents; a day-boundary hour with real usage separates them.
A best fit other than `--billing-zone` (default America/Los_Angeles) is flagged
and the message names the option to re-run with. Allocation days are read in the
same zone.

America/Los_Angeles is implemented in the module as the US rule since 2007
(second Sunday of March to first Sunday of November) so the check does not need
a time zone database; other names go through Python's `zoneinfo`.

## Known structural gaps

The report prints these on every run, because each can leave a gap that no
meter fix removes:

- The Jobs SKUs bill every Cloud Run job of the project, and the intake jobs
  bill under them. The meter does not allocate the intake jobs.
- Google services other than Cloud Run, Cloud Storage and Cloud SQL are not
  metered.
- Google's free tier is aggregated across all projects of the billing account
  (cloud.google.com/run/pricing, researched 2026-10-20), so another project's usage
  can use up what the meter assumed was free.
- Held calls are counted at their full reservation; the bill charges what
  finished.
- A provider can charge less than the list price (cached input), so a gap with
  matching request counts can be a discount.
- Tool calls have no provider in the meter and are never compared.
- Google reports late usage on the next invoice month, so the latest days of a
  bill can change after the report.

## Running it

```
uv run --frozen python scripts/ops/reconcile_costs.py --month 2026-10 --print-queries
uv run --frozen python scripts/ops/reconcile_costs.py --month 2026-10 \
    --meter-rows cost_rows_2026-10_0.json --meter-rows cost_rows_2026-10_1000.json \
    --huggingface hf_usage_2026-10.json \
    --google google_export_2026-10.json --google console_lines_2026-10.json \
    --out-json reconcile_2026-10.json --out-md reconcile_2026-10.md
```

Without `--out-md` the Markdown report is printed. An input the check cannot
read stops it with `error: <file>: <why>` on standard error and exit status 2,
and writes nothing: a path that does not exist or cannot be opened, a
directory, a file that is empty or only whitespace, a file that is not UTF-8
text, text that is neither JSON nor JSON Lines, or a file whose content is not
one of the shapes above. A folder for `--out-json` or `--out-md` that does not
exist is refused the same way before any input is read. Either bill may be left
out; its section then says so, and the overall comparison is marked partial.

## Not confirmed

- The raw field names of the usage page's `inferenceUsageMetrics` beyond
  `histogram`, `numRequests` and `usedNanoUsd`: no raw page object was available
  when this was written, so the raw reader is tested against layouts made up
  from the names the 2026-10-17 and 2026-10-18 hand readings reported. The first
  real month may need the reader adjusted; the normalized shape always works.
- Whether the page's request count includes calls Hugging Face refused. The
  check treats refused meter calls as possibly counted (`requests_outside_meter`
  compares against all meter calls).
- Which credit type the Cloud Run free tier carries in the export (`FREE_TIER`
  is assumed; the pricing page calls it a spending-based discount).
- The billing-day zone, and the zone of `invoice.month` (Pacific is implied, not
  stated for that column).
- That the console's Standard usage cost section is labelled as above.
- The exact `costEntries` argument names in `executeGraphqlRead` on the
  deployed service. The query uses `where`, `orderBy`, `limit` and `offset`
  as `scripts/data/cost-meter-test.mjs` does against the emulator (which uses
  `limit:2000`); try `limit: 1` first, and lower the page size if the service
  refuses 1,000. A raw list read that names no `limit` returns at most 100 rows
  (the cost meter's first change, SESSION_LEARNINGS 2026-10-20), so the
  query always names one.
- How the allocation change writes its rows (see "What is compared").
- Whether Cloud Run jobs and instance-based services share one free allowance
  (the pricing page prints the same amounts in two blocks and does not say).
