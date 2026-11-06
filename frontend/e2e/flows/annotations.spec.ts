import { expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// SPEC_V3 §6.3 on the real board: the scripted coach's chat answer carries a board tag (a blue
// highlight on d5). It is drawn on the position the question was asked from, clears when the
// board moves on, comes back on return and after a reload.
test("the coach's board tag is drawn on its position, and only there", async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Annotations ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 60_000 })

  const coachShapes = page.locator('cg-container svg.cg-shapes circle')
  await page.getByRole('button', { name: /^Moves/ }).click()
  const moves = page.getByLabel('Moves')
  await moves.getByRole('button', { name: '3. Ng5' }).click()
  await page.getByLabel('Your question').fill('What should I look at?')
  await page.getByRole('button', { name: 'Send' }).click()

  const tag = page.getByRole('button', { name: 'Show this on the board' })
  await expect(tag).toBeVisible()
  await expect(page.getByText('E2E chat answer: look at the loose pieces.')).toBeVisible()
  await expect(coachShapes).toHaveCount(1)

  await moves.getByRole('button', { name: '2. Nf3' }).click()
  await expect(coachShapes).toHaveCount(0)
  await moves.getByRole('button', { name: '3. Ng5' }).click()
  await expect(coachShapes).toHaveCount(1)

  // Clicking the tag from elsewhere goes back to the position it is about.
  await moves.getByRole('button', { name: '1. e4' }).click()
  await expect(coachShapes).toHaveCount(0)
  await tag.click()
  await expect(page.getByText(/Your questions are about the board: after 3\. Ng5/)).toBeVisible()
  await expect(coachShapes).toHaveCount(1)

  // Stored with the chat: after a reload, the tag and its drawing come back.
  await page.reload()
  await page.getByRole('button', { name: /^Moves/ }).click()
  await page.getByLabel('Moves').getByRole('button', { name: '3. Ng5' }).click()
  await expect(page.getByRole('button', { name: 'Show this on the board' })).toBeVisible()
  await expect(coachShapes).toHaveCount(1)
})
