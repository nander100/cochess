import { defineConfig } from '@playwright/test'
import { E2E_DATABASE, E2E_DATABASE_URL, TEST_RESULTS } from './e2e/paths.ts'

// E2E runs FastAPI (a fresh SQLite file) + the Vite dev server in the system Google Chrome. Ports
// differ from the dev defaults so a running dev setup isn't touched.
//
// By default the flows run against a scripted engine (src/test/scriptedEngine.ts, swapped in by
// E2E_FAKE_ENGINE) and a scripted coach (backend tests/e2e_app.py): fast, the same every run, and
// free. E2E_REAL_ENGINE=1 runs the v1 test instead: real Stockfish on an owner game (real coach
// too with E2E_COACH=1, which calls the paid API).
const BACKEND_PORT = 8001
const FRONTEND_PORT = 5174

// E2E_BASE_URL (e.g. http://localhost:8080) runs against an already running stack, such as the
// production `docker compose up`, instead of starting dev servers.
const EXTERNAL_URL = process.env.E2E_BASE_URL
const REAL_ENGINE = process.env.E2E_REAL_ENGINE === '1'

function env(extra: Record<string, string>): Record<string, string> {
  const base = Object.entries(process.env).filter(
    (entry): entry is [string, string] => entry[1] !== undefined,
  )
  return { ...Object.fromEntries(base), ...extra }
}

export default defineConfig({
  testDir: './e2e',
  testMatch: REAL_ENGINE ? 'analysis.spec.ts' : 'flows/*.spec.ts',
  timeout: REAL_ENGINE ? 10 * 60_000 : 90_000,
  workers: 1, // one backend and database for every test
  reporter: [['list']],
  use: {
    baseURL: EXTERNAL_URL ?? `http://localhost:${FRONTEND_PORT}`,
    channel: 'chrome',
    headless: true,
  },
  webServer: EXTERNAL_URL ? [] : [
    {
      // Starts from an empty database every run.
      command: `rm -f ${E2E_DATABASE} && mkdir -p ${TEST_RESULTS} && uv run uvicorn ${REAL_ENGINE ? 'app.main:create_app' : 'tests.e2e_app:make'} --factory --port ${BACKEND_PORT}`,
      cwd: '../backend',
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      // The real coach calls the paid Claude API, so it's off unless E2E_COACH=1 (an empty key
      // overrides backend/.env: the real app's coach answers 503, the scripted one needs none).
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
      env: env({ BACKEND_URL: `http://localhost:${BACKEND_PORT}`, E2E_FAKE_ENGINE: REAL_ENGINE ? '0' : '1' }),
      reuseExistingServer: false,
    },
  ],
})
