import { execFileSync } from 'node:child_process'
import type { Page } from '@playwright/test'
import { BACKEND_DIR, E2E_DATABASE_URL } from './paths.ts'

/**
 * A one-time login link for a new player, made with the owner CLI against the E2E database.
 * Against an already running stack (E2E_BASE_URL) the test can't reach its database: pass a
 * link from `python -m app.cli invite` in E2E_LOGIN_LINK instead.
 */
export function newLoginLink(name: string): string {
  if (process.env.E2E_BASE_URL) {
    const link = process.env.E2E_LOGIN_LINK
    if (!link) throw new Error('E2E_BASE_URL needs E2E_LOGIN_LINK (from `python -m app.cli invite`).')
    return link
  }
  const cli = (...args: string[]) =>
    execFileSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
      cwd: BACKEND_DIR,
      env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
      encoding: 'utf8',
    })
  cli('create-user', '--name', name)
  const link = cli('invite', '--user', name).trim().split('\n').at(-1)
  if (!link?.includes('/redeem#token=')) throw new Error(`Unexpected invite output: ${link}`)
  return link
}

/** Open the login link and fill in the profile, landing on the analysis page. */
export async function logInWithProfile(page: Page, link: string, elo: number): Promise<void> {
  const url = new URL(link)
  await page.goto(`${url.pathname}${url.hash}`)
  await page.getByLabel(/rating/i).fill(String(elo))
  await page.getByLabel(/time control/i).selectOption('rapid')
  await page.getByRole('button', { name: /^Save/ }).click()
  await page.getByLabel(/your game/i).waitFor()
}
