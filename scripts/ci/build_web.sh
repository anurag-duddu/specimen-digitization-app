#!/usr/bin/env bash
set -euo pipefail

# Called from the Flutter application directory. Public settings only; no OIDC.
args=(--release)
if [[ "${GITHUB_ACTIONS:-}" == "true" && "${GITHUB_EVENT_NAME:-}" == "push" && "${GITHUB_REF:-}" == "refs/heads/main" ]]; then
  python3 ../../scripts/ci/validate_public_settings.py
  if [[ -n "${SPECIMEN_API_BASE_URL:-}" ]]; then
    args+=("--dart-define=SPECIMEN_API_BASE_URL=$SPECIMEN_API_BASE_URL")
    args+=("--dart-define=SPECIMEN_RECAPTCHA_SITE_KEY=$SPECIMEN_RECAPTCHA_SITE_KEY")
  fi
fi
flutter build web "${args[@]}"
