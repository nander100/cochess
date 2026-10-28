import { Chess } from 'chess.js'
import { expect, test } from '@playwright/test'
import { playMove } from '../board.ts'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// Login → upload → board → synopsis → chat and Explain → a critical moment, with the scripted
// engine and coach (playwright.config.ts).
test('a player uploads a game, reads the coach, and steps through a critical moment', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle') // Vite can reload once while it bundles
  await expect(page.getByRole('alert')).toContainText("You're not logged in")

  await logInWithProfile(page, newLoginLink(`Coaching ${Date.now()}`), 1200)
  await page.getByLabel('White', { exact: true }).check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()

  // Board: the game opens on the analysis board once the engine is done.
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  const gameId = page.url().split('/').at(-1) ?? ''
  await expect(page.locator('cg-board')).toBeVisible()
  await page.getByRole('button', { name: '3. Ng5' }).click()
  await expect(page.locator('.eval-bar')).toBeVisible()

  // Synopsis: written on its own after the upload, behind a spoiler while moments are unsolved.
  const spoiler = page.getByText(/Show the synopsis \(spoilers/)
  await expect(spoiler).toBeVisible()
  await spoiler.click()
  await expect(page.getByText('E2E synopsis: a fighting game.')).toBeVisible()

  // Chat and Explain, about the position on the board.
  await page.getByLabel('Your question').fill('Why was that bad?')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('E2E chat answer: look at the loose pieces.')).toBeVisible()
  await page.getByRole('button', { name: 'Explain this position' }).click()
  await expect(page.getByText('E2E explanation: both sides are developing.')).toBeVisible()

  // Critical moments: 3. Ng5?? is one of them.
  const detail = await (await page.request.get(`/api/games/${gameId}`)).json()
  const moment = detail.moments.find((m: { san: string }) => m.san === 'Ng5')
  expect(moment).toBeDefined()
  expect(moment.best_san).toBeNull() // withheld until solved or revealed
  await page.getByRole('tab', { name: /Critical moments/ }).click()
  await page.getByRole('list', { name: 'Moments in this game' }).getByRole('button', { name: /Ng5/ }).click()
  await page.getByRole('button', { name: 'Start this moment' }).click()
  await expect(page.getByText('E2E moment: what would you play here instead?')).toBeVisible()
  await expect(page.getByText(/The engine is off/)).toBeVisible()

  // Try a legal move other than the game's, as a player would: click it on the board.
  const fen = detail.moves[moment.ply - 1].fen_before
  const tryUci = 'd2d4'
  expect(new Chess(fen).moves({ verbose: true }).some((m) => m.lan === tryUci)).toBe(true)
  await playMove(page, tryUci, 'white')
  await expect(page.getByText(/Your move: 3\. d4/)).toBeVisible()
  await page.getByLabel(/Why this move/).fill('Take the centre.')
  await page.getByRole('button', { name: 'Check my move' }).click()
  await expect(page.locator('.moment-grade')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/E2E (feedback|moment)/).last()).toBeVisible()

  // "Show me" reveals the engine's move and unlocks the board.
  if (await page.getByRole('button', { name: 'Show me' }).isVisible()) {
    await page.getByRole('button', { name: 'Show me' }).click()
  }
  await expect(page.getByText(/The engine's move:/)).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/The engine is off/)).toBeHidden()
})
