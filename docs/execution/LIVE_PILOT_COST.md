# First-ten resource and cost proposal

Status: proposal only, not spend authorization or a complete quote. Scope is the
exact ten existing specimens; no expansion, model calls or cloud changes occur
until the coordinator receives the user's budget and approves concrete actions.
Project `specimen-digitization`; runtime region proposed `us-east4`. Initial
admin identity remains private. No runtime resource or IAM existence is assumed.

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

The proposed resource names/sizes above can be reviewed now. A complete monetary
proposal needs cloud metadata/authentication refresh, actual ten-object byte
manifest, measured model/build startup, exact reader-rate reservation policy,
existing SQL/backup rates and the user's daily/total pilot budget. Keep these
fields **Not confirmed** until measured. Authorize only the itemized bootstrap,
one bounded execution and independently verified evidence workflow; do not treat
this document or an illustrative subtotal as permission to spend.
