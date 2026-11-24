# CoChess v4 — Implementation Plan (M0)

Status: **M0, M1 and M2 approved by the owner (2026-11-23 to 2026-11-24); M3 in progress.** Sources: `SPEC_V4.md`, `docs/v3-as-built.md`, the code on branch `v4` (main `7bd264e` + the spec commits), `llm_usage` from the deployed server (pasted by the owner on 2026-11-23), the stored real engine runs in `backend/tests/fixtures/engine/`, and the official pricing pages of Anthropic and Stripe (read 2026-11-23).

## Context

v3 is deployed on the owner's EC2 instance (`https://3-15-12-174.sslip.io`, Docker Compose + Caddy, SQLite) and merged into `main`. SPEC_V4 §3 asks M0 for: an as-built check, the real cost per task and per game, the engine-time baseline, the remaining decisions, and this plan.

## 1. As-built check

`docs/v3-as-built.md` is current. The only commits after it on `main` are docs (`7bd264e`: deploy and approval); `f8c9284` ("Analyze my latest game") updated it itself. Points found while planning that the spec relies on:

- **Coach metering hooks exist.** Every coach call already writes `llm_usage` with input, output, cache-read and cache-write tokens (`db/coach.py::record_usage`). The v3 budget check `api/budget.py::check_token_budget` is already a dependency on every coach route (`api/coach.py`, `api/moments.py`, `api/onboarding.py`, `api/walkthrough.py`), so the credit check replaces it in the same places.
- **Prompt caching is on** (`coach/client.py`, 5-minute `ephemeral` breakpoints).
- **The import cooldown lives in memory** (`api/imports.py::_cool_down`, `app.state.import_times`).
- **Postgres risks:** SQLite here doesn't enforce foreign keys (no `PRAGMA foreign_keys`) or `String(n)` lengths, and Postgres enforces both, so the server's data may hold orphan rows or over-long strings. Migrations use `batch_alter_table` (portable) and three raw `UPDATE` statements in `0003`/`0004` (standard SQL). `db/session.py::make_engine` already handles non-SQLite URLs.
- **No CI.** Tests run locally only; "tests on both databases" (SPEC_V4 §12.1) means a local Postgres (Docker) for the second run, plus CI if the owner wants it (adjustment 6).
- Baseline checks on `v4`: see §8.

## 2. Cost report (SPEC_V4 §3.2)

Official prices per million tokens (platform.claude.com pricing page, 2026-11-23):

| Model | Input | Output | Cache write (5 min) | Cache read |
|---|---|---|---|---|
| Haiku 5.5 (prompts up to 100k tokens) | $0.10 | $0.50 | $0.125 | $0.01 |
| Sonnet 5.5 | $2 | $10 | $2.50 | $0.10 |
| Opus 5.5 | $4 | $20 | $5 | $0.20 |

The server's `llm_usage` (60 calls, 8 games, all players), priced:

| Task | Model | Calls | Cost | Per call | If one model up |
|---|---|---|---|---|---|
| synopsis | Sonnet | 8 | $0.167 | $0.0208 | Opus: $0.0416 |
| chat | Haiku | 11 | $0.015 | $0.0013 | Sonnet: $0.0261 |
| moment intro | Haiku | 15 | $0.017 | $0.0012 | Sonnet: $0.0231 |
| moment feedback | Haiku | 22 | $0.018 | $0.0008 | Sonnet: $0.0162 |
| walkthrough | Haiku | 4 | $0.005 | $0.0011 | Sonnet: $0.0226 |
| **all** | | 60 | **$0.221** | | |

**A typical game** (synopsis, 3 chat questions, 2.5 moment intros and 4.4 moment replies as players actually use them, 1 walkthrough):

- **Standard: $0.033 (3.3 credits).** The Sonnet synopsis is two-thirds of it; Haiku 5.5 is so cheap that everything else is about a cent.
- **Deep as specced (Opus synopsis, Sonnet for the rest): $0.27 (27 credits), about 8× Standard**, not the 4× SPEC_V4 §7 assumed.

What the approved amounts buy:

| | Standard | Deep as specced |
|---|---|---|
| 50-credit trial | about 15 games | about 2 games |
| 300-credit monthly allowance | about 90 games | about 11 games |
| 150-credit top-up | about 45 games | about 6 games |

Stripe per sale (stripe.com, 2026-11-23): cards 2.9% + 30¢, Billing 0.7% of subscription volume.

