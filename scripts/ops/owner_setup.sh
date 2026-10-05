#!/usr/bin/env bash
# The owner's one step for the simple release model: the setup (standing permissions, the
# Cloud SQL role, manual runs on main, the GitHub variables and secret), then the data release,
# the runtime release and the web app build, each started on main and followed to its end.
# Safe to run again: every step reads the live state first and changes only what is missing.
#
# Usage: owner_setup.sh [--dry-run] [--setup-only | --redeploy-web]
#   --dry-run       read the live state and print every command that would run; change and start nothing.
#   --setup-only    do the setup and stop; start no release.
#   --redeploy-web  build and publish the web app again even when its variables were already set.
#
# Self-contained: it reads no other file of the repository and nothing relative to its own
# location, so a copy fetched from main runs from any directory. It needs no terminal either:
# no question is asked, no pager is used, and every tool it starts reads from /dev/null.
#
# Needs gcloud signed in as a project Owner (or IAM admin plus Cloud SQL admin) and gh signed
# in with admin rights on the repository. Written for the stock macOS bash 3.2: no associative
# arrays, no mapfile, and no pattern substitution with a computed replacement.

# Bash only. Any other shell (zsh, a plain sh, bash started as sh) stops here, at lines every
# shell reads the same way, before it misreads the rest; a shell that sourced the file survives.
case ${BASH_VERSION:-}:${SHELLOPTS:-} in
  :* | *:*posix*)
    echo 'run this script with bash: bash scripts/ops/owner_setup.sh' >&2
    # shellcheck disable=SC2317
    return 2 2> /dev/null || exit 2
    ;;
esac
set -euo pipefail

readonly PROJECT=specimen-digitization
readonly PROJECT_NUMBER=716045864126
readonly REGION=us-east4
readonly REPOSITORY=anurag-duddu/specimen-digitization-app
readonly BUCKET="$PROJECT.firebasestorage.app"
readonly REGISTRY=specimen-runtime
readonly API_SERVICE=specimen-api
readonly INSTANCE=specimen-digitization-instance
readonly SQL_USER="specimen-data-release@$PROJECT.iam"
readonly POOL=github-actions
readonly CUSTOM="projects/$PROJECT/roles"
readonly ACCOUNTS="$PROJECT.iam.gserviceaccount.com"
readonly DATA="serviceAccount:specimen-data-release@$ACCOUNTS"
readonly BUILD="serviceAccount:specimen-runtime-build@$ACCOUNTS"
readonly RELEASE="serviceAccount:specimen-runtime-release@$ACCOUNTS"
readonly API="serviceAccount:specimen-api-runtime@$ACCOUNTS"
readonly WORKER="serviceAccount:specimen-worker-runtime@$ACCOUNTS"
readonly SAM="serviceAccount:specimen-sam-runtime@$ACCOUNTS"
readonly PLANE="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.release_plane"

readonly API_BASE_URL="https://specimen-api-$PROJECT_NUMBER.$REGION.run.app"
readonly RECAPTCHA_SITE_KEY=6LfP0bEtAAAAAGtD_o-SD8EnjvgGGzVugURtWUAw # pragma: allowlist secret (public site key)
readonly DATA_ENVIRONMENT=data-production
readonly ARTIFACT_NAME=DATA_BOOTSTRAP_ARTIFACT_B64
readonly ARTIFACT_FILE="${HOME:?}/specimen-release-private/hierarchy-bootstrap.artifact.json"

readonly APP_URL=https://specimen-digitization.web.app
# The site's compiled program; when the site was built with the API address it names this host.
readonly SITE_PROGRAM="$APP_URL/main.dart.js"
readonly API_HOST="${API_BASE_URL#https://}"
readonly DATA_WORKFLOW=data-release.yml
readonly RUNTIME_WORKFLOW=runtime-release.yml
readonly WEB_WORKFLOW=ci-cd.yml
# One reading of a run for gh's built-in jq: an R line (status, conclusion, address, attempt),
# then an S line for every finished step and a J line for every finished job, tab-separated.
# shellcheck disable=SC2016
readonly RUN_JQ='"R\t\(.status)\t\(.conclusion)\t\(.url)\t\(.attempt)", ((.jobs // [])[] | . as $job | (($job.steps // [])[] | select(.status == "completed") | "S\t\($job.name)\t\(.number)\t\(.name)\t\(.conclusion)"), (select($job.status == "completed") | "J\t\($job.name)\t\($job.conclusion)"))'
readonly NEWEST_JQ='.[0] | select(. != null) | "\(.databaseId)\t\(.attempt)\t\(.status)\t\(.url)"'
# A new run shows up within 18 short waits (90 seconds); a run is followed for 180 polls (45 minutes).
readonly FIND_TRIES=18
readonly WATCH_POLLS=180

# Conditions of the standing grants, exactly as the live bindings carry them.
readonly OBJECTS="projects/_/buckets/$BUCKET/objects/"
readonly APP_TITLE=specimen_application_objects
readonly APP_EXPRESSION="resource.name.startsWith(\"${OBJECTS}application/sha256/\")"
# Exact immutable dataset objects committed in application/georef_datasets.py.
# The data workflow can create missing generations and read them back, never
# list, delete, replace an existing object, or write another application object.
readonly GEO_TITLE=specimen_georeference_datasets
readonly GEO_EXPRESSION="resource.name in [\
\"${OBJECTS}application/sha256/7a9189637a5af9677a92e765b9448bdfe425383fae8e39a6808a96b8fe8f19d0\",\
\"${OBJECTS}application/sha256/155424cb1ede34d2b0e4e92b51b5c359164e3d0834507166d1b28969389e2e5c\",\
\"${OBJECTS}application/sha256/0f6f645d310b4aa02fffc0cba0f3ad130a5fd2303d953e5f8931ba48817b0c6c\",\
\"${OBJECTS}application/sha256/37d8bc68715f937fc2a568d9e88245aa6323a46cc4c2e56a5836fa89febe8536\",\
\"${OBJECTS}application/sha256/7a8dc145e57ea42c26b35393a281f248ff35e70aaf794eed20c989ff2d718759\",\
\"${OBJECTS}application/sha256/24965821b5541833efb63ced996ac9a508feb049ec02442727f28cbdf15dfe96\",\
\"${OBJECTS}application/sha256/8eeef6a9a525a81a647dcaac85e1337b990fc527c4a0e9c70556d5b0905be087\",\
\"${OBJECTS}application/sha256/fa77b9f17db2e419acaae714a935f7812be4409e2983675d34020e8426a3e189\",\
\"${OBJECTS}application/sha256/2ece3d44a5c6a2afb385ffbf3a6b88d83e4d3a3e7eed9a52cb3be1bc59e289fc\",\
\"${OBJECTS}application/sha256/f178eda98c46329380bdbb43f0637b4c43535bc843de6a0b8b960193b8f4363f\"]"
# The research harness's three prefixes (SPECIMEN_RESEARCH_HARNESS=on): the worker alone creates and gets there.
readonly RESEARCH_TITLE=specimen_research_objects
readonly RESEARCH_EXPRESSION="resource.name.startsWith(\"${OBJECTS}research-capture/\") || resource.name.startsWith(\"${OBJECTS}research-journal/\") || resource.name.startsWith(\"${OBJECTS}research-media/\")"
readonly SLIDES_TITLE=specimen_source_slides
readonly SLIDES_EXPRESSION="resource.name.startsWith(\"${OBJECTS}microscopic-slides/\") || api.getAttribute(\"storage.googleapis.com/objectListPrefix\", \"\").startsWith(\"microscopic-slides/\")"
readonly SQL_TITLE=specimen_source_inventory_only
readonly SQL_EXPRESSION="resource.name == 'projects/$PROJECT/instances/$INSTANCE' && resource.service == 'sqladmin.googleapis.com' && resource.type == 'sqladmin.googleapis.com/Instance'"
readonly SQL_DESCRIPTION='Connect, IAM login and metadata only for the existing source instance.'

# The only shape of expired grant this script removes: a plain time window that has ended.
readonly STAMP='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
readonly WINDOW="^request\\.time >= timestamp\\('($STAMP)'\\) && request\\.time < timestamp\\('($STAMP)'\\)\$"

