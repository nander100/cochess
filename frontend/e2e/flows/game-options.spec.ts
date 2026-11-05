import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// PLAN_V3 M1: a game analyzed from the wrong side can be switched to the other color (the
// analysis is redone from stored engine work, topping up any missing positions in the browser),
// and a game can be deleted.
test('a game analyzed as the wrong color is switched, then deleted', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Game options ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  const gameId = page.url().split('/').at(-1) ?? ''
  const heading = page.locator('.game-heading')
  await expect(heading).toContainText('you played white')

  const options = page.getByRole('region', { name: 'Game options' })
  await options.getByRole('button', { name: 'I played Black' }).click()
  await options.getByRole('button', { name: 'Switch to Black' }).click()

  await expect(heading).toContainText('you played black')
  // Any positions Black needs verified are analyzed on their own; then the game is ready again.
  await expect.poll(async () => (await (await page.request.get(`/api/games/${gameId}`)).json()).status, {
    timeout: 60_000,
  }).toBe('analyzed')
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 30_000 })

  await options.getByRole('button', { name: 'Delete game' }).click()
  await page.getByRole('alertdialog', { name: 'Delete game' }).getByRole('button', { name: 'Delete game' }).click()

  await expect(page).toHaveURL(/\/games$/)
  await expect(page.getByRole('heading', { name: 'No games yet' })).toBeVisible()
  expect((await page.request.get(`/api/games/${gameId}`)).status()).toBe(404)
})
