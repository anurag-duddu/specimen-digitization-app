#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
target="${1:-}"
case "$target" in
  api|worker) ;;
  *) printf 'Expected api or worker image target.\n' >&2; exit 1 ;;
esac
source_sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { printf 'Invalid source SHA.\n' >&2; exit 1; }
dockerfile="containers/$target/Dockerfile"
[[ -f "$dockerfile" ]] || { printf 'Not run: %s is absent.\n' "$dockerfile" >&2; exit 1; }
# Build without credentials, publishing, mounting private data or host networking.
image="specimen-ci-$target:$source_sha"
# Archive only the reviewed committed build inputs. Ignored credentials and local
# specimen files never enter the Docker daemon build context.
git archive --format=tar "$source_sha" pyproject.toml uv.lock README.md src "$dockerfile" | \
  docker build --build-arg "SOURCE_SHA=$source_sha" --file "$dockerfile" \
    --label "org.opencontainers.image.revision=$source_sha" --tag "$image" -
revision="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
[[ "$revision" == "$source_sha" ]] || { printf 'Image source label mismatch.\n' >&2; exit 1; }
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges "$image" --help
if [[ "$target" == "api" ]]; then
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint python "$image" -c \
    'import importlib.resources,json,sys; p=importlib.resources.files("specimen_digitization.application").joinpath("_build.json"); assert json.loads(p.read_text())["source_sha"] == sys.argv[1]' "$source_sha"
fi
printf 'Built and CLI-smoked %s at %s; no cloud release or inference.\n' "$target" "$source_sha"
