#!/usr/bin/env bash
#
# Device captures for the composition checkpoint (13 section 6, slot A4).
#
# Drives the booted Android emulator and the booted iPad simulator through
# every route the client has, at a phone and a tablet window, in both modes,
# and writes one PNG per cell into design/screenshots/refactor/composition/.
#
# What it captures is the shipped client. The target is
# test/verification/capture_app.dart, which composes the real
# SpecimenDigitizationApp with the size class goldens' own fixture: the
# application's own main() needs Firebase and a reachable API, and a capture of
# the setup screen says nothing about the queue or the record. Every pixel a
# capture shows is still the product's.
#
# Captures are evidence, not artefacts. Nothing here is committed; the
# integrator runs this at the checkpoint and reads the PNGs.
#
# Usage:
#   scripts/ci/capture_devices.sh                      every cell
#   scripts/ci/capture_devices.sh --device android     one device
#   scripts/ci/capture_devices.sh --routes queue,record
#   scripts/ci/capture_devices.sh --modes dark --sizes phone
#   scripts/ci/capture_devices.sh --dry-run            print the plan
#   scripts/ci/capture_devices.sh --force              retake what exists
#
# Run from apps/specimen_digitization. Needs a booted emulator-5554 and a
# booted iOS simulator; check with `flutter devices` first.

set -euo pipefail

# ---------------------------------------------------------------------------
# What the matrix is.
# ---------------------------------------------------------------------------

# The collection the fixture publishes, encoded the way AppRoutes encodes it.
readonly COLLECTION='org%2Finsects'

# The record the fixture answers for.
readonly SPECIMEN='fixture-001'

# name:location:signed_out, in the order a reviewer meets them.
readonly ROUTES=(
  "signin:/sign-in:yes"
  "setup:/setup:no"
  "queue:/c/${COLLECTION}/queue:no"
  "record:/c/${COLLECTION}/queue/${SPECIMEN}:no"
  "intake:/c/${COLLECTION}/intake:no"
  "sources:/c/${COLLECTION}/intake/sources:no"
  "source:/c/${COLLECTION}/intake/sources/src-1:no"
  "help:/help:no"
)

# The Android emulator is resized per window class, because the client lays
# out by window size and one emulator therefore yields both. The densities are
# chosen so the logical size is exactly the size class golden's window: 390 by
# 844 and 768 by 1024 at two device pixels to the point.
readonly ANDROID_PHONE_SIZE='780x1688'
readonly ANDROID_TABLET_SIZE='1536x2048'
readonly ANDROID_DENSITY='320'

readonly ANDROID_SERIAL='emulator-5554'
readonly ANDROID_PACKAGE='org.fieldmuseum.specimen_digitization'
readonly IOS_BUNDLE='org.fieldmuseum.specimenDigitization'

# Where `adb` is. It is not on the PATH of a plain login shell on this
# machine, and the Android SDK does not put it there; Flutter finds it through
# the SDK root instead. Resolved once so a missing emulator reads as a missing
# emulator rather than as a missing tool.
ADB="$(command -v adb 2>/dev/null || true)"
for candidate in \
  "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
  "${ANDROID_HOME:-}/platform-tools/adb" \
  "${HOME}/Library/Android/sdk/platform-tools/adb" \
  "${HOME}/Android/Sdk/platform-tools/adb"; do
  [ -n "${ADB}" ] && break
  [ -x "${candidate}" ] && ADB="${candidate}"
done
readonly ADB

readonly TARGET='test/verification/capture_app.dart'
readonly OUT_DEFAULT='design/screenshots/refactor/composition'

# How long to wait for a build to reach the device, the least time to let the
# first frame arrive after it does, and the most time to wait for the screen to
# stop changing. The Android emulator on this machine skips about three hundred
# frames getting to the first one, so a cell is a minute or so and a whole
# sweep is the better part of an hour. It is resumable: a capture that exists
# is skipped unless --force says otherwise.
readonly RUN_TIMEOUT_SECONDS=600
readonly SETTLE_SECONDS=12
readonly STILL_TIMEOUT_SECONDS=90
readonly CHANGED_GRACE_SECONDS=8