readonly PUSH_ONLY="assertion.event_name == 'push'"
readonly PUSH_OR_MANUAL="(assertion.event_name == 'push' || assertion.event_name == 'workflow_dispatch')"

# One line per member of a policy: member, role, condition title, expression, description.
readonly POLICY_FORMAT='value(bindings.members,bindings.role,bindings.condition.title,bindings.condition.expression,bindings.condition.description)'
readonly ROLE_FORMAT='value[separator="|"](stage,deleted,includedPermissions.list())'
readonly TAB=$'\t'
readonly NL=$'\n'

DRY_RUN=0
SETUP_ONLY=0
REDEPLOY_WEB=0
STARTED=0
COMPLETE=0
CHANGE_WORD=change
PENDING=''
CHANGES=''
CHANGE_COUNT=0
FAILURES=''
FAILURE_COUNT=0
IN_PLACE=0
WARNINGS=''
FILE_COUNT=0
WORK=''
NOW=''
POLICY=''
CONDITION_FILE=''
REPLACED=''
COMMAND=(gcloud)
# Release stages: what the summary says about each, and what the waits are.
LAST_OK=0
HELD=0
LENIENT=0
NARROWED=0
ACCESS_CHANGED=0
VARIABLES_CHANGED=0
NOT_MERGED=0
STOPPED=0
CURRENT=setup
SETUP_STATE=''
DATA_STATE=''
RUNTIME_STATE=''
WEB_STATE=''
STAGE_STATE=''
STAGE_FAILURES=0
LOG_COMMANDS=''
RUN_URL=''
RUN_FAILED_AT=''
SITE_NOTE=''
SETTLE_SECONDS=120
RETRY_SECONDS=180
POLL_SECONDS=15
FIND_SECONDS=5

usage() {
  printf 'Usage: owner_setup.sh [--dry-run] [--setup-only | --redeploy-web]\n'
  printf '  (no flag)       do the setup, then start the data release, the runtime release and, when the\n'
  printf '                  repository variables changed, the web app build; follow each to its end.\n'
  printf '  --dry-run       read the live state and print every command that would run; change and start nothing.\n'
  printf '  --setup-only    do the setup and stop; start no release.\n'
  printf '  --redeploy-web  build and publish the web app again even when its variables were already set.\n'
}

bad_usage() {
  usage >&2
  exit 2
}

die() {
  printf 'owner_setup: %s\n' "$1" >&2
  exit 1
}

finish() {
  local code=$?
  # The summary is printed on every way out once the run has begun.
  if [ "$code" -ne 0 ] && [ "$COMPLETE" -eq 0 ] && [ "$STARTED" -eq 1 ]; then
    stopped_early
    summary
  fi
  if [ -n "$WORK" ]; then rm -rf "$WORK"; fi
  if [ "$code" -ne 0 ] && [ "$COMPLETE" -eq 0 ]; then
    printf '\nStopped before the end (exit %s). Fix the problem above and run this script again: finished steps are skipped.\n' "$code" >&2
  fi
}

heading() { printf '\n== %s ==\n' "$1"; }

note() { printf '  note: %s\n' "$1"; }

in_place() {
  IN_PLACE=$((IN_PLACE + 1))
  printf '  ok: %s\n' "$1"
}

# Announces one change; the one command that makes it follows through run.
change() {
  PENDING=$1
  printf '  %s: %s\n' "$CHANGE_WORD" "$1"
}

succeeded() {
  CHANGE_COUNT=$((CHANGE_COUNT + 1))
  CHANGES="$CHANGES  - $PENDING"$'\n'
}

# A failed change does not stop the steps after it: they do not depend on it for safety, and
# the next run retries exactly what is still missing.
failed() {
  if [ "$LENIENT" -eq 1 ]; then
    warn "$PENDING: this did not go through (the error is above); the next run of this script tries again"
    return 0
  fi
  FAILURE_COUNT=$((FAILURE_COUNT + 1))
  FAILURES="$FAILURES  - $PENDING"$'\n'
  printf '  FAILED: %s (the error is above; the steps after it still run)\n' "$PENDING"
}

warn() {
  WARNINGS="$WARNINGS  - $1"$'\n'
  printf '  WARNING: %s\n' "$1"
}

# Sets REPLACED to $1 with every $2 replaced by $3; a loop, because bash 5.2 gives "&" a
# meaning in a substitution's replacement and bash 3.2 keeps its quotes.
replace_all() {
  local rest=$1 out=''
  while [ "${rest#*"$2"}" != "$rest" ]; do
    out="$out${rest%%"$2"*}$3"
    rest=${rest#*"$2"}
  done
  REPLACED="$out$rest"
}

# Prints a command the way it could be typed: an argument is quoted only when it needs it.
show() {
  local line='+' arg
  for arg in "$@"; do
    case $arg in
      '' | *[!A-Za-z0-9_@%+=:,./-]*)
        case $arg in
          *\'*)
            case $arg in
              *[\"\$\`\\!]*)
                replace_all "$arg" "'" "'\\''"
                arg="'$REPLACED'"
                ;;
              *) arg="\"$arg\"" ;;
            esac
            ;;
          *) arg="'$arg'" ;;
        esac
        ;;
    esac
    line="$line $arg"
  done
  printf '%s\n' "$line"
}

# Every setup change goes through here: printed first, then run unless this is a dry run.
run() {
  show "$@"
  LAST_OK=1
  if [ "$DRY_RUN" -eq 0 ]; then
    if ! "$@" > /dev/null < /dev/null; then
      LAST_OK=0
      failed
      return 0
    fi
  fi
  succeeded
  # New Google access takes a moment to reach every server; a removal needs no wait.
  if [ "$1" = gcloud ]; then
    case " $* " in
      *' remove-iam-policy-binding '*) ;;
      *) ACCESS_CHANGED=1 ;;
    esac
  fi
}

yaml_field() {
  replace_all "$2" "'" "''"
  printf "%s: '%s'\\n" "$1" "$REPLACED"
}

# Writes a condition file for --condition-from-file and sets CONDITION_FILE; a file, because
# an expression may hold commas and quotes that the inline flag would split.
condition_file() { # condition_file TITLE EXPRESSION [DESCRIPTION]
  FILE_COUNT=$((FILE_COUNT + 1))
  CONDITION_FILE="$WORK/condition-$FILE_COUNT-$1.yaml"
  {
    yaml_field expression "$2"
    yaml_field title "$1"
    if [ -n "${3:-}" ]; then yaml_field description "$3"; fi
  } > "$CONDITION_FILE"
  printf '    condition %s: %s\n' "$1" "$2"
}

# Sets COMMAND to gcloud's command for one verb on one resource.
resource_command() { # resource_command VERB KIND NAME
  case $2 in
    project) COMMAND=(gcloud projects "$1" "$3") ;;
    bucket) COMMAND=(gcloud storage buckets "$1" "gs://$3") ;;
    repository) COMMAND=(gcloud artifacts repositories "$1" "$3" "--location=$REGION" "--project=$PROJECT") ;;
    service-account) COMMAND=(gcloud iam service-accounts "$1" "$3" "--project=$PROJECT") ;;
    secret) COMMAND=(gcloud secrets "$1" "$3" "--project=$PROJECT") ;;
    service) COMMAND=(gcloud run services "$1" "$3" "--region=$REGION" "--project=$PROJECT") ;;
    job) COMMAND=(gcloud run jobs "$1" "$3" "--region=$REGION" "--project=$PROJECT") ;;
    *) die "unknown kind of resource: $2" ;;
  esac
}

# Reads a resource's live policy once per run and sets POLICY to the file that holds it.
load_policy() { # load_policy KIND NAME
  local key
  key=$(printf '%s' "$1.$2" | tr -c 'A-Za-z0-9._-' '_')
  POLICY="$WORK/policy.$key"
  if [ -f "$POLICY" ]; then return 0; fi
  resource_command get-iam-policy "$1" "$2"
  if ! "${COMMAND[@]}" '--flatten=bindings[].members' "--format=$POLICY_FORMAT" > "$POLICY.new" < /dev/null; then
    if [ "$LENIENT" -eq 0 ]; then die "could not read the access policy of $1 $2 (see the error above)"; fi
    warn "could not read the access policy of $1 $2 (the error is above)"
    return 1
  fi
  mv "$POLICY.new" "$POLICY"
}

