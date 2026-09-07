#!/usr/bin/env bash
set -euo pipefail

failed=0

for path in "$@"; do
  case "$path" in
    .env.example|*.env.example|*.example|*.template|*.sample)
      continue
      ;;
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|*.jks|*.keystore|*.mobileprovision|*.provisionprofile|terraform.tfstate|terraform.tfstate.*)
      ;;
    */google-services.json|google-services.json|*/GoogleService-Info.plist|GoogleService-Info.plist)
      ;;
    *service-account*.json|*service_account*.json|*serviceAccount*.json|*/client_secret*.json|client_secret*.json|*/credentials.json|credentials.json)
      ;;
    secrets/*|*/secrets/*|private/*|*/private/*|credentials/*|*/credentials/*)
      ;;
    data/*|datasets/*|uploads/*|specimens/*|exports/*)
      ;;
    *)
      continue
      ;;
  esac

  printf 'Blocked sensitive or private path: %s\n' "$path" >&2
  failed=1
done

if [[ "$failed" -ne 0 ]]; then
  printf 'Move private data out of the repository or add only a sanitized *.example file.\n' >&2
  exit 1
fi
