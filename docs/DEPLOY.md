# Deploying CoChess v1 on one small server

v1 is for a handful of testers, so it runs on a single machine with Docker Compose: nginx serves the frontend and proxies the API, the FastAPI backend keeps its data in SQLite on a Docker volume, and a reverse proxy in front adds HTTPS.

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
ACCESS_CODE=<a long random string; share it with your testers>
ANTHROPIC_API_KEY=<your key>
```

Generate a code with `openssl rand -base64 18`. **Don't leave `ACCESS_CODE` empty in production**: empty turns the gate off.

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

Check it: open `https://coach.example.com`, enter the access code, analyze a game, and open the "Engine details" line under the result. It should say `stockfish-19-lite` with more than one thread. If it says `stockfish-19-lite-single`, the cross-origin isolation headers aren't reaching the browser; it still works, just more slowly.

## Day-to-day

**Update to a new version**

```bash
git pull
docker compose up --build -d
```

The database lives on the `cochess-data` volume and survives rebuilds.

**Change the access code**: edit `ACCESS_CODE` in `backend/.env`, then `docker compose up -d` (this recreates the backend). Testers are asked for the new code on their next request.

**Logs**

```bash
docker compose logs -f backend
```

Warnings worth watching for: `coach moves removed` (the coach wrote a move that wasn't in the data, even after a retry, and it was removed) and `synopsis too long`.

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

## Limits in v1

- One shared access code; no accounts (real sign-in arrives in v4).
- At most 10 new games a day for the whole server and 30 questions per game (see the configuration table in the README to change them).
- SQLite and a single backend process: fine for a few testers, not for public traffic.
