import { expect, test } from '@playwright/test'
import { logIn, logInWithProfile, newLoginLink } from '../login.ts'
import { rapidGame } from './games.ts'

// SPEC_V3 §4.6: testers had games analyzed from the wrong side because White was pre-selected.
// No color is ever selected for the player, on either form.
test('the upload form starts with no color and waits for one', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Color upload ${Date.now()}`), 1200)

  await expect(page.getByLabel('I played White')).not.toBeChecked()
  await expect(page.getByLabel('I played Black')).not.toBeChecked()
  await expect(page.getByText('Choose the color you played first.')).toBeVisible()
  await expect(page.getByLabel(/your game/i)).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Analyze' })).toBeDisabled()

  await page.getByLabel('I played Black').check()
  await expect(page.getByLabel(/your game/i)).toBeEnabled()
  await expect(page.getByText('Choose the color you played first.')).toBeHidden()
})

test('onboarding rows start with no color; submit waits for every row', async ({ page }) => {
  await logIn(page, newLoginLink(`Color onboarding ${Date.now()}`), 1200)
  const games = [rapidGame(0, 'white', '1-0'), rapidGame(1, 'black', '0-1')]
  await page.getByLabel(/Paste one or more games/).fill(games.join('\n\n'))
  await page.getByRole('button', { name: 'Check games' }).click()

  const table = page.locator('table.paste-table')
  await expect(table.locator('tr.needs-color')).toHaveCount(2)
  await expect(page.getByLabel('Your color in game 1')).toHaveValue('')
  await expect(page.getByLabel('Your color in game 2')).toHaveValue('')
  await expect(table.getByText('Detected: you played White')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Choose your color for 2 games' })).toBeDisabled()

  await page.getByLabel('Your color in game 1').selectOption('white')
  await expect(page.getByRole('button', { name: 'Choose your color for 1 game' })).toBeDisabled()
  await page.getByLabel('Your color in game 2').selectOption('black')
  await expect(page.getByRole('button', { name: 'Add 2 games' })).toBeEnabled()
  await expect(table.locator('tr.needs-color')).toHaveCount(0)
})
