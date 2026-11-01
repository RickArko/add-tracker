# Habit Helper

Private, simple tracking for substance use and habits you want to change. Log with one tap, note urges you got through, and see the pattern over time.

Habit Helper is a personal log. It doesn't diagnose, treat or give dosing advice.

## Run it

You need [uv](https://docs.astral.sh/uv/) and Node 24 on Linux, WSL or macOS (Apple silicon included).

```bash
scripts/dev.sh    # your real tracker at http://127.0.0.1:8000, data in data/tally.db
scripts/demo.sh   # a throwaway copy with 60 days of made-up data at http://127.0.0.1:8001
                  # log in as demo / demo-passphrase
```

The first account created on a fresh database is the only one allowed, unless you change `TALLY_SIGNUP`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `TALLY_DB_PATH` | `data/tally.db` | Where the SQLite file lives |
| `TALLY_SIGNUP` | `first` | `first` allows one account, `open` allows anyone, `closed` allows no one |
| `TALLY_SECURE_COOKIES` | `0` | Set to `1` whenever the app is served over HTTPS |
| `TALLY_SESSION_DAYS` | `30` | How long a login lasts |

## Back up and recover

- **Back up:** Settings has CSV and JSON downloads. For a full copy, run `uv run python -m app.cli backup backup.db`.
- **Import:** there's no way to load an export back in yet, so a `.backup` copy is what you'd restore from.
- **Forgotten passphrase:** there's no email reset. Whoever runs the server can use `uv run python -m app.cli reset-password <username>`. On Fly, open `fly ssh console`, then run `cd /srv && .venv/bin/python -m app.cli <command>`. Files you back up there can be fetched with `fly ssh sftp get`.

## Deploy to Fly

Needed to use Habit Helper from your phone. Create your account right after the first deploy, because until then anyone who finds the URL could claim the single account.

```bash
fly launch --no-deploy --copy-config    # choose a unique app name
fly volumes create habit_helper_data --size 1 --region iad
fly deploy
```

Fly needs exactly one machine, because SQLite and the login throttle live on that machine. If `fly launch` or `fly deploy` created a second one, run `fly scale count 1`.

## Test

`scripts/check.sh` runs linting, type checks, unit and API tests, and browser tests. Browser tests need `npx playwright install chromium` once, run inside `frontend/`.

See [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) for the product spec, architecture and roadmap.
