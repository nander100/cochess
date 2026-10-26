import { defineConfig } from '@playwright/test'
import { E2E_DATABASE, E2E_DATABASE_URL, TEST_RESULTS } from './e2e/paths.ts'

// E2E runs the real stack: FastAPI (a fresh SQLite file) + Vite dev server + Stockfish in the
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
      // Starts from an empty database every run.
      command: `rm -f ${E2E_DATABASE} && mkdir -p ${TEST_RESULTS} && uv run uvicorn app.main:create_app --factory --port ${BACKEND_PORT}`,
      cwd: '../backend',
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      // The coach calls the paid Claude API, so it's off unless E2E_COACH=1 (an empty key
      // overrides backend/.env and the coach endpoint answers 503).
      env: env({
        DATABASE_URL: E2E_DATABASE_URL,
        PUBLIC_BASE_URL: `http://localhost:${FRONTEND_PORT}`,
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