# Drops what was read of a resource's policy, so that the next look reads it again.
forget_policy() { # forget_policy KIND NAME
  rm -f "$WORK/policy.$(printf '%s' "$1.$2" | tr -c 'A-Za-z0-9._-' '_')"
}

# True when the policy file holds exactly this binding: no condition at all when TITLE is
# empty, otherwise the same title and expression.
has_binding() { # has_binding FILE MEMBER ROLE TITLE EXPRESSION
  local head="$2$TAB$3" line rest
  while IFS= read -r line; do
    case $line in
      "$head"*) rest=${line#"$head"} ;;
      *) continue ;;
    esac
    if [ -z "$4" ]; then
      if [ -z "${rest//$TAB/}" ]; then return 0; fi
    else
      case $rest in
        "$TAB$4$TAB$5" | "$TAB$4$TAB$5$TAB"*) return 0 ;;
      esac
    fi
  done < "$1"
  return 1
}

member_name() {
  case $1 in
    serviceAccount:*)
      REPLACED=${1#serviceAccount:}
      REPLACED=${REPLACED%%@*}
      ;;
    principalSet:*) REPLACED="GitHub workflow identity ${1##*/}" ;;
    *) REPLACED=$1 ;;
  esac
}

# Adds one binding unless the exact binding is already live. Sets HELD: 1 when the binding
# is in place afterwards (in a dry run: would be), 0 when it could not be read or added.
grant() { # grant KIND NAME MEMBER ROLE [TITLE EXPRESSION [DESCRIPTION]]
  local kind=$1 name=$2 member=$3 role=$4 title=${5:-} expression=${6:-} description=${7:-} what
  HELD=0
  member_name "$member"
  what="$REPLACED: ${role##*/} on $kind $name"
  if [ -n "$title" ]; then what="$what, condition $title"; fi
  if ! load_policy "$kind" "$name"; then return 0; fi
  if has_binding "$POLICY" "$member" "$role" "$title" "$expression"; then
    in_place "$what"
    HELD=1
    return 0
  fi
  change "grant $what"
  resource_command add-iam-policy-binding "$kind" "$name"
  if [ "$kind" = job ] && [ -z "$title" ]; then
    run "${COMMAND[@]}" "--member=$member" "--role=$role" --quiet
  elif [ -z "$title" ]; then
    run "${COMMAND[@]}" "--member=$member" "--role=$role" --condition=None
  else
    condition_file "$title" "$expression" "$description"
    run "${COMMAND[@]}" "--member=$member" "--role=$role" "--condition-from-file=$CONDITION_FILE"
  fi
  HELD=$LAST_OK
}

# Removes one binding that has no condition, when it is live: never another binding of that
# role or member, and never --all.
revoke() { # revoke KIND NAME MEMBER ROLE
  local kind=$1 name=$2 member=$3 role=$4 what
  member_name "$member"
  what="$REPLACED: ${role##*/} on $kind $name"
  if ! load_policy "$kind" "$name"; then return 0; fi
  if ! has_binding "$POLICY" "$member" "$role" '' ''; then
    in_place "not granted (nothing to remove): $what"
    return 0
  fi
  change "remove the wider grant $what"
  resource_command remove-iam-policy-binding "$kind" "$name"
  run "${COMMAND[@]}" "--member=$member" "--role=$role" --condition=None
}

# Whether the API's Cloud Run service exists: 0 it does, 1 not yet, 2 that could not be read.
api_service_exists() {
  if gcloud run services describe "$API_SERVICE" "--region=$REGION" "--project=$PROJECT" \
    '--format=value(metadata.name)' > /dev/null 2> "$WORK/stderr" < /dev/null; then
    return 0
  fi
  if grep -q 'Cannot find service' "$WORK/stderr"; then return 1; fi
  cat "$WORK/stderr" >&2
  return 2
}

# The right to say who may call the API (specimenRuntimeInvokerPolicy) belongs on that one
# service. Cloud Run takes no condition on a resource name, and a grant on a service needs
# the service, which the first release creates. So: while the service does not exist the
# grant sits on the project; once it exists the grant moves to the service, and the wider
# one goes only after the narrow one holds.
scope_invoker_policy() {
  local role="$CUSTOM/specimenRuntimeInvokerPolicy" status
  if api_service_exists; then status=0; else status=$?; fi
  case $status in
    0)
      grant service "$API_SERVICE" "$RELEASE" "$role"
      if [ "$HELD" -eq 1 ]; then
        revoke project "$PROJECT" "$RELEASE" "$role"
        NARROWED=1
      fi
      ;;
    1)
      grant project "$PROJECT" "$RELEASE" "$role"
      note "the service $API_SERVICE does not exist yet, so the first release needs this right on the project; the next run of this script narrows it to that one service."
      ;;
    *)
      if [ "$LENIENT" -eq 0 ]; then die "could not tell whether the service $API_SERVICE exists (see the error above)"; fi
      warn "could not tell whether the service $API_SERVICE exists (the error is above); the next run of this script narrows the right to it"
      ;;
  esac
}

# Right after a passed runtime release the service exists, so the right moves now instead of
# at the next run. This is tidying up, not part of the release: a failure here is a warning.
narrow_after_release() {
  printf 'runtime release: the right to set who may call the API now moves from the project to the one service\n'
  forget_policy project "$PROJECT"
  forget_policy service "$API_SERVICE"
  LENIENT=1
  scope_invoker_policy
  LENIENT=0
}

# A runtime reads one exact version of a secret, never "latest".
pinned_secret() { # pinned_secret MEMBER SECRET VERSION
  local title
  title="$(printf '%s' "$2" | tr - _)_v$3"
  grant secret "$2" "$1" roles/secretmanager.secretAccessor "$title" \
    "resource.name.endsWith(\"/secrets/$2/versions/$3\")"
}

# Creates a missing custom role, or sets a differing one to exactly these permissions.
ensure_role() { # ensure_role NAME TITLE DESCRIPTION PERMISSION...
  local name=$1 title=$2 description=$3 want live stage rest deleted have
  shift 3
  want=$(printf '%s\n' "$@" | LC_ALL=C sort -u | paste -sd, -)
  if live=$(gcloud iam roles describe "$name" "--project=$PROJECT" "--format=$ROLE_FORMAT" 2> "$WORK/stderr" < /dev/null); then
    stage=${live%%|*}
    rest=${live#*|}
    deleted=${rest%%|*}
    have=$(printf '%s\n' "${rest#*|}" | tr ',' '\n' | LC_ALL=C sort -u | paste -sd, -)
    if [ "$deleted" = True ]; then
      change "restore the deleted role $name"
      run gcloud iam roles undelete "$name" "--project=$PROJECT"
    elif [ "$stage" = GA ] && [ "$have" = "$want" ]; then
      in_place "role $name holds exactly its permission list ($#)"
      return 0
    fi
    change "set role $name to exactly its permission list ($#)"
    run gcloud iam roles update "$name" "--project=$PROJECT" "--permissions=$want" --stage=GA
  elif grep -q 'NOT_FOUND' "$WORK/stderr"; then
    change "create role $name"
    run gcloud iam roles create "$name" "--project=$PROJECT" "--title=$title" "--description=$description" \
      "--permissions=$want" --stage=GA
  else
    cat "$WORK/stderr" >&2
    die "could not read role $name"
  fi
}

preflight() {
  local account login number
  command -v gcloud > /dev/null 2>&1 || die "gcloud is not on PATH: install the Google Cloud SDK"
  command -v gh > /dev/null 2>&1 || die "gh is not on PATH: install the GitHub CLI"
  account=$(gcloud config get-value account 2> /dev/null < /dev/null) || account=''
  [ -n "$account" ] || die "gcloud is not signed in: run gcloud auth login"
  gh auth status > /dev/null 2>&1 < /dev/null || die "gh is not signed in: run gh auth login"
  login=$(gh api user --jq .login 2> /dev/null < /dev/null) || login='(not shown by gh)'
  if ! number=$(gcloud projects describe "$PROJECT" '--format=value(projectNumber)' 2> "$WORK/stderr" < /dev/null); then
    cat "$WORK/stderr" >&2
    die "cannot reach project $PROJECT as $account (if the sign-in has expired: gcloud auth login)"
  fi
  [ "$number" = "$PROJECT_NUMBER" ] || die "project $PROJECT has number $number, expected $PROJECT_NUMBER"
  printf 'Google Cloud account: %s\n' "$account"
  printf 'GitHub account: %s\n' "$login"
  printf 'Project: %s (%s)\n' "$PROJECT" "$PROJECT_NUMBER"
  printf 'Repository: %s\n' "$REPOSITORY"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'Mode: dry run. The live state is read; lines that start with + are printed, not run.\n'
  else
    printf 'Mode: apply. Each line that starts with + is run right after it is printed.\n'
  fi
}

# Removes one expired grant by its exact live condition; never --all, which would also drop
# the standing grant of the same role.
remove_expired() { # remove_expired ROLE
  local role="$CUSTOM/$1" title="specimen_pr21_$1" head line rest expression description end found=0
  head="$DATA$TAB$role$TAB$title$TAB"
  load_policy project "$PROJECT"
  while IFS= read -r line; do
    case $line in
      "$head"*) rest=${line#"$head"} ;;
      *) continue ;;
    esac
    found=1
    expression=${rest%%"$TAB"*}
    description=''
    case $rest in
      *"$TAB"*) description=${rest#*"$TAB"} ;;
    esac
    if [[ ! $expression =~ $WINDOW ]]; then
      warn "$title is not a plain time window; left in place, review it by hand"
      continue
    fi
    end=${BASH_REMATCH[2]}
    if [[ ! $end < $NOW ]]; then
      warn "$title is open until $end; left in place"
      continue
    fi
    change "remove the expired grant $title (ended $end)"
    condition_file "$title" "$expression" "$description"
    run gcloud projects remove-iam-policy-binding "$PROJECT" "--member=$DATA" "--role=$role" \
      "--condition-from-file=$CONDITION_FILE"
  done < "$POLICY"
  if [ "$found" -eq 0 ]; then in_place "already removed: $title"; fi
}

