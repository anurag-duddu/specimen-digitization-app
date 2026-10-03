# Runtime ops scripts

Plain scripts that put the SAM 3 service and the worker job in place. Run them from the repository root with
`uv run --frozen python scripts/ops/<script>`. Each one is safe to re-run. Settings come from
`scripts/ci/runtime_settings.py` and are never copied into these scripts. With `DRY_RUN=1`, a script prints every
command, reads included, and runs none of them. Secret values are never printed.

`PROJECT` and `REGION` default to the committed settings (`specimen-digitization`, `us-east4`). Each script's
docstring lists its other parameters.

## Before you start

- Sign in to `gcloud` as a project owner.
- The seed script needs both: the `gcloud` sign-in, with which it reads the secrets `specimen-worker-actor-uid` and
  `specimen-collection-bindings`, and application-default credentials (`gcloud auth application-default login`),
  with which it calls Data Connect as the worker actor. The project owner's own credentials suffice. Impersonating
  `specimen-worker-runtime` instead (`IMPERSONATE=<its email>`) is opt-in and needs
  `roles/iam.serviceAccountTokenCreator` on it, which `roles/owner` does not include and `iam.py` does not grant.
- The runtime secrets are granted at their pinned versions (`runtime_settings.SECRET_VERSIONS`), each by a binding
  conditioned on that one version: `huggingface-runtime-token` v2 to the worker; `specimen-worker-logfire` v1 to the
  worker, SAM 3 and the API; `specimen-worker-actor-uid` v1 to the worker; `specimen-collection-bindings` v1 to the
  worker and the API; `specimen-source-registry` v1 to the API. The owner's setup (`owner_setup.sh`) grants them. `iam.py`
  grants no secret access.
- Build and deploy a commit that is pushed to GitHub and reaches `main` by a merge, not a squash or rebase.
  `deploy.py` labels the service and the job `source-sha=<that commit>`, so the deployed commit can be read back.

## Run order

| Step | Command | Result |
|---|---|---|
| 1 | `uv run --frozen python scripts/ops/sam_checkpoint.py` | Prints the checkpoint digest. It downloads nothing when every checkpoint file is already in the bucket, as it is now. It stops if the bucket listing fails. |
| 2 | `uv run --frozen python scripts/ops/iam.py` | Grants for the worker, SAM 3 and the API, none on a secret. Grants on the service and the job are skipped until they exist. |
| 3 | `uv run --frozen python scripts/ops/build_images.py` | Enables Cloud Build and builds the `worker` and `sam` images, tagged with the commit SHA. Prints their digests. |
| 4 | `uv run --frozen python scripts/ops/deploy.py sam` | Deploys the private SAM 3 service with the read-only checkpoint mount. |
| 5 | `uv run --frozen python scripts/ops/deploy.py worker` | Defines the worker job: one task, no retries, 3600 s. |
| 6 | `uv run --frozen python scripts/ops/iam.py` | Adds the invoker grants on `specimen-sam` and `specimen-worker`. |
| 7 | `ORG_ID=<uuid> uv run --frozen python scripts/ops/seed_allowance_ledger.py` | Creates the program's allowance ledger as the worker actor, only if it is absent, in the one collection `specimen-collection-bindings` binds to `insects`. |
| 8 | `uv run --frozen python scripts/ops/scale_sam.py 1` | Before the import: keeps one SAM 3 instance running. Alternatively, deploy in step 4 with `SAM_MIN_INSTANCES=1`. |
| 9 | `uv run --frozen python scripts/ops/warm_sam.py` | Returns once SAM 3 has loaded its model. |
| 10 | Import the ten specimens in the app. | Right after step 9. Each import starts a worker execution (`jobs:run`) at once. |
| 11 | `uv run --frozen python scripts/ops/scale_sam.py 0` | After the ten have finished (all in a queue state). REQUIRED: stops the warm instance, which is billed for as long as it runs (about USD 0.37 an hour: 4 vCPU and 16 GiB at the instance-based list prices of cloud.google.com/run/pricing, Tier 1, which includes us-east4). It also restores the minimum of 0 at both levels. |

Steps 1 to 3 do not depend on each other. Steps 8 and 11 print the minimum at the service and revision level.

## Starting the worker

The API starts the worker itself. It calls `jobs:run` on `SPECIMEN_WORKER_JOB`, which is already in the API's
committed environment. Its identity holds `run.invoker` on the job from step 6.

To start the worker by hand instead, run steps 8 and 9 first, then step 11 when it has finished:

```
gcloud run jobs execute specimen-worker --region=us-east4
```

## Tests

```
uv run --frozen pytest -q scripts/ops
```
