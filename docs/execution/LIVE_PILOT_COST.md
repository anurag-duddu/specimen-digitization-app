# First-ten resource and cost proposal

Status updated 2026-09-08: the user supplied a **USD 5 total maximum** for testing
the complete application/pipeline/agents/harness with the exact ten existing
Firebase object-storage specimens. The maximum is shared by all sessions,
attempts and test days; it is not USD 5 per agent or run. Resource actions and
the runtime/data deployment contract still require their existing review.
Project `specimen-digitization`; runtime region proposed `us-east4`. Initial
admin identity remains private. No runtime resource or IAM existence is assumed.

## Current budget and verified provider prices

Target ordinary reservations at or below USD 4 and retain USD 1 contingency.
Include inference, incremental runtime/startup, image build/registry/storage,
network transfers and backup/restore testing in that shared total. Existing
Cloud SQL baseline billing is reported separately; no capacity upgrade or new
always-on resource is included. No free-tier credit is assumed. A cumulative
ledger must survive sessions/retries; usage already incurred is not reset by a
new launch policy or process. Stop before an unpriced action rather than exceed
the user's limit. This budget does not remove backup or access-control gates.

| Proposed envelope | USD | Admission condition |
|---|---:|---|
| All model inference | 1.50 | Exact input/image accounting, per-request output limit, retry and region bounds, durable reservations |
| API, worker and CPU SAM including startup | 0.75 | Bounded executions and runtime expiry; no idle minimum instances |
| Builds, registry, object storage and transfer | 0.75 | Actual source/checkpoint/image bytes and retention period priced first |
| Incremental backup and isolated restore | 1.00 | Existing SQL tier and bounded temporary restore cost verified first |
| Contingency | 1.00 | Shared unspent reserve, not an automatic retry allowance |
| Total ceiling | **5.00** | Combined reservations plus incurred costs must fit |

These are planning allocations, not measured costs or a cloud-provider billing
cap. The coordinator may rebalance them within USD 5 after checking concrete
costs; unused infrastructure allocation need not be spent. Preserving retained
evidence and keeping the live app available have ongoing costs after the test
window, so continuing operation must be reported separately rather than called
free. Do not silently delete data to stop charges.

Current official prices, verified 2026-09-08, per million tokens:

