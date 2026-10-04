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
#   ops/sync_production.sh status              # side-by-side local vs production row counts + content hashes, no writes
#   ops/sync_production.sh pull-suggestions     # pull new public Suggestion submissions down
#   ops/sync_production.sh push [--prune]       # push local editorial data + reviewed suggestions up
set -euo pipefail

APP=openanc
cd "$(dirname "$0")/.."   # webapp/, so manage.py is found
PYTHON=".venv/bin/python"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

subcommand="${1:-}"

# With more than one machine, flyctl prints "No machine specified, using ..." to stdout, which
# corrupts anything we capture. Pin one started machine and route every remote call through it.
# All machines share one Postgres database, so any started machine sees the same data; uploaded
# files (push) only exist on the machine they were sent to, which is why they must share this pin.
pick_machine() {
  machine=$(flyctl machines list -a "$APP" --json | "$PYTHON" -c "
import json, sys
started = [m['id'] for m in json.load(sys.stdin) if m.get('state') == 'started']
print(started[0] if started else '')
")
  if [ -z "$machine" ]; then
    echo "No started machine found for '$APP'."
    exit 1
  fi
}

remote() {
  flyctl ssh console -a "$APP" --machine "$machine" -C "$1"
}

case "$subcommand" in
  status|pull-suggestions|push) pick_machine ;;
esac

case "$subcommand" in
  status)
    "$PYTHON" manage.py editorial_row_counts > "$WORKDIR/local_counts.txt"
    remote "python manage.py editorial_row_counts" > "$WORKDIR/prod_counts.txt"

    "$PYTHON" - "$WORKDIR/local_counts.txt" "$WORKDIR/prod_counts.txt" <<'PY'
import re
import sys


def parse(path):
    # Keep only "app.Model: N [hash]" lines; flyctl may add connection chatter around them.
    # Production images deployed before content hashes existed print the count alone.
    rows = {}
    for line in open(path):
        m = re.fullmatch(r"\s*(\S+): (\d+)(?: ([0-9a-f]+))?\s*", line)
        if m:
            rows[m.group(1)] = (int(m.group(2)), m.group(3))
    return rows


local, prod = parse(sys.argv[1]), parse(sys.argv[2])
if not prod:
    sys.exit("Could not read production row counts (see flyctl output above).")

tables = list(local) + [t for t in prod if t not in local]
width = max(len(t) for t in tables)
print(f"{'Table':<{width}}  {'Local':>7}  {'Prod':>7}  {'Diff':>7}  Content")
print(f"{'-' * width}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 9}")

count_diffs = []    # (table, local_count - prod_count or None if missing on one side)
edited = []         # same count, different content
unverified = []     # same count, but a hash is missing on one side
for t in tables:
    l, p = local.get(t), prod.get(t)
    lc, ph = (l or (None, None)), (p or (None, None))
    if l is None or p is None:
        diff, content = "missing", ""
        count_diffs.append((t, None))
    elif lc[0] != ph[0]:
        diff, content = f"{lc[0] - ph[0]:+d}", "differs"
        count_diffs.append((t, lc[0] - ph[0]))
    elif lc[1] is None or ph[1] is None:
        diff, content = "", "unchecked"
        unverified.append(t)
    elif lc[1] != ph[1]:
        diff, content = "0", "DIFFERS"
        edited.append(t)
    else:
        diff, content = "", "match"
    print(f"{t:<{width}}  {'-' if l is None else lc[0]:>7}  {'-' if p is None else ph[0]:>7}  {diff:>7}  {content}")

print()
if not count_diffs and not edited and not unverified:
    print("Local and production are IDENTICAL: same row counts and same content (hash) in every table.")
else:
    n = len(count_diffs) + len(edited)
    if n:
        rows = sum(abs(d) for _, d in count_diffs if d is not None)
        print(f"Local and production DIFFER in {n} table(s):")
        for t, d in count_diffs:
            if d is None:
                where = "local" if t not in local else "production"
                print(f"  {t}: table not present on {where}")
            elif d > 0:
                print(f"  {t}: local has {d} more row(s) than production")
            else:
                print(f"  {t}: production has {-d} more row(s) than local")
        for t in edited:
            print(f"  {t}: same row count, but at least one row's contents differ")
    else:
        print("Row counts match everywhere, but content could not be fully compared.")
    if any(t == "directory.Suggestion" for t, _ in count_diffs) or "directory.Suggestion" in edited:
        print("Suggestions differ: 'pull-suggestions' brings new public submissions down; 'push' sends reviews back up.")
    if unverified:
        print(f"Content hash unavailable for {len(unverified)} table(s) (production is running an older image;")
        print("run 'flyctl deploy' to enable exact comparison): " + ", ".join(unverified))
