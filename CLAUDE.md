# OpenANC

The live site is the Django app in `webapp/` (deployed to Fly.io as app `openanc`). The rest of the
repo (`scripts/`, `build_site.py`, `docs/`, `data/`) is the older static-site pipeline plus the
source data files the Django app is seeded from. Operational details live in `webapp/README.md`;
read it before touching data or deploys.

## Working in `webapp/`

- Python deps are only installed in the venv: use `.venv/bin/python manage.py ...`, not bare `python`.
- Run the suite with `.venv/bin/python manage.py test` (all of it should pass before committing).
- New machine setup is in `webapp/README.md` ("Setting up on a new machine").
- `db.sqlite3` is gitignored and is the editorial source of truth (audit history, import batches,
  reviewed suggestions live only there). Never delete or overwrite it.
- Admin pages require login, so verify admin changes with tests or the shell, not the browser.
- Django template literal text is not HTML-escaped; template variables are.

## Standing rules

- **Editorial data (Person, CommissionerTerm, Candidate, Election, etc.) is created and edited
  locally only**, then pushed with `webapp/ops/sync_production.sh`. Production's only organic
  write path is the public Suggestion form.
- **The user runs anything that touches production** (`flyctl deploy`, `flyctl ssh`,
  `sync_production.sh`). Write the commands and explain them; don't execute them.
- **Only commit when the user says so** ("commit this"). Don't push either unless asked.
- Don't re-run `scripts/import_legacy_data.py` wholesale: it `update_or_create`s from CSVs and
  could overwrite current commissioner data. `data/ancs.csv` is its source for ANC fields.
- `check_oanc_commissioners` scrapes each `ANC.dc_oanc_link` page; some ANCs host their own
  site (e.g. ANC 3C at anc3c.dc.gov). Its daily cache CSVs in `data/oanc/` are tracked in git.
- Prefer one bulk query plus grouping over per-district queries; list pages cover 345 districts.
