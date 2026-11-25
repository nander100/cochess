import { readFile } from 'node:fs/promises'
import { type Page, expect, test } from '@playwright/test'
import { logInWithProfile, newLoginLink } from '../login.ts'

// A player's own account (SPEC_V4 §11) against the E2E backend: the public legal pages, the Profile
// page's email switches, downloading everything, and deleting the account. Screenshots for M7.

const SHOTS = new URL('../../test-results/', import.meta.url)

async function shot(page: Page, name: string) {
  await page.screenshot({ path: new URL(`m7-${name}.png`, SHOTS).pathname, fullPage: true })
}

test('the terms and privacy pages are public', async ({ page }) => {
  await page.goto('/privacy')
  await expect(page.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeVisible()
  await expect(page.getByText(/Anthropic's API/).first()).toBeVisible()
  await expect(page.getByText(/^Version /)).toBeVisible()
  await shot(page, '1-privacy')
  await page.goto('/terms')
  await expect(page.getByRole('heading', { level: 1, name: 'Terms of Service' })).toBeVisible()
})

test('a player downloads their data, then deletes their account', async ({ page }) => {
  const name = `Leaver ${Date.now()}`
  await logInWithProfile(page, newLoginLink(name), 1400)
  await page.goto('/profile')

  const email = page.getByRole('region', { name: 'Email' })
  await expect(email.getByLabel(/Low on credits/)).toBeChecked()
  await email.getByLabel(/Credits added/).click()
  await expect(email.getByLabel(/Credits added/)).not.toBeChecked()
  await page.reload()
  await expect(page.getByRole('region', { name: 'Email' }).getByLabel(/Credits added/)).not.toBeChecked()

  const data = page.getByRole('region', { name: 'Your data' })
  await data.scrollIntoViewIfNeeded()
  await shot(page, '2-profile')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    data.getByRole('button', { name: 'Download my data' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^cochess-export-\d{4}-\d{2}-\d{2}\.zip$/)
  const zip = await readFile(await download.path())
  expect(zip.subarray(0, 2).toString()).toBe('PK') // a zip file
  expect(zip.includes(Buffer.from('profile.json'))).toBe(true)

  await data.getByRole('button', { name: 'Delete my account' }).click()
  const dialog = page.getByRole('dialog', { name: 'Delete your account?' })
  await expect(dialog.getByRole('button', { name: 'Delete for good' })).toBeDisabled()
  await dialog.getByLabel(/Type your name/).fill(name)
  await shot(page, '3-delete-dialog')
  await dialog.getByRole('button', { name: 'Delete for good' }).click()

  await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible()
  await shot(page, '4-deleted')
  const status = await page.evaluate(async () => (await fetch('/api/me')).status)
  expect(status).toBe(401)
})