# ---------------------------------------------------------------------------
# Arguments.
# ---------------------------------------------------------------------------

devices='all'
routes='all'
modes='light,dark'
sizes='phone,tablet'
out="${OUT_DEFAULT}"
dry_run='no'
force='no'

usage() {
  sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --device|--devices) devices="$2"; shift 2 ;;
    --routes) routes="$2"; shift 2 ;;
    --modes) modes="$2"; shift 2 ;;
    --sizes) sizes="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --dry-run) dry_run='yes'; shift ;;
    --force) force='yes'; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "capture_devices.sh: unknown argument $1" >&2; usage >&2; exit 2 ;;
  esac
done

# True when $2 is in the comma separated list $1, or the list is "all".
in_list() {
  case "$1" in all) return 0 ;; esac
  case ",$1," in *",$2,"*) return 0 ;; esac
  return 1
}

log() { printf '%s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Where we are, and what the platforms need.
# ---------------------------------------------------------------------------

if [ ! -f 'pubspec.yaml' ] || [ ! -f "${TARGET}" ]; then
  log "capture_devices.sh: run this from apps/specimen_digitization"
  exit 2
fi

# The three gitignored placeholders a debug build needs on a device. None is
# in the repository and none is written by the build, so a device build fails
# without them. They are written here rather than left to the reader because
# the iOS one has to be well formed: the Firebase iOS SDK calls
# [FIRApp configure] at plugin registration and throws on a malformed
# GOOGLE_APP_ID before any Dart runs, so "1:000000000000:ios:ci-placeholder"
# crashes the app on launch and a well shaped identifier does not. Slot H3
# spent twenty minutes finding that; this is the twenty minutes, written down.
ensure_placeholders() {
  if [ ! -f 'lib/firebase_options.dart' ]; then
    cp 'lib/firebase_options.ci.dart' 'lib/firebase_options.dart'
    log 'wrote the gitignored lib/firebase_options.dart placeholder'
  fi
  if [ ! -f 'android/app/google-services.json' ]; then
    cat > 'android/app/google-services.json' <<'JSON'
{
  "project_info": {
    "project_number": "123456789012",
    "project_id": "specimen-digitization",
    "storage_bucket": "specimen-digitization.firebasestorage.app"
  },
  "client": [
    {
      "client_info": {
        "mobilesdk_app_id": "1:123456789012:android:abcdef0123456789abcdef",
        "android_client_info": {
          "package_name": "org.fieldmuseum.specimen_digitization"
        }
      },
      "oauth_client": [],
      "api_key": [{ "current_key": "capture-placeholder" }],
      "services": { "appinvite_service": { "other_platform_oauth_client": [] } }
    }
  ],
  "configuration_version": "1"
}
JSON
    log 'wrote the gitignored android/app/google-services.json placeholder'
  fi
  if [ ! -f 'ios/Runner/GoogleService-Info.plist' ]; then
    cat > 'ios/Runner/GoogleService-Info.plist' <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>API_KEY</key>
  <string>capture-placeholder</string>
  <key>GCM_SENDER_ID</key>
  <string>123456789012</string>
  <key>PLIST_VERSION</key>
  <string>1</string>
  <key>BUNDLE_ID</key>
  <string>org.fieldmuseum.specimenDigitization</string>
  <key>PROJECT_ID</key>
  <string>specimen-digitization</string>
  <key>STORAGE_BUCKET</key>
  <string>specimen-digitization.firebasestorage.app</string>
  <key>IS_ADS_ENABLED</key><false/>
  <key>IS_ANALYTICS_ENABLED</key><false/>
  <key>IS_APPINVITE_ENABLED</key><false/>
  <key>IS_GCM_ENABLED</key><false/>
  <key>IS_SIGNIN_ENABLED</key><false/>
  <key>GOOGLE_APP_ID</key>
  <string>1:123456789012:ios:abcdef0123456789abcdef</string>
</dict>
</plist>
PLIST
    log 'wrote the gitignored ios/Runner/GoogleService-Info.plist placeholder'
  fi
}

# ---------------------------------------------------------------------------
# The devices.
# ---------------------------------------------------------------------------

android_ready() {
  [ -n "${ADB}" ] &&
    "${ADB}" -s "${ANDROID_SERIAL}" get-state 2>/dev/null | grep -q '^device$'
}

# The booted simulator's identifier.
#
# `xcrun simctl` takes the word "booted" and `flutter run -d` does not: it
# matches a device id or a name, so the first version of this script asked
# flutter for a device called "booted" and was told there is no such thing.
# One identifier is resolved here and both tools are given it.
ios_udid() {
  xcrun simctl list devices booted 2>/dev/null |
    grep '(Booted)' |
    head -n 1 |
    sed -E 's/.*\(([0-9A-Fa-f-]{36})\).*/\1/'
}

IOS_UDID=''

ios_ready() {
  command -v xcrun >/dev/null 2>&1 || return 1
  [ -n "${IOS_UDID}" ] || IOS_UDID="$(ios_udid)"
  [ -n "${IOS_UDID}" ]
}

# The emulator's own window size and density, restored at the end whatever
# happens: an emulator left at 1536 by 2048 is the next person's puzzle.
android_restore() {
  if android_ready; then
    "${ADB}" -s "${ANDROID_SERIAL}" shell wm size reset >/dev/null 2>&1 || true
    "${ADB}" -s "${ANDROID_SERIAL}" shell wm density reset >/dev/null 2>&1 || true
    "${ADB}" -s "${ANDROID_SERIAL}" shell cmd uimode night no >/dev/null 2>&1 || true
    "${ADB}" -s "${ANDROID_SERIAL}" shell am force-stop "${ANDROID_PACKAGE}" \
      >/dev/null 2>&1 || true
  fi
}

ios_restore() {
  if [ -n "${IOS_UDID}" ]; then
    xcrun simctl ui "${IOS_UDID}" appearance light >/dev/null 2>&1 || true
    xcrun simctl terminate "${IOS_UDID}" "${IOS_BUNDLE}" >/dev/null 2>&1 || true
  fi
}

running_pid=''

stop_run() {
  if [ -n "${running_pid}" ] && kill -0 "${running_pid}" 2>/dev/null; then
    kill "${running_pid}" 2>/dev/null || true
    wait "${running_pid}" 2>/dev/null || true
  fi
  running_pid=''
}

# Leaves nothing running on either device.
stop_app() {
  case "$1" in
    android)
      "${ADB}" -s "${ANDROID_SERIAL}" shell am force-stop "${ANDROID_PACKAGE}" \
        >/dev/null 2>&1 || true
      ;;
    ipad)
      xcrun simctl terminate "${IOS_UDID}" "${IOS_BUNDLE}" >/dev/null 2>&1 ||
        true
      ;;
  esac
}