remove_expired_grants() {
  heading 'Clean-up: remove four expired time-limited grants from the data release account'
  remove_expired specimenDataSchemaPublish
  remove_expired specimenDataStorageRules
  remove_expired specimenDataSourceBackup
  remove_expired specimenDataRuntimeAbsence
}

data_release_grants() {
  heading 'Data release: standing permissions to publish the schema, the connector, the Storage rules and the first rows'
  # PATCH with allowMissing needs create and update; the skip checks and the operation poll need the gets.
  ensure_role specimenDataSchemaPublish 'Specimen compatible SQL Connect publication' \
    'Publish the Data Connect schema and connector; no delete.' \
    firebasedataconnect.schemas.create firebasedataconnect.schemas.get firebasedataconnect.schemas.update \
    firebasedataconnect.connectors.create firebasedataconnect.connectors.get firebasedataconnect.connectors.update \
    firebasedataconnect.operations.get
  ensure_role specimenDataStorageRules 'Specimen private Storage rule publication' \
    'Publish the Storage rules; no delete.' \
    firebaserules.rulesets.create firebaserules.rulesets.get \
    firebaserules.releases.create firebaserules.releases.get firebaserules.releases.update
  ensure_role specimenDataInventoryProjectRead 'Specimen inventory project identity read' \
    'Read the identity of the project.' \
    resourcemanager.projects.get
  ensure_role specimenDataInventorySqlConnect 'Specimen source inventory connection' \
    'Only get, connect and IAM login; conditionally bound to the existing source instance.' \
    cloudsql.instances.connect cloudsql.instances.get cloudsql.instances.login cloudsql.databases.get
  # Not specimenDataOwnerBootstrap: that role also reads Firebase accounts, which the release no longer does.
  ensure_role specimenDataBootstrapRows 'Specimen data bootstrap rows' \
    'Read and write the first organization, collection and membership rows through Data Connect.' \
    firebasedataconnect.services.executeGraphql firebasedataconnect.services.executeGraphqlRead
  grant project "$PROJECT" "$DATA" "$CUSTOM/specimenDataSchemaPublish"
  grant project "$PROJECT" "$DATA" "$CUSTOM/specimenDataStorageRules"
  grant project "$PROJECT" "$DATA" "$CUSTOM/specimenDataInventoryProjectRead"
  grant project "$PROJECT" "$DATA" "$CUSTOM/specimenDataInventorySqlConnect" "$SQL_TITLE" "$SQL_EXPRESSION" "$SQL_DESCRIPTION"
  grant project "$PROJECT" "$DATA" "$CUSTOM/specimenDataBootstrapRows"
  pinned_secret "$DATA" specimen-worker-actor-uid 1
  ensure_role specimenGeoreferenceDatasets 'Specimen immutable georeferencing datasets' \
    'Create and verify only the committed georeferencing objects; no list, overwrite or delete.' \
    storage.objects.create storage.objects.get
  grant bucket "$BUCKET" "$DATA" "$CUSTOM/specimenGeoreferenceDatasets" "$GEO_TITLE" "$GEO_EXPRESSION"
  note 'specimenDataSourceBackup is not granted: the release takes no backups.'
}

cloud_sql_role() {
  local roles
  heading 'Cloud SQL: let the data release create the three database roles once (later releases only use the firebaseowner role)'
  roles=$(gcloud sql users describe "$SQL_USER" "--instance=$INSTANCE" "--project=$PROJECT" \
    '--format=value(databaseRoles.list())' < /dev/null) ||
    die "could not read the database user $SQL_USER on $INSTANCE (see the error above)"
  roles=${roles//;/,}
  case ",${roles// /}," in
    *,cloudsqlsuperuser,*) in_place "$SQL_USER is a member of cloudsqlsuperuser" ;;
    *)
      change "make $SQL_USER a member of cloudsqlsuperuser"
      run gcloud sql users assign-roles "$SQL_USER" "--instance=$INSTANCE" --type=CLOUD_IAM_SERVICE_ACCOUNT \
        --database-roles=cloudsqlsuperuser "--project=$PROJECT"
      ;;
  esac
}

