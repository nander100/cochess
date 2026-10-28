# Deploying CoChess on one small server

CoChess is for a handful of testers, so it runs on a single machine with Docker Compose: nginx serves the frontend and proxies the API, the FastAPI backend keeps its data in SQLite on a Docker volume, and a reverse proxy in front adds HTTPS.

The chess engine runs in each user's browser, so the server does very little work. A 1 vCPU / 1–2 GB VPS is plenty.

## 1. Prepare the server

- A Linux VPS (Ubuntu 24.04 or similar) with a domain name pointing at it (for example `coach.example.com`).
- Install Docker Engine with the Compose plugin: <https://docs.docker.com/engine/install/>.
- Open only ports 22 (SSH), 80 and 443 in the firewall.

## 2. Get the code and configure it

```bash
git clone <your repo URL> cochess
cd cochess
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```bash
ANTHROPIC_API_KEY=<your key>
PUBLIC_BASE_URL=https://coach.example.com    # login links are built from it
```

Players log in with one-time links you create (step 5); links are built from `PUBLIC_BASE_URL`, so set it to the HTTPS address players use. Session cookies are `Secure`, so CoChess must be served over HTTPS (step 4): over plain HTTP on a non-localhost address the browser drops the cookie and every login seems to fail.

Keep the app off the public interface so only the HTTPS proxy can reach it:

```bash
echo "COCHESS_PORT=127.0.0.1:8080" > .env      # read by docker compose, next to docker-compose.yml
```

## 3. Start it

```bash
docker compose up --build -d
docker compose ps            # backend should become "healthy"
curl -s http://127.0.0.1:8080/api/health    # {"ok":true}
```

The backend brings the database schema up to date itself every time it starts (Alembic migrations).

## 4. Add HTTPS with Caddy

[Caddy](https://caddyserver.com/docs/install) gets and renews certificates automatically. Install it on the host, then put this in `/etc/caddy/Caddyfile`:

```
coach.example.com {
    reverse_proxy 127.0.0.1:8080 {
        # Coach answers are server-sent events: pass them through as they arrive.
        flush_interval -1
    }
}
```

```bash
sudo systemctl reload caddy
```

Caddy passes nginx's response headers through unchanged, including `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy`, which multi-threaded Stockfish needs. If you use a different proxy, make sure it doesn't strip them and doesn't buffer `/api/` responses.

## 5. Add players

Create each player once, then send them a login link. A link works once and expires after 7 days; the login it starts lasts 30 days. If someone loses access (new browser, cleared cookies), send a new link.

```bash
docker compose exec backend uv run --no-dev python -m app.cli create-user --name "Alex"
docker compose exec backend uv run --no-dev python -m app.cli invite --user Alex
```

Check it: open your own link, fill in the profile, analyze a game, and open the "Engine details" line under the board (or tick "Engine" on any game). It should say `stockfish-19-lite` / Stockfish 19 lite with more than one thread. If it says `stockfish-19-lite-single`, the cross-origin isolation headers aren't reaching the browser; it still works, just more slowly.

## Day-to-day

**Update to a new version**

```bash
git pull
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

## Limits

- Login links from the owner only; Google sign-in arrives in v4.
- At most 10 new games a day per player (onboarding's 12 don't count) and 30 questions per game (see the configuration table in the README to change them).
- Optional: `USER_DAILY_TOKEN_LIMIT` in `backend/.env` caps each player's Claude tokens per rolling 24 hours (off by default).
- SQLite and a single backend process: fine for a few testers, not for public traffic.