| | Price | Stripe | API cost if every credit is used | Left before tax and hosting |
|---|---|---|---|---|
| Monthly | $10 | $0.66 | $3.00 | $6.34 |
| Top-up | $5 | $0.45 | $1.50 | $3.05 |

The amounts hold up: even a player who uses every credit leaves about 63% of the subscription. The decision is the Deep tier (adjustment 1).

## 3. Engine baseline (SPEC_V4 §3.3, §8)

From the stored real runs of the owner's games (multi-threaded lite build, scan tier then verify tier):

| Game | Plies | Scan | Verify (positions) | Total |
|---|---|---|---|---|
| game1w | 126 | 26.7 s | 53.5 s (18) | 80 s |
| game3w | 181 | 44.6 s | 55.9 s (21) | 100 s |
| game4w | 144 | 35.0 s | 34.5 s (12) | 70 s |
| game5b | 74 | 18.4 s | 21.3 s (8) | 40 s |
| game2b | 18 | 5.0 s | 17.7 s (6) | 23 s |

What it shows:
- **Scan waits for time, not depth.** Every scan search runs about 250 ms (the `min_time_ms` floor) and reaches depth 16 to 19 (median), while the tier only needs depth 12. Stopping at depth should cut the scan by well over half on its own.
- **Verify is the bigger half and is capped, not finished.** About 80% of verify searches hit the 3-second cap without reaching depth 18, because each asks for 4 lines (`multipv=4`). Fewer lines, fewer positions, or a lower depth is where most of the time is.
- A 40-move game (80 plies) takes about 45 seconds today; the target is 15 seconds (SPEC_V4 §8.1).

M3 re-measures on the owner's laptop with `npm run e2e:real` (scan and verify time per game), since these runs were recorded at earlier milestones.

## 4. What the outside services need (SPEC_V4 §15 D10)