| Explicit route | Input USD | Output USD | Source |
|---|---:|---:|---|
| Qwen3-VL-30B-A3B-Instruct / Novita | 0.20 | 0.70 | [Novita model pricing](https://novita.ai/models/model-detail/qwen-qwen3-vl-30b-a3b-instruct?from=pricing) |
| Muse-Glimmer-30B / DeepInfra | 0.30 | 1.20 | [DeepInfra model pricing](https://deepinfra.com/meta-models/Muse-Glimmer-30B) |

[Hugging Face routed billing](https://huggingface.co/docs/inference-providers/pricing)
passes through provider prices without markup. The non-paid preflight
`uv run --env-file .env specimen-huggingface-preflight` succeeded: both exact
routes are live, advertise image and structured-output support, the existing
token has the needed permissions, and the pinned SAM revision is accessible.
This is metadata/access proof, not a paid inference result or invoice.

Illustrative reading workload only: ten specimens, four regions each, two
independent readers, at most two requests per reader stage gives 160 requests.
At **assumed** 10,000 input/image tokens and 4,096 output tokens per request,
80 Qwen requests plus 80 Muse requests cost **USD 1.022592** at those rates.
Actual region/input counts, extraction/classification and other model stages
must be accounted for; the scenario does not establish a complete run quote.

The runtime audit subsequently identified why that illustration cannot yet be
used as an admission reservation. Reserving 131,072 input tokens and 4,096
output tokens on each of two requests costs USD 0.0581632 for Qwen and
USD 0.0884736 for Muse per reading stage. The current profile has one uniform
per-effect cost reservation, also applied to SAM. Rounding that reservation to
USD 0.09 consumes USD 4.50 across ten specimens with just two label regions
each: ten times one SAM plus four reading stages. This leaves only USD 0.50
for the independently accounted infrastructure envelope. It does not prove the
complete pilot fits. Runtime is checking enforceable input bounds and stage
reservations; actual source/region counts remain unknown. Do not discard regions
or replace source specimens to make the budget pass.

Coordinator TDD found that Pydantic usage totals are checked after responses;
they do not cap provider generation. A candidate repair supplies a per-request
maximum of 4,096 output tokens to the shared bounded runtime agent helper,
preserving stricter agent/output/total limits and the existing two-request and
16,000-total checks. Initial request and schema retry regressions were red before
the fix and green afterward. Input/image costs, full provider reservations and
all cloud charges still need their own bounds. Candidate review/validation is
recorded in `PRODUCTION_RELEASE_PLAN.md`; no live launch is claimed here.

## One shared scenario

The cohort denominator is ten. Actual source bytes and label-region counts are
unknown until the frozen cloud manifest exists. Use one worker execution, ten
SAM requests of at most 120 seconds each, and an illustrative **aggregate** 600
billed API instance-seconds (not 600 wall seconds for every instance).

| Component | Proposed initial resources | Scenario and controls |
|---|---|---|
| API service specimen-api | 1 vCPU/1 GiB, minimum 0, maximum 2, concurrency 8, request timeout 60s | 600 aggregate billed instance-seconds is an estimate, not a cap. Application Firebase/App Check/membership gates remain mandatory. |
| Worker Job specimen-worker | 1 vCPU/1 GiB, tasks1/parallelism1, platform retries0, timeout1800s | One execution; app deadline1500s; external effects max120s; only ten digest/generation-bound specimens; unknown outcomes require reconciliation. |
| CPU SAM service | 4 vCPU/16 GiB, minimum0/maximum1, concurrency1 | Ten120s requests =1200 active instance-seconds; startup/model download additional. Absolute expiry at most1hour from before download. Memory sizing is not measured live. |
| SQL | Existing instance; no new persistent instance proposed | Existing tier/storage/baseline spend unknown. One separately approved temporary restore clone proposed, with a two-hour initial TTL and no automatic extension. No source database deletion or replacement. |
| Artifact Registry/builds | One named runtime repository; API/worker/SAM immutable digests | Three builds; build duration and final compressed/uncompressed image sizes require measurement. Retain the released and rollback digests; retention approval remains separate. |
| Storage/backup | Existing source/evidence bucket; preserve generations and raw provenance | Source bytes, derivatives/raw observations/masks, SQL backup GiB and retained duration require metadata. No object deletion is proposed. |

API/worker attached identities use `specimen-api-runtime` and
`specimen-worker-runtime`; release/build/data identities remain separate. SAM
identity/ingress permissions need the same concrete least-privilege review and
worker-only invocation. Maximum instances and expiry constrain execution; they
do not cap all account, SQL, networking or provider charges.

## Compute arithmetic and unknown billable items

Using the pricing page's displayed default-region USD rates, before free tiers:

- Worker: 1800 × (1 × $0.000018 + 1 × $0.000002) = **$0.0360**.
- API: 600 × (1 × $0.000024 + 1 × $0.0000025) = **$0.0159**.
- SAM: 1200 × (4 × $0.000024 + 16 × $0.0000025) = **$0.1632**.

Illustrative inference-serving compute subtotal: **$0.2151**. This is not a full
pilot estimate or approved ceiling. Proposed-region SKUs and billing account
free-tier availability remain unverified. SAM startup/download would add
$0.000136 per active instance-second at those reference rates; actual billable
startup/CPU boost/model load must be measured. The pinned checkpoint is about
3.44GB per the processing owner; disk/memory allocation and transfers add costs.
See [Cloud Run pricing](https://cloud.google.com/run/pricing), checked 2026-09-08.

| Additional item | Required measurement or rate before total can be quoted |
|---|---|
| HF blind readers | Approved model/provider routes, input/output prices, image token accounting, per-stage conservative monetary reservation, total launch budget |
| SAM checkpoint | Pinned model revision/license/access; exact artifact bytes and transfer/cache behavior; startup duration |
| Builds and images | Build runner minutes, three final image sizes, regional registry GiB-month and pull/transfer rates |
| API/network | Actual requests and aggregate billed time; source/evidence upload/download bytes and regional/internet transfer rates |
| SQL baseline | Actual machine tier, running hours, storage/PITR/backup settings and rates; attributable existing cost shown separately |
| Restore rehearsal | One clone's actual tier/rate × bounded authorized hours, temporary storage and snapshot/backup retention costs |
| Evidence retention | Immutable originals/masks/crops/raw readings/history/log volume and approved retention; no assumed zero storage cost |
| Authentication/telemetry | Current App Check/reCAPTCHA, Auth, Secret Manager access/version, Logging and Logfire usage/tier |

## Provider reservation envelope

Evidence-only processing has one SAM stage and two independent reading routes per
region. Processing's proposed bound is up to two provider requests and 16,000
reserved tokens **per reader stage**. Actual region count is unknown; these are
scenarios, not claims about the ten specimens:

| Regions per specimen | Maximum reader requests across ten | Reader-stage token reservations across ten |
|---|---:|---:|
| 2 | 80 | 640,000 |
| 4 | 160 | 1,280,000 |

Do not multiply a blended token price by these totals to invent cost: routes can
charge input, output and images differently. The draft profile and private launch
policy must pin positive cost/call/token reservations and a reviewed region bound;
ten per-specimen allocations must fit the total launch limit. The source manifest,
launch policy, profile, runtime and pinned secret version must agree. No token
value, real source object name or admin identity belongs in this proposal.

## Decision packet still needed

The proposed resource names/sizes above can be reviewed now. The total budget is
now supplied: USD 5 for the entire test, with the same maximum on any single day
and no daily reset. A complete monetary proposal still needs cloud metadata/
authentication refresh, actual ten-object byte manifest, measured model/build
startup, exact reader-rate reservation policy and existing SQL/backup rates. Keep these
fields **Not confirmed** until measured. Authorize only the itemized bootstrap,
one bounded execution and independently verified evidence workflow; do not treat
this document or an illustrative subtotal as permission to spend.
