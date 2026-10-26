import { defineConfig } from '@playwright/test'

// E2E runs the real stack: FastAPI (in-memory SQLite) + Vite dev server + Stockfish in the
// system Google Chrome. Ports differ from the dev defaults so a running dev setup isn't touched.
const BACKEND_PORT = 8001
const FRONTEND_PORT = 5174

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
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    channel: 'chrome',
    headless: true,
  },
  webServer: [
    {
      command: `uv run uvicorn app.main:create_app --factory --port ${BACKEND_PORT}`,
      cwd: '../backend',
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      env: env({ DATABASE_URL: 'sqlite://' }),
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