cleanup() {
  stop_run
  android_restore
  ios_restore
}
trap cleanup EXIT INT TERM

android_window() {
  case "$1" in
    phone) "${ADB}" -s "${ANDROID_SERIAL}" shell wm size "${ANDROID_PHONE_SIZE}" ;;
    tablet) "${ADB}" -s "${ANDROID_SERIAL}" shell wm size "${ANDROID_TABLET_SIZE}" ;;
  esac >/dev/null
  "${ADB}" -s "${ANDROID_SERIAL}" shell wm density "${ANDROID_DENSITY}" >/dev/null
}

android_mode() {
  case "$1" in
    dark) "${ADB}" -s "${ANDROID_SERIAL}" shell cmd uimode night yes ;;
    *) "${ADB}" -s "${ANDROID_SERIAL}" shell cmd uimode night no ;;
  esac >/dev/null
}

ios_mode() {
  xcrun simctl ui "${IOS_UDID}" appearance "$1" >/dev/null
}

# ---------------------------------------------------------------------------
# One capture.
# ---------------------------------------------------------------------------

# start_app <flutter device id> <location> <signed out> <log file>
#
# `flutter run` rather than an install: CAPTURE_LOCATION is a compile time
# define, so each route is its own build. There is no deep link into this
# client to open a route on an installed build with, and adding one would be a
# change to the shipped application rather than to a capture script.
start_app() {
  local device="$1" location="$2" signed_out="$3" logfile="$4"
  local defines=(--dart-define="CAPTURE_LOCATION=${location}")
  if [ "${signed_out}" = 'yes' ]; then
    defines+=(--dart-define=CAPTURE_SIGNED_OUT=true)
  fi
  : > "${logfile}"
  flutter run -d "${device}" -t "${TARGET}" "${defines[@]}" \
    >"${logfile}" 2>&1 &
  running_pid=$!

  local waited=0
  while [ "${waited}" -lt "${RUN_TIMEOUT_SECONDS}" ]; do
    if grep -q 'Flutter run key commands' "${logfile}" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "${running_pid}" 2>/dev/null; then
      log "the run exited before it launched. Tail of ${logfile}:"
      tail -n 25 "${logfile}" >&2
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  log "the run did not launch within ${RUN_TIMEOUT_SECONDS} seconds"
  tail -n 25 "${logfile}" >&2
  return 1
}

