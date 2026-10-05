#!/usr/bin/env bash
# Push the image scripts/ci/build_runtime_image.sh built and hand its digest
# reference to the release job. The release deploys by digest, never by tag.
set -euo pipefail

role="${1:-}"
[[ "$role" == "api" || "$role" == "worker" || "$role" == "sam" ]] \
  || { printf 'Expected api, worker or sam image role.\n' >&2; exit 1; }
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || { printf 'Invalid source SHA.\n' >&2; exit 1; }
[[ "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ && "${GITHUB_RUN_ATTEMPT:-}" =~ ^[1-9][0-9]*$ ]] \
  || { printf 'Invalid run id or attempt.\n' >&2; exit 1; }

registry="us-east4-docker.pkg.dev"
image="$registry/specimen-digitization/specimen-runtime/$role"
# The repository has immutable tags, so a re-run needs its own tag: the run id and attempt make it unique.
tag="$image:sha-$GITHUB_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"

# gcloud turns the sign-in step's credential file into a registry token. The token only ever travels
# through a pipe: never a variable, an argument or a log line. The first call is a check, so a missing
# sign-in stops here with a clear line before docker runs.
command -v gcloud >/dev/null \
  || { printf 'gcloud is not on PATH: the build job needs the Google Cloud CLI to log in to the registry.\n' >&2; exit 1; }
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
gcloud auth print-access-token | grep . >/dev/null \
  || { printf 'gcloud printed no access token: the Google sign-in step must run before this script.\n' >&2; exit 1; }
gcloud auth print-access-token | docker login --username oauth2accesstoken --password-stdin "https://$registry"
docker tag "specimen-ci-$role:$GITHUB_SHA" "$tag"
docker push "$tag"

# The local image also carries digests of other names; only this repository's one is the pushed reference.
digests="$(docker image inspect "$tag" --format '{{range .RepoDigests}}{{println .}}{{end}}')"
reference=""
while IFS= read -r digest; do
  if [[ "$digest" == "$image@sha256:"* ]]; then reference="$digest"; fi
done <<< "$digests"
[[ "$reference" =~ /$role@sha256:[0-9a-f]{64}$ ]] \
  || { printf 'The registry reported no digest for %s.\n' "$tag" >&2; exit 1; }

printf 'image=%s\n' "$reference" >> "$GITHUB_OUTPUT"
printf 'Pushed %s\n' "$reference"