runtime_grants() {
  local name
  heading 'Runtime release: permissions to push the image, deploy the API and open it to the web client'
  ensure_role specimenRuntimeRelease 'Specimen runtime release' \
    'Create and update the Cloud Run services and the worker job; no delete, no job runs.' \
    run.services.create run.services.get run.services.update run.services.getIamPolicy \
    run.jobs.create run.jobs.get run.jobs.update run.jobs.getIamPolicy run.operations.get run.revisions.get
  # This deployment role reads worker invokers but cannot execute jobs or set
  # their IAM. The separate execution role below is bound only to specimen-worker.
  ensure_role specimenRuntimeInvokerPolicy 'Specimen runtime invoker policy' \
    'Read and set who may call the API service.' \
    run.services.getIamPolicy run.services.setIamPolicy
  ensure_role specimenWorkerExecution 'Specimen queued worker execution' \
    'Run the existing worker without overrides and read its execution outcome.' \
    run.jobs.run run.executions.get
  ensure_role specimenWorkerRead 'Specimen worker readiness read' \
    'Read only the deployed specimen worker definition for API readiness.' \
    run.jobs.get
  ensure_role specimenRuntimeConnector 'Specimen runtime connector' \
    'call the named operations of the connector only, never arbitrary GraphQL' \
    firebasedataconnect.connectors.impersonateQuery firebasedataconnect.connectors.impersonateMutation
  ensure_role specimenApiUserLookup 'Specimen API user lookup' \
    'look up the Firebase user behind a verified ID token' \
    firebaseauth.users.get

  grant repository "$REGISTRY" "$BUILD" roles/artifactregistry.writer
  grant project "$PROJECT" "$RELEASE" "$CUSTOM/specimenRuntimeRelease"
  scope_invoker_policy
  grant project "$PROJECT" "$RELEASE" "$CUSTOM/specimenDataInventoryProjectRead"
  grant repository "$REGISTRY" "$RELEASE" roles/artifactregistry.reader
  grant job specimen-worker "$RELEASE" "$CUSTOM/specimenWorkerExecution"
  grant job specimen-worker "$API" "$CUSTOM/specimenWorkerRead"
  for name in api worker sam; do
    grant service-account "specimen-$name-runtime@$ACCOUNTS" "$RELEASE" roles/iam.serviceAccountUser
  done

  # The runtime accounts' own grants are live already; asserting them again keeps the script self-healing.
  grant project "$PROJECT" "$API" "$CUSTOM/specimenRuntimeConnector"
  grant project "$PROJECT" "$WORKER" "$CUSTOM/specimenRuntimeConnector"
  grant project "$PROJECT" "$API" "$CUSTOM/specimenApiUserLookup"
  for name in "$API" "$WORKER" "$SAM"; do
    grant bucket "$BUCKET" "$name" roles/storage.objectViewer "$APP_TITLE" "$APP_EXPRESSION"
    grant bucket "$BUCKET" "$name" roles/storage.objectCreator "$APP_TITLE" "$APP_EXPRESSION"
  done
  # The research harness creates objects with a generation match and reads them back; it never lists or deletes.
  # So the worker, and no other account, gets create and get on its three prefixes.
  grant bucket "$BUCKET" "$WORKER" roles/storage.objectViewer "$RESEARCH_TITLE" "$RESEARCH_EXPRESSION"
  grant bucket "$BUCKET" "$WORKER" roles/storage.objectCreator "$RESEARCH_TITLE" "$RESEARCH_EXPRESSION"
  grant bucket "$BUCKET" "$API" roles/storage.objectViewer "$SLIDES_TITLE" "$SLIDES_EXPRESSION"
  # Versions as pinned in scripts/ci/runtime_settings.py. The worker reads no Google Maps key
  # any more (the owner took Maps out of the pipeline): that read is neither granted nor removed here.
  pinned_secret "$API" specimen-worker-logfire 1
  pinned_secret "$API" specimen-source-registry 1
  pinned_secret "$API" specimen-collection-bindings 1
  pinned_secret "$WORKER" huggingface-runtime-token 2
  pinned_secret "$WORKER" specimen-worker-logfire 1
  pinned_secret "$WORKER" specimen-worker-actor-uid 1
  pinned_secret "$WORKER" specimen-collection-bindings 1
  pinned_secret "$SAM" specimen-worker-logfire 1

  # For the SAM 3 checkpoint mount (follow-up change #236, scripts/ops/iam.py LIST_BUCKET): when
  # the mount starts it asks for the bucket and lists it without a prefix. This role holds the
  # bucket read and the object listing and no object read: names and metadata, never contents.
  grant bucket "$BUCKET" "$SAM" roles/storage.legacyBucketReader
  note 'specimen-sam-runtime may list the bucket (object names and metadata, never contents): the SAM 3 checkpoint mount needs it (follow-up change #236).'
  note 'the listing grant limited to the checkpoint prefix is not made here: its condition names the checkpoint digest, which change #236 commits and grants with its scripts/ops/iam.py.'

  for name in specimen-data-release specimen-runtime-build specimen-runtime-release; do
    grant service-account "$name@$ACCOUNTS" "$PLANE/$name" roles/iam.workloadIdentityUser
  done
}

# Widens one provider from push-only to push or a manual run; every other clause stays verbatim.
widen_provider() { # widen_provider PROVIDER
  local condition before after
  condition=$(gcloud iam workload-identity-pools providers describe "$1" "--workload-identity-pool=$POOL" \
    --location=global "--project=$PROJECT" '--format=value(attributeCondition)' < /dev/null) ||
    die "could not read provider $1 (see the error above)"
  case $condition in
    *"$PUSH_OR_MANUAL"*)
      in_place "$1 already allows manual runs on main"
      return 0
      ;;
    *workflow_dispatch*)
      warn "$1 names workflow_dispatch in another form; nothing changed, review it by hand"
      return 0
      ;;
    *"$PUSH_ONLY"*) ;;
    *)
      warn "$1 has no clause \"$PUSH_ONLY\"; nothing changed, review it by hand"
      return 0
      ;;
  esac
  before=${condition%%"$PUSH_ONLY"*}
  after=${condition#*"$PUSH_ONLY"}
  case $after in
    *"$PUSH_ONLY"*)
      warn "$1 has the clause \"$PUSH_ONLY\" more than once; nothing changed, review it by hand"
      return 0
      ;;
  esac
  change "let $1 accept a manual run on main as well as a push"
  run gcloud iam workload-identity-pools providers update-oidc "$1" "--workload-identity-pool=$POOL" \
    --location=global "--project=$PROJECT" "--attribute-condition=$before$PUSH_OR_MANUAL$after"
}

manual_runs() {
  heading 'Manual runs: let "Run workflow" on main sign in as the three release identities'
  widen_provider specimen-data-release
  widen_provider specimen-runtime-build
  widen_provider specimen-runtime-release
  note 'the Hosting provider (specimen-digitization) is not touched.'
}

ensure_variable() { # ensure_variable NAME VALUE
  local current
  current=$(gh variable get "$1" -R "$REPOSITORY" 2> /dev/null < /dev/null) || current=''
  if [ "$current" = "$2" ]; then
    in_place "repository variable $1"
    return 0
  fi
  change "set repository variable $1"
  run gh variable set "$1" -R "$REPOSITORY" --body "$2"
  if [ "$LAST_OK" -eq 1 ]; then VARIABLES_CHANGED=1; fi
}

repository_variables() {
  heading 'GitHub: the two repository variables the web build reads'
  ensure_variable SPECIMEN_API_BASE_URL "$API_BASE_URL"
  ensure_variable SPECIMEN_RECAPTCHA_SITE_KEY "$RECAPTCHA_SITE_KEY"
}

# The value travels from the file to gh through a pipe: never in an argument, never printed.
bootstrap_secret() {
  local size names
  heading 'GitHub: the bootstrap artifact the data release reads once to write the first rows'
  if [ -s "$ARTIFACT_FILE" ]; then
    size=$(wc -c < "$ARTIFACT_FILE" | tr -d ' ')
    change "set secret $ARTIFACT_NAME in environment $DATA_ENVIRONMENT from the artifact file ($size bytes)"
    note "GitHub never shows a secret, so it is set again on every run while $ARTIFACT_FILE exists."
    printf "+ base64 < %s | tr -d '\\\\n' | gh secret set %s --env %s -R %s\\n" \
      "$ARTIFACT_FILE" "$ARTIFACT_NAME" "$DATA_ENVIRONMENT" "$REPOSITORY"
    if [ "$DRY_RUN" -eq 1 ]; then
      succeeded
      return 0
    fi
    if base64 < "$ARTIFACT_FILE" | tr -d '\n' |
      gh secret set "$ARTIFACT_NAME" --env "$DATA_ENVIRONMENT" -R "$REPOSITORY" > /dev/null; then
      succeeded
    else
      failed
    fi
    return 0
  fi
  names=$(gh secret list --env "$DATA_ENVIRONMENT" -R "$REPOSITORY" --json name --jq '.[].name' < /dev/null) ||
    die "could not list the secrets of environment $DATA_ENVIRONMENT (see the error above)"
  if grep -Fxq "$ARTIFACT_NAME" <<< "$names"; then
    in_place "secret $ARTIFACT_NAME exists and is left as it is (no artifact file at $ARTIFACT_FILE)"
  else
    warn "secret $ARTIFACT_NAME is MISSING in environment $DATA_ENVIRONMENT and there is no artifact file at $ARTIFACT_FILE: the data release will fail at the bootstrap step"
  fi
}

retire_candidates() {
  heading 'Retire later: printed only, nothing here is removed'
  printf '  The simple release no longer uses these. Delete them by hand once the first release has succeeded:\n'
  printf '  - variables of environment %s: RELEASE_AUTHORIZED_SHA, RELEASE_BUDGET_LEDGER_SHA256, RELEASE_INPUTS_SHA256, RELEASE_PACKET_SHA256\n' "$DATA_ENVIRONMENT"
  printf '  - secrets of environment %s: RELEASE_INPUTS_B64, DATA_BOOTSTRAP_APPROVED_SHA256, DATA_WORKER_ACTOR_UID\n' "$DATA_ENVIRONMENT"
  printf '  - GitHub environment data-initialization-production\n'
  printf '  - workload identity provider specimen-data-initialize\n'
  printf '  - service account specimen-data-initialize@%s\n' "$ACCOUNTS"
  printf '  - custom role specimenFirstReleaseMetadataRead\n'
  printf '  - secret specimen-google-maps-key and the read of its version 1 by specimen-worker-runtime (Google Maps is no longer part of the pipeline)\n'
  printf '  Also unused now: the standing grant of specimenDataSourceBackup to specimen-data-release, and the role specimenDataOwnerBootstrap.\n'
}

