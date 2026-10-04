# OpenANC data admin guide

This is the operational guide for making data changes to OpenANC: adding/removing candidates,
recording commissioner changes, reviewing public suggestions, and getting those changes onto
the live site. It assumes you're working from a checkout of this repo with the local
Django app running (`python manage.py runserver`) and `/admin/` reachable at
`http://localhost:8000/admin/`.

## Setting up on a new machine

Everything is in git **except three things**, which you have to bring over yourself:

1. **`webapp/db.sqlite3`** (gitignored) — your local database. This is the editorial source of
   truth: it holds the audit-trail history, import batches, and reviewed suggestions, none of
   which exist in a fresh checkout or on production. Losing it means losing that history.
2. **`webapp/.venv`** (gitignored) — rebuilt from `requirements.txt`, see below.
3. **`flyctl` login** — authenticated per machine.

```bash
git clone git@github.com:devinbrady/openanc.git && cd openanc/webapp
python -m venv .venv                      # Python version is pinned in ../.python-version (3.10.3)
source .venv/bin/activate                  # the rest of this README assumes the venv is active
pip install -r requirements.txt
brew install flyctl && flyctl auth login   # only needed for deploys and ops/sync_production.sh
```

Then get the database over, in order of preference:

- **Copy it from the old laptop** (AirDrop, scp, or a cloud drive) into `webapp/db.sqlite3`.
  On the old laptop, make a consistent copy first rather than copying the live file:
  `sqlite3 db.sqlite3 ".backup '/tmp/openanc-backup.sqlite3'"`.
- **Or rebuild from production** if the old laptop is gone:
  dump production with `flyctl ssh console -a openanc -C "python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission" > prod.json` and `loaddata` it into a fresh local DB (production is Postgres, so there is no SQLite file to download). You get all editorial data
  and suggestions, but not the audit-trail history or import batches (those are local-only).

Finish with `python manage.py migrate`, `python manage.py collectstatic --noinput`,
`python manage.py test`, then
`python manage.py runserver` and open <http://localhost:8000/admin/>. Create a login
if you rebuilt from scratch: `python manage.py createsuperuser` (production accounts
are separate from local ones).

`collectstatic` is required because the static storage is WhiteNoise's manifest-based one
(gitignored `staticfiles/`); without it the admin-page tests fail with "Missing staticfiles
manifest entry".

**Only one machine should be the editing machine at a time.** The local database is
authoritative and the sync script pushes it over production by primary key, so two laptops with
diverging databases would overwrite each other's edits. Before switching laptops, `push` from
the old one, then copy the database across.

## The one rule everything else depends on

**All "editorial" data (People, CommissionerTerms, Candidates, Elections, SiteUpdates, etc.) is
created locally only, never directly in the production admin.** Production's only organic write
path is the public Suggestion form at `/suggest/` (or whatever it's routed as). This is what
makes the sync script safe: it can upsert by primary key in both directions without worrying
about the two databases inventing conflicting rows with the same ID.

In practice this means: **make every change on your local machine, verify it looks right on
`localhost`, then push it to production with the sync script.** Never edit `Person`,
`CommissionerTerm`, `Candidate`, etc. in `https://openanc.org/admin/` directly.

## The three ways data changes

1. **Direct edit in the local Django admin** — for one-off changes (renaming a councilmember,
   fixing a typo, tweaking a date). Fast, and automatically recorded in the audit trail.
2. **The candidate-import tool** — for bulk changes from a spreadsheet (e.g. a new list of
   declared candidates for an election).
3. **A structured Suggestion** — for changes that arrived as a public submission, or that you
   want to record with a specific "type" (new candidate, withdrawal, commissioner change) so the
   Updates-page generator can describe them automatically.

All three feed the same audit trail and the same sync process below.

## 1. Direct admin edits

Just edit the model in `/admin/` as normal (`Person`, `CommissionerTerm`, `Candidate`, etc.).
Every save is automatically recorded by `django-simple-history` — no extra step needed. You can
see the history of any tracked object via the "History" button on its admin change page.

Models with history tracking: `Person`, `CommissionerTerm`, `Candidate`, `ElectionResult`,
`SiteUpdate`, `WriteInWinner`. (`Ward`/`ANC`/`District`/`Election`/`CandidateStatus`/overlaps are
static/geographic and not tracked.)

## 2. Importing a spreadsheet of candidates

Use this when you have a CSV of names + districts (e.g. a new candidate filing list) and need to
figure out which names are already `Person` rows and which are new.

1. Go to `/admin/directory/person/` and click **Import candidates**.
2. Upload a CSV with `name` and `district` columns, pick the `Election` it's for, and pick the
   default `CandidateStatus` to apply (defaults to "Declared Intention to Run").
3. You're taken to a review page, one row per spreadsheet row. Each row shows the top fuzzy-name
   matches against existing `Person` records with a confidence score, and a pre-selected decision:
   - **Link** — high-confidence match to an existing person (score ≥ 95). Pre-selected automatically.
   - **New** — no decent match found (score < 70). Pre-selected automatically.
   - **Pending** — a middle-confidence match (70–95). You have to decide by hand: either pick
     "Link" and choose the right person from the dropdown, or "New" to create a fresh `Person`.
   - **Skip** — don't do anything with this row (e.g. a duplicate line, a name you don't
     recognize enough to trust either way).