PY

    # Same row count but different content: drill into which rows and fields differ.
    differing=$("$PYTHON" - "$WORKDIR/local_counts.txt" "$WORKDIR/prod_counts.txt" <<'PY'
import re, sys
def parse(path):
    return {m.group(1): (m.group(2), m.group(3)) for m in (re.fullmatch(r"\s*(\S+): (\d+)(?: ([0-9a-f]+))?\s*", l) for l in open(path)) if m}
l, p = parse(sys.argv[1]), parse(sys.argv[2])
print(" ".join(t for t in l if t in p and l[t][0] == p[t][0] and l[t][1] and p[t][1] and l[t][1] != p[t][1]))
PY
)
    for model in $differing; do
      echo
      echo "== Row-level differences in $model =="
      "$PYTHON" manage.py editorial_rows "$model" > "$WORKDIR/local_rows.json"
      remote "python manage.py editorial_rows $model" > "$WORKDIR/prod_rows.json" || true
      "$PYTHON" - "$WORKDIR/local_rows.json" "$WORKDIR/prod_rows.json" <<'PY'
import json, sys
def load(path):
    for line in open(path):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return None
local, prod = load(sys.argv[1]), load(sys.argv[2])
if local is None or prod is None:
    print("Could not read row data (production may need 'flyctl deploy' for the editorial_rows command).")
    sys.exit(0)
bad = [pk for pk in local if pk in prod and local[pk] != prod[pk]]
only_local = [pk for pk in local if pk not in prod]
only_prod = [pk for pk in prod if pk not in local]
print(f"{len(bad)} row(s) with differing fields; {len(only_local)} only local (pks {only_local[:10]}); {len(only_prod)} only on production (pks {only_prod[:10]}).")
fields = {}
for pk in bad:
    for f in local[pk]:
        if local[pk][f] != prod[pk].get(f):
            fields[f] = fields.get(f, 0) + 1
print("Differing fields (rows affected):", ", ".join(f"{f} ({n})" for f, n in sorted(fields.items(), key=lambda x: -x[1])) or "none")
for pk in bad[:10]:
    for f in local[pk]:
        if local[pk][f] != prod[pk].get(f):
            print(f"  pk {pk} {f}: local={local[pk][f]!r} prod={prod[pk].get(f)!r}")
if len(bad) > 10:
    print(f"  ... and {len(bad) - 10} more row(s)")
PY
    done

    echo
    local_max=$("$PYTHON" manage.py max_suggestion_id)
    echo "Local Suggestion high-water mark: $local_max"
    echo "(run 'pull-suggestions' to fetch anything newer from production)"
    ;;

  pull-suggestions)
    since_id=$("$PYTHON" manage.py max_suggestion_id)
    echo "Pulling suggestions newer than id=$since_id from production..."
    remote "python manage.py dump_new_suggestions --since-id $since_id" | sed -n '/^\[/,$p' > "$WORKDIR/new_suggestions.json"

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

    echo "Using machine $machine"
    SYNC=/tmp/sync
    remote "mkdir -p $SYNC"
    flyctl ssh sftp put "$WORKDIR/editorial.json" $SYNC/editorial.json -a "$APP" --machine "$machine"
    flyctl ssh sftp put "$WORKDIR/manifest.json" $SYNC/manifest.json -a "$APP" --machine "$machine"
    flyctl ssh sftp put "$WORKDIR/suggestions_reviewed.json" $SYNC/suggestions_reviewed.json -a "$APP" --machine "$machine"

    echo "Loading editorial data on production..."
    remote "python manage.py load_editorial_data $SYNC/editorial.json --prune-manifest $SYNC/manifest.json $prune_flag"

    echo "Loading reviewed suggestions on production..."
    remote "python manage.py loaddata $SYNC/suggestions_reviewed.json"

    remote "rm -rf $SYNC"
    echo "Push complete. Spot-check https://openanc.org/ before you walk away."
    ;;

  *)
    echo "Usage: $0 {status|pull-suggestions|push [--prune]}"
    exit 1
    ;;
esac
