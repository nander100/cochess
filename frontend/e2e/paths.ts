import { fileURLToPath } from 'node:url'

export const TEST_RESULTS = fileURLToPath(new URL('../test-results', import.meta.url))
// A file, not in-memory, so the test can create a player with the owner CLI (e2e/login.ts).
export const E2E_DATABASE = `${TEST_RESULTS}/e2e.db`
export const E2E_DATABASE_URL = `sqlite:///${E2E_DATABASE}`
export const BACKEND_DIR = fileURLToPath(new URL('../../backend', import.meta.url))
