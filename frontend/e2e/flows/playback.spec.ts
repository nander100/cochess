import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// SPEC_V3 §9.5 with the scripted engine and coach: the chat answer links to the position's top
// engine line; clicking it plays the line on the board, stops with a caption, and "Back to
// position" returns to where the player was.
test('a line link plays on the board and stops with a caption', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Playback ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 60_000 })

  await page.getByRole('button', { name: /^Moves/ }).click()
  await page.getByLabel('Moves').getByRole('button', { name: '3. Ng5' }).click()
  const before = await page.locator('.board[data-fen]').getAttribute('data-fen')
  await page.getByLabel('Your question').fill('What is the plan?')
  await page.getByRole('button', { name: 'Send' }).click()

  await page.getByRole('button', { name: "Play the engine's idea" }).click()
  const bar = page.getByRole('region', { name: 'Line playback' })
  await expect(bar).toBeVisible()
  await expect(bar.getByRole('status')).toBeVisible({ timeout: 30_000 }) // stopped, with a caption
  await expect(page.locator('.board[data-fen]')).not.toHaveAttribute('data-fen', before ?? '')

  await bar.getByRole('button', { name: 'Back to position' }).click()
  await expect(bar).toBeHidden()
  await expect(page.locator('.board[data-fen]')).toHaveAttribute('data-fen', before ?? '')
})
