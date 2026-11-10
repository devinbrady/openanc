# OpenANC maintainer guidelines

The reasoning behind how OpenANC data is maintained: the rules the workflow depends on, and how
to make the judgment calls the commands leave to you. For the commands themselves, see
[README.md](README.md).

## Editorial data is edited locally only

**All editorial data (People, CommissionerTerms, Candidates, Elections, SiteUpdates, etc.) is
created locally, never directly in the production admin.** Production's only organic write path
is the public Suggestion form. This is what makes the sync script safe: it upserts by primary key
in both directions, and that only works if the two databases never invent conflicting rows with
the same ID.

So: make every change on your local machine, verify it on `localhost`, then push it with
`ops/sync_production.sh`. Never edit `Person`, `CommissionerTerm`, `Candidate`, etc. in
`https://openanc.org/admin/`.

The sync script writes to production, so run it yourself from your own terminal. It's
intentionally not something to automate or hand off.

## The local database is the source of truth

`webapp/db.sqlite3` holds the audit-trail history, import batches, and reviewed suggestions, none
of which exist in a fresh checkout or on production. Losing it means losing that history; a
rebuild from a production dump recovers the editorial data and suggestions but not those.

**Only one machine should be the editing machine at a time.** The sync script pushes the local
database over production by primary key, so two laptops with diverging databases would overwrite
each other's edits. Before switching laptops, `push` from the old one, then copy the database
across.

## Choosing how to make a change

There are three ways data changes, and all three feed the same audit trail and sync process:

1. **Direct edit in the local admin** — for one-off changes (renaming a councilmember, fixing a
   typo, tweaking a date). Fast, and recorded automatically.
2. **The candidate-import tool** — for bulk changes from a spreadsheet, such as a new list of
   declared candidates.
3. **A structured Suggestion** — for changes that arrived as a public submission, or that you
   want recorded with a specific type (new candidate, withdrawal, commissioner change) so the
   Updates-page generator can describe them precisely.

History is tracked for `Person`, `CommissionerTerm`, `Candidate`, `ElectionResult`, `SiteUpdate`
and `WriteInWinner`. `Ward`/`ANC`/`District`/`Election`/`CandidateStatus`/overlaps are static or
geographic and not tracked.

## Matching names to existing people

The import tool and structured Suggestions both fuzzy-match names against existing `Person`
rows. A score of 95 or more links automatically; under 70 creates a new person. In between, the
row is **Pending** and the call is yours:

- **Link** when it's the same person, and pick them from the dropdown.
- **New** when it's a different person who happens to have a similar name.
- **Skip** for duplicate lines or names you can't place confidently either way.

DCBOE ballot spellings often differ from how a person is stored (e.g. "Zach Adams" for Zachary
Adams). Record those as person aliases rather than renaming the person, so results and candidate
lists keep resolving to them.

## Reviewing OANC mismatches

`check_oanc_commissioners` never changes data; for each district where OANC and OpenANC disagree
it creates a pending Suggestion:

- We show a seat vacant, OANC shows a name → **New commissioner appointed**.
- We show someone serving, OANC shows the seat vacant → **Commissioner resigned**.
- Different names that aren't obviously the same person → both of the above, cross-referenced so
  you review them as a pair (a resignation and an appointment are two separate actions).
- Same name spelled, capitalized or accented differently (e.g. "López" vs "Lopez") → a
  **General** suggestion. It's the same person; whether to change the stored spelling is an
  editorial call.

The command only scrapes `oanc.dc.gov` once per calendar day and caches the results in
`data/oanc/`. The roster doesn't change quickly, and there's no reason to hammer a public
government site; use `--force-refresh` only when you know something changed today.

## Approving vs applying Suggestions

Setting a Suggestion's status to **Approved** only records your review decision. Nothing changes
until you run the **Apply selected suggestions** action. Keeping the two separate lets you review
a batch first and apply it once. Use the **By approved but not applied** filter to catch anything
you approved but forgot to apply.

An apply is all-or-nothing per suggestion: if a reference is bad or a record conflicts, nothing
about that suggestion changes, so fix the fields and try again.

## Writing Updates-page entries

`draft_site_update` produces a draft, not a finished entry. Tidy the wording before publishing.
After a large one-time data load
the draft will be oversized, because it summarizes everything since the last published update;
trim it, or publish something first to reset the window.

## Election results

DCBOE reuses filenames as it republishes results, so save each download with its date appended
to keep every version. Always read the dry-run report (vote changes, leader changes, contests
without a first-choice majority) before applying.

Winners are only marked from certified results; until then the site shows the first-ranked
candidate as "Leading". 2026 uses ranked choice voting, and the imported totals are first-choice
votes; round-by-round tabulation isn't imported yet.

## Pushing to production

- Run `status` before you start. If local and production disagree and you don't know why, find
  out before pushing; a push would overwrite whatever production has.
- Use `push --prune` only when you've actually deleted rows locally and want them gone on
  production too. Plain `push` never deletes.
- Spot-check `https://openanc.org/` afterward.

## Code changes and tests

Run the test suite before any deploy or push. New features and bug fixes start with a failing
test; tests live under `directory/tests/`, alongside the existing coverage for matching, imports,
suggestion apply and the Updates-page generator.

Build and check the Docker image before `flyctl deploy`. It catches dependency and migration
problems in the exact environment Fly runs, before they reach production.
