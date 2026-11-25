# Deploying CoChess on one small server

CoChess is for a handful of testers, so it runs on a single machine with Docker Compose: nginx serves the frontend and proxies the API, the FastAPI backend keeps its data in SQLite on a Docker volume, and Caddy in front adds HTTPS.

The chess engine runs in each user's browser, so the server does very little work. A small cloud server (2 vCPU, 2 GB) is plenty.

This guide uses **AWS EC2** and assumes you're new to it. You **don't need a domain**: step 3 gives the server a free hostname from [sslip.io](https://sslip.io), and Caddy gets a real HTTPS certificate for it. If you already have a server or a domain, skip the parts that don't apply.

**Why HTTPS even for testing?** Login cookies are `Secure`, so browsers only send them over HTTPS (or on `localhost`). Over plain `http://<ip>` every login seems to fail. HTTPS also makes the browser run the faster multi-threaded engine.

## 1. Set up your AWS account (once)

1. Sign up at <https://aws.amazon.com>. You'll need a card.
2. **Turn on MFA for the root user**: account menu (top right) → *Security credentials* → *Assign MFA device*.
3. **Set a budget alert** so a forgotten server can't surprise you: search for *Budgets* in the console → *Create budget* → *Use a template* → *Monthly cost budget*, for example $20, with your email.
4. Pick a **region** close to you and your testers (region menu, top right, for example *US East (Ohio)*). Everything below happens in that region.

## 2. Create the server (EC2 instance)

In the console, search for **EC2** → **Launch instance**:

| Setting | Choose |
|---|---|
| Name | `cochess` |
| Application and OS image | **Ubuntu Server 24.04 LTS**, 64-bit (x86) |
| Instance type | **t3.small** (2 vCPU, 2 GB, roughly $15/month). `t3.micro` (1 GB) also works with the swap file in step 4 and may be covered by the AWS Free Tier on your account. |
| Key pair (login) | **Create new key pair** → name `cochess`, type ED25519, format `.pem` → it downloads `cochess.pem`. Keep it safe: it's the only way in. |
| Network settings | **Create security group** with these rules: *Allow SSH traffic from* **My IP**; tick **Allow HTTPS traffic from the internet** and **Allow HTTP traffic from the internet** (Caddy needs port 80 to get the certificate). |
| Configure storage | **20 GiB** gp3 |

Click **Launch instance**.

**Give it a fixed IP address.** A new instance's public IP changes whenever it's stopped, which would break your hostname. EC2 → *Network & Security* → **Elastic IPs** → *Allocate Elastic IP address* → *Allocate*. Then select it → *Actions* → **Associate Elastic IP address** → choose the `cochess` instance → *Associate*. Note the address, for example `3.141.59.26` (AWS charges about $3.60/month for any public IPv4 address).

**Connect to it** from your computer (macOS/Linux terminal, or PowerShell on Windows):

```bash
chmod 400 ~/Downloads/cochess.pem                  # ssh refuses keys others can read
ssh -i ~/Downloads/cochess.pem ubuntu@3.141.59.26  # your Elastic IP; answer "yes" the first time
```

Everything from step 4 on runs on the server, in this SSH session. If SSH stops working later, your home IP probably changed: edit the security group's SSH rule to *My IP* again.

## 3. Your hostname (no domain needed)

sslip.io turns any IP address into a hostname: `3-141-59-26.sslip.io` resolves to `3.141.59.26`. Write your Elastic IP with dashes and add `.sslip.io`. Check it from your computer:

```bash
nslookup 3-141-59-26.sslip.io      # should answer 3.141.59.26
```

Use that hostname everywhere this guide says `coach.example.com`. When you buy a domain later, point it at the Elastic IP and change the hostname in two places, the Caddyfile and `PUBLIC_BASE_URL`, then send new login links.

## 4. Prepare the server

```bash
# Updates
sudo apt update && sudo apt -y upgrade

# 2 GB of swap: building the frontend needs more memory than a small instance has
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker Engine with the Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit        # log out and ssh in again so the docker group applies
```

After you reconnect, `docker compose version` should print a version.

The AWS security group is the firewall: only SSH (from your IP), 80 and 443 are open. The app itself listens on `127.0.0.1` only (step 5), so it's reachable only through Caddy.

## 5. Get the code and configure it

**Option A: copy it from your computer** (works without GitHub). Run this on your computer, from the project folder:

```bash
rsync -av -e "ssh -i ~/Downloads/cochess.pem" \
  --exclude .git --exclude node_modules --exclude .venv --exclude '*.db' \
  --exclude backend/.env --exclude frontend/public/engine --exclude test-results --exclude .claude \
  ./ ubuntu@3.141.59.26:~/cochess/
```

**Option B: clone from GitHub** (after the branch you want is pushed). For a private repository, create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens) with read access to the repository's contents and use it as the password when git asks:

