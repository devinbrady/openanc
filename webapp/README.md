# OpenANC maintainer commands

What to run to change OpenANC data and ship it to the live site. Commands run from `webapp/` with
the venv active, unless noted. For the rules behind this workflow and how to make the judgment
calls, read [GUIDELINES.md](GUIDELINES.md) first.

## Setting up on a new machine

Everything is in git except `webapp/db.sqlite3` (the local database, which is the editorial
source of truth), `webapp/.venv`, and your `flyctl` login.

```bash
git clone git@github.com:devinbrady/openanc.git && cd openanc/webapp
python -m venv .venv                       # Python version is pinned in ../.python-version
source .venv/bin/activate
pip install -r requirements-dev.txt        # requirements.txt plus local-only tools (PDF parsing)
brew install flyctl && flyctl auth login   # only for deploys and ops/sync_production.sh
```

Then bring the database over, preferably by copying it from the old laptop into
`webapp/db.sqlite3`. Make a consistent copy there first instead of copying the live file:

```bash
sqlite3 db.sqlite3 ".backup '/tmp/openanc-backup.sqlite3'"
```

If the old laptop is gone, dump production (it's Postgres, so there's no SQLite file) and
`loaddata` the dump into a fresh local database. You lose the audit history and import batches.

```bash
flyctl ssh console -a openanc -C "python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission" > prod.json
```

Finish with:

```bash
python manage.py migrate
python manage.py collectstatic --noinput   # tests fail with "Missing staticfiles manifest entry" without it
python manage.py test
python manage.py createsuperuser           # only if you rebuilt the database
python manage.py runserver                 # admin at http://localhost:8000/admin/
```

## Editing data in the admin

Edit `Person`, `CommissionerTerm`, `Candidate`, etc. in the local `/admin/`. Every save is
recorded in the audit trail; the **History** button on a change page shows it.

## Importing a spreadsheet of candidates

1. At `/admin/directory/person/`, click **Import candidates**.
2. Upload a CSV with `name` and `district` columns and pick the `Election` and default
   `CandidateStatus`.
3. On the review page, set each row to **Link**, **New**, **Pending** or **Skip**. Rows are
   pre-set from the fuzzy-match score; Pending rows need your decision.
4. **Save decisions** persists your choices without writing anything.
5. **Apply batch** creates the `Person` and `Candidate` rows in one transaction.
6. Check the district and candidate pages on `localhost`.

To turn DCBOE's "ANC Candidates in Ballot Order" or "General Election Write-in Candidates" PDF
into a CSV in `data/dcboe/excel-clean` (run from the repo root):

```bash
webapp/.venv/bin/python scripts/dcboe_pdf_to_csv.py links                      # current PDF URLs on dcboe.org
webapp/.venv/bin/python scripts/dcboe_pdf_to_csv.py write-in ~/Downloads/WRITE-IN.pdf
```

The output is named after the PDF's creation date unless you pass `-o`.

## Applying Suggestions

Public submissions land in `/admin/directory/suggestion/` as **General** suggestions. You can
also create one yourself.

