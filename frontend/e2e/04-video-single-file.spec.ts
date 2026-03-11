import { test, expect } from '@playwright/test'
import { openProject, navigateTo, expectToast, TEST_VIDEO_FILE } from './helpers'

test.describe('4. Video Pipeline — Single File Ingest', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await navigateTo(page, 'Video')
    await expect(page.locator('.video-page')).toBeVisible()
  })

  test('steps 23-26: single file ingest with SSE', async ({ page }) => {
    // Step 23: toggle to single file mode
    await page.getByRole('button', { name: 'Single File' }).click()
    await expect(page.locator('.video-mode-btn.active')).toHaveText('Single File')

    // Step 24: enter path to a single .mp4
    await page.locator('.video-input').fill(TEST_VIDEO_FILE)

    // Step 25: click Start Ingest → verify SSE flow
    await page.getByRole('button', { name: 'Start Ingest' }).click()
    await expectToast(page, 'Ingest started', 15_000)

    // Wait for progress bar
    await expect(page.locator('.video-progress')).toBeVisible({ timeout: 30_000 })

    // Wait for completion
    await expectToast(page, /Ingest complete/, 120_000)

    // Step 26: verify success message with file count
    await expect(page.locator('.video-success')).toBeVisible()
    await expect(page.locator('.video-success')).toContainText(/clip/)
  })
})
