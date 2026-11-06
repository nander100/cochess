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

// SPEC_V3 §10, assessment path, with Lichess faked: the import picks only games that fill an
// empty slot (the player's own White loss), says which slots are still short, and stores it once.
test('the assessment imports games from Lichess into the paste table', async ({ page }) => {
  const name = `e2e_lichess_${Date.now()}`
  await logInWithProfile(page, newLoginLink(`Lichess ${name}`), 1200)
  await page.goto('/profile')
  const accounts = page.getByRole('form', { name: 'Your online accounts' })
  await accounts.getByLabel('Lichess username').fill(name)
  await accounts.getByRole('button', { name: 'Save usernames' }).click()
  await expect(accounts.getByRole('status')).toHaveText('Saved')

  await page.goto('/onboarding')
  await page.getByRole('button', { name: 'Import 12 games from Lichess' }).click()

  // Only the player's own game fills a slot (a White loss); the other game isn't theirs.
  const table = page.locator('table.paste-table')
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await expect(page.getByLabel(/Paste one or more games/)).toHaveValue(new RegExp(`\\[White "${name}"\\]`))
  await expect(table.getByText('From your username')).toHaveCount(1)
  await expect(page.getByText(/Picked 1 game from your last 2 Lichess games/)).toBeVisible()
  await expect(page.getByText(/Still needed: 3 white wins, 2 white losses, 3 black wins, 3 black losses/)).toBeVisible()
  await page.getByRole('button', { name: 'Add 1 game' }).click()
  await expect(page.getByText('Added 1 game.')).toBeVisible()

  await page.goto('/games')
  const panel = page.getByRole('region', { name: 'Import recent games' })
  await panel.getByLabel('From').selectOption('lichess')
  await panel.getByRole('button', { name: 'Fetch games' }).click()
  await expect(panel.getByRole('table', { name: 'Fetched games' }).getByText('Already added')).toHaveCount(1)
})