1. Open the suggestion and set **Suggestion type**. The form shows the fields that type needs:
   - **New candidate declared**: District, Person name, Election year, Ballot/Write-in.
   - **Candidate withdrew**: Candidate.
   - **Commissioner resigned**: District, End date, Reason (optional).
   - **New commissioner appointed**: District, Person name, Start date (the end date is
     inferred from the rest of that cycle's commissioners).
   - **General**: free text; handle it by hand.
2. Set **Status** to **Approved** and save. Fields are only required once it's Approved.
3. In the suggestion list, select the row and run **Apply selected suggestions (structured types
   only)**. This is the step that writes the change. On success, **Applied at**, **Resulting
   person** and **Resulting district** fill in; on failure you get a per-row error and nothing
   changes.

The **By status** and **By approved but not applied** filters show the queue.

## Checking against the Office of ANCs

```bash
python manage.py check_oanc_commissioners                  # creates pending Suggestions for mismatches
python manage.py check_oanc_commissioners --anc 1A         # one ANC
python manage.py check_oanc_commissioners --dry-run        # preview, create nothing
python manage.py check_oanc_commissioners --force-refresh  # re-scrape even if today's cache exists
```

The first run each day caches the roster in `data/oanc/commissioners_<date>.csv`; later runs
that day read the cache. Review the resulting Suggestions as above.

## Drafting an Updates-page entry

```bash
python manage.py draft_site_update                      # since the last published update
python manage.py draft_site_update --since 2026-09-01   # or set the window explicitly
python manage.py draft_site_update --date 2026-09-27
```

This creates an unpublished `SiteUpdate` from the audit trail. Edit it at
`/admin/directory/siteupdate/` and check **Is published** to show it on `/updates/`.

## Importing election results

1. Save the DCBOE results CSV under `data/dcboe/election_results/` with the download date
   appended, e.g. `November_3_2026_General_Election_Election_Night_Unofficial_Results_2026-11-04.csv`.
2. Dry run and read the report:

   ```bash
   python manage.py import_election_results ../data/dcboe/election_results/<file>.csv \
       --year 2026 --status election_night --as-of 2026-11-04
   ```

   `--status` is `election_night`, `unofficial` or `certified`; winners are set only for
   `certified`.
3. Rerun with `--apply`, then push to production.

If a name doesn't resolve to exactly one candidate in that district, nothing is written and the
name is listed. Add the alias in the Person admin (or the missing Candidate) and rerun.

## Pushing changes to production

Run these yourself, from `webapp/`:

```bash
./ops/sync_production.sh status              # compare local vs production, no writes
./ops/sync_production.sh pull-suggestions    # pull new public submissions down for review
./ops/sync_production.sh push                # push local editorial data + reviewed suggestions
./ops/sync_production.sh push --prune        # also delete on production rows deleted locally
```

A typical session: `status`, `pull-suggestions`, make and verify edits locally, `status` again,
`push` (it shows row counts and asks y/N before writing), then spot-check
`https://openanc.org/`.

`status` prints one row per editorial table with local and production counts, the difference,
and a `Content` column:

| Content | Meaning |
|---|---|
| `match` | Same count and same content hash |
| `DIFFERS` | Same count, but at least one row's field values differ |
| `differs` | The counts differ (see the `Diff` column) |
| `unchecked` | Counts match but a hash is missing (production is on an older image; `flyctl deploy`) |
| `missing` | The table exists on only one side |

It then says `Local and production are IDENTICAL` or `DIFFER in N table(s)`, and for each
`DIFFERS` table lists which fields differ with local vs production values for up to 10 rows.
Timestamps are compared to the millisecond, since the push drops microseconds. `Suggestion` is
compared too, so new public submissions show as a difference until you `pull-suggestions`, and
unpushed reviews until you `push`.

If `status` or `push` fail on production with `ModuleNotFoundError` or "command not found", the
commands haven't been deployed yet: run `flyctl deploy` first.

## Deploying code changes

Production runs on several Fly machines sharing one Postgres database (`DATABASE_URL` secret);
migrations run once per deploy via `release_command` in `fly.toml`. Before deploying, check the
image:

```bash
docker build -t openanc-test .
docker run --rm openanc-test sh -c "python manage.py makemigrations --check --dry-run && python manage.py check && echo 'OK: image builds, no missing migrations, checks pass'"
```

It should end with `OK: image builds, no missing migrations, checks pass`. Then:

```bash
flyctl deploy --app openanc
```

## Running tests

```bash
python manage.py test
python manage.py test directory.tests.test_suggestion_apply                            # one file
python manage.py test directory.tests.test_suggestion_apply.ApplyNewCommissionerTests  # one case
```

## Reference: management commands

You only run `check_oanc_commissioners`, `draft_site_update` and `import_election_results`
directly; `ops/sync_production.sh` calls the rest.

| Command | Runs where | Purpose |
|---|---|---|
| `check_oanc_commissioners [--anc] [--dry-run] [--force-refresh]` | local | Compare against the official OANC roster; creates review Suggestions |
| `draft_site_update [--date] [--since]` | local | Draft an Updates-page entry from the audit trail |
| `import_election_results <csv> --year --status --as-of [--apply]` | local | Load a DCBOE results CSV (dry run unless `--apply`) |
| `backfill_person_aliases [--apply]` | local | Add aliases from spellings already in the database and DCBOE lists |
| `dump_editorial_data --output --manifest` | local | Export editorial data + PK manifest (used by `push`) |
| `load_editorial_data <path> [--prune-manifest] [--yes]` | production | Load an editorial fixture (used by `push`) |
| `dump_new_suggestions --since-id` | production | Serialize new public Suggestions (used by `pull-suggestions`) |
| `dump_reviewed_suggestions --output` | local | Export reviewed Suggestions to push back |
| `editorial_row_counts` | both | Print per-model row count + content hash (used by `status`) |
| `editorial_rows <Model>` | both | Print one model's rows as JSON, for `status`'s row-level diff |
| `max_suggestion_id` | local | Print the highest local Suggestion PK (used by `status`/`pull-suggestions`) |
| `import_legacy_data` | local | Full rebuild from the original CSV source data (disaster recovery only) |