```bash
git clone https://github.com/<you>/cochess.git ~/cochess
```

Then, on the server:

```bash
cd ~/cochess
cp backend/.env.example backend/.env
nano backend/.env        # Ctrl+O, Enter to save; Ctrl+X to quit
```

Set at least:

```bash
ANTHROPIC_API_KEY=<your key>
PUBLIC_BASE_URL=https://3-141-59-26.sslip.io    # your hostname; login links are built from it
IMPORTS__CONTACT=<an email or URL>              # Chess.com asks game-import clients for a contact
```

Game import calls `lichess.org` and `api.chess.com` from the server over HTTPS; EC2's default outbound rules allow it.

Keep the app off the public interface so only Caddy can reach it:

```bash
echo "COCHESS_PORT=127.0.0.1:8080" > .env      # read by docker compose, next to docker-compose.yml
```

## 6. Start it

```bash
docker compose up --build -d     # the first build takes a few minutes
docker compose ps                # backend should become "healthy"
curl -s http://127.0.0.1:8080/api/health    # {"ok":true}
```

The backend brings the database schema up to date itself every time it starts (Alembic migrations). The containers restart on their own after a reboot.

## 7. Add HTTPS with Caddy

[Caddy](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) gets and renews certificates automatically. Install it:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Replace `/etc/caddy/Caddyfile` (`sudo nano /etc/caddy/Caddyfile`) with your hostname:

```
3-141-59-26.sslip.io {
    reverse_proxy 127.0.0.1:8080 {
        # Coach answers are server-sent events: pass them through as they arrive.
        flush_interval -1
    }
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile   # must end with "Valid configuration"
sudo systemctl reload caddy
curl -s https://3-141-59-26.sslip.io/api/health     # {"ok":true} once the certificate is issued
```

The first request can take up to a minute while Caddy gets the certificate. If the reload fails, Caddy keeps its old config and shows its own welcome page: run the `validate` line to see the error (a stray comma or extra text in the site address is common). Manage Caddy with `systemctl` only; `caddy start` fails with "address already in use" because the service is already running. If the page doesn't load, `sudo journalctl -u caddy --no-pager | tail -30` says why; the usual cause is port 80 or 443 missing from the security group. Many people share sslip.io, so Let's Encrypt occasionally refuses it for a while (rate limits); Caddy then gets a certificate from ZeroSSL instead, automatically.

Caddy passes nginx's response headers through unchanged, including `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy`, which multi-threaded Stockfish needs. If you use a different proxy, make sure it doesn't strip them and doesn't buffer `/api/` responses.

## 8. Add players

Create each player once, then send them a login link. A link works once and expires after 7 days; the login it starts lasts 30 days. If someone loses access (new browser, cleared cookies), send a new link.

```bash
docker compose exec backend uv run --no-dev python -m app.cli create-user --name "Alex"
docker compose exec backend uv run --no-dev python -m app.cli invite --user Alex
```

Check it: open your own link (`https://<your hostname>/redeem#token=...`), fill in the profile, analyze a game, and open the "Engine details" line under the board (or tick "Engine" on any game). It should say `stockfish-19-lite` / Stockfish 19 lite with more than one thread. If it says `stockfish-19-lite-single`, the cross-origin isolation headers aren't reaching the browser; it still works, just more slowly.

## Day-to-day

**Update to a new version**

