#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
flutter_root="$repo_root/apps/specimen_digitization"
firebase_options="$flutter_root/lib/firebase_options.dart"
ci_firebase_options="$flutter_root/lib/firebase_options.ci.dart"
created_ci_options=0

require_version() {
  local tool="$1"
  local actual="$2"
  local expected="$3"

  if [[ "$actual" != "$expected" ]]; then
    printf '%s %s is required; found %s.\n' "$tool" "$expected" "$actual" >&2
    exit 1
  fi
}

restore_local_state() {
  if [[ "$created_ci_options" -eq 1 && -f "$firebase_options" ]]; then
    rm -f "$firebase_options"
  fi
}
trap restore_local_state EXIT HUP INT TERM

cd "$repo_root"

command -v uv >/dev/null 2>&1 || {
  printf 'uv is required. Install the pinned project version documented in docs/DEPLOYMENT.md.\n' >&2
  exit 1
}
command -v flutter >/dev/null 2>&1 || {
  printf 'Flutter is required. Install the pinned project version documented in docs/DEPLOYMENT.md.\n' >&2
  exit 1
}
command -v firebase >/dev/null 2>&1 || {
  printf 'Firebase CLI is required. Install version 15.8.0.\n' >&2
  exit 1
}

require_version "uv" "$(uv --version | awk '{print $2}')" "0.12.5"
require_version "Flutter" "$(flutter --version | awk 'NR == 1 {print $2}')" "3.38.5"
require_version "Firebase CLI" "$(firebase --version)" "15.8.0"

if [[ ! -f "$firebase_options" ]]; then
  cp "$ci_firebase_options" "$firebase_options"
  created_ci_options=1
  printf 'Using the credential-free FlutterFire placeholder for local verification.\n'
fi

uvx --from pre-commit==4.5.1 pre-commit run --all-files
uv sync --frozen
uv run pytest -q

cd "$flutter_root"
flutter pub get --enforce-lockfile
flutter analyze --fatal-infos
flutter test
flutter build web --release

printf 'All local CI gates passed. This script does not deploy.\n'
