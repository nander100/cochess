import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'

// SPEC_V3 §10 with Chess.com faked by the e2e backend: the player's recent games are fetched,
// reviewed (their color found from the username), added, analyzed, and marked on a second fetch.
test('recent games are imported from Chess.com and analyzed', async ({ page }) => {
  const name = `e2e_import_${Date.now()}`
  await logInWithProfile(page, newLoginLink(`Import ${name}`), 1200)
  await page.goto('/profile')
  const accounts = page.getByRole('form', { name: 'Your online accounts' })
  await accounts.getByLabel('Chess.com username').fill(name)
  await accounts.getByRole('button', { name: 'Save usernames' }).click()
  await expect(accounts.getByRole('status')).toHaveText('Saved')

  await page.getByRole('link', { name: 'Games', exact: true }).click()
  const panel = page.getByRole('region', { name: 'Import recent games' })
  await panel.getByRole('button', { name: 'Fetch games' }).click()
  const table = panel.getByRole('table', { name: 'Fetched games' })
  await expect(table.getByRole('row')).toHaveCount(3)
  await expect(table.getByText('From your username')).toHaveCount(1)

  // The second game isn't the player's (no username): leave it out.
  await table.getByLabel('Add Somebody vs Rival1').uncheck()
  await panel.getByRole('button', { name: 'Add and analyze 1 game' }).click()

  await expect(page.getByText('Added and analyzed 1 game.')).toBeVisible({ timeout: 60_000 })
  const all = page.getByRole('table', { name: 'All games' })
  await expect(all.getByText('Rival0')).toBeVisible()
  await expect(all.getByText('Analyzed')).toBeVisible()

  await panel.getByRole('button', { name: 'Fetch games' }).click()
  await expect(table.getByText('Already added')).toBeVisible()
})

// SPEC_V3 §10, assessment path, with Lichess faked: "Import from Lichess" fills the paste box,
// the player's own game gets its color from the username and fills a slot, and it's stored once.
test('the assessment imports games from Lichess into the paste table', async ({ page }) => {
  const name = `e2e_lichess_${Date.now()}`
  await logInWithProfile(page, newLoginLink(`Lichess ${name}`), 1200)
  await page.goto('/profile')
  const accounts = page.getByRole('form', { name: 'Your online accounts' })
  await accounts.getByLabel('Lichess username').fill(name)
  await accounts.getByRole('button', { name: 'Save usernames' }).click()
  await expect(accounts.getByRole('status')).toHaveText('Saved')

  await page.goto('/onboarding')
  await page.getByRole('button', { name: 'Import from Lichess' }).click()

  const table = page.locator('table.paste-table')
  await expect(table.locator('tbody tr')).toHaveCount(2)
  await expect(page.getByLabel(/Paste one or more games/)).toHaveValue(new RegExp(`\\[White "${name}"\\]`))
  await expect(table.getByText('From your username')).toHaveCount(1)
  await expect(page.getByLabel('Your color in game 1')).toHaveValue('white')
  // The other game isn't the player's: it waits for a color, so Add waits too.
  await expect(page.getByRole('button', { name: 'Choose your color for 1 game' })).toBeDisabled()
  await page.getByLabel('Your color in game 2').selectOption('black')
  await page.getByRole('button', { name: 'Add 2 games' }).click()
  await expect(page.getByText('Added 2 games.')).toBeVisible()

  await page.goto('/games')
  const panel = page.getByRole('region', { name: 'Import recent games' })
  await panel.getByLabel('From').selectOption('lichess')
  await panel.getByRole('button', { name: 'Fetch games' }).click()
  await expect(panel.getByRole('table', { name: 'Fetched games' }).getByText('Already added')).toHaveCount(2)
})