# Starts a workflow run or a re-run: printed first, never run in a dry run. Its status is the
# command's own.
launch() {
  show "$@"
  if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
  "$@" > /dev/null < /dev/null
}

pause() { # pause SECONDS
  if [ "$1" -gt 0 ]; then sleep "$1"; fi
}

# The text of one field of a small JSON document on standard input; nothing when it is absent.
json_text() { # json_text FIELD
  tr -d '\n' | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p"
}

# Says which commit a public address serves; a failed read is only a warning.
report_live() { # report_live LABEL URL FIELD WHAT
  local body value=''
  if body=$(curl -fsS --max-time 10 "$2" 2> /dev/null < /dev/null); then
    value=$(printf '%s' "$body" | json_text "$3")
  fi
  if [ -n "$value" ]; then
    printf '%s: %s now serves commit %s\n' "$1" "$4" "$value"
  else
    warn "$1: could not read $2 to confirm the commit; the run itself passed"
  fi
}

skip_releases() { # skip_releases REASON
  DATA_STATE="SKIPPED ($1)"
  RUNTIME_STATE=$DATA_STATE
  WEB_STATE=$DATA_STATE
}

# A stage that ended without a run to point at.
stage_failed() { # stage_failed LABEL REASON
  printf '%s: FAIL - %s\n' "$1" "$2"
  STAGE_STATE="FAIL ($2)"
  STAGE_FAILURES=$((STAGE_FAILURES + 1))
}

# A run that failed or outlived the cap: its address, where it failed and the log command.
run_failed() { # run_failed LABEL RUN_ID RESULT
  local command="gh run view $2 --log-failed -R $REPOSITORY"
  STAGE_STATE="FAIL $RUN_URL"
  if [ "$3" -eq 2 ]; then
    STAGE_STATE="$STAGE_STATE (not finished after $((WATCH_POLLS * POLL_SECONDS / 60)) minutes of watching)"
  fi
  printf '%s: %s\n' "$1" "$STAGE_STATE"
  if [ -n "$RUN_FAILED_AT" ]; then printf '%s: failed at: %s\n' "$1" "$RUN_FAILED_AT"; fi
  printf '%s: to read the log: %s\n' "$1" "$command"
  LOG_COMMANDS="$LOG_COMMANDS  $command$NL"
  STAGE_FAILURES=$((STAGE_FAILURES + 1))
}

# True when both simple workflows on main can be started by hand; 1 when not yet, 2 when
# main could not be read.
workflows_on_main() {
  local name text
  for name in "$DATA_WORKFLOW" "$RUNTIME_WORKFLOW"; do
    text=$(gh workflow view "$name" -R "$REPOSITORY" --ref main --yaml < /dev/null) || return 2
    grep -Eq '^[[:space:]]*workflow_dispatch:' <<< "$text" || return 1
  done
}

# The id of the newest run of a workflow that was started by hand on main; nothing when none.
newest_manual_run() { # newest_manual_run WORKFLOW
  gh run list --workflow "$1" -R "$REPOSITORY" --branch main --event workflow_dispatch --limit 1 \
    --json databaseId --jq '.[0].databaseId // empty' < /dev/null
}

# Follows one run to its end and prints one line for each step (or, in mode "jobs", each job)
# as it finishes; housekeeping and skipped steps stay silent. AFTER is the attempt number a
# re-run must exceed before its state counts. Sets RUN_URL and RUN_FAILED_AT; returns 0 when
# the run passed, 1 when it failed, 2 when it is still running after the cap.
watch_run() { # watch_run LABEL RUN_ID MODE AFTER
  local label=$1 id=$2 mode=$3 after=$4 polls=0 waits=0 errors=0 seen="$NL"
  local report line kind rest status attempt conclusion job number name result key
  RUN_URL="https://github.com/$REPOSITORY/actions/runs/$id"
  RUN_FAILED_AT=''
  while :; do
    # One failed reading in a long watch is not worth a line; five in a row end the watch.
    if ! report=$(gh run view "$id" -R "$REPOSITORY" --json attempt,status,conclusion,url,jobs --jq "$RUN_JQ" \
      2> "$WORK/stderr" < /dev/null); then
      errors=$((errors + 1))
      if [ "$errors" -ge 5 ]; then
        cat "$WORK/stderr" >&2
        RUN_FAILED_AT='the run could not be read five times in a row'
        return 1
      fi
      pause "$POLL_SECONDS"
      continue
    fi
    errors=0
    status=''
    conclusion=''
    attempt=0
    while IFS= read -r line; do
      kind=${line%%"$TAB"*}
      rest=${line#*"$TAB"}
      case $kind in
        R)
          status=${rest%%"$TAB"*}
          rest=${rest#*"$TAB"}
          conclusion=${rest%%"$TAB"*}
          rest=${rest#*"$TAB"}
          if [ -n "${rest%%"$TAB"*}" ]; then RUN_URL=${rest%%"$TAB"*}; fi
          attempt=${rest#*"$TAB"}
          case $attempt in
            '' | *[!0-9]*) attempt=0 ;;
          esac
          if [ "$attempt" -le "$after" ]; then break; fi
          ;;
        S)
          job=${rest%%"$TAB"*}
          rest=${rest#*"$TAB"}
          number=${rest%%"$TAB"*}
          rest=${rest#*"$TAB"}
          name=${rest%%"$TAB"*}
          result=${rest#*"$TAB"}
          key="S$TAB$job$TAB$number"
          case $seen in
            *"$NL$key$NL"*) continue ;;
          esac
          seen="$seen$key$NL"
          case $result in
            skipped | neutral) continue ;;
            success)
              case $name in
                'Set up job' | 'Complete job' | 'Post '*) continue ;;
              esac
              result='done'
              ;;
            *)
              result=FAILED
              if [ -z "$RUN_FAILED_AT" ]; then RUN_FAILED_AT="$job / $name"; fi
              ;;
          esac
          case $mode in
            steps) printf '%s: %s - %s\n' "$label" "$result" "$name" ;;
            job-steps) printf '%s: %s - %s: %s\n' "$label" "$result" "$job" "$name" ;;
          esac
          ;;
        J)
          job=${rest%%"$TAB"*}
          result=${rest#*"$TAB"}
          key="J$TAB$job"
          case $seen in
            *"$NL$key$NL"*) continue ;;
          esac
          seen="$seen$key$NL"
          case $result in
            skipped | neutral) continue ;;
            success) result='done' ;;
            *)
              result=FAILED
              if [ -z "$RUN_FAILED_AT" ]; then RUN_FAILED_AT=$job; fi
              ;;
          esac
          if [ "$mode" = jobs ]; then printf '%s: %s - %s\n' "$label" "$result" "$job"; fi
          ;;
      esac
    done <<< "$report"
    if [ "$attempt" -le "$after" ]; then
      waits=$((waits + 1))
      if [ "$waits" -gt "$FIND_TRIES" ]; then
        RUN_FAILED_AT='the new attempt did not start'
        return 1
      fi
      pause "$FIND_SECONDS"
      continue
    fi
    if [ "$status" = completed ]; then
      if [ "$conclusion" = success ]; then return 0; fi
      if [ -z "$RUN_FAILED_AT" ]; then RUN_FAILED_AT="the run ended as ${conclusion:-unknown}"; fi
      return 1
    fi
    polls=$((polls + 1))
    if [ "$polls" -ge "$WATCH_POLLS" ]; then return 2; fi
    pause "$POLL_SECONDS"
  done
}