# The digest of what is on the device's screen right now.
frame_digest() {
  local kind="$1" shot
  shot="$(mktemp -t capture_frame)"
  grab "${kind}" "${shot}" || true
  shasum -a 256 "${shot}" 2>/dev/null | cut -d' ' -f1
  rm -f "${shot}"
}

# wait_for_app <device kind>
#
# A launch is not a frame. The native splash is on screen from the moment the
# activity starts until Flutter draws, and "Flutter run key commands" is
# printed well before that: the first version of this script captured the
# splash every time. So the screen is watched rather than timed. The frame at
# launch is the splash by definition, and the app is ready once the screen has
# both changed from it and stopped changing, which also covers the photograph
# decoding a second after the layout lands.
wait_for_app() {
  local kind="$1"
  local baseline previous current waited=0 changed_at=-1
  baseline="$(frame_digest "${kind}")"
  previous=''
  while [ "${waited}" -lt "${STILL_TIMEOUT_SECONDS}" ]; do
    sleep 2
    waited=$((waited + 2))
    current="$(frame_digest "${kind}")"
    if [ -n "${current}" ] && [ "${current}" != "${baseline}" ] &&
      [ "${changed_at}" -lt 0 ]; then
      changed_at="${waited}"
    fi
    if [ "${waited}" -ge "${SETTLE_SECONDS}" ] && [ "${changed_at}" -ge 0 ]; then
      # Two frames the same means the screen has settled. Some screens never
      # produce two the same: the queue draws "Updated 3 s ago", so every
      # frame differs from the last and the first version of this waited out
      # its whole timeout on every queue cell. A grace period after the splash
      # clears is the answer for those, and it is the same answer for a screen
      # whose photograph is still decoding.
      if [ "${current}" = "${previous}" ] ||
        [ $((waited - changed_at)) -ge "${CHANGED_GRACE_SECONDS}" ]; then
        return 0
      fi
    fi
    previous="${current}"
  done
  log "the screen never left the splash within ${STILL_TIMEOUT_SECONDS} seconds; capturing it anyway"
  return 0
}

