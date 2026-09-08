#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
target="${1:-}"
case "$target" in
  api) dockerfile="containers/api/Dockerfile" ;;
  worker) dockerfile="containers/worker/Dockerfile" ;;
  sam) dockerfile="containers/worker/sam3.Dockerfile" ;;
  *) printf 'Expected api, worker or sam image target.\n' >&2; exit 1 ;;
esac
source_sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { printf 'Invalid source SHA.\n' >&2; exit 1; }
[[ -f "$dockerfile" ]] || { printf 'Not run: %s is absent.\n' "$dockerfile" >&2; exit 1; }
# Build without credentials, publishing, mounting private data or host networking.
image="specimen-ci-$target:$source_sha"
# Archive only the reviewed committed build inputs. Ignored credentials and local
# specimen files never enter the Docker daemon build context.
build_paths=(pyproject.toml uv.lock README.md src "$dockerfile")
if [[ "$target" == "sam" ]]; then
  build_paths+=(containers/worker/sam3-requirements.lock)
fi
git archive --format=tar "$source_sha" "${build_paths[@]}" | \
  docker build --platform linux/amd64 --build-arg "SOURCE_SHA=$source_sha" --file "$dockerfile" \
    --label "org.opencontainers.image.revision=$source_sha" --tag "$image" -
architecture="$(docker image inspect "$image" --format '{{.Os}}/{{.Architecture}}')"
[[ "$architecture" == "linux/amd64" ]] || { printf 'Image architecture is not the Cloud Run target.\n' >&2; exit 1; }
revision="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
[[ "$revision" == "$source_sha" ]] || { printf 'Image source label mismatch.\n' >&2; exit 1; }
docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges "$image" --help
if [[ "$target" == "api" ]]; then
  docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint python "$image" -c \
    'import importlib.resources,json,sys; p=importlib.resources.files("specimen_digitization.application").joinpath("_build.json"); assert json.loads(p.read_text())["source_sha"] == sys.argv[1]' "$source_sha"
else
  docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges "$image" --version | \
    python3 -c 'import json,sys; assert json.load(sys.stdin)["source_sha"] == sys.argv[1]' "$source_sha"
fi
if [[ "$target" != "api" ]]; then
  # The preparation process writes only synthetic fixtures as root. Verification
  # uses the image's configured UID with the volume read-only and no network.
  smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/specimen-runtime-smoke.XXXXXX")"
  smoke_volume="specimen-runtime-smoke-$target-$(basename "$smoke_dir" | tr '[:upper:]' '[:lower:]')"
  cleanup_runtime_smoke() {
    docker volume rm "$smoke_volume" >/dev/null 2>&1 || true
    rm -rf "$smoke_dir"
  }
  trap cleanup_runtime_smoke EXIT HUP INT TERM
  git show "$source_sha:scripts/ci/smoke_runtime_inputs.py" > "$smoke_dir/verify.py"
  chmod 0444 "$smoke_dir/verify.py"
  docker volume create "$smoke_volume" >/dev/null
  docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user 0 \
    --mount "type=bind,src=$smoke_dir/verify.py,dst=/verify.py,readonly" \
    --mount "type=volume,src=$smoke_volume,dst=/inputs" \
    --entrypoint python "$image" /verify.py --prepare
  docker run --rm --platform linux/amd64 --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --env PYTHONPATH=/app --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --mount "type=bind,src=$smoke_dir/verify.py,dst=/verify.py,readonly" \
    --mount "type=volume,src=$smoke_volume,dst=/inputs,readonly" \
    --entrypoint python "$image" /verify.py --target "$target"
fi
printf 'Built and CLI-smoked %s at %s; no cloud release or inference.\n' "$target" "$source_sha"
