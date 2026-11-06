import { expect, test } from '@playwright/test'
import { playMove } from '../board.ts'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// SPEC_V3 §7 with the scripted engine and coach: a variation the player played is walked through
// from its menu. The browser scans each position (the backend had no walkthrough of it yet), the
// coach answers one step per move, the board follows the steps, and Esc goes back to the game.
// The second time, the walkthrough comes from the cache.
test('a variation is walked through step by step, then served from the cache', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Walkthrough ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 60_000 })

  await page.getByRole('button', { name: /^Moves/ }).click()
  const moves = page.getByLabel('Moves')
  await moves.getByRole('button', { name: '1... e5' }).click()
  await playMove(page, 'f1c4', 'white')
  await playMove(page, 'g8f6', 'white') // the board is from White's side

  const walked = page.waitForResponse((r) => r.url().endsWith('/walkthrough') && r.status() === 200)
  await moves.getByRole('button', { name: 'Variation options' }).click()
  await page.getByRole('menuitem', { name: 'Walk me through it' }).click()
  const panel = page.getByRole('region', { name: 'Walkthrough' })
  await expect(panel.getByText('E2E walkthrough intro: watch the centre.')).toBeVisible({ timeout: 30_000 })
  await walked

  await panel.getByRole('button', { name: 'Start ▶' }).click()
  await expect(panel.getByText('Step 1 of 2: 2. Bc4')).toBeVisible()
  await expect(panel.getByText('E2E step 1: a purposeful move.')).toBeVisible()
  await page.keyboard.press('ArrowRight')
  await expect(panel.getByText('E2E takeaway: keep developing.')).toBeVisible()
  // The board shows the step's position: Black's knight has reached f6.
  await expect(page.locator('.board[data-fen]')).toHaveAttribute('data-fen', /\/5n2\//)

  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(page.getByRole('region', { name: 'Chat with your coach' })).toBeVisible()

  // Again: straight from the cache, in one request with no scans.
  const requests: string[] = []
  page.on('request', (r) => {
    if (r.url().endsWith('/walkthrough')) requests.push(r.postData() ?? '')
  })
  await moves.getByRole('button', { name: 'Variation options' }).click()
  await page.getByRole('menuitem', { name: 'Walk me through it' }).click()
  await expect(panel.getByText('E2E walkthrough intro: watch the centre.')).toBeVisible()
  expect(requests).toHaveLength(1)
  expect(JSON.parse(requests[0]).step_results).toEqual([])
})
