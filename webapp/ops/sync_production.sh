#!/usr/bin/env bash
# Local <-> production data sync for OpenANC.
#
# Editorial data (People, CommissionerTerms, Candidates, Elections, etc -- see
# directory/sync.py) is only ever created LOCALLY. Production's only organic write path is the
# public Suggestion form. That rule is what makes the upserts below safe: this script is the one
# place data moves between the two databases, and it writes to production, so it must be run by
# a human from their own terminal, never automated.
#
# Before the first real push, make sure the commands this script shells out to
# (dump_editorial_data, load_editorial_data, dump_new_suggestions, dump_reviewed_suggestions,
# editorial_row_counts, max_suggestion_id) are already deployed to production -- `flyctl deploy`
# ships code only, so this script only works against a production image that already has them.
#
# Usage:
#   ops/sync_production.sh status              # row-count diff both directions, no writes
#   ops/sync_production.sh pull-suggestions     # pull new public Suggestion submissions down
#   ops/sync_production.sh push [--prune]       # push local editorial data + reviewed suggestions up
set -euo pipefail

APP=openanc
cd "$(dirname "$0")/.."   # webapp/, so manage.py is found
PYTHON=".venv/bin/python"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

subcommand="${1:-}"

case "$subcommand" in
  status)
    echo "== Local row counts =="
    "$PYTHON" manage.py editorial_row_counts

    echo
    echo "== Production row counts =="
    flyctl ssh console -a "$APP" -C "python manage.py editorial_row_counts"

    echo
    local_max=$("$PYTHON" manage.py max_suggestion_id)
    echo "Local Suggestion high-water mark: $local_max"
    echo "(run 'pull-suggestions' to fetch anything newer from production)"
    ;;

  pull-suggestions)
    since_id=$("$PYTHON" manage.py max_suggestion_id)
    echo "Pulling suggestions newer than id=$since_id from production..."
    flyctl ssh console -a "$APP" -C "python manage.py dump_new_suggestions --since-id $since_id" > "$WORKDIR/new_suggestions.json"

    count=$("$PYTHON" -c "import json; print(len(json.load(open('$WORKDIR/new_suggestions.json'))))")
    if [ "$count" = "0" ]; then
      echo "No new suggestions."
      exit 0
    fi

    echo "Loading $count new suggestion(s) locally..."
    "$PYTHON" manage.py loaddata "$WORKDIR/new_suggestions.json"
    echo "Done -- review them in the local admin, then push their decisions back with 'push'."
    ;;

  push)
    prune_flag=""
    if [ "${2:-}" = "--prune" ]; then
      prune_flag="--yes"
    fi

    echo "Dumping local editorial data..."
    "$PYTHON" manage.py dump_editorial_data --output "$WORKDIR/editorial.json" --manifest "$WORKDIR/manifest.json"
    "$PYTHON" manage.py dump_reviewed_suggestions --output "$WORKDIR/suggestions_reviewed.json"

    editorial_count=$("$PYTHON" -c "import json; print(len(json.load(open('$WORKDIR/editorial.json'))))")
    reviewed_count=$("$PYTHON" -c "import json; print(len(json.load(open('$WORKDIR/suggestions_reviewed.json'))))")

    echo
    echo "About to push to production app '$APP':"
    echo "  editorial rows (all models combined): $editorial_count"
    echo "  reviewed suggestion rows: $reviewed_count"
    if [ -n "$prune_flag" ]; then
      echo "  --prune requested: rows deleted locally WILL be deleted on production too."
    else
      echo "  (rows deleted locally will NOT be deleted on production -- check 'status' first, then rerun with --prune once the diff looks right)"
    fi
    read -r -p "Continue? [y/N] " ok
    if [ "$ok" != "y" ] && [ "$ok" != "Y" ]; then
      echo "Aborted."
      exit 1
    fi

    flyctl ssh console -a "$APP" -C "mkdir -p /data/sync"
    flyctl ssh sftp put "$WORKDIR/editorial.json" /data/sync/editorial.json -a "$APP"
    flyctl ssh sftp put "$WORKDIR/manifest.json" /data/sync/manifest.json -a "$APP"
    flyctl ssh sftp put "$WORKDIR/suggestions_reviewed.json" /data/sync/suggestions_reviewed.json -a "$APP"

    echo "Loading editorial data on production..."
    flyctl ssh console -a "$APP" -C "python manage.py load_editorial_data /data/sync/editorial.json --prune-manifest /data/sync/manifest.json $prune_flag"

    echo "Loading reviewed suggestions on production..."
    flyctl ssh console -a "$APP" -C "python manage.py loaddata /data/sync/suggestions_reviewed.json"

    flyctl ssh console -a "$APP" -C "rm -rf /data/sync"
    echo "Push complete. Spot-check https://openanc.fly.dev/ before you walk away."
    ;;

  *)
    echo "Usage: $0 {status|pull-suggestions|push [--prune]}"
    exit 1
    ;;
esac