4. Click **Save decisions** as often as you like while reviewing — it just persists your choices,
   nothing is written to `Person`/`Candidate` yet.
5. When every row's decision looks right, click **Apply batch**. This creates the new `Person`
   rows, links the existing ones, and creates a `Candidate` row for each — all inside one
   transaction, so a bad row won't leave things half-applied.
6. Check the result on `localhost` (the relevant district/candidate pages) before moving on to
   the sync step below.

## 3. Structured Suggestions

Every submission from the public "suggest an edit" form lands in `/admin/directory/suggestion/`
as a `general` (free-text) suggestion. You can also create a `Suggestion` yourself in the admin
to represent a change you want the audit trail / Updates generator to describe precisely.

To apply one automatically:

1. Open the suggestion in the admin.
2. Set **Suggestion type**. The form shows only the fields that type needs (and marks them with
   a red `*`) — there's no JSON to hand-edit:
   - **New candidate declared** — District, Person name, Election year, Ballot/Write-in (defaults to ballot).
   - **Candidate withdrew** — Candidate (autocomplete).
   - **Commissioner resigned** — District, End date, Reason (optional).
   - **New commissioner appointed** — District, Person name, Start date. The term's end date is
     inferred automatically — whatever end date the rest of that election cycle's commissioners share.
   - **General edit / suggestion (free text)** — no automatic apply; handle it by hand as before.
3. Save. Fields are only required once **Status** is set to **Approved** — saving a suggestion
   as Pending or Rejected never requires them, even if a structured type is selected.
4. **Setting Status to Approved does not apply the change** — that field only records your review
   decision. Go back to the suggestion list, select the row, and run the **"Apply selected
   suggestions (structured types only)"** admin action — that's the step that actually writes to
   `CommissionerTerm`/`Candidate`/etc. Use the **"By approved but not applied"** filter in the
   sidebar to catch anything you approved but forgot to apply.
5. If applying succeeds, the suggestion's **Applied at** / **Resulting person** / **Resulting
   district** fields fill in. If something's wrong (bad reference, a conflicting existing
   record), you'll get a red error message per row and *nothing* about that suggestion changes —
   fix the fields and try again.
6. Person name fields reuse the same fuzzy-matching as the import tool: a high-confidence match
   links to the existing person automatically, otherwise a new `Person` is created.

The suggestion list's **By status** filter shows a count next to each option (Pending review,
Approved, Rejected) so you can see the queue size at a glance.

## 4. Checking against the Office of ANCs

A regular task: compare the official commissioner roster (scraped from each ANC's page on
`oanc.dc.gov`) against our own data, and flag anything that disagrees.

```bash
python manage.py check_oanc_commissioners
```

For each district where the two disagree, it creates a `pending` Suggestion instead of changing
anything directly:

- We show a seat vacant, OANC shows a name → **New commissioner appointed** suggestion.
- We show someone serving, OANC shows the seat vacant → **Commissioner resigned** suggestion.
- Both show a different name that isn't obviously the same person → both of the above together
  (a resignation and an appointment are two separate actions), cross-referenced so you review
  them as a pair.
- Both show the same name but spelled/capitalized/accented differently (e.g. "López" vs
  "Lopez") → a **General** suggestion, since that's the same person — whether to update the
  stored spelling is an editorial call, not something this command decides.

Review and apply them the same way as any other suggestion (section 3). Add `--anc 1A` to check
just one ANC, or `--dry-run` to preview without creating anything.

**Rate limiting**: this only ever scrapes `oanc.dc.gov` once per calendar day — the first run
each day saves the results to `data/oanc/commissioners_<date>.csv` (same format the old
notebook-based pipeline used), and every run after that the same day reads that file back
instead of hitting the site again. This data doesn't change quickly, and there's no reason to
hammer a public government site. Pass `--force-refresh` to re-scrape anyway.

## 5. Drafting an Updates-page entry

After making changes (by any of the methods above), generate a draft summary for the public
Updates page:

```bash
python manage.py draft_site_update
```

This mines the audit trail since the last *published* update (or pass `--since 2026-09-01` /
`--date 2026-09-27` to control the window explicitly) and creates one **unpublished**
`SiteUpdate` describing commissioner term changes, new/withdrawn candidates, and new people. Go
to `/admin/directory/siteupdate/`, open the draft, tidy the wording, and check **Is published**
when it's ready to appear on the live `/updates/` page.

Note: the first time you run this after a large one-time data load (a full CSV re-import, a big
batch import, etc.), the draft will be noisy/oversized since it's summarizing everything since
the last published update. That's expected — just trim it, or publish something first to reset
the window before drafting again.

## 6. Pushing changes to production

