# CoChess — v4 Spec

Status: **Draft for owner review** (third draft, 2026-11-23, with the owner's answers on hosting, waitlist, pricing, coach strength, mobile layout, the owner dashboard, Postgres on RDS, the minimum age and account email). This builds on v3 (`SPEC_V3.md`, as built in `docs/v3-as-built.md`), v2 and v1, all kept for reference. Where they disagree, this file wins once approved. Sections 1–14 define v4 (§13 is the milestone plan). §15 records the owner's decisions and the few still open.

---

## 1. What v4 adds

v3 made CoChess pleasant to use every day for a handful of invited testers. v4 makes it a product strangers can sign up for and pay for, on the same EC2 server, without the owner losing money or data:

1. **Google sign-in and a waitlist.** Anyone can join the waitlist with Google. Once the owner accepts them, the same Google sign-in opens their account. Invite links stay as an owner tool.
2. **Coaching credits.** Every Claude call is priced from its real token usage and paid for from the player's credit balance. Players see what they have left; at zero the coach stops, the engine doesn't.
3. **Free trial and payments.** Accepted players get trial credits. A monthly subscription includes a coaching allowance, and one-time top-ups add more, through Stripe's hosted pages.
4. **Coach strength.** Players can choose a Deep coach that uses their credits faster.
5. **Faster game analysis.** A game is analyzed in seconds instead of about a minute, so importing games keeps up with other chess sites (owner request, §8).
6. **Owner dashboard.** The owner sees every user, their usage and the site's numbers (paid vs unpaid, cost vs revenue), accepts or revokes access, and adds credits.
7. **Cost controls.** Measured cost per game, better prompt-cache use, smaller payloads, and per-task model routing.
8. **Production hardening on EC2.** Postgres, backups with a tested restore, monitoring, a staging copy, and rate limiting.
9. **Accounts and legal.** Terms of service, privacy policy, a minimum age of 13, account deletion and data export.
10. **Account email.** Players get email about their account, starting with "You've been accepted".

**Rules carried forward:**
- **The engine analyzes, the LLM explains.**
- **Withhold, don't instruct.**
- **Never trust the client** for chess facts or identity.
- **Every visual claim is checked.**

**New rules for v4:**
- **Money comes from the payment provider, not the browser.** A balance changes only through a ledger entry written by a verified Stripe (or Paddle) webhook, by metered usage, or by the owner (dashboard or CLI, always audited). A redirect back from checkout proves nothing.
- **No coach call without credit.** The balance is checked before a call starts; the real cost is charged after it ends. Engine analysis runs in the player's browser and is never charged.
- **Identity comes from Google's verified token, on the backend.** The browser never tells the backend who the user is.
- **Owner powers are checked on the backend and audited.** The owner role is set only from the CLI on the server, every owner route checks it, and every owner action is logged.

## 2. v4 scope

**In:** everything in §1.

**Out (later):** mobile layout (owner decision: a later version), opening courses and drills, in-app puzzles from the player's own mistakes, coach-written weekly summaries, other sign-in providers (Apple, email/password), teams or coaches managing students, languages other than English, moving off the single EC2 server (ECS, load balancers, several backend processes).

## 3. Step zero: reconcile and measure

Before planning:
1. Check `docs/v3-as-built.md` against the code on `main` and note anything that changed since (it's current as of 2026-11-23).
2. **Measure real cost.** From `llm_usage` on the deployed server, compute the cost per task and per analyzed game (synopsis + the questions players actually ask + moments + walkthroughs) at today's prices, for Standard and (by replaying a few owner games) Deep. The credit amounts in §6 are checked against this.
3. **Measure engine time.** Scan and verify time per game, with both Stockfish builds, on the owner's fixture games: the baseline for §8.
4. Settle the open decisions in §15 and write `docs/PLAN_V4.md` (plan, adjustments, decision log), as in v3.

## 4. Google sign-in and the waitlist

### 4.1 Flow

- "Continue with Google" on the login page starts an OpenID Connect authorization-code flow with PKCE, run entirely by the backend: `GET /api/auth/google/start` stores `state`, `nonce` and the PKCE verifier (hashed, short-lived) and redirects to Google; `GET /api/auth/google/callback` exchanges the code, verifies the ID token (signature against Google's keys, `iss`, `aud`, `exp`, `nonce`), and requires `email_verified`.
- The account key is Google's `sub`, never the email. Sessions are the existing cookie sessions (`httpOnly`, `SameSite=Lax`, `Secure`).
- Scopes: `openid email profile` only. The Google access token is not stored.

### 4.2 Joining the waitlist

- A new Google `sub` creates a user with status `waitlisted`, after the person passes the age check and accepts the terms and privacy policy (§11). Their name comes from Google and can be changed later. They get the "You're on the waitlist" email (§12.4).
- A waitlisted user who signs in sees one page: "You're on the waitlist", the date they joined, and a sign-out link. Every other route refuses them (`403`, "Your account is waiting for approval"). They can still delete their waitlist entry (§11).
- Waitlisted users cost nothing: no coach calls, no trial credits, no game uploads.

### 4.3 Accepted players

- The owner accepts a user from the owner dashboard (§10) or `app.cli admit --user`. Their status becomes `active` and the trial grant (§6.1) is added once.
- The next time they sign in with Google (or reload, if signed in), they reach the normal first-run profile flow and the app.
- They get the "You've been accepted" email (§12.4) with a sign-in link to the app. The waitlist page also opens the app by itself once they're accepted.

### 4.4 Revoked access

- The owner can revoke access (status `suspended`, with a reason kept in the audit log). Their sessions are deleted at once; signing in again shows "Your access has been paused" and nothing else. Their data is kept, and they can still export or delete it. They get the "access paused" email; the owner's reason is not included unless the owner ticks "include the reason".
- Restoring access sets them back to `active` and sends the "access restored" email. No second trial grant.

### 4.5 Existing players and invite links

- Existing invite-link players keep their accounts and are `active`. While logged in, the Profile page offers "Connect Google"; after that they sign in with Google. An account is never linked or merged by matching email addresses.
- `app.cli invite` stays for the owner (support, testers, recovering an account). Invite links never create a new account in production (`AUTH__INVITES_CREATE_USERS=false`); a redeemed invite always logs in an existing user.

### 4.6 Data

- `users`: add `email` (verified, from Google, shown on the Profile page and the owner dashboard), `google_sub` (unique, nullable for invite-only users), `status` (`waitlisted`, `active`, `suspended`, `deleted`), `role` (`player`, `owner`), `age_band` (`13_17`, `18_plus`), `age_checked_at`, `waitlisted_at`, `admitted_at`, `last_active_at` (updated at most once an hour).
- `email_preferences`: user, kind, enabled (only for the kinds a player can turn off, §12.4).
- `oauth_states`: hashed state, nonce, PKCE verifier, created_at, expires_at; deleted after use or expiry.
- `terms_acceptances`: user, version, accepted_at.
- The email is personal data: never logged, never sent to the coach, never sent to Chess.com or Lichess.

## 5. Credits and metering

### 5.1 What a call costs

- Every `llm_usage` row gains `cost_microusd` and `tier`, computed when the row is written from its token counts (input, output, cache read, cache write) and the model's price in config (`PRICING__MODELS`, with an `effective_from` date). Past rows are never repriced.
- Prices live in config only, are checked against Anthropic's published prices at M0 and at each model change, and an unknown model is a startup error, not a free call.
- Players see **credits**, not dollars: 1 credit = $0.01 of API cost (`CREDITS__MICROUSD_PER_CREDIT`). The UI shows credits left and roughly how many games that covers at the player's coach strength, from the measured average.

### 5.2 Ledger

- `credit_ledger`: id, user_id, `delta_microusd` (signed), `kind` (`trial`, `allowance`, `top_up`, `usage`, `refund`, `expiry`, `owner_grant`, `owner_removal`), `source` (Stripe event id, `llm_usage` id, or admin action id), `note` (required for owner entries), `expires_at` for allowance entries, created_at. Unique on (`kind`, `source`), so a replayed webhook or a retried request can't apply twice.
- The balance is the sum of the ledger, kept in a `credit_balances` row updated in the same transaction as each entry (row-locked on Postgres) so the pre-call check is one read.
- Spending order: allowance first, then trial, then top-ups and owner grants. Unused allowance expires at the end of its billing period (an `expiry` entry); trial credits, top-ups and owner grants don't expire.

### 5.3 Before and after a call

- Before any coach call (synopsis, chat, explain, moment intro/feedback, baseline report, walkthrough), the backend checks the user is `active` and the balance is above zero. If not: `402` with "You're out of coaching credits", and the page shows the subscribe and top-up buttons. The coach-typing indicator never starts.
- After the call, a `usage` entry charges the real cost. A call that started with a positive balance always finishes, so the balance can go slightly negative (bounded by one call's `max_tokens`); the next call is refused until it's positive. The backend's own retries (validation regenerations) are charged too, since they cost money; the per-task retry limits stay as they are.
- A call that fails before Anthropic returns usage is not charged.
- **Warnings:** at 20% of the period's allowance (or of the trial) left, and at zero: a banner on the Games page and a note under the chat input (`CREDITS__WARN_AT`).
- **Safety cap:** a per-player daily spend ceiling (`CREDITS__DAILY_CAP_MICROUSD`) stops runaway use even with credits available. It replaces `USER_DAILY_TOKEN_LIMIT`, which is removed.
- Owner and test accounts can be marked `unmetered` (dashboard or CLI); their usage is still recorded and priced.

### 5.4 What stays free

For every active player, paid or not, and with zero credits: uploading and importing games, engine analysis (it runs in the browser), the move list, eval graph, critical moments without coach text, saved variations, PGN export, and the dashboard's numbers and charts. Cached coach output (a walkthrough already generated for the same line and tier) costs nothing to show again.

## 6. Free trial and payments (Stripe)

v4 launches with Stripe, selling to US customers (owner decision, §15 D13). A move to Paddle may come later if CoChess sells internationally, so the provider sits behind one `BillingProvider` interface (create checkout, open the customer portal, verify and parse a webhook, cancel a subscription), and nothing outside it names Stripe:
- Data uses provider-neutral names (`billing_provider`, `billing_customer_id`, `billing_events`), and every billing record carries its provider, so Stripe history stays readable after a switch.
- Plans are keyed by CoChess's own product names in config (`monthly`, `top_up`), mapped to the provider's price ids.
- No provider-only features the ledger depends on (Stripe coupons, metered billing): credits, trials and owner grants live in CoChess's ledger.
- The ledger, the webhook rules (signature checked, events stored, repeats ignored, the browser never trusted) and the plans don't change with the provider. A switch means a second `BillingProvider`, a terms update naming the new seller, and moving subscribers (Stripe's card-data export to the new provider, or asking them to re-subscribe).

### 6.1 Plans (owner approved; amounts in config)

| Product | Price | What it gives |
|---|---|---|
| Free trial | free, once, when accepted from the waitlist | 50 credits |
| CoChess monthly | $10 / month | 300 credits of allowance each paid period ($3 of API, the v1 cost review's ceiling) |
| Top-up | $5 | 150 credits, no expiry |

Unpaid players are those on the trial (or with only owner grants); they use everything, and the coach until their credits run out. Amounts are config, mirrored from Stripe Price ids (`STRIPE__PRICE_MONTHLY`, `STRIPE__PRICE_TOPUP`). The backend never takes a price from the browser. M0 checks the amounts against measured cost and Stripe's fees.

### 6.2 Flow

- **Checkout:** `POST /api/billing/checkout {product}` creates a Stripe Checkout Session for the logged-in active user (customer created on first use, `client_reference_id` = user id) and returns its URL; the browser redirects there. Card details only ever go to Stripe's hosted page.
- **Manage or cancel:** `POST /api/billing/portal` returns a Stripe Customer Portal URL.
- **Webhooks** (`POST /api/billing/webhook`, no session, signature checked with the webhook secret on the raw body): the only place money becomes credits.
  - `checkout.session.completed` (payment mode) → `top_up` entry.
  - `invoice.paid` for the subscription → `allowance` entry for that period, expiring at its end.
  - `customer.subscription.updated` / `.deleted` → subscription status on the user.
  - `charge.refunded` → `refund` entry removing the refunded credits (the balance may go negative).
  - Each event is stored (`billing_events`) with its amount and currency, for the owner dashboard's revenue; a repeat is acknowledged and ignored. Unknown events are logged and acknowledged.
- The return page after checkout says "Payment received, your credits will appear in a moment" and polls `GET /api/billing` until the webhook has landed.
- Failed renewals: the subscription goes `past_due` per Stripe's retry settings; no new allowance until an invoice is paid. Remaining credits stay usable.
- Taxes: see §15, D4. Stripe sends receipts by email.

### 6.3 Data

- `users`: add `billing_provider`, `billing_customer_id` (unique per provider), `subscription_status`, `subscription_period_end`.
- `billing_events`: provider, event id (unique per provider), type, user_id, amount_cents, currency, received_at, processed_at, outcome.

## 7. Coach strength (owner approved)

- `user_settings.coach_strength`: `standard` (today's defaults: Sonnet at low effort for synopsis and baseline, Haiku for chat, moments and walkthroughs) or `deep` (owner decision at M0, option c: Opus for synopsis and baseline, Sonnet for chat and explain, Haiku for moments and walkthroughs; about 12 credits a game against Standard's 3). Each tier is a whole `CoachTier` in config (model and effort per task), like engine tiers; models still come from env.
- The Profile page shows both with the measured credits per game for each (measured: about 3 credits a game at Standard, about 12 at Deep) and says Deep uses credits about 3.5× faster. Trial players can choose Deep too. The choice applies to new coach calls only.
- Cached walkthroughs record their tier; a Deep player is not served a Standard walkthrough.

## 8. Faster game analysis (owner request, M3)

Analyzing a game takes about a minute today (scan and verify, multi-threaded Stockfish on a laptop), so importing 20 games takes about 20 minutes, much slower than other chess sites. The game import itself (fetching from Chess.com or Lichess) is quick; the engine is the bottleneck. The engine stays in the player's browser and the backend keeps checking every result (golden rule 3).

### 8.1 Targets

Measured with real Stockfish on the owner's fixture games, on the same laptop as the v3 figures (M0 records the baseline per game and per phase):
- A 40-move game is fully analyzed (scan and verify) in **15 seconds or less** with the multi-threaded build, and in 30 seconds or less with the single-threaded fallback.
- The board, move list and eval graph open as soon as the scan is done; the verify step finishes in the background.
- An import of 20 games: the first game opens within 15 seconds, all 20 are analyzed within 5 minutes, and the player can keep using the app while it runs.
- **Quality doesn't drop:** on the owner's fixture games, every blunder and mistake found today is still found, at least 95% of move classifications are unchanged, and the critical moments picked are the same or the owner accepts the differences. A regression test compares new results to the stored v3 engine results.

### 8.2 How (each change measured on its own, kept only if it helps)

- **Stop the scan by depth, not time.** Today every position waits at least 250 ms even when depth 12 is reached sooner. The scan tier stops as soon as its depth is reached, with the hard cap kept for slow positions; the depth is set from the quality test.
- **Several engines at once.** Scan positions are independent, so a pool of single-threaded Stockfish workers (sized from the device's cores and memory, `ENGINE__POOL_SIZE` as the ceiling) searches several positions at the same time. That scales better than one engine with several threads on short searches, and it also works without cross-origin isolation, so the single-threaded fallback gets faster too. Verify searches, which are longer, keep one multi-threaded engine.
- **Reuse the engine's memory.** Each worker scans a run of consecutive positions from the end of the game backwards, so its hash table already knows the positions that follow.
- **Skip searches whose answer is known.** A position with only one legal move gets the evaluation of the position after that move. The backend fills it in from that result (the browser doesn't send it), so the backend's checks don't change. Terminal positions are already scored from the board.
- **Lighter verify.** Verify runs on fewer positions when the scan already makes the verdict clear, and with fewer lines or less time where the quality test allows. The settings stay in `EngineSettings`.
- **Import in the background.** The import queue keeps running while the player opens other pages (it survives navigation within the app and resumes after a reload). The Games page shows its progress, and each game opens as soon as its scan is done.
- Not in v4: running Stockfish on the server (it would load the single EC2 instance with every player's analysis and change the browser-engine design), and taking evaluations from outside services.

### 8.3 Tests

- Vitest with the fake engine transport: the worker pool splits and orders positions correctly, a worker that fails or stops responding has its positions retried on another, a cancelled analysis stops every worker, and results come back in ply order.
- Backend: a scan without the forced-move positions is accepted and filled in correctly; any other missing position is still rejected.
- The quality regression test (§8.1) on the owner's fixture games, and a timing check in `npm run e2e:real` that reports scan and verify time per game.

## 9. Cost controls

Target, measured on the owner's games: a typical analyzed game at Standard (synopsis, three chat questions, the critical moments, one walkthrough) costs **no more than it does in v3**, and the v3 quality checks still pass. M0 records the baseline.

- **Prompt caching:** measure the cache-read share per task from `llm_usage`. Put stable content first (system prompt, shared rules, game context) and per-message content last; one cache breakpoint per stable block. Report the hit rate on the owner dashboard.
- **Compact payloads:** drop fields the prompts don't use; cap repeated engine lines (`coach_engine_lines`, `coach_line_plies` already exist); measure input tokens per task before and after.
- **Model routing:** each task's model comes from the tier (§7), so cheaper tasks can move to Haiku without touching code.
- **Caching coach output:** walkthroughs are cached (v3). The synopsis and baseline report are stored and never regenerated unless the player asks; a regeneration costs credits and says so.

## 10. Owner dashboard

A page at `/owner` for users with `role = owner`. The role is set only on the server (`app.cli set-role --user "..." owner`), never from the UI. Every `/api/admin/*` route checks it on the backend; for anyone else they return `404`, and the nav never shows the link.

### 10.1 Overview

- **Users:** total, and by status (waitlisted, active, suspended); waitlist length and the oldest wait.
- **Paid vs unpaid:** active subscribers, past-due, cancelled this month, trial-only players (with and without credits left), players at zero credits.
- **Activity:** sign-ups, acceptances and active players over the last 7 and 30 days; games added; coach calls per task.
- **Money:** revenue in the period (from `billing_events`), API cost in the period (from `llm_usage`), the difference, API cost per active player and per game, credits granted vs spent, the prompt-cache hit rate. Stripe fees aren't known to CoChess and are shown as "before Stripe fees".
- Period filter: 7 days, 30 days, this month, all time. Charts use Recharts and the chart tokens, as in the v3 dashboard.

### 10.2 Users

- A table with search (name, email) and filters (status, plan, coach strength, zero credits): name, email, status, plan, balance, credits used in the last 30 days, API cost in the last 30 days, games, last active, joined. Sorted and paginated on the server.
- **The waitlist** is its own tab, oldest first, with "Accept" on each row and for a selection.
- **A user's page:** their numbers, cost per task over time, the credit ledger, subscription status and a link to the Stripe customer, and the audit log of owner actions on them.
- **Actions** (each confirmed, each written to the audit log):
  - Accept (from the waitlist; adds the trial once).
  - Revoke access, with a reason (§4.4). If the user has an active subscription, the dialog says so and offers to cancel it in Stripe as well; it is never cancelled silently.
  - Restore access.
  - Add credits or remove credits, with a required note (`owner_grant` / `owner_removal` ledger entries).
  - Mark or unmark `unmetered`.
- The dashboard shows counts and usage, not the content of anyone's games or chats.

### 10.3 Data and limits

- `admin_actions`: id, admin user id, target user id, action, details (JSON: reason, credits, note), created_at. Ledger entries from the owner point to their action.
- The overview and the users page each load in under 500 ms with 10,000 generated users and a year of usage (performance test).
- The same actions stay in the CLI (`admit`, `suspend`, `restore`, `grant-credits`, `set-role`, `usage-report`) for when the web app is down.

## 11. Accounts and legal

- **Pages:** `/terms` and `/privacy`, public, versioned (`LEGAL__TERMS_VERSION`). The text is the owner's (with legal advice); v4 ships the pages, the version check and the consent records, not the legal wording. A new version asks logged-in users to accept before they continue.
- **The privacy policy must say:** games, chat messages and profile notes are sent to Anthropic's API to produce coaching; usernames are used to fetch games from Chess.com and Lichess; payments go through Stripe; Google provides the name and email; the owner can see each account's email and usage; only an essential login cookie is set. California's privacy law (CCPA) has thresholds a small app is unlikely to meet at launch, but the export and deletion below cover its main rights anyway.
- **Data export:** `POST /api/me/export` builds a zip (profile, settings, every game as PGN with variations and notes via the v3 exporter, chat history, baseline report, credit history) and the page downloads it. Rate-limited.
- **Account deletion:** Profile → "Delete my account" (also on the waitlist page), confirmed by typing the account name. It cancels any Stripe subscription immediately, deletes the user's games, chats, variations, walkthroughs, line links, moments, tendencies, reports, settings and sessions, and anonymizes `llm_usage`, `credit_ledger`, `billing_events` and `admin_actions` rows (user id removed) because they're financial and audit records. The Stripe customer and invoices stay with Stripe, as needed for accounting. Done in one transaction; the session ends.
- **Minimum age: 13** (owner decision on the recommendation). The chess content suits all ages, but collecting an email from a child under 13 brings the US children's privacy law (COPPA) and its verified parental consent, and Google accounts for under-13s are parent-supervised. So:
  - Sign-up asks for the birth year with a neutral question (no hint of the cutoff, no "I'm 13 or older" checkbox, as the FTC advises). Under 13: sign-up stops with a friendly message, nothing is stored, and a cookie stops an immediate retry with another year.
  - Only `age_band` (`13_17` or `18_plus`) and the check's time are stored, not the birth year.
  - 13–17: the terms say a parent or guardian must agree to them, and paying needs a parent or guardian. The checkout page says so for `13_17` accounts.
  - The site is a general-audience site: it isn't marketed to children, and the privacy policy says what happens if the owner learns an under-13 account exists (it's deleted).
  - The terms and privacy wording is still the owner's, reviewed by a lawyer (§15, D6).

## 12. Production on the EC2 server

The owner hosts on one EC2 instance with Docker Compose and Caddy (`docs/DEPLOY.md`), and v4 stays there. One backend process is kept.

### 12.1 Postgres

- SQLAlchemy and Alembic on Postgres (driver `psycopg`). Every existing migration must run on both SQLite (local dev, tests) and Postgres; the test suite runs on both, and Postgres-only behavior (row locks for the ledger) has its own tests.
- Postgres runs on **Amazon RDS** (owner decision): the smallest current instance class, single availability zone, in the same region and VPC as the EC2 instance, not publicly reachable (its security group only admits the instance), encrypted storage, TLS required, automated backups kept 14 days with point-in-time recovery, deletion protection on. Staging uses its own database on the same RDS instance.
- `app.cli migrate-sqlite --from <db> --to <postgres url>` copies the v3 server's data into Postgres, then compares row counts and a checksum per table. Run once at the switch.

### 12.2 Server setup

- **Domain:** the app runs at `https://3-15-12-174.sslip.io` today. v4 needs a domain the owner controls (§15, D10), because:
  - email can't be sent from `sslip.io`: SES only sends for a domain whose DNS the sender can change (SPF, DKIM, DMARC records), and mail without them lands in spam;
  - the hostname is tied to the Elastic IP, so a new IP means a new address for every player and new Google and payment settings;
  - Google's sign-in consent screen and the payment provider's account review both ask for the business's website, with its terms and privacy pages.
  Until it's bought, M1 and the parts of M2–M5 that don't need Google or email can be built and tested on the current hostname and staging. Caddy's HTTPS covers the new domain as today, and the old hostname redirects to it.
- **Secrets:** the Anthropic key, payment-provider secret and webhook secret, Google client secret, SES SMTP credentials and database password stay in `backend/.env` on the server, readable only by the deploy user; never in images or the repo. `.env.example` lists every name with placeholders.
- **Staging:** a second Compose project on the same instance (as the v3 smoke test did) on its own subdomain and database, with Stripe test mode and a separate Google OAuth client. Every release goes to staging first.
- **Migrations** still run at startup (one process).
- **Rate limiting** in the database (`rate_limits`: key, window start, count), so limits survive restarts and staging and production don't share them: login and OAuth callback per IP; coach calls per user per minute; the import cooldown (moved from memory); export per user per day; checkout per user per minute. The webhook only accepts signed requests. Existing per-player limits (`LIMITS__MAX_GAMES_PER_DAY`, chat messages per game, walkthroughs per game) stay.

### 12.3 Monitoring and backups

- Structured JSON logs with a request id; never the API key, tokens, cookies or emails. Shipped to CloudWatch with the CloudWatch agent, kept 30 days.
- Alarms emailed to the owner: the health check failing, disk above 80%, backend errors, Anthropic errors, webhook failures, daily API spend above a threshold, and the AWS budget. `GET /api/health` (database reachable, migrations at head) is what the uptime check calls.
- Backups: RDS automated backups (14 days, point-in-time) plus a manual snapshot before every release's migrations. **Restore drill:** restoring a backup into a fresh database and running staging against it is part of the M8 checkpoint and written up in `docs/DEPLOY.md`.

### 12.4 Account email (Amazon SES)

**Service:** Amazon SES in the server's region, sending from `CoChess <account@mail.<domain>>` with a reply-to the owner chooses. The domain is verified in SES with DKIM, and SPF and DMARC records are added. The SES account is moved out of the sandbox (an AWS request) before launch. The backend sends through SES's SMTP interface with Python's standard library (`smtplib`, `email`), so no new dependency. The SMTP credentials come from an IAM user that can only send mail.

**How sending works:**
- An `email_outbox` table: id, user_id, kind, dedupe key (unique), status (`pending`, `sent`, `failed`, `skipped`), attempts, last error (no addresses), created_at, sent_at. The action that triggers an email (accepting a user, a webhook, a low balance) writes the outbox row in the same transaction, so an email is never lost or sent for something that rolled back.
- A sender loop inside the backend process sends pending rows, retrying with backoff up to 5 times (`EMAIL__*` settings), and marks them `failed` after that. A dedupe key such as `accepted:<user_id>` means each email is sent once.
- Turned off in development and tests (`EMAIL__ENABLED=false`): rows are written and marked `skipped`, and a fake transport records them for tests. Staging sends only to addresses on an allow list.
- Bounces and complaints: SES's account-level suppression list is turned on, so addresses that bounce or complain aren't mailed again. A later version can read SES's notifications.
- Logs and the owner dashboard show the email kind, user id and status, never the address or the body.

**Emails** (plain text plus simple HTML from template files in `app/email/templates/`; the only player data in them is the escaped name):

| Kind | When | Can the player turn it off? |
|---|---|---|
| `waitlist_joined` | after joining the waitlist | no (it confirms the sign-up) |
| `accepted` | when the owner accepts them, **first to build** | no |
| `access_paused` / `access_restored` | owner revokes or restores access | no |
| `credits_low` / `credits_out` | the balance crosses the warning level or reaches zero, at most once per billing period each | yes |
| `credits_added` | the owner adds credits (with the owner's note if ticked) | yes |
| `account_deleted` | after deletion, to the address on file, then the address is gone | no |
| `terms_updated` | a new terms version | no |

Payment receipts, renewal reminders and failed-payment emails come from the payment provider, not CoChess, so players don't get two of each.

All of these are account messages, not marketing: no newsletters or promotions are sent in v4. The ones players can turn off sit under Profile → "Email", with a one-click link at the bottom of each email (a signed token, no login needed).

## 13. v4 milestones and checkpoints

Stop for owner review at every ✅.

- **M0 — Reconcile, measure and plan.** §3: as-built check, real cost per task and per game at both strengths, the domain and Google/Stripe requirements, Postgres location, `docs/PLAN_V4.md`. ✅ *Checkpoint: the cost report and the remaining decisions.*
- **M1 — Postgres.** Driver, migrations on both databases, tests on both, `migrate-sqlite` with checks. ✅ *Checkpoint: the full suite green on Postgres; a copy of the server's database moved and compared.*
- **M2 — Google sign-in, the waitlist and account email.** The domain and SES set up; OIDC flow, user status and role, the age check, the waitlist page, accept/suspend/restore from the CLI, Connect Google for existing players, terms consent, invites as an owner tool; the outbox and sender with the `waitlist_joined`, `accepted`, `access_paused` and `access_restored` emails. ✅ *Checkpoint: screenshots of joining the waitlist, being accepted and signing in, and Connect Google, on staging; the acceptance email as received in a real inbox (not spam); the security tests (state, nonce, audience, unverified email, replay, under-13, waitlisted and suspended users refused).*
- **M3 — Credits, coach strength and faster analysis.** Pricing config, `cost_microusd`, ledger and balance, trial grant on acceptance, the pre-call check and post-call charge on every coach task, warnings, the daily safety cap, CLI grants and `unmetered`, the credits UI, Standard and Deep. No Stripe yet. Faster game analysis (§8): depth-based scan, the worker pool, backwards runs, forced-move skips, lighter verify, background imports, the quality regression test. ✅ *Checkpoint: a week of the owner's real use priced by CoChess against the Anthropic console (within 2%); the out-of-credits screens; one game coached at each strength; engine time per game before and after on the owner's games, a 20-game import timed, and the quality comparison.*
- **M4 — Stripe.** Checkout, portal, webhooks, refunds, failed renewals, the billing page, in test mode. ✅ *Checkpoint: a full subscription life on a Stripe test clock (subscribe, renew, top-up, failed payment, cancel, refund), showing the ledger after each step.*
- **M5 — Owner dashboard.** Overview, users table, waitlist tab, user page, the actions with the audit log, the performance test. ✅ *Checkpoint: the dashboard on staging with real and generated users; accepting, revoking, restoring and adding credits, with the audit log after each.*
- **M6 — Cost controls.** Cache ordering, payload trims, routing. ✅ *Checkpoint: cost per game before and after on the owner's games, and the same 3 synopses and replies side by side for the owner to judge.*
- **M7 — Accounts and legal.** Terms and privacy pages with versioned consent, export, deletion. ✅ *Checkpoint: an exported zip from the owner's account; a deleted test account with the database showing what's left (anonymized money and audit records only).*
- **M8 — Production hardening.** Staging, Postgres on RDS in production, SES out of the sandbox, rate limits in the database, health check, logs and alarms, backups and the restore drill, `docs/DEPLOY.md` for v4. ✅ *Checkpoint: staging running end to end (join the waitlist, get accepted, pay in test mode, analyze, coach); an alarm firing; a restored backup.*
- **M9 — Harden and launch.** Playwright end-to-end tests for joining the waitlist, acceptance, out-of-credits, checkout return, top-up, the owner actions, deletion and export (Google and Stripe faked); a security review of auth, billing, owner routes and deletion; a load test of the coach routes and dashboards; Stripe live mode; the v3 data moved to Postgres in production. ✅ *Checkpoint: final review, then launch on the owner's go.*

**v4 is done when:**
- A stranger can join the waitlist with Google, and once the owner accepts them, sign in with Google, use the trial, subscribe, and keep getting coached without the owner doing anything more.
- Waitlisted and suspended users can't reach anything but their status page, export and deletion.
- Existing players keep all their games and history and sign in with Google.
- A 40-move game is analyzed in 15 seconds or less (multi-threaded build), a 20-game import finishes within 5 minutes, and no blunder or mistake found in v3 is lost (§8.1).
- Every coach call is priced, charged and visible in the player's credit history; CoChess's total matches the Anthropic bill within 2% over a month.
- Nobody gets coaching with zero credits, and no balance ever changes from a player's browser request.
- A replayed or forged Stripe webhook changes nothing.
- The owner dashboard shows every user, their usage, paid vs unpaid, and cost vs revenue; every owner action is in the audit log; no other user can reach it.
- Cost per typical game at Standard is no higher than v3's, with the owner agreeing quality hasn't dropped.
- Export gives the player everything that's theirs; deletion removes it, keeping only anonymized money and audit records.
- A backup has been restored successfully, and alarms reach the owner.
- All v3 done-conditions still hold (zero `moment_leak` incidents, validated annotations, plain language).
- All tests, lint, type checks and end-to-end tests pass, on SQLite and Postgres.

## 14. API, data model and testing

### 14.1 New and changed endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/auth/google/start` / `GET /api/auth/google/callback` | Google sign-in (§4.1) |
| `POST /api/auth/google/connect` | Start linking Google to the logged-in account (§4.5) |
| `GET /api/me` | Gains `status`, `role`, `email` |
| `POST /api/me/terms` | Accept the current terms version |
| `GET /api/billing` | Balance, allowance left, subscription status, recent credit history |
| `POST /api/billing/checkout` | `{ product }` → Stripe Checkout URL |
| `POST /api/billing/portal` | Stripe Customer Portal URL |
| `POST /api/billing/webhook` | Stripe events (signed, no session) |
| `POST /api/me/export` | Data export zip |
| `DELETE /api/me` | Account deletion (§11) |
| `GET /api/health` | Uptime check |
| `GET /api/admin/overview?period=` | Owner dashboard numbers (§10.1) |
| `GET /api/admin/users?q=&status=&plan=&sort=&page=` | Users table (§10.2) |
| `GET /api/admin/users/{id}` | A user's page: numbers, ledger, audit log |
| `POST /api/admin/users/{id}/accept` · `/suspend` · `/restore` · `/credits` · `/metering` | Owner actions (audited) |
| Every coach route | `402` out of credits, `403` not active; the SSE `done` event carries the call's credits |

`PATCH /api/settings` gains `coach_strength`.

### 14.2 Data model

- **Changed:** `users` (§4.6, §6.3), `llm_usage` (`cost_microusd`, `tier`), `user_settings` (`coach_strength`, `unmetered`), `walkthroughs` (`tier`).
- **New:** `oauth_states`, `terms_acceptances`, `credit_ledger`, `credit_balances`, `billing_events`, `admin_actions`, `rate_limits`, `email_outbox`, `email_preferences`.
- **Removed:** `USER_DAILY_TOKEN_LIMIT` (replaced by the daily safety cap).

### 14.3 Testing rules (added to CLAUDE.md's)

- Google is faked (a local signing key and JWKS); never call Google in tests. Tests cover bad state, bad nonce, wrong audience, expired token, unverified email, a reused code, and waitlisted and suspended users.
- Stripe is faked with signed test events; never call Stripe in tests. Tests cover each webhook type, a replayed event, a bad signature, out-of-order events, and a refund that drives the balance negative.
- Every coach route has a test that it's refused at zero balance and for a non-active user, and charges the right amount after a call (mocked usage).
- Ledger tests: two concurrent calls on a small balance (Postgres), the spending order, allowance expiry at period end, the trial granted exactly once.
- Every `/api/admin/*` route returns `404` for a player; every owner action writes one audit row; credit actions need a note.
- Deletion test: after deleting a user, no table holds their user id except anonymized money and audit records; another user's data is untouched.
- Export test: the zip's PGNs re-import to the same games.
- Every new user-data endpoint gets the other-user 404 test.
- Email is faked (a recording transport); never send real mail in tests. Tests cover: each trigger writes exactly one outbox row in the same transaction, a rolled-back action writes none, a repeat trigger is deduplicated, retries stop after the limit, a turned-off kind is skipped, the unsubscribe link only works with a valid token, and no address or body reaches the logs.
- Age check: under 13 stores nothing; 13–17 and 18+ store only the band.

### 14.4 New dependencies (owner approval needed, per CLAUDE.md)

- `stripe` (Python SDK) for Checkout, Portal, webhook signature checks and cancelling a subscription from the owner dashboard.
- `psycopg[binary]` for Postgres.
- One library for Google ID-token verification (`google-auth`, or `authlib`), decided at M0.
- None for email: SES's SMTP interface through the standard library.

## 15. Owner decisions

**Decided (2026-11-23):**

| # | Decision | Owner's answer |
|---|---|---|
| D1a | Hosting | Stay on the current EC2 instance (no ECS, no load balancer) |
| D2 | Sign-up | Waitlist, joined with Google sign-in; accepted users sign in with the same Google account |
| D3 | Prices | $10/month with 300 credits, a 50-credit free trial for unpaid users, $5 top-ups for 150 credits (to be checked against M0's measured cost) |
| D5 | Rollover | Unused allowance expires each period; trial, top-ups and owner grants don't (recommended, not contested) |
| D8 | Deep coach | In v4; at M0, option c: Opus synopsis and baseline, Sonnet chat, Haiku moments and walkthroughs |
| D9 | Mobile layout | A later version |
| D12 | Owner dashboard | In v4: all users, usage, site stats, paid vs unpaid, accept/revoke access, add credits |
| D1 | Where Postgres runs | Amazon RDS (§12.1) |
| D6a | Minimum age | 13, with parent or guardian agreement for 13–17 (§11) |
| D11 | Account email | Yes, through Amazon SES, starting with the acceptance email (§12.4) |
| D13 | Payment provider | Stripe at launch, US customers only; Paddle (merchant of record) considered later for international sales, so billing is provider-neutral (§6) |

**Still open (at M0):**

| # | Decision | Recommendation |
|---|---|---|
| D4 | Sales tax | Talk to a CPA first. Sell to US customers only (Checkout collects the billing address and accepts US only), with Stripe Tax watching state registration thresholds; turn on collection in a state once its threshold is reached |
| D6 | The terms and privacy text | Owner, reviewed by a lawyer |
| D10 | A domain the owner controls (today: `3-15-12-174.sslip.io`) | Buy one (Route 53 or any registrar) before M2; needed for email, Google sign-in and the payment provider's review |
