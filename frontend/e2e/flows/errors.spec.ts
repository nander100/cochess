import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

test('a used login link and logging out say what to do next', async ({ page }) => {
  const link = newLoginLink(`Errors ${Date.now()}`)
  await logInWithProfile(page, link, 1200)

  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page.getByRole('alert')).toContainText("You're not logged in")

  const url = new URL(link)
  await page.goto(`${url.pathname}${url.hash}`)
  await expect(page.getByRole('alert')).toContainText('expired or was already used')
})

test('upload errors are explained', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Upload errors ${Date.now()}`), 1200)
  const input = page.getByLabel(/your game/i)
  const analyze = page.getByRole('button', { name: 'Analyze' })

  // An illegal move names the move.
  await input.fill('1. e4 e5 2. Ke3 Nc6 *')
  await analyze.click()
  await expect(page.getByRole('alert')).toContainText('Move 2 (White): Ke3 is not a legal move')

  // A non-standard start is refused.
  await input.fill('[SetUp "1"]\n[FEN "8/8/8/8/8/8/8/K6k w - - 0 1"]\n\n1. Kb1 *')
  await analyze.click()
  await expect(page.getByRole('alert')).toContainText(/standard/i)

  // The same game twice.
  await input.fill(HUNG_KNIGHT)
  await analyze.click()
  await expect(page).toHaveURL(/\/games\//, { timeout: 60_000 })
  await page.getByRole('link', { name: 'Analyze a game' }).first().click()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page.getByRole('alert')).toContainText("You've already uploaded this game")
})

test('a game that is not yours is not found', async ({ page, browser }) => {
  await logInWithProfile(page, newLoginLink(`Owner ${Date.now()}`), 1200)
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  const gamePath = new URL(page.url()).pathname

  const other = await browser.newPage()
  await logInWithProfile(other, newLoginLink(`Other ${Date.now()}`), 1200)
  await other.goto(gamePath)
  await expect(other.getByRole('alert')).toContainText("That game doesn't exist, or it isn't yours.")
  await other.close()
})
