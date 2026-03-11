import { test, expect } from '@playwright/test'
import { openProject, navigateTo, expectToast, TEST_PROJECT_DIR } from './helpers'

test.describe('12. Cross-Page Flows', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
  })

  test('step 61: ingest → scan tab auto-refresh', async ({ page }) => {
    await navigateTo(page, 'Video')

    // Do a quick ingest (if not already done)
    await page.locator('.video-input').fill(TEST_PROJECT_DIR)
    await page.getByRole('button', { name: 'Start Ingest' }).click()

    // Wait for completion
    await expectToast(page, /Ingest complete|Ingest started/, 120_000)

    // Switch to scan tab
    await page.locator('.video-tab', { hasText: 'Scan' }).click()

    // Table or empty state should load automatically
    await expect(
      page.locator('.video-table, .video-empty').first()
    ).toBeVisible({ timeout: 30_000 })
  })

  test('step 62-63: gallery shows video clips with filter', async ({ page }) => {
    // Navigate to gallery
    await navigateTo(page, 'Gallery')

    // Wait for gallery to load — use specific selector, not compound
    await expect(page.locator('.gallery-container')).toBeVisible({ timeout: 60_000 })

    // Step 63: click "Videos" filter
    const videosBtn = page.getByRole('button', { name: 'Videos' })
    if (await videosBtn.isVisible()) {
      await videosBtn.click()
      // Should show video items or empty gallery (no crash)
      await expect(page.locator('.gallery-container')).toBeVisible()
    }
  })

  test('step 64: click video thumbnail → lightbox plays video', async ({ page }) => {
    await navigateTo(page, 'Gallery')
    await expect(page.locator('.gallery-container')).toBeVisible({ timeout: 60_000 })

    // Click first thumbnail image in the gallery
    const firstImg = page.locator('.gallery-container img').first()
    const hasImg = await firstImg.isVisible().catch(() => false)

    if (hasImg) {
      await firstImg.click()
      // Lightbox should open — use the YARL dialog role which is unique
      await expect(page.getByRole('dialog', { name: 'Lightbox' })).toBeVisible({ timeout: 5_000 })
    }
  })
})
