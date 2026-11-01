# Tally build plan

## Goal

A working app one person can start using today to log consumption or a habit and see trends. It also has to be a sound base for more users and a phone app.

**Definition of done for the demo:** a fresh checkout runs with one command, and each spec item below is covered by an automated check.

## Product spec

### What the clinical thinking changes

| Principle | What it means in the product |
|---|---|
| Self-monitoring is itself an intervention, but only if it's kept up | Logging takes one tap. Details are optional and offered after the log. |
| Shame drives under-reporting and dropping out, and a slip can turn into giving up (the abstinence violation effect) | Neutral wording, with no red, no scores and no streak that resets to zero. Trends show "days within your limit" and "longest stretch", which a slip can't erase. |
| Moderation and harm reduction are valid goals | Four goals: cut back, stop, stay within a limit, or just watch. |
| Getting through an urge is a skill worth noticing | "Had an urge, didn't use" is as easy to log as a use, and is counted separately. |
| Triggers and timing are what people can act on | Craving strength (0 to 10), trigger, and a day-by-time view. |
| Some withdrawal is dangerous | Alcohol and benzodiazepines warn about seizures, and opioids warn about lost tolerance, before the person commits to a goal. A support page is reachable without logging in. |
| The app isn't a clinician | No dosing advice. Limits are labelled as the user's own and not as safe levels. |

### Functional requirements

| ID | Requirement | Verified by |
|---|---|---|
| F1 | Track any number of substances or habits, with unit, default amount, goal and optional daily limit | `test_data.py`, e2e core loop |
| F2 | One-tap logging of a use or an urge, with undo | e2e core loop |
| F3 | Optional details: time, amount, craving, trigger, note. Edit or delete any entry later | `test_data.py`, e2e core loop and backdating |
| F4 | Today view: tally marks, total against limit, time since last use | e2e core loop |
| F5 | Trends over 7, 30, 90 or 365 days: daily chart, 7-day average, limit line, week-on-week change, days within goal, longest stretch, urges, craving, day-by-time grid, triggers, table view | `test_stats.py`, e2e core loop |
| F6 | History, filterable by tracker, with paging | `test_data.py`, e2e core loop |
| F7 | Hide or delete a tracker | `test_data.py`, e2e settings |
| F8 | Support page and safety notes | e2e logged-out and core loop |

### Correctness rules

- Calendar days are the device's local days, including 23- and 25-hour daylight saving days.
- Days before tracking began aren't counted as zero, because that would flatter early averages.
- Week-on-week compares finished days only, so a part-finished today can't look like an improvement.
- An entry stores its own amount, so changing a tracker's default later doesn't rewrite history.

### Privacy and security requirements

| ID | Requirement | Verified by |
|---|---|---|
| P1 | No email or real name needed | Registration schema |
| P2 | No third-party requests, including fonts, analytics and CDNs | e2e fails on any external request |
| P3 | Export everything, and permanently delete everything | `test_auth.py`, `test_data.py`, e2e |
| P4 | One user can't read or change another's data | `test_users_cannot_touch_each_others_data` |
| P5 | Argon2 passphrases, session tokens stored only as hashes, HttpOnly and SameSite=Strict cookies | `test_auth.py` |
| P6 | Login throttling, cross-site write refusal, strict CSP and no-store on API responses | `test_auth.py`; the e2e fails on any CSP violation |
| P7 | Spreadsheet formula injection neutralised in CSV | `test_export_csv_neutralises_spreadsheet_formulas` |
| P8 | Single-account signup by default | `test_first_mode_allows_only_one_account` |

**Known limit:** data isn't end-to-end encrypted. Fly encrypts volumes at rest, but whoever runs the server can read the database. Tally is also not a HIPAA-covered service. Both must be resolved or disclosed before hosting data for other people (see Phase 3).

### Non-functional requirements

Works at 360px wide, in light and dark, with WCAG 2.1 AA checks passing and reduced motion respected.

## Architecture

```
Browser (Vue 3, TypeScript, hand-written SVG charts, self-hosted font)
   |  same-origin JSON and a session cookie
FastAPI (app/routers, app/security, pure stats in app/stats.py)
   |  SQLAlchemy, Alembic migrations run at startup
SQLite in WAL mode, one file on one volume
```

| Decision | Why | Revisit when |
|---|---|---|
| SQLite on one machine | Simple, cheap and easy to back up, and enough for many users | Multiple machines are needed; move to Postgres (only `app/db.py` and the migrations are SQLite-aware) |
| Server computes stats | One tested implementation that a future phone app can reuse | Offline-first needs them on the device |
| Time zone sent with each request | Days follow the person, and storage stays plain UTC | Per-entry zones are wanted, so travel doesn't re-bucket old days |
| No chart library | Smaller dependency surface, and full control of accessibility and dark mode | Charts need zooming or similar |
| Web app first, installable to the home screen | One codebase gets onto a phone today | Reminders, widgets or offline logging are needed |

## Agentic build process

Each phase has one owner agent and a gate that must pass before the next one starts. `scripts/check.sh` runs all the automated gates. Agents work from this document, so it's updated first when scope changes.

| Phase | Output | Gate | Status |
|---|---|---|---|
| 0. Spec | This document | Each requirement names its check | Done |
| 1. Backend | Schema, migrations, auth, API, stats | `pytest` and `ruff` pass; migrations match models | Done |
| 2. Frontend | Today, Trends, History, Settings, Support | `vue-tsc` and `vitest` pass; palette validator passes in both modes | Done |
| 3. Integration | Browser tests against the built app | Playwright passes, including axe and overflow checks | Done |
| 4. Design review | Screenshots of each screen, phone and desktop, light and dark | Reviewed by eye and fixes applied | Done |
| 5. Independent review | A fresh agent with no build context reviews security and correctness | Confirmed findings fixed, with regression tests | Done |
| 6. Packaging | Dockerfile, `fly.toml`, scripts, README | Container builds and passes a smoke test | Done |

### Running this on later work

1. **Planner:** turns a request into requirement rows here, each naming its check.
2. **Builder:** writes the code and tests for one phase, in a git worktree if work is parallel.
3. **Reviewer:** a fresh agent given the code and not the builder's reasoning, so it isn't anchored.
4. **Gatekeeper:** runs `scripts/check.sh`. Nothing merges on a failure, and failures are fixed rather than skipped.
5. **Clinical check:** any change to safety wording or goals gets human review by a qualified clinician.

## Roadmap

### Phase 1: daily use (next)
- Reminders the user opts into
- Installable offline logging that queues when there's no signal
- Import from the JSON export
- Scheduled encrypted backups of the database
- A money or time saved figure

### Phase 2: phone
- Service worker and web push, then a Capacitor wrapper around the same Vue app if store presence matters
- App lock with a PIN or biometrics, and a discreet app name and icon
- Native quick log from a widget

### Phase 3: other people's data
Required before opening signup to the public:
- Decide on client-side encryption of notes and entries
- Privacy policy and legal review, covering the US state health-data laws (such as Washington's My Health My Data Act), GDPR, and whether HIPAA applies
- Clinician review of all safety wording, with crisis resources for each country served
- Rate limiting at the proxy, a third-party penetration test, and Postgres with point-in-time recovery if traffic requires it
- Account recovery that keeps the no-email option

### Phase 4: support features
- Clinician-shareable report that the user generates and controls
- If-then coping plans shown at high-risk times the data reveals
- Taper planning only with clinician involvement, never automated