- **Google sign-in:** while the app is in Google's **Testing** mode it works for up to 100 listed test users without verification, so M2 can be built and tested on staging before the domain exists. Going public with Sign in with Google needs **brand verification**, which verifies ownership of the domain (its "top private domain") in Google Search Console and needs a homepage and privacy policy on that domain. That can't be done for `sslip.io`, which the owner doesn't control. **A domain is needed before launch, not before M2 starts.**
- **Amazon SES:** sending needs a verified domain identity (Easy DKIM records in the domain's DNS); new accounts start in the sandbox (verified recipients only, 200 messages a day, 1 a second), and production access is a per-region request describing the mail and how bounces are handled. $0.10 per 1,000 emails. **Real acceptance emails need the domain.** The sandbox is enough to build and test M2 with the owner's own verified address.
- **Stripe:** asks for a business website showing what's sold, prices, terms, privacy and a refund policy when the account is activated for live payments. Test mode works without it, so M4 can be built first; live mode (M9) needs the domain and the M7 pages.
- **RDS:** the smallest Graviton instance (`db.t4g.micro`, single-AZ) is about $12 a month on demand in Ohio (us-east-2, where the instance's 3.15.x address points), plus about $2–3 for 20 GB of gp3 storage; backups up to the database size are free. **About $15 a month.** Confirm in the AWS pricing calculator for the instance's actual region before creating it.

## 5. Adjustments to SPEC_V4 (for owner approval at M0)

1. **Deep coach tier (decision needed).** As specced it costs 8× Standard, so a subscriber gets about 11 Deep games a month. Options:
   - **(a) Keep it** (Opus synopsis, Sonnet everything else): the most in-depth, 27 credits a game; the UI says "about 8× faster".
   - **(b) Deep synopsis only** (Opus synopsis, Haiku for the rest): about 5 credits a game (1.6×), still a stronger written review.
   - **(c) Middle** (Opus synopsis and baseline, Sonnet chat, Haiku moments and walkthroughs): about 12 credits a game (3.5×).
   - Recommendation: **(c)**. The synopsis and chat are where a stronger model shows most, and it keeps Deep usable on the allowance (about 25 games a month). Either way the per-task tier config makes this a config change, and §7's "about 4× faster" text becomes the measured figure.
2. **Credits per game in the UI** use the measured averages above (Standard about 3, Deep per the chosen option) and are recomputed from `llm_usage` by the cost report, not hard-coded.
3. **Payment provider for later international sales:** Stripe now offers **Managed Payments**, its own merchant of record (tax, VAT, disputes in 75+ countries) for software subscriptions, at 3.5% on top of the normal card fees. Staying on Stripe and turning it on later is a smaller move than switching to Paddle (no new integration, no subscriber migration). Record it in §6 as the first option to consider when going international; Paddle stays the alternative.
4. **The domain gates launch, not M2.** M2 is built with Google in Testing mode and SES in the sandbox on staging; the domain must be bought, verified in Google and SES, and moved to before M8 ends. §12.2 and the M2 checkpoint ("acceptance email in a real inbox") are reworded so the inbox check uses the owner's verified address until the domain is ready.
5. **Postgres data checks before the move.** `migrate-sqlite` first reports orphan rows (foreign keys SQLite never enforced) and strings longer than their column, and the owner decides what to do with each before anything is copied. Turn on `PRAGMA foreign_keys=ON` for SQLite in M1, so dev and tests catch the same errors Postgres will.
6. **CI (optional, owner's call):** a GitHub Actions workflow running the backend tests on SQLite and Postgres, the frontend tests, lint and type checks on every push. Not in the spec; free for this repo's size. Recommended, since "tests on both databases" is easy to skip locally.
7. **Engine verify settings are part of M3's quality test:** the verify tier's `multipv`, depth and cap change only together with the regression comparison against the stored v3 results (§8.1), and the chosen values are recorded in this log.

## 6. Dependencies (SPEC_V4 §14.4, owner approval needed)

| Package | For | Notes |
|---|---|---|
| `psycopg[binary]` 3 | Postgres driver (M1) | The SQLAlchemy 2 default for `postgresql+psycopg://` |
| `stripe` | Checkout, Portal, webhook signatures, cancel from the owner dashboard (M4, M5) | Stripe's official SDK |
| `google-auth` | Verifying Google ID tokens against Google's keys (M2) | Google's official library; small. The code exchange itself uses `httpx` (already a dependency) |
| none for email | SES through `smtplib` | standard library |
| Docker `postgres` image | local and CI test database (M1) | dev tooling only, not shipped |

`authlib` (the alternative for Google) is a bigger framework than needed; `google-auth` plus `httpx` keeps the OIDC flow small and readable.

## 7. M1–M9 implementation plan

**M1 — Postgres.**
- `psycopg` in `backend/pyproject.toml`; `DATABASE_URL=postgresql+psycopg://...`; `make_engine` sets a connection pool and `pool_pre_ping`.
- SQLite connections turn on foreign keys (adjustment 5); fix whatever existing tests then catch.
- `tests/conftest.py` runs the suite against `TEST_DATABASE_URL` when set (a throwaway Postgres in Docker), SQLite otherwise; `alembic upgrade head` and `downgrade` checked on both.
- `app.cli migrate-sqlite --from --to [--check-only]`: pre-checks (orphans, lengths), copies table by table in dependency order, fixes sequences, compares row counts and a checksum per table.
- `docs/DEPLOY.md`: creating the RDS instance (security group from the EC2 instance only, TLS, backups, deletion protection), the switch-over steps, rollback (keep the SQLite file, point `DATABASE_URL` back).
- Checkpoint: both suites green; a copy of the server database checked and moved to a local Postgres, with the comparison.

**M2 — Google sign-in, waitlist, email.**
- `auth/google.py`: start, callback (code exchange over `httpx`, ID-token check with `google-auth`), PKCE, `oauth_states`.
- Migration: `users` gains email, `google_sub`, status, role, age band, timestamps; `terms_acceptances`.
- Status gate in `get_current_user` (waitlisted and suspended users reach only their status page, export and deletion).
- The age check page, the waitlist page, Connect Google on the Profile page, `AUTH__INVITES_CREATE_USERS`.
- `app/email/`: outbox table, sender loop started in the app lifespan, SMTP transport, a fake transport for tests, templates for `waitlist_joined`, `accepted`, `access_paused` and `access_restored`.
- CLI: `admit`, `suspend`, `restore`, `set-role`.
- Checkpoint as in SPEC_V4 §13, with adjustment 4.

**M3 — Credits, coach strength, faster analysis.**
- Credits: `PricingSettings` (the table in §2), `cost_microusd` and `tier` on `llm_usage` (a backfill CLI prices old rows once), `credit_ledger` and `credit_balances`, the trial on acceptance, `require_credit` replacing `check_token_budget` on the four route modules, the charge in `record_usage`, warnings, the daily cap, `grant-credits`, `unmetered`, `GET /api/billing` (balance and history only), the credits banner and the chat-input note.
- Coach strength: `CoachTier` per task in config, `coach_strength` setting, the walkthrough cache keyed by tier, the Profile choice with measured credits per game.
- Engine (SPEC_V4 §8): a quality regression harness first (replays the stored v3 results through classification and moment selection, so each engine change is compared before it's kept); then depth-based scan; the worker pool (`engine/pool.ts`, single-threaded workers, `ENGINE__POOL_SIZE` through `/api/engine-config`); backwards runs; forced-move skips (backend fills them from the next position); verify tuning (adjustment 7); the background import queue that survives navigation and reloads, and opening each game after its scan. `npm run e2e:real` reports scan and verify time per game.
- Checkpoint as in SPEC_V4 §13.

**M4 — Stripe.** `billing/provider.py` (`BillingProvider`), `billing/stripe_provider.py`; checkout, portal, webhook route with signature check on the raw body, `billing_events`, the ledger entries per event, the billing page and the checkout return page; Stripe test mode and the Stripe CLI for local webhooks; a test clock run for the checkpoint.

**M5 — Owner dashboard.** `/api/admin/*` behind a `require_owner` dependency (404 for others); `admin_actions`; overview queries over `users`, `billing_events`, `llm_usage`; the users table (server-side search, filters, pages); the waitlist tab; the user page; the actions; the 10,000-user performance test; `/owner` pages using the v3 design tokens and Recharts.

**M6 — Cost controls.** Measure the cache-read share per task from `llm_usage`; reorder payloads (stable blocks first); trim payload fields the prompts don't use; compare the 3 owner games before and after.

**M7 — Accounts and legal.** `/terms` and `/privacy` pages from owner-supplied text, versioned consent; export zip; deletion with anonymized money and audit rows; the remaining emails (`credits_low`, `credits_out`, `credits_added`, `account_deleted`, `terms_updated`), email preferences and the signed unsubscribe link.

**M8 — Production hardening.** Staging as a second Compose project on the instance; the domain moved to (Caddy, Google, SES, Stripe); RDS in production; SES production access; `rate_limits` table and limits; `/api/health`; JSON logs and the CloudWatch agent; alarms; the restore drill; `docs/DEPLOY.md` for v4.

**M9 — Harden and launch.** Playwright flows for the new features (Google, Stripe and email faked); a security review of auth, billing, owner routes and deletion; a load test; Stripe live mode; the production move of the v3 data; final review.

## 8. Verification

Per milestone: `uv run pytest` on SQLite and on Postgres (from M1), `ruff`, `mypy app`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run e2e`; screenshots for UI milestones; real runs on the owner's games for coach and engine changes.

**M0 baseline on branch `v4` (2026-11-23):** backend 880 tests passed (98% coverage), `ruff check` and `mypy app` clean; frontend 381 Vitest tests passed (44 files), `oxlint` and `typecheck` clean. `npm run e2e` and `npm run build` weren't rerun at M0 (no code changed since v3's final run).

## 9. Decision log

| Date | Decision | By |
|---|---|---|
| 2026-11-23 | v3 approved and deployed on EC2; merged into `main`; branch `v4` started from `main`. | Owner |
| 2026-11-23 | Hosting stays on the current EC2 instance with Docker Compose and Caddy; no ECS or load balancer. | Owner |
| 2026-11-23 | Sign-up is a waitlist joined with Google sign-in; accepted users sign in with the same Google account. | Owner |
| 2026-11-23 | $10/month with 300 credits, a 50-credit free trial for unpaid users, $5 top-ups for 150 credits. Unused allowance expires each period; trial, top-ups and owner grants don't. | Owner |
| 2026-11-23 | A Deep coach tier is in v4. | Owner |
| 2026-11-23 | Mobile layout moves to a later version. | Owner |
| 2026-11-23 | An owner dashboard is in v4: all users, usage, site stats, paid vs unpaid, accept and revoke access, add credits. | Owner |
| 2026-11-23 | Postgres runs on Amazon RDS. | Owner (on Claude's recommendation) |
| 2026-11-23 | Minimum age 13, with parent or guardian agreement for 13 to 17. | Owner (on Claude's recommendation) |
| 2026-11-23 | Account email through Amazon SES, starting with the acceptance email. | Owner |
| 2026-11-23 | Stripe at launch, US customers only; billing provider-neutral so a later move (Stripe Managed Payments or Paddle) for international sales stays small. | Owner |
| 2026-11-23 | Faster game analysis is a v4 requirement, built in M3 (SPEC_V4 §8). | Owner |
| 2026-11-23 | Still open: D4 (tax, with a CPA), D6 (terms and privacy text), D10 (domain). | Owner |
| 2026-11-23 | M0 approved. Deep coach tier is option (c): Opus synopsis and baseline, Sonnet chat and explain, Haiku moments and walkthroughs (about 12 credits a game, 3.5x Standard). | Owner |
| 2026-11-23 | All M0 adjustments approved (§5: measured credits per game, Stripe Managed Payments as the first international option, the domain gates launch not M2, Postgres data checks and SQLite foreign keys, verify settings tied to the quality test). | Owner |
| 2026-11-23 | Dependencies approved: `psycopg[binary]`, `stripe`, `google-auth`. | Owner |
| 2026-11-23 | CI added: a GitHub Actions workflow runs backend tests on SQLite and Postgres, frontend tests, lint and type checks on every push (adjustment 6). | Owner |

| Date | Decision (while building) | By |
|---|---|---|
| 2026-11-23 | M1 test databases: `tests/databases.py` gives each test its own database. On Postgres it's cloned from a template migrated once per run and dropped (`WITH (FORCE)`) after the test, so tests stay isolated and each test app's pooled connections end with it. Migration tests get an empty database; the v1-upgrade test stays SQLite-only (v1 databases only ever existed as SQLite). | Claude |
| 2026-11-23 | SQLite now enforces foreign keys (a `connect` listener in `db/session.py`). `db/migrate.py::upgrade` switches them off while migrations run (batch migrations copy, drop and rename tables) and runs `PRAGMA foreign_key_check` afterwards, failing if any row points at a missing row. One test inserted an engine result before its game and was fixed. | Claude |
| 2026-11-23 | `migrate-sqlite` reads and writes through the app's own table definitions, so timestamps and JSON convert as the app reads them, and compares each table by row count and a SHA-256 checksum of normalized rows (UTC ISO timestamps, JSON with sorted keys). It refuses a source not at the latest migration, a source with problems, and a target with data. `--check-only` needs no target. Id sequences are moved past the copied ids on Postgres. | Claude |
| 2026-11-23 | `docker-compose.yml` reads `DATABASE_URL` from `./.env` next to it (variable substitution), defaulting to the SQLite volume, so the switch to RDS is one line and going back is deleting it. Connections use `sslmode=require` (RDS for PostgreSQL 15+ refuses unencrypted connections by default). Migrations still run at backend startup (one process). | Claude |
| 2026-11-23 | Trial on real data: a copy of the owner's dev database (1,418 rows in 19 tables) had no problems, copied into Postgres 17 in under a second with every table matching, and the app served login, the games list, the dashboard, a game, variations, PGN export, settings and the baseline report from the copy. | Claude |
| 2026-11-24 | M1 checkpoint on the server's data: a copy of the deployed database (revision 0018, SQLite integrity check ok) had no problems, copied into Postgres 17 in about a second (4,075 rows in 19 tables: 5 players, 38 games, 3,500 engine results), every table matched, and the app served all 134 pages of all five players from the copy (129 OK; the 5 not-found answers are the baseline report, which no player has yet). The throwaway copies were deleted afterwards. | Claude |
| 2026-11-24 | M1 approved. The server stays on SQLite (and v3) until M8; branch `v4` pushed to GitHub for CI. | Owner |
| 2026-11-24 | M2 built (awaiting checkpoint): Google OIDC with PKCE run by the backend (state, nonce and verifier stored only as hashes; the verifier cookie binds the round trip to the browser); accounts keyed by Google `sub`, never matched by email; a pending sign-up row until the age check and terms are done (deleted on an under-13 answer, which also closes sign-up in that browser for 24 h). The age check takes the birth year only and errs young: born 13 years ago counts as under 13, born 18 years ago as 13 to 17. `CurrentUser` now requires an active account; `CurrentAccount` (waitlisted or paused) is used only by `GET /api/me` and logout. Invite links never create accounts (only `create-user` does), so `AUTH__INVITES_CREATE_USERS` wasn't needed. Email text lives in `app/email/templates.py`, with the HTML made from the text (instead of separate template files). The E2E backend fakes Google with a chooser page (tests/e2e_app.py). | Claude |
| 2026-11-24 | M2 approved on the faked-Google evidence (unit, API and E2E tests, screenshots). The real Google client and SES are set up by the owner later; the real-Google and real-inbox checks move to M8 (staging). | Owner |
| 2026-11-24 | M3 credits: every coach call is priced at the config's prices (rounded up to whole microdollars) and charged in `record_usage`'s transaction; the ledger's (kind, source) is unique, the balance has an allowance part (spent first) and a lasting part, and the balance row is locked on Postgres (8 simultaneous charges tested). Coach routes check credit before calling (402 at zero, 429 past the $2 daily cap); a stored synopsis, walkthrough or baseline report is served free. Players made by `create-user` get the trial too; `grant-trials` covers the v3 players. `unmetered` is a column on `users`, not `user_settings` (it's the owner's flag, not the player's). Not done: the SSE `done` event carrying the call's credits (the credits UI reads `/api/billing` instead), and critical moments without coach text at zero credits (moments are refused at zero for now). | Claude |
| 2026-11-24 | M3 faster analysis, measured with real Stockfish on this machine (16 cores; the v3 timings here match the owner's laptop within a few percent): searches stop at their depth with no minimum time, and scan and verify run on a pool of 4 single-threaded engines (`engine/pool.ts`), each searching runs of consecutive positions from the end backwards. Scan depth 16 (v3's 250 ms floor really reached depth 18 to 19, so depth 12 or 14 lost too much), verify depth 18 with 4 lines. game5b (37 moves) 40.8 s to 9.4 s, game1w (63 moves) about 80 s to 17.0 s, game3w (91 moves) 86 to 100 s to 19.0 s. | Claude |
| 2026-11-24 | Engine quality (§8.1): multi-threaded Stockfish isn't deterministic, so v3's own settings re-run disagree with v3: 94.6% and 97.3% of labels on game5b, 96.1% on game3w, 97.6% on game1w, where the re-run also lost one of the player's mistakes (23. Rxc5) and a critical moment. The chosen settings: 97.3%, 97.6% and 96.7%, no blunder lost in any run, one borderline opponent mistake lost on game1w (10...Na7), critical moments changing at the edges as in v3's re-runs. The spec's "every v3 mistake still found" fails v3 against itself; proposed at the M3 checkpoint: no blunder lost, and label agreement no lower than v3's re-runs minus one point. Captures in `backend/tests/fixtures/engine/v4/`. | Claude (owner to decide at M3) |
| 2026-11-24 | Owner request: the coach was narrating the engine instead of teaching. The shared prompt gains "Sound like a coach, not an engine" (lead with the idea, not the evaluation; find the one thing that matters; a reusable rule of thumb; name the thinking habit behind a mistake; talk like at the board; be selective; never justify a move by its verdict; every concrete claim still from the data) with a side-by-side example, and "Teaching to the player's level" (beginner: safety and one idea; intermediate: plans and principles; advanced: concise and concrete). The synopsis, moment, Explain, chat and walkthrough instructions stop asking for before-and-after evaluations as the content. The hard rules (moves only from the data, move tags, line links, withholding) are unchanged. Checked on game1w at 1200: the old synopsis built every key moment on numbers; the new one explains each as an idea with a habit to take away, no moves removed by validation. | Owner request, Claude |
| 2026-11-24 | M3 checkpoint answers: the engine quality bar is "no blunder lost, and label agreement no lower than v3's own re-runs minus one point" (replaces SPEC_V4 §8.1's "every mistake still found"). Critical moments without coach text at zero credits: later (moments stay refused at zero for now). Skipping one-legal-move positions: dropped (targets met without it). Imports that keep running while the player browses: built now, in M3. The "week of the owner's real use priced against the Anthropic console" check moves to M8. | Owner |
| 2026-11-24 | Background imports (§8.2): the analysis queue moved from the import panel into the app (`analysis/backgroundQueue.ts`, provided by `App.tsx`), so imported games keep being analyzed while the player uses other pages. The waiting list is kept in localStorage (`cochess.analysisQueue`) so a reload carries on; Web Locks keep it to one tab; a failing game is set aside and the rest go on; a 401 stops the run and keeps the rest until sign-in; signing out clears it. A status line under the header shows progress and a dismissible summary; the Games page refreshes as each game finishes. `runGamesQueue` (the panel's one-shot loop) was removed. Opening each game straight after its scan was not built: at about 10 s a game the whole analysis is quick enough. | Claude |
