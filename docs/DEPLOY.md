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
```

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
sudo systemctl reload caddy
curl -s https://3-141-59-26.sslip.io/api/health     # {"ok":true} once the certificate is issued
```

The first request can take up to a minute while Caddy gets the certificate. If it doesn't work, `sudo journalctl -u caddy --no-pager | tail -30` says why; the usual cause is port 80 or 443 missing from the security group. Many people share sslip.io, so Let's Encrypt occasionally refuses it for a while (rate limits); Caddy then gets a certificate from ZeroSSL instead, automatically.

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
docker compose exec -T backend python -c "
import sqlite3
db = sqlite3.connect('/data/cochess.db')
for row in db.execute('select model, count(*), sum(input_tokens), sum(output_tokens), sum(cache_read_tokens) from llm_usage group by model'):
    print(row)"
```

Multiply by the current per-token prices for each model to get the cost.

## Pausing it, and stopping the bill

- **Stop** the instance (EC2 → Instances → select it → *Instance state* → *Stop*) to pause it: compute charges stop, but the disk (about $1.60/month for 20 GB) and the Elastic IP (about $3.60/month) still cost. *Start* brings it back with the same address and data.
- **Terminate** it to delete the server and its disk for good: back up the database first (above) and copy it to your computer (`scp -i ~/Downloads/cochess.pem ubuntu@<ip>:~/cochess/cochess-<date>.db .`). Then **release the Elastic IP** (Elastic IPs → *Actions* → *Release*): an unattached Elastic IP is still billed.
- The budget alert from step 1 emails you if spending passes your limit.

## Limits

- Login links from the owner only; Google sign-in arrives in v4.
- At most 10 new games a day per player (onboarding's 12 don't count) and 30 questions per game (see the configuration table in the README to change them).
- Optional: `USER_DAILY_TOKEN_LIMIT` in `backend/.env` caps each player's Claude tokens per rolling 24 hours (off by default).
- SQLite and a single backend process: fine for a few testers, not for public traffic.
