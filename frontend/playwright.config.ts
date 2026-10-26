import { defineConfig } from '@playwright/test'

// E2E runs the real stack: FastAPI (in-memory SQLite) + Vite dev server + Stockfish in the
// system Google Chrome. Ports differ from the dev defaults so a running dev setup isn't touched.
const BACKEND_PORT = 8001
const FRONTEND_PORT = 5174
// E2E_BASE_URL (e.g. http://localhost:8080) runs against an already running stack, such as the
// production `docker compose up`, instead of starting dev servers.
const EXTERNAL_URL = process.env.E2E_BASE_URL

function env(extra: Record<string, string>): Record<string, string> {
  const base = Object.entries(process.env).filter(
    (entry): entry is [string, string] => entry[1] !== undefined,
  )
  return { ...Object.fromEntries(base), ...extra }
}

export default defineConfig({
  testDir: './e2e',
  timeout: 10 * 60_000,
  reporter: [['list']],
  use: {
    baseURL: EXTERNAL_URL ?? `http://localhost:${FRONTEND_PORT}`,
    channel: 'chrome',
    headless: true,
  },
  webServer: EXTERNAL_URL ? [] : [
    {
      command: `uv run uvicorn app.main:create_app --factory --port ${BACKEND_PORT}`,
      cwd: '../backend',
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      // The coach calls the paid Claude API, so it's off unless E2E_COACH=1 (an empty key
      // overrides backend/.env and the coach endpoint answers 503).
      env: env({
        DATABASE_URL: 'sqlite://',
        ACCESS_CODE: process.env.E2E_ACCESS_CODE ?? '', // gate off unless a code is given
        ...(process.env.E2E_COACH === '1' ? {} : { ANTHROPIC_API_KEY: '' }),
      }),
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      env: env({ BACKEND_URL: `http://localhost:${BACKEND_PORT}` }),
      reuseExistingServer: false,
    },
  ],
})
