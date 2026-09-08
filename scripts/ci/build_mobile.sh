#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
app_root="$repo_root/apps/specimen_digitization"
target="${1:-}"
case "$target" in
  android|ios) ;;
  *) printf 'Usage: %s android|ios\n' "$0" >&2; exit 2 ;;
esac

# Never replace a developer's ignored configuration, even temporarily.
config_paths=(
  "$app_root/lib/firebase_options.dart"
  "$app_root/android/app/google-services.json"
  "$app_root/ios/Runner/GoogleService-Info.plist"
)
for config in "${config_paths[@]}"; do
  if [[ -e "$config" || -L "$config" ]]; then
    printf 'Refusing to overwrite existing Firebase configuration: %s\nUse a clean worktree for credential-free mobile verification.\n' "$config" >&2
    exit 1
  fi
done
created_paths=()
cleanup() {
  for config in "${created_paths[@]}"; do rm -f "$config"; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

# Noclobber also prevents replacing a file created after the preflight check.
set -o noclobber
cat "$app_root/lib/firebase_options.ci.dart" > "${config_paths[0]}"
created_paths+=("${config_paths[0]}")
cat > "${config_paths[1]}" <<'JSON'
{
  "project_info": {
    "project_number": "000000000000",
    "project_id": "demo-specimen-mobile-ci",
    "storage_bucket": "demo-specimen-mobile-ci.invalid"
  },
  "client": [{
    "client_info": {
      "mobilesdk_app_id": "1:000000000000:android:0000000000000000",
      "android_client_info": {"package_name": "org.fieldmuseum.specimen_digitization"}
    },
    "oauth_client": [],
    "api_key": [{"current_key": "ci-placeholder"}],
    "services": {"appinvite_service": {"other_platform_oauth_client": []}}
  }],
  "configuration_version": "1"
}
JSON
created_paths+=("${config_paths[1]}")
cat > "${config_paths[2]}" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>API_KEY</key><string>ci-placeholder</string>
<key>GCM_SENDER_ID</key><string>000000000000</string>
<key>PLIST_VERSION</key><string>1</string>
<key>BUNDLE_ID</key><string>org.fieldmuseum.specimenDigitization</string>
<key>PROJECT_ID</key><string>demo-specimen-mobile-ci</string>
<key>STORAGE_BUCKET</key><string>demo-specimen-mobile-ci.invalid</string>
<key>GOOGLE_APP_ID</key><string>1:000000000000:ios:0000000000000000</string>
<key>IS_ADS_ENABLED</key><false/>
<key>IS_ANALYTICS_ENABLED</key><false/>
</dict></plist>
PLIST
created_paths+=("${config_paths[2]}")

cd "$app_root"
flutter pub get --enforce-lockfile
if [[ "$target" == "android" ]]; then
  flutter build apk --debug
else
  flutter build ios --release --no-codesign
fi
printf 'Credential-free %s build passed. No signing/distribution/device validation is implied.\n' "$target"
