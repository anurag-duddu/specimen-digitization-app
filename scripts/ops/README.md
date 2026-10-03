# Runtime ops scripts

Plain scripts that put the SAM 3 service and the worker job in place. Run them from the repository root with
`uv run --frozen python scripts/ops/<script>`. Each one is safe to re-run. Settings come from
`scripts/ci/runtime_settings.py` and are never copied into these scripts. With `DRY_RUN=1`, a script prints every
command, reads included, and runs none of them. Secret values are never printed.

`PROJECT` and `REGION` default to the committed settings (`specimen-digitization`, `us-east4`). Each script's
docstring lists its other parameters.

## Before you start

- Sign in to `gcloud` as a project owner.
- The seed script also needs application-default credentials (`gcloud auth application-default login`). It also
  needs `roles/iam.serviceAccountTokenCreator` on `specimen-worker-runtime`.

## Run order

| Step | Command | Result |
|---|---|---|
| 1 | `uv run --frozen python scripts/ops/sam_checkpoint.py` | Prints the checkpoint digest. The checkpoint is already in the bucket, so this downloads nothing. |
| 2 | `uv run --frozen python scripts/ops/iam.py` | Grants for the worker, SAM 3 and the API. Grants on the service and the job are skipped until they exist. |
| 3 | `uv run --frozen python scripts/ops/build_images.py` | Enables Cloud Build and builds the `worker` and `sam` images, tagged with the commit SHA. Prints their digests. |
| 4 | `uv run --frozen python scripts/ops/deploy.py sam` | Deploys the private SAM 3 service with the read-only checkpoint mount. |
| 5 | `uv run --frozen python scripts/ops/deploy.py worker` | Defines the worker job: one task, no retries, 3600 s. |
| 6 | `uv run --frozen python scripts/ops/iam.py` | Adds the invoker grants on `specimen-sam` and `specimen-worker`. |
| 7 | `ORG_ID=<uuid> COLLECTION_ID=<uuid> uv run --frozen python scripts/ops/seed_allowance_ledger.py` | Creates the program's allowance ledger as the worker, only if it is absent. |
| 8 | `uv run --frozen python scripts/ops/warm_sam.py` | Run this right before each worker execution. It returns once SAM 3 has loaded its model. |

Steps 1 to 3 do not depend on each other.

## After step 8

The API starts the worker itself. It calls `jobs:run` on `SPECIMEN_WORKER_JOB`, which is already in the API's
committed environment. Its identity holds `run.invoker` on the job from step 6.

To start the worker by hand instead:

```
gcloud run jobs execute specimen-worker --region=us-east4
```

## Tests

```
uv run --frozen pytest -q scripts/ops
```