# grab <device kind> <output file>
grab() {
  case "$1" in
    android) "${ADB}" -s "${ANDROID_SERIAL}" exec-out screencap -p > "$2" ;;
    ipad) xcrun simctl io "${IOS_UDID}" screenshot "$2" >/dev/null 2>&1 ;;
  esac
}

taken=0
skipped=0
failed=0

capture_cell() {
  local kind="$1" device="$2" route="$3" location="$4" signed_out="$5"
  local size="$6" mode="$7"
  local file="${out}/${kind}__${route}__${size}__${mode}.png"

  if [ -f "${file}" ] && [ "${force}" = 'no' ]; then
    skipped=$((skipped + 1))
    return 0
  fi
  if [ "${dry_run}" = 'yes' ]; then
    printf '%s\n' "${file}"
    taken=$((taken + 1))
    return 0
  fi

  case "${kind}" in
    android) android_window "${size}"; android_mode "${mode}" ;;
    ipad) ios_mode "${mode}" ;;
  esac

  local logfile
  logfile="$(mktemp -t capture_devices)"
  if start_app "${device}" "${location}" "${signed_out}" "${logfile}"; then
    wait_for_app "${kind}"
    grab "${kind}" "${file}"
    log "captured ${file}"
    taken=$((taken + 1))
  else
    log "failed ${file}"
    failed=$((failed + 1))
  fi
  stop_run
  stop_app "${kind}"
  rm -f "${logfile}"
}

# ---------------------------------------------------------------------------
# The sweep.
# ---------------------------------------------------------------------------

mkdir -p "${out}"
if [ "${dry_run}" = 'no' ]; then
  ensure_placeholders
fi

want_android='no'
want_ipad='no'
in_list "${devices}" 'android' && want_android='yes'
in_list "${devices}" 'ipad' && want_ipad='yes'

if [ "${want_android}" = 'yes' ] && [ "${dry_run}" = 'no' ]; then
  if ! android_ready; then
    if [ -z "${ADB}" ]; then
      log 'adb was not found. Set ANDROID_SDK_ROOT, or pass --device ipad.'
    else
      log "no ${ANDROID_SERIAL}. Boot the emulator, or pass --device ipad."
    fi
    want_android='no'
    failed=$((failed + 1))
  fi
fi
if [ "${want_ipad}" = 'yes' ] && [ "${dry_run}" = 'no' ]; then
  if ! ios_ready; then
    log 'no booted iOS simulator. Boot one, or pass --device android.'
    want_ipad='no'
    failed=$((failed + 1))
  fi
fi

for entry in "${ROUTES[@]}"; do
  route="${entry%%:*}"
  rest="${entry#*:}"
  location="${rest%%:*}"
  signed_out="${rest##*:}"
  in_list "${routes}" "${route}" || continue

  for mode in light dark; do
    in_list "${modes}" "${mode}" || continue

    if [ "${want_android}" = 'yes' ]; then
      for size in phone tablet; do
        in_list "${sizes}" "${size}" || continue
        capture_cell android "${ANDROID_SERIAL}" "${route}" "${location}" \
          "${signed_out}" "${size}" "${mode}"
      done
    fi

    # The iPad is the tablet window and has no other. `xcrun simctl` has no
    # rotate verb and driving the Simulator's own Device menu through
    # AppleScript needs an accessibility grant, so there is no landscape
    # capture and the large window class has no device capture at all. Slot H3
    # recorded the same gap; it is a gap rather than something worked around.
    if [ "${want_ipad}" = 'yes' ] && in_list "${sizes}" 'tablet'; then
      capture_cell ipad "${IOS_UDID}" "${route}" "${location}" \
        "${signed_out}" tablet "${mode}"
    fi
  done
done

log ""
log "captured ${taken}, skipped ${skipped} that already existed, failed ${failed}"
log "in ${out}"
log "Captures are evidence for the checkpoint. Do not commit them."

[ "${failed}" -eq 0 ]
