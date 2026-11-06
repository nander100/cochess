import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// PLAN_V3 M6: a new player sees how to start; after one analyzed game the Games page shows the
// dashboard (recent games, games to continue, accuracy trend), and the filters narrow it.
test('the dashboard grows from the first analyzed game', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Dashboard ${Date.now()}`), 1200)
  await expect(page.getByRole('heading', { name: 'Nothing to show yet' })).toBeVisible()

  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  const gameId = page.url().split('/').at(-1) ?? ''
  await expect.poll(async () => (await (await page.request.get(`/api/games/${gameId}`)).json()).status, {
    timeout: 60_000,
  }).toBe('analyzed')

  await page.getByRole('link', { name: 'Games', exact: true }).click()
  const recent = page.getByRole('table', { name: 'Recent analyzed games' })
  await expect(recent.getByRole('row')).toHaveCount(2)
  await expect(page.getByRole('figure', { name: 'Accuracy trend' })).toBeVisible()
  await expect(page.locator('.dashboard-chart .recharts-surface').first()).toBeVisible()

  await page.getByLabel('Color').selectOption('black')
  await expect(page.getByRole('table', { name: 'Recent analyzed games' })).toBeHidden()
  await page.getByLabel('Color').selectOption('')
  await expect(recent.getByRole('row')).toHaveCount(2)
})
