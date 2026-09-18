#!/usr/bin/env bash
set -euo pipefail

# Called from the Flutter application directory. Public settings only; no OIDC.
args=(--release)
# The build stamp the help sheet shows (APP_BUILD, help_screen.dart): the exact
# commit in CI, the same value the deployment marker carries, so a reviewer
# can quote the build they are on. A local build stays unstamped and says so.
if [[ -n "${GITHUB_SHA:-}" ]]; then
  args+=("--dart-define=APP_BUILD=${GITHUB_SHA}")
fi
if [[ "${GITHUB_ACTIONS:-}" == "true" && "${GITHUB_EVENT_NAME:-}" == "push" && "${GITHUB_REF:-}" == "refs/heads/main" ]]; then
  python3 ../../scripts/ci/validate_public_settings.py
  if [[ -n "${SPECIMEN_API_BASE_URL:-}" ]]; then
    args+=("--dart-define=SPECIMEN_API_BASE_URL=$SPECIMEN_API_BASE_URL")
    args+=("--dart-define=SPECIMEN_RECAPTCHA_SITE_KEY=$SPECIMEN_RECAPTCHA_SITE_KEY")
  fi
  if [[ -n "${SPECIMEN_ADMIN_CONTACT:-}" ]]; then
    args+=("--dart-define=SPECIMEN_ADMIN_CONTACT=$SPECIMEN_ADMIN_CONTACT")
  fi
  # A bounded pilot names its scope in the reviewer's words (environment
  # band, 07 section 1.3); production is the empty default and shows no band.
  if [[ -n "${SPECIMEN_PILOT_SCOPE:-}" ]]; then
    args+=("--dart-define=SPECIMEN_PILOT_SCOPE=$SPECIMEN_PILOT_SCOPE")
  fi
fi
flutter build web "${args[@]}"