Get the new code (Option B: `git pull` in `~/cochess`; Option A: run the same `rsync` command from your computer again, which leaves the server's `backend/.env` and database alone), then on the server:

```bash
cd ~/cochess
docker compose up --build -d
```

The database lives on the `cochess-data` volume and survives rebuilds, and new migrations run when the backend starts. **Back up the database before updating** (below).

**Upgrading from v2 to v3**: back up the database first (below). Then get the v3 code and add `IMPORTS__CONTACT=<an email or URL>` to `backend/.env`, and rebuild:

```bash
cd ~/cochess
docker compose up --build -d
docker compose logs backend | grep -i -E "alembic|error" | tail     # migrations 0009 to 0018 run once, at startup
docker compose exec -T backend python -c "import sqlite3; print(sqlite3.connect('/data/cochess.db').execute('select version_num from alembic_version').fetchone())"   # ('0018',)
```

Nothing else changes on the server: same volume, same Caddy setup, same headers. Then run the checks below as a player:

1. Open a login link, then the Games page: the dashboard loads (with no games, it says how to start).
2. Profile → *Your online accounts*: save your Chess.com or Lichess username.
3. Games → *Import recent games* → *Fetch games*: your games appear with your color filled in. Add one; it's analyzed in the browser and shows as Analyzed.
4. Open it: the board, critical moments and the coach work; *Export PGN* downloads a file with `[%eval]` comments.
5. Tick "Engine" or open "Engine details": it says `stockfish-19-lite` with more than one thread.
6. In the browser's developer console, the only expected red lines are a `404` for `/api/onboarding/report` (no baseline report yet) and, on a game page, four "Applying inline style violates … style-src" lines from the board library (harmless; the stylesheet sets the same thing).

**Upgrading from v1**: v1's games have no owner, so nobody sees them until you give them to a player. Back up first, then:

```bash
docker compose exec backend uv run --no-dev python -m app.cli create-user --name "Alex"
docker compose exec backend uv run --no-dev python -m app.cli assign-games --user Alex
docker compose exec backend uv run --no-dev python -m app.cli backfill
```

`backfill` rebuilds analyzed games' summaries from their stored engine results (no engine runs), so v1 games get critical moments, theme facts and tendencies, and lists any game uploaded more than once (it deletes nothing). Run it again after any update whose notes say summaries changed. v1's `ACCESS_CODE` setting is no longer used; you can delete it from `backend/.env`.

**Logs**

```bash
docker compose logs -f backend
```

Warnings worth watching for:
- `coach moves removed`: the coach wrote a move that wasn't in the data, even after a retry, and it was removed.
- `moment_leak`: during a critical-moment exercise the coach named the move the player was meant to find, and it was removed. This should never happen; if it does, the exercise's `moment_progress.leaks` count says where.
- `synopsis too long`, `baseline report too long`.

**Back up the database** (safe while running; uses SQLite's backup API):

```bash
docker compose exec -T backend python -c "import sqlite3; sqlite3.connect('/data/cochess.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose cp backend:/data/backup.db ./cochess-$(date +%F).db
```

**Check API spend**

```bash
docker compose exec -T backend uv run --no-dev python -c "
import os
from sqlalchemy import create_engine, text
query = 'select task, model, count(*), sum(input_tokens), sum(output_tokens), sum(cache_read_tokens), sum(cache_write_tokens) from llm_usage group by task, model'
for row in create_engine(os.environ['DATABASE_URL']).connect().execute(text(query)):
    print(tuple(row))"
```

This works on SQLite and, after the move below, on Postgres.

Multiply by the current per-token prices for each model to get the cost.

## Coaching credits (v4)

Every coach call is priced from its tokens and charged to the player's credits (1 credit = $0.01 of API cost). Engine analysis runs in the browser and is never charged. New players get a 50-credit trial when you accept them (or create them with `create-user`).

When the server first runs v4, give the trial to the players you already have, mark your own account (and any testers) as never charged, and price the coach calls recorded before v4 (nobody is charged for those):

```bash
docker compose exec backend uv run --no-dev python -m app.cli grant-trials
docker compose exec backend uv run --no-dev python -m app.cli metering --user "Alex" --off
docker compose exec backend uv run --no-dev python -m app.cli price-usage
```

Add or remove credits for a player (the note is kept with the entry):

```bash
docker compose exec backend uv run --no-dev python -m app.cli grant-credits --user player@example.com --credits 20 --note "beta tester"
```

A player at zero credits can still analyze games and reread any synopsis, walkthrough or report already written; new coach answers wait until they have credits. Each player's coaching also stops for the day after $2 of API cost (`CREDITS__DAILY_CAP_MICROUSD`).

## Payments with Stripe (v4)

Stripe Managed Payments sells CoChess's plans for you: Stripe is the merchant of record, so it adds, collects and files sales tax and VAT, and sends players their receipts. Payments stay off (the Subscribe and Buy buttons are hidden) until `STRIPE__SECRET_KEY` is set.

Once, in Stripe's Dashboard (test mode first):

1. Activate Managed Payments (Settings, Managed Payments) and complete the business details it asks for.
2. Turn on the Customer portal (Settings, Billing, Customer portal) and allow players to cancel and update their payment method.
3. Put the keys in `backend/.env`: `STRIPE__SECRET_KEY` and `STRIPE__PUBLISHABLE_KEY` (Developers, API keys).
4. Create the products and prices (safe to run again; it refuses a live key unless you pass `--live`):

   ```bash
   docker compose exec backend uv run --no-dev python -m scripts.stripe_setup
   ```

5. Add the webhook endpoint (Developers, Webhooks): `https://YOUR-HOSTNAME/api/billing/webhook`, with the events `checkout.session.completed`, `invoice.paid`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted` and `charge.refunded`. Put its signing secret in `STRIPE__WEBHOOK_SECRET` and restart the backend.

On your laptop, the Stripe CLI forwards test webhooks to the dev server and prints the secret to use:

```bash
stripe login
stripe listen --forward-to localhost:8000/api/billing/webhook \
  --events checkout.session.completed,invoice.paid,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,charge.refunded
```

Put the printed `whsec_...` in `STRIPE__WEBHOOK_SECRET` and restart the backend. Newer CLIs refuse `listen` without `--events`. An event that arrived while the secret was missing can be sent again with `stripe events resend <evt_id>` while `listen` runs.

Credits only ever come from these webhooks: if a player paid but has no credits, check the endpoint's recent deliveries in the Dashboard (a failed delivery is retried by Stripe for up to three days). Every event received is kept in the `billing_events` table.

## Google sign-in and account email (v4)

**Google sign-in.** In the [Google Cloud console](https://console.cloud.google.com/):
1. Create a project (for example `cochess`), then *APIs & Services* → *OAuth consent screen*: user type **External**, app name **CoChess**, your support email, and the app's home page and privacy policy links. Scopes: only `openid`, `email` and `profile` (the defaults for sign-in). Leave it in **Testing** and add yourself and your testers as test users (up to 100) until the domain and the privacy policy are ready; then publish it and submit it for brand verification (which needs a domain you own).
2. *Credentials* → *Create credentials* → *OAuth client ID* → **Web application**. Authorized redirect URI: `https://<your hostname>/api/auth/google/callback` (exactly `PUBLIC_BASE_URL` plus that path). No JavaScript origins are needed: the backend does the whole exchange.
3. Put the client ID and secret in `backend/.env` as `GOOGLE__CLIENT_ID` and `GOOGLE__CLIENT_SECRET`, then `docker compose up -d`. The sign-in page's "Continue with Google" now works; without them it says Google sign-in isn't set up.

New players land on the waitlist. Accept one (they get the acceptance email if email is on):

```bash
docker compose exec backend uv run --no-dev python -m app.cli admit --user player@example.com
```

`suspend --user X --reason "..." [--tell-reason]`, `restore --user X` and `set-role --user X --role owner` work the same way (a name or an email). Invite links keep working for players you create with `create-user`; those players can connect Google from their Profile page.

**Account email (Amazon SES)**, in the same region as the server:
1. SES → *Identities* → *Create identity* → **Domain** (needs a domain you own; `sslip.io` won't work). Add the DKIM records it shows to your DNS, plus an SPF record and a DMARC record (`v=DMARC1; p=none;` to start). Wait until the identity says *Verified*.
2. SES → *SMTP settings* → *Create SMTP credentials* (this makes an IAM user that can only send). Keep the username and password.
3. While the account is in the SES sandbox it can only send to verified addresses: verify your own email under *Identities* to test. Before launch, *Account dashboard* → **Request production access** (describe the account emails and that bounces go to SES's suppression list), and turn on the **account-level suppression list** for bounces and complaints.
4. In `backend/.env`: `EMAIL__ENABLED=true`, `EMAIL__SMTP_HOST=email-smtp.<region>.amazonaws.com`, `EMAIL__SMTP_USERNAME`, `EMAIL__SMTP_PASSWORD`, `EMAIL__FROM_ADDRESS="CoChess <account@<your domain>>"`, optional `EMAIL__REPLY_TO`. On staging also `EMAIL__ALLOW_LIST=["you@example.com"]`. Then `docker compose up -d`.

5. Set `EMAIL__LINK_SECRET` to a long random value (`openssl rand -hex 32`) and keep it: it signs the one-click unsubscribe links in the credit emails, and a new secret breaks the links in emails already sent.

Sent, skipped and failed emails are in the `email_outbox` table (kind, player, status, attempts); the logs name the kind and player, never the address.

## Terms, privacy, export and deletion (v4)

**The texts.** `/terms` and `/privacy` show the Markdown files in `LEGAL__TEXTS_DIR` (default: the drafts in `backend/app/legal/texts/`, marked as drafts). Put your lawyer-reviewed `terms.md` and `privacy.md` in a folder on the server, mount it into the backend container (for example `- /srv/legal:/srv/legal:ro` under `volumes` in `docker-compose.yml`) and set `LEGAL__TEXTS_DIR=/srv/legal`.

**Changing the terms.** Update the files, raise `LEGAL__TERMS_VERSION` (for example `2027-01-15`), `docker compose up -d`, then email everyone once:

```bash
docker compose exec backend uv run --no-dev python -m app.cli notify-terms
```

Every signed-in account is asked to accept the new version before it continues; acceptances are in the `terms_acceptances` table.

**Export and deletion** are on each player's Profile page (and on the waitlist and paused pages). Deleting cancels any live subscription in Stripe first (if Stripe refuses, nothing is deleted), then removes the player's games, chats, reports, settings and sessions in one transaction. Coaching costs, credit history, payments and owner actions are kept without the player's id. The owner's own account can't be deleted from the app: make another account the owner first (`set-role`).

## Moving the database to Postgres (RDS)

v4 moves the database from the SQLite file on the `cochess-data` volume to Amazon RDS for PostgreSQL: managed daily backups with point-in-time recovery, and the database the v4 payment features need. It costs about $15 a month (the smallest instance plus 20 GB of storage). Do this once; nothing else on the server changes.

**1. Create the database** (AWS console → RDS → *Create database*), in the same region as the EC2 instance:
- *Standard create*, engine **PostgreSQL**, version 17.
- Template *Dev/Test* (or *Free tier* if offered), deployment **Single-AZ**.
- DB instance identifier `cochess`; master username `cochess`; *Self managed* password: generate a long random one and keep it in your password manager.
- Instance class **db.t4g.micro**; storage **gp3, 20 GB**, storage autoscaling off.
- Connectivity: **Connect to an EC2 compute resource** → choose the `cochess` instance. AWS then creates security groups that only let that instance in. **Public access: No.**
- *Additional configuration*: initial database name `cochess`; backup retention **14 days**; encryption **on**; **deletion protection on**.
- *Create database*. When it's *Available*, copy its **Endpoint** (like `cochess.abc123xyz.us-east-2.rds.amazonaws.com`).

RDS for PostgreSQL 15 and later only accepts encrypted connections (`rds.force_ssl` is on by default), so the URL below asks for TLS.

**2. Check the server can reach it** (on the server):

```bash
docker run --rm postgres:17 psql "postgresql://cochess:<password>@<endpoint>:5432/cochess?sslmode=require" -c "select version()"
```

**3. Back up the SQLite database** (see *Back up the database* above) and keep the file.

**4. Check the SQLite data for anything Postgres would refuse.** v3 ran SQLite without enforcing links between tables or text lengths, and Postgres enforces both:

```bash
docker compose exec backend uv run --no-dev python -m app.cli migrate-sqlite --from sqlite:////data/cochess.db --check-only
```

It should say `No problems found in 19 tables.` If it lists problems, stop and keep the output: each one needs a decision before copying.

**5. Copy.** Stop the frontend first so nobody changes anything mid-copy (the backend keeps running for the command):

```bash
docker compose stop frontend
docker compose exec backend uv run --no-dev python -m app.cli migrate-sqlite --from sqlite:////data/cochess.db --to "postgresql+psycopg://cochess:<password>@<endpoint>:5432/cochess?sslmode=require"
```

It lists each table with its row counts and ends with `every table matches`. If any table says `DIFFERENT`, don't switch: start the frontend again (`docker compose start frontend`) and keep the output.

**6. Switch.** Put the URL in `~/cochess/.env` (next to `docker-compose.yml`, not `backend/.env`; create it if needed, `chmod 600 .env`):

```bash
DATABASE_URL=postgresql+psycopg://cochess:<password>@<endpoint>:5432/cochess?sslmode=require
```

```bash
docker compose up -d
docker compose exec -T backend uv run --no-dev python -c "import os; print(os.environ['DATABASE_URL'].split('@')[-1])"   # the RDS endpoint
```

Then log in and open a game, the dashboard and the profile.

**Going back:** remove the `DATABASE_URL` line from `~/cochess/.env` and run `docker compose up -d`. The SQLite file on the volume is untouched, but anything players did after the switch stays in Postgres only.

**After the move:** RDS backs up daily and keeps 14 days, and can restore to any minute in that window (RDS → the database → *Actions* → *Restore to point in time*). Before each update, also take a manual snapshot (*Actions* → *Take snapshot*). The SQLite backup commands above no longer apply.

## Production for v4 (M8)

The order that works: the domain, then RDS (above), then staging, then monitoring, then the restore drill. Every later release goes to staging first.

### Your domain

1. Buy a domain (any registrar; Route 53 is fine). In its DNS, add **A records** for `cochess.example.com` (or the bare domain) and `staging.cochess.example.com`, both pointing at the server's Elastic IP.
2. Copy `deploy/Caddyfile.example` to `/etc/caddy/Caddyfile`, replace `cochess.example.com` with your domain, then `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`. Caddy gets the certificates; the old `sslip.io` address redirects to the domain.
3. Set `PUBLIC_BASE_URL=https://<your domain>` in `backend/.env`.
4. **Google:** in your OAuth client, add `https://<your domain>/api/auth/google/callback` as a redirect URI, and the domain, terms and privacy pages on the consent screen. Make a **second OAuth client** for staging with `https://staging.<your domain>/api/auth/google/callback`.
5. **SES:** verify the domain (*Account email* above) and request production access.
6. **Stripe:** add the webhook endpoint `https://<your domain>/api/billing/webhook` (and one for staging in test mode), each with its own `STRIPE__WEBHOOK_SECRET`.
7. In both env files: `RATE_LIMITS__PROXY_HOPS=2` (Caddy and nginx sit in front of the backend; the rate limits read the player's address from behind them).

### Staging

Staging is a second Compose project on the same server: its own containers, volume, port (`8081`), log group and database (a `cochess_staging` database on the same RDS instance), with Stripe in test mode and its own Google client.

1. Create the staging database once: `docker run --rm -it postgres:17 psql "postgresql://cochess:<password>@<endpoint>:5432/cochess?sslmode=require" -c "create database cochess_staging"`.
2. `cp backend/.env backend/.env.staging` and change in it: `PUBLIC_BASE_URL=https://staging.<your domain>`, the staging Google client, Stripe **test** keys and the staging webhook secret, `EMAIL__ALLOW_LIST=["you@example.com"]`, and a different `EMAIL__LINK_SECRET`.
3. Create `~/cochess/.env.staging` (next to `docker-compose.yml`, `chmod 600`):

   ```bash
   BACKEND_ENV_FILE=./backend/.env.staging
   COCHESS_PORT=127.0.0.1:8081
   COCHESS_ENV=staging
   DATABASE_URL=postgresql+psycopg://cochess:<password>@<endpoint>:5432/cochess_staging?sslmode=require
   ```

4. Start it: `docker compose --env-file .env.staging -p cochess-staging -f docker-compose.yml -f deploy/docker-compose.aws.yml up -d --build`.

Check it end to end on `https://staging.<your domain>`: join the waitlist with Google, accept yourself from the owner dashboard (`set-role` first, against staging: `docker compose -p cochess-staging exec backend uv run --no-dev python -m app.cli set-role --user you@example.com --role owner`), pay with a Stripe test card, analyze a game, ask the coach.

### Monitoring

1. **Give the server permission** (IAM → *Roles* → the instance's role, or create one and attach it under EC2 → *Actions* → *Security* → *Modify IAM role*): attach `CloudWatchAgentServerPolicy` (logs and metrics).
2. **Logs:** start both projects with `-f deploy/docker-compose.aws.yml` (production: `docker compose -f docker-compose.yml -f deploy/docker-compose.aws.yml up -d --build`). Logs land in CloudWatch Logs under `/cochess/production/backend` and `/cochess/staging/backend`, as JSON lines with a request id; addresses, keys and tokens are blanked before they're written. Set each log group's retention to **30 days** (CloudWatch → *Log groups* → *Actions* → *Edit retention*).
3. **Metrics:** `crontab -e` on the server and add

   ```cron
   * * * * * COCHESS_ENV=production /home/ubuntu/cochess/deploy/monitor.sh
   * * * * * COCHESS_ENV=staging HEALTH_URL=http://127.0.0.1:8081/api/health COMPOSE_PROJECT=cochess-staging /home/ubuntu/cochess/deploy/monitor.sh
   ```

   Every minute: whether `/api/health` answers and how full the disk is; every hour: the last 24 hours of API spend.
4. **Alarms**, from your own computer with the AWS CLI (or CloudShell): `deploy/alarms.sh you@example.com`, then `COCHESS_ENV=staging deploy/alarms.sh you@example.com`. Confirm the subscription email. It sets: health failing for 3 minutes (or not reported), disk above 80%, 5 backend errors in 5 minutes, 3 Anthropic errors in 5 minutes, any payment error, API spend above `SPEND_LIMIT_USD` (default $5) in 24 hours, and a monthly AWS budget (`BUDGET_USD`, default $30, emailed at 80%).
5. **Prove one fires:** `docker compose -p cochess-staging stop backend`, wait 4 minutes for the *health-failing* email, then `docker compose -p cochess-staging start backend` and wait for the *OK* email.

`/api/health` answers 200 only when the database answers and its migrations are at the code's version; anything else is a 503 saying which.

### Releasing

1. `git pull`, then staging: `docker compose --env-file .env.staging -p cochess-staging -f docker-compose.yml -f deploy/docker-compose.aws.yml up -d --build`; check it.
2. Snapshot production's database: `DB_INSTANCE=cochess deploy/snapshot.sh` (waits until it's ready).
3. Production: `docker compose -f docker-compose.yml -f deploy/docker-compose.aws.yml up -d --build`. Migrations run at start; `curl -fsS http://127.0.0.1:8080/api/health` should print `"ok":true`.
4. If the terms changed: `docker compose exec backend uv run --no-dev python -m app.cli notify-terms`.

### Restore drill

Do this once for the M8 checkpoint and every few months after. Nothing touches production.

1. From your computer: `DB_INSTANCE=cochess deploy/restore-drill.sh`. It restores production as of a few minutes ago into a new instance `cochess-restore-drill` (10 to 20 minutes) and prints its endpoint.
2. Point staging at it: in `~/cochess/.env.staging`, set `DATABASE_URL=postgresql+psycopg://cochess:<password>@<drill endpoint>:5432/cochess?sslmode=require` and restart staging (step 1 of *Releasing*).
3. Check: `curl -fsS http://127.0.0.1:8081/api/health`, sign in to staging, open a game and the owner dashboard: production's players and games should be there as of the restore time.
4. Put staging's `DATABASE_URL` back, restart staging, then `DB_INSTANCE=cochess deploy/restore-drill.sh --delete`.

## Pausing it, and stopping the bill

- **Stop** the instance (EC2 → Instances → select it → *Instance state* → *Stop*) to pause it: compute charges stop, but the disk (about $1.60/month for 20 GB) and the Elastic IP (about $3.60/month) still cost. *Start* brings it back with the same address and data.
- **Terminate** it to delete the server and its disk for good: back up the database first (above) and copy it to your computer (`scp -i ~/Downloads/cochess.pem ubuntu@<ip>:~/cochess/cochess-<date>.db .`). Then **release the Elastic IP** (Elastic IPs → *Actions* → *Release*): an unattached Elastic IP is still billed.
- The budget alert from step 1 emails you if spending passes your limit.

## Limits

- Game import fetches at most 50 games at a time, one import per player every 10 seconds, and imported games count toward the daily limit of new games.

- Players join with Google (a waitlist you accept from) or by your invite links.
- At most 10 new games a day per player (onboarding's 12 don't count) and 30 questions per game (see the configuration table in the README to change them).
- Coaching credits: every coach call is charged to the player's credits, and each player stops for the day at $2 of API cost (see *Coaching credits*).
- A single backend process, with SQLite or Postgres (RDS); v4 hardens it for public traffic.