# Starts one workflow on main, finds the run it created and follows it. A first failure
# right after new access was granted gets one more try. Sets STAGE_STATE; returns 0 only
# when the run passed (in a dry run: when it would be started).
release_stage() { # release_stage LABEL WORKFLOW MODE
  local label=$1 workflow=$2 mode=$3 attempt=1 before id tries result
  if [ "$DRY_RUN" -eq 1 ]; then
    launch gh workflow run "$workflow" --ref main -R "$REPOSITORY"
    STAGE_STATE='WOULD RUN'
    return 0
  fi
  while :; do
    if ! before=$(newest_manual_run "$workflow"); then
      stage_failed "$label" 'the existing runs could not be listed (the error is above)'
      return 1
    fi
    if ! launch gh workflow run "$workflow" --ref main -R "$REPOSITORY"; then
      stage_failed "$label" 'the run could not be started (the error is above)'
      return 1
    fi
    id=''
    tries=0
    while [ "$tries" -lt "$FIND_TRIES" ]; do
      pause "$FIND_SECONDS"
      id=$(newest_manual_run "$workflow") || id=''
      if [ -n "$id" ] && [ "$id" != "$before" ]; then break; fi
      id=''
      tries=$((tries + 1))
    done
    if [ -z "$id" ]; then
      stage_failed "$label" 'the new run did not appear; look for it on the Actions page before running this again'
      return 1
    fi
    printf '%s: started https://github.com/%s/actions/runs/%s\n' "$label" "$REPOSITORY" "$id"
    if watch_run "$label" "$id" "$mode" 0; then
      printf '%s: PASS %s\n' "$label" "$RUN_URL"
      STAGE_STATE="PASS $RUN_URL"
      return 0
    else
      result=$?
    fi
    if [ "$result" -eq 1 ] && [ "$attempt" -eq 1 ] && [ "$ACCESS_CHANGED" -eq 1 ]; then
      printf '%s: the first try failed (%s). The new access may still be settling: waiting %s seconds, then trying once more\n' \
        "$label" "$RUN_URL" "$RETRY_SECONDS"
      pause "$RETRY_SECONDS"
      attempt=2
      continue
    fi
    run_failed "$label" "$id" "$result"
    return 1
  done
}

data_stage() {
  heading 'Stage: data release'
  CURRENT=data
  if release_stage 'data release' "$DATA_WORKFLOW" steps; then
    DATA_STATE=$STAGE_STATE
    return 0
  fi
  DATA_STATE=$STAGE_STATE
  RUNTIME_STATE='SKIPPED (the data release did not pass)'
  WEB_STATE=$RUNTIME_STATE
  return 1
}

runtime_stage() {
  heading 'Stage: runtime release'
  CURRENT=runtime
  if release_stage 'runtime release' "$RUNTIME_WORKFLOW" job-steps; then
    RUNTIME_STATE=$STAGE_STATE
    if [ "$DRY_RUN" -eq 0 ]; then report_live 'runtime release' "$API_BASE_URL/version" source_sha 'the API'; fi
    if [ "$NARROWED" -eq 0 ]; then
      if [ "$DRY_RUN" -eq 0 ]; then
        narrow_after_release
      else
        printf 'runtime release: once it has passed, the right to set who may call the API would move from the project to the one service\n'
      fi
    fi
    return 0
  fi
  RUNTIME_STATE=$STAGE_STATE
  WEB_STATE='SKIPPED (the runtime release did not pass)'
  return 1
}

# Whether the live site was built with the API address. The program is saved, never printed,
# and fetched under a new address each time so that no cache answers. Returns 0 when it names
# the API host, 1 when it does not, 2 when that could not be checked: the download failed, or
# what came back is not the compiled program (compressed, or the page served for a missing file).
site_names_api() {
  local file="$WORK/site-program"
  curl -fsS --max-time 60 -o "$file" "$SITE_PROGRAM?check=$(date +%s)" 2> /dev/null < /dev/null || return 2
  LC_ALL=C grep -q -F 'dartProgram' "$file" || return 2
  LC_ALL=C grep -q -F "$API_HOST" "$file"
}

# Says whether the live site points at the API and sets SITE_NOTE for the summary. A site
# that does not is a warning, never a failure: every later merge to main builds it again with
# the variables set. Returns 1 only in that case.
check_site() { # check_site WORD  ("now " right after a build, "" otherwise)
  local status
  if site_names_api; then status=0; else status=$?; fi
  case $status in
    0)
      printf 'web app: the site %spoints at the API\n' "$1"
      SITE_NOTE='the site points at the API'
      ;;
    1)
      warn 'web: variables not picked up; the next merge to main will redeploy'
      SITE_NOTE='the site does not point at the API yet'
      return 1
      ;;
    *)
      warn "web app: could not check whether the site points at the API ($SITE_PROGRAM did not come back as the built program)"
      SITE_NOTE='the site could not be checked'
      ;;
  esac
}

# The site reads the two repository variables when it is built, so new values need one more
# build: the newest build of main is run again and followed to its end. A re-run is not
# trusted to have read the new values: the live site is checked for the API address afterwards.
web_stage() {
  local found id attempt status rest result
  heading 'Stage: web app'
  CURRENT=web
  if [ "$VARIABLES_CHANGED" -eq 0 ] && [ "$REDEPLOY_WEB" -eq 0 ]; then
    printf 'web app: variables already set; no rebuild needed\n'
    # The check only reads, so a dry run makes it too.
    if check_site ''; then
      WEB_STATE="SKIPPED (variables already set; no rebuild needed; $SITE_NOTE)"
    else
      WEB_STATE="WARN (variables already set, but $SITE_NOTE)"
    fi
    return 0
  fi
  found=$(gh run list --workflow "$WEB_WORKFLOW" -R "$REPOSITORY" --branch main --event push --limit 1 \
    --json databaseId,attempt,status,conclusion,createdAt,url --jq "$NEWEST_JQ" < /dev/null) || found=''
  if [ -z "$found" ]; then
    stage_failed 'web app' 'no build of main was found to run again'
    WEB_STATE=$STAGE_STATE
    return 0
  fi
  id=${found%%"$TAB"*}
  rest=${found#*"$TAB"}
  attempt=${rest%%"$TAB"*}
  rest=${rest#*"$TAB"}
  status=${rest%%"$TAB"*}
  RUN_URL=${rest#*"$TAB"}
  case $attempt in
    '' | *[!0-9]*) attempt=0 ;;
  esac
  if [ "$DRY_RUN" -eq 1 ]; then
    launch gh run rerun "$id" -R "$REPOSITORY"
    printf 'web app: after that build the live site would be checked for the API address\n'
    WEB_STATE="WOULD RUN $RUN_URL"
    return 0
  fi
  if [ "$status" != completed ]; then
    printf 'web app: the newest build of main is still running; following it to its end first\n'
    # Its result does not matter: the same build is run again below.
    watch_run 'web app' "$id" jobs 0 || true
  fi
  printf 'web app: running the build of main again so that it reads the repository variables\n'
  if ! launch gh run rerun "$id" -R "$REPOSITORY"; then
    stage_failed 'web app' 'the build could not be started again (the error is above)'
    WEB_STATE=$STAGE_STATE
    return 0
  fi
  if watch_run 'web app' "$id" jobs "$attempt"; then
    printf 'web app: PASS %s\n' "$RUN_URL"
    report_live 'web app' "$APP_URL/deployment.json" commitSha 'the site'
    if check_site 'now '; then
      WEB_STATE="PASS $RUN_URL ($SITE_NOTE)"
    else
      WEB_STATE="WARN $RUN_URL ($SITE_NOTE)"
    fi
    return 0
  else
    result=$?
  fi
  run_failed 'web app' "$id" "$result"
  WEB_STATE=$STAGE_STATE
}

# After the setup: the releases start only when every setup step went through and the simple
# workflows are on main; each stage starts only when the one before it passed.
releases() {
  local status
  heading 'Releases: start them when the setup went through and the simple workflows are on main'
  if [ "$SETUP_ONLY" -eq 1 ]; then
    printf '  --setup-only: no release is started.\n'
    skip_releases '--setup-only'
    return 0
  fi
  if [ "$FAILURE_COUNT" -gt 0 ]; then
    printf '  A setup step failed, so no release is started.\n'
    skip_releases 'a setup step failed'
    return 0
  fi
  if workflows_on_main; then status=0; else status=$?; fi
  if [ "$status" -eq 2 ]; then
    printf '  The workflows on main could not be read (the error is above), so no release is started.\n'
    skip_releases 'the workflows on main could not be read'
    STAGE_FAILURES=$((STAGE_FAILURES + 1))
    return 0
  fi
  if [ "$status" -eq 1 ]; then
    NOT_MERGED=1
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '  The simple release workflows are not on main yet (the pull request is not merged). Run this script again after the merge.\n'
    else
      printf '  The simple release workflows are not on main yet (the pull request is not merged). Setup is complete. Run this script again after the merge.\n'
    fi
    skip_releases 'the simple workflows are not on main yet'
    return 0
  fi
  printf '  ok: both release workflows on main can be started by hand\n'
  if [ "$ACCESS_CHANGED" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '  Would wait %s seconds for the new access to take effect\n' "$SETTLE_SECONDS"
    else
      printf 'Waiting %s seconds for the new access to take effect\n' "$SETTLE_SECONDS"
      pause "$SETTLE_SECONDS"
    fi
  fi
  data_stage || return 0
  runtime_stage || return 0
  web_stage
}

# On an early stop the summary still names the stage that was under way.
stopped_early() {
  local state='FAIL (stopped early; the error is above)'
  STOPPED=1
  case $CURRENT in
    setup) SETUP_STATE=$state ;;
    data) DATA_STATE=${DATA_STATE:-$state} ;;
    runtime) RUNTIME_STATE=${RUNTIME_STATE:-$state} ;;
    web) WEB_STATE=${WEB_STATE:-$state} ;;
  esac
}