Once you've verified everything on `localhost`, use `ops/sync_production.sh` from the `webapp/`
directory. **Run this yourself from your own terminal** — it writes to production, so it's
intentionally not something to automate or hand off.

```bash
./ops/sync_production.sh status              # dry-run: compare local vs production, no writes
./ops/sync_production.sh pull-suggestions     # pull new public submissions down for review
./ops/sync_production.sh push                 # push local editorial data + reviewed suggestions up
./ops/sync_production.sh push --prune         # also delete on production any rows you deleted locally
```

Typical session:

1. `status` — confirms local/production agree before you start (if they don't, figure out why
   before pushing). See "Reading `status`" below.
2. `pull-suggestions` — brings down anything the public submitted since your last pull. Review/
   classify them locally (section 3 above).
3. Make your edits locally (sections 1–3), verify on `localhost`.
4. `status` again — sanity check the diff looks like what you expect.
5. `push` — dumps local editorial data + your reviewed suggestions, copies them to production via
   `flyctl ssh sftp`, and loads them there. It asks for a y/N confirmation and shows you row
   counts before writing anything. Use `--prune` only when you've actually deleted rows locally
   and want that deletion to also happen on production (plain `push` never deletes on
   production, only inserts/updates).
6. Spot-check `https://openanc.org/` afterward.

**Reading `status`.** It prints one row per editorial table with the local and production row
counts side by side, the difference, and a `Content` column:

| Content | Meaning |
|---|---|
| `match` | Same count and same content hash |
| `DIFFERS` | Same count, but at least one row's field values differ |
| `differs` | The counts already differ (see the `Diff` column) |
| `unchecked` | Counts match but a hash is missing (production is on an older image; `flyctl deploy`) |
| `missing` | The table exists on only one side |

Below the table it states either `Local and production are IDENTICAL` (every table matches on
count and content) or `DIFFER in N table(s)` with a line per table, such as "local has 3 more
rows than production". For a `DIFFERS` table it also fetches both copies and lists how many rows
differ, which fields differ, and local vs production values for the first 10 rows. The hash covers
every field of every row, so it catches edits that leave the count unchanged. Timestamps are
compared to the millisecond, because the JSON push drops microseconds. `Suggestion` is
compared too, even though it syncs through its own flow, so a new public submission on production
shows up as a difference until you `pull-suggestions`, and reviews you haven't pushed yet show up
until you `push`. `status` ends with the local Suggestion high-water mark.

**If `status` or `push` fail with something like `ModuleNotFoundError` or "command not found" on
production**, the new management commands haven't been deployed yet — run `flyctl deploy` first
(code-only deploys ship instantly; the sync script can only call commands that already exist in
the deployed image).

## 7. Deploying code changes

Production runs on several Fly machines sharing one Postgres database (`DATABASE_URL`, a Fly
secret). Local development still uses SQLite. Migrations run once per deploy via the
`release_command` in `fly.toml`, not at container start.

Whenever you change Python/template/static code (not just data), before `flyctl deploy`:

```bash
docker build -t openanc-test .
docker run --rm openanc-test sh -c "python manage.py migrate --check && python manage.py check"
```

This catches dependency/migration problems in the exact environment Fly runs, before they hit
production. Then:

```bash
flyctl deploy --app openanc
```

## Running tests

Before pushing any change to production, run the test suite locally:

```bash
python manage.py test
```

Run a single file or case while iterating on one area, e.g.:

```bash
python manage.py test directory.tests.test_suggestion_apply
python manage.py test directory.tests.test_suggestion_apply.ApplyNewCommissionerTests
```

If you add a new management command, model behavior, or admin view, add a test for it under
`directory/tests/` — that's where the existing coverage for matching, imports, suggestion
apply, and the audit-trail draft generator all live.

## Reference: management commands

| Command | Runs where | Purpose |
|---|---|---|
| `check_oanc_commissioners [--anc] [--dry-run] [--force-refresh]` | local | Compare against the official OANC roster; creates review Suggestions |
| `draft_site_update [--date] [--since]` | local | Draft an Updates-page entry from the audit trail |
| `dump_editorial_data --output --manifest` | local | Export editorial data + PK manifest (used by `push`) |
| `load_editorial_data <path> [--prune-manifest] [--yes]` | production | Load an editorial fixture (used by `push`) |
| `dump_new_suggestions --since-id` | production | Serialize new public Suggestions (used by `pull-suggestions`) |
| `dump_reviewed_suggestions --output` | local | Export reviewed Suggestions to push back |
| `editorial_row_counts` | both | Print per-model row count + content hash (used by `status`) |
| `editorial_rows <Model>` | both | Print one model's rows as JSON, for `status`'s row-level diff |
| `max_suggestion_id` | local | Print the highest local Suggestion PK (used by `status`/`pull-suggestions`) |
| `import_legacy_data` | local | Full rebuild from the original CSV source data (disaster recovery only) |

You should never need to run any of these directly except `check_oanc_commissioners` and
`draft_site_update` — the others are called by `ops/sync_production.sh`.
