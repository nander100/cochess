import { expect, test } from '@playwright/test'
import { logIn, newLoginLink } from '../login.ts'
import { rapidGame } from './games.ts'

// Onboarding (SPEC_V2 §10): paste 12 games, see the slots fill, let the queue analyze them, and
// get the baseline report. A reload mid-analysis resumes from the server's status.
test('a player completes the onboarding assessment and gets a baseline report', async ({ page }) => {
  await logIn(page, newLoginLink(`Onboarding ${Date.now()}`), 1200)

  const outcomes: ['white' | 'black', '1-0' | '0-1'][] = [
    ['white', '1-0'], ['white', '0-1'], ['black', '0-1'], ['black', '1-0'],
  ]  // prettier-ignore
  const games = Array.from({ length: 12 }, (_, i) => rapidGame(i, ...outcomes[i % 4]))
  const draw = rapidGame(20, 'white', '1-0').replaceAll('1-0', '1/2-1/2')
  await page.getByLabel(/Paste one or more games/).fill([...games, draw].join('\n\n'))
  await page.getByRole('button', { name: 'Check games' }).click()

  const table = page.locator('table.paste-table')
  await expect(table.locator('tbody tr')).toHaveCount(13)
  await expect(table.getByText("Draws don't fill a slot.")).toBeVisible()
  await page.getByRole('button', { name: 'Add 12 games' }).click()
  await expect(page.getByText('Added 12 games.')).toBeVisible()

  // The queue starts on its own. Reload partway: it picks up where it stopped.
  await expect(page.getByText(/Game \d+ of 12/)).toBeVisible({ timeout: 30_000 })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Games (12 of 12 analyzed)' })).toBeVisible({ timeout: 120_000 })
  for (const name of ['Wins as White', 'Losses as White', 'Wins as Black', 'Losses as Black']) {
    await expect(page.locator('.slot-checklist li', { hasText: name })).toContainText('3/3')
  }

  await page.getByRole('button', { name: 'Write my baseline report' }).click()
  await expect(page.getByText('E2E baseline report.')).toBeVisible()
  await page.getByRole('link', { name: 'Profile' }).click()
  await expect(page.getByRole('region', { name: 'Baseline report' })).toContainText('E2E baseline report.')
})
