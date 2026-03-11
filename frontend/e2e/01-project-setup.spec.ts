import { test, expect } from '@playwright/test'
import { TEST_PROJECT_DIR, BASE_URL } from './helpers'

test.describe('1. Project Setup', () => {
  test('steps 1-5: open project and verify navbar + gallery', async ({ page }) => {
    // Clear any existing project so we see the picker
    await page.request.delete(`${BASE_URL}/api/v1/settings/project`).catch(() => {})

    // Step 1: Open http://localhost:9000
    await page.goto('/')

    // Step 2: Verify project picker renders
    await expect(page.locator('.picker-container')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.picker-title')).toHaveText('klippbok')

    // Step 3: Type test project path → click "Open Project"
    await page.getByText('Or type a path manually').click()
    await page.locator('#manual-dir').fill(TEST_PROJECT_DIR)
    await page.getByRole('button', { name: 'Open Project' }).click()

    // Step 4: Verify navbar appears with all 7 links
    await expect(page.locator('.navbar')).toBeVisible({ timeout: 15_000 })
    const expectedLinks = ['Gallery', 'Import', 'Video', 'Crop', 'Caption', 'Triage', 'Settings']
    for (const link of expectedLinks) {
      await expect(
        page.locator('.nav-links').getByText(link, { exact: true })
      ).toBeVisible()
    }

    // Step 5: Verify gallery loads with thumbnails
    // Gallery auto-imports then renders — wait for the gallery container
    await expect(page.locator('.gallery-container')).toBeVisible({ timeout: 60_000 })
  })
})