summary() {
  local web_pending=0
  heading 'Summary'
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'Dry run: nothing was changed. %s step(s) would change:\n' "$CHANGE_COUNT"
  else
    printf '%s step(s) changed:\n' "$CHANGE_COUNT"
  fi
  if [ "$CHANGE_COUNT" -eq 0 ]; then printf '  (none)\n'; else printf '%s' "$CHANGES"; fi
  printf 'Already in place: %s check(s).\n' "$IN_PLACE"
  if [ -n "$WARNINGS" ]; then printf 'Warnings:\n%s' "$WARNINGS"; fi
  if [ "$FAILURE_COUNT" -gt 0 ]; then printf 'FAILED: %s step(s) did not go through:\n%s' "$FAILURE_COUNT" "$FAILURES"; fi

  if [ -z "$SETUP_STATE" ]; then
    if [ "$FAILURE_COUNT" -gt 0 ]; then
      SETUP_STATE="FAIL ($FAILURE_COUNT step(s) did not go through)"
    elif [ "$DRY_RUN" -eq 1 ]; then
      SETUP_STATE="WOULD RUN ($CHANGE_COUNT change(s))"
    else
      SETUP_STATE="PASS ($CHANGE_COUNT changed, $IN_PLACE already in place)"
    fi
  fi
  printf '\nStages:\n'
  printf '  Setup: %s\n' "$SETUP_STATE"
  printf '  Data release: %s\n' "${DATA_STATE:-SKIPPED}"
  printf '  Runtime release: %s\n' "${RUNTIME_STATE:-SKIPPED}"
  printf '  Web app: %s\n' "${WEB_STATE:-SKIPPED}"
  if [ "$DRY_RUN" -eq 0 ] && [ "$FAILURE_COUNT" -eq 0 ] && [ "$STOPPED" -eq 0 ]; then
    if [ "$SETUP_ONLY" -eq 1 ]; then
      printf 'State: SETUP DONE, RELEASES NOT STARTED (--setup-only)\n'
    elif [ "$NOT_MERGED" -eq 1 ]; then
      printf 'State: SETUP DONE, RELEASES NOT STARTED\n'
    fi
  fi
  printf 'Live addresses:\n  API: %s\n  App: %s\n' "$API_BASE_URL" "$APP_URL"
  if [ -n "$LOG_COMMANDS" ]; then printf 'To read the log of what failed:\n%s' "$LOG_COMMANDS"; fi

  # New variable values reach the site only through a build; a later run sees them as already set.
  case $WEB_STATE in
    PASS* | WOULD* | WARN*) ;;
    *) if [ "$VARIABLES_CHANGED" -eq 1 ] && [ "$DRY_RUN" -eq 0 ] && [ "$NOT_MERGED" -eq 0 ]; then web_pending=1; fi ;;
  esac
  printf '\nNext steps:\n'
  if [ "$FAILURE_COUNT" -gt 0 ] || [ "$STOPPED" -eq 1 ]; then
    printf '  Fix the errors shown above and run this script again; it retries only what is still missing.\n'
  elif [ "$STAGE_FAILURES" -gt 0 ]; then
    printf '  Nothing is half-done. Send the output of the log command above to the coordinator, then run this script again.\n'
  elif [ "$NOT_MERGED" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then printf '  Run this script again without --dry-run to apply the steps above.\n'; fi
    printf '  Merge the pull request, then run this script again: it starts the releases and watches them.\n'
  elif [ "$DRY_RUN" -eq 1 ]; then
    printf '  Run this script again without --dry-run to apply the steps above.\n'
  elif [ "$SETUP_ONLY" -eq 1 ]; then
    printf '  The releases were not started (--setup-only): the next merge to main starts them and builds the site with these settings.\n'
    if [ "$web_pending" -eq 1 ]; then
      printf '  To start them without a merge, run this script again without --setup-only and with --redeploy-web.\n'
      web_pending=0
    else
      printf '  To start them without a merge, run this script again without --setup-only.\n'
    fi
  else
    case $WEB_STATE in
      WARN*) printf '  None now: the setup and the releases are done, and the next merge to main builds the site with the API address.\n' ;;
      *) printf '  None: the setup and the releases are done.\n' ;;
    esac
  fi
  if [ "$web_pending" -eq 1 ]; then
    printf '  The site has not been built with the new repository variables yet: add --redeploy-web to that next run.\n'
  fi
  printf 'Safe to run again: every step checks what exists first.\n'
}

main() {
  local base=${TMPDIR:-/tmp} arg
  for arg in "$@"; do
    case $arg in
      --dry-run)
        if [ "$DRY_RUN" -eq 1 ]; then bad_usage; fi
        DRY_RUN=1
        CHANGE_WORD='would change'
        ;;
      --setup-only)
        if [ "$SETUP_ONLY" -eq 1 ]; then bad_usage; fi
        SETUP_ONLY=1
        ;;
      --redeploy-web)
        if [ "$REDEPLOY_WEB" -eq 1 ]; then bad_usage; fi
        REDEPLOY_WEB=1
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *) bad_usage ;;
    esac
  done
  if [ "$SETUP_ONLY" -eq 1 ] && [ "$REDEPLOY_WEB" -eq 1 ]; then bad_usage; fi
  # The two waits a test may shorten: after new access (and, half as long again, before the
  # one retry), and between two readings of a run (a third of it while a new run shows up).
  SETTLE_SECONDS=${OWNER_SETUP_SETTLE_SECONDS:-120}
  POLL_SECONDS=${OWNER_SETUP_POLL_SECONDS:-15}
  case $SETTLE_SECONDS$POLL_SECONDS in
    *[!0-9]*) die 'OWNER_SETUP_SETTLE_SECONDS and OWNER_SETUP_POLL_SECONDS must be whole numbers of seconds' ;;
  esac
  RETRY_SECONDS=$((SETTLE_SECONDS * 3 / 2))
  FIND_SECONDS=$((POLL_SECONDS / 3))
  # gcloud and gh must never stop to ask a question, page their output, colour it or announce an
  # update: the script also runs from a shell with no terminal.
  export CLOUDSDK_CORE_DISABLE_PROMPTS=1 GH_PROMPT_DISABLED=1 GH_PAGER=cat PAGER=cat GH_NO_UPDATE_NOTIFIER=1 NO_COLOR=1
  trap finish EXIT
  # WORK stays empty until mktemp succeeds: the exit trap removes whatever it names.
  WORK=$(mktemp -d "${base%/}/owner-setup.XXXXXX")
  NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  preflight
  STARTED=1
  remove_expired_grants
  data_release_grants
  cloud_sql_role
  runtime_grants
  manual_runs
  repository_variables
  bootstrap_secret
  retire_candidates
  releases
  summary
  COMPLETE=1
  if [ "$FAILURE_COUNT" -gt 0 ] || [ "$STAGE_FAILURES" -gt 0 ]; then exit 1; fi
}

main "$@"
