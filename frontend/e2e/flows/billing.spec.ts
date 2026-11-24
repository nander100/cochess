import { type Page, expect, test } from '@playwright/test'
import { logIn, newLoginLink } from '../login.ts'

// Paying (SPEC_V4 §6.2) against the E2E backend's fake Stripe (backend/tests/e2e_app.py): the
// Checkout page is a stand-in whose Pay button sends the signed webhooks Stripe would, through
// the real webhook rules. Credits only appear once those have landed.

const SHOTS = new URL('../../test-results/', import.meta.url)

async function shot(page: Page, name: string) {
  await page.screenshot({ path: new URL(`m4-${name}.png`, SHOTS).pathname, fullPage: true })
}

function creditsCard(page: Page) {
  return page.getByRole('region', { name: 'Coaching credits' })
}

async function pay(page: Page, heading: string) {
  await expect(page.getByRole('heading', { name: heading })).toBeVisible()
  await page.getByRole('button', { name: 'Pay (test)' }).click()
  await expect(page).toHaveURL(/\/billing\/return\?product=/)
}

test('a trial player buys credits, then subscribes, and manages the subscription', async ({ page }) => {
  const name = `Payer ${Date.now()}`
  await logIn(page, newLoginLink(name), 1350)
  await page.goto('/profile#credits')
  const card = creditsCard(page)
  await expect(card.getByText(/50 credits left/)).toBeVisible()
  await expect(card.getByText(/Prices are before tax/)).toBeVisible()
  await card.scrollIntoViewIfNeeded()
  await shot(page, '1-credits-card')

  await card.getByRole('button', { name: 'Buy 150 credits for $5' }).click()
  await pay(page, 'Pay for 150 coaching credits')
  await expect(page.getByRole('status')).toHaveText(/150 credits added\. You now have 200 coaching credits\./)
  await shot(page, '2-top-up-arrived')

  await page.getByRole('link', { name: 'See your credits' }).click()
  await creditsCard(page).getByRole('button', { name: 'Subscribe: $10 a month for 300 credits' }).click()
  await pay(page, 'Pay for CoChess monthly')
  await expect(page.getByRole('status')).toHaveText(/300 credits added\. You now have 500 coaching credits\./)

  await page.getByRole('link', { name: 'See your credits' }).click()
  const after = creditsCard(page)
  await expect(after.getByText(/500 credits left/)).toBeVisible()
  await expect(after.getByText(/Your subscription renews on/)).toBeVisible()
  await expect(after.getByRole('button', { name: 'Manage subscription' })).toBeVisible()
  await expect(after.getByRole('button', { name: /Subscribe/ })).toHaveCount(0)
  await expect(after.getByRole('list', { name: 'Recent credit changes' })).toContainText('Monthly allowance+300')
  await after.scrollIntoViewIfNeeded()
  await shot(page, '3-subscribed')
})
