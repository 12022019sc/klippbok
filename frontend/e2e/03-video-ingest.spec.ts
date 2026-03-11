import { test, expect } from '@playwright/test'
import { openProject, navigateTo, expectToast, TEST_PROJECT_DIR } from './helpers'

test.describe('3. Video Pipeline — Ingest Tab', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await navigateTo(page, 'Video')
    await expect(page.locator('.video-page')).toBeVisible()
  })

  test('step 11-12: Video page loads with Ingest tab active', async ({ page }) => {
    // Step 11: verify styled page loads
    await expect(page.locator('.page-title')).toHaveText('Video Pipeline')

    // Step 12: verify "Ingest" tab is active
    await expect(page.locator('.video-tab.active')).toHaveText('Ingest')
  })

  test('step 13: Directory mode button is active by default', async ({ page }) => {
    await expect(page.locator('.video-mode-btn.active')).toHaveText('Directory')
  })

  test('step 14-15: Single File toggle switches input field', async ({ page }) => {
    // Step 14: toggle to single file
    await page.getByRole('button', { name: 'Single File' }).click()
    await expect(page.locator('.video-label')).toHaveText('Video file path')

    // Step 15: toggle back to directory
    await page.getByRole('button', { name: 'Directory' }).click()
    await expect(page.locator('.video-label')).toHaveText('Directory path')
  })

  test('step 16: empty directory path → toast error', async ({ page }) => {
    // Ensure directory mode, leave empty
    await page.getByRole('button', { name: 'Start Ingest' }).click()
    await expectToast(page, /Please enter a directory path/)
  })

  test('step 17: empty single file path → toast error', async ({ page }) => {
    await page.getByRole('button', { name: 'Single File' }).click()
    await page.getByRole('button', { name: 'Start Ingest' }).click()
    await expectToast(page, /Please enter a video file path/)
  })

  test('step 18-19: advanced settings toggle', async ({ page }) => {
    // Step 18: show advanced
    await page.getByRole('button', { name: 'Show Advanced' }).click()
    await expect(page.locator('.video-advanced')).toBeVisible()
    // Verify fields: FPS, Resolution, Scene threshold, Max frames
    await expect(page.locator('.video-advanced .video-label').nth(0)).toHaveText('FPS')
    await expect(page.locator('.video-advanced .video-label').nth(1)).toContainText('Resolution')
    await expect(page.locator('.video-advanced .video-label').nth(2)).toContainText('Scene threshold')
    await expect(page.locator('.video-advanced .video-label').nth(3)).toContainText('Max frames')

    // Step 19: hide advanced
    await page.getByRole('button', { name: 'Hide Advanced' }).click()
    await expect(page.locator('.video-advanced')).not.toBeVisible()
  })

  test('steps 20-21: real directory ingest with SSE progress', async ({ page }) => {
    // Step 20: enter real directory path
    await page.locator('.video-input').fill(TEST_PROJECT_DIR)

    // Step 21: click Start Ingest
    await page.getByRole('button', { name: 'Start Ingest' }).click()

    // 21a: button text changes to "Starting..."
    await expect(page.locator('.video-btn-primary')).toContainText(/Starting|Ingesting/)

    // 21b: toast "Ingest started"
    await expectToast(page, 'Ingest started', 15_000)

    // 21c: progress bar appears
    await expect(page.locator('.video-progress')).toBeVisible({ timeout: 30_000 })

    // 21d: cancel button appears
    await expect(page.locator('.video-btn-cancel')).toBeVisible()

    // 21e: progress updates stream via SSE — wait for stage text
    await expect(page.locator('.video-progress-stage')).not.toBeEmpty({ timeout: 30_000 })

    // 21f: on completion — toast "Ingest complete" + success banner
    await expectToast(page, /Ingest complete/, 120_000)
    await expect(page.locator('.video-success')).toBeVisible({ timeout: 5_000 })

    // 21g: "View in Scan tab" link appears
    await expect(page.getByText('View in Scan tab')).toBeVisible()
  })

  test('step 22: cancel ingest', async ({ page }) => {
    await page.locator('.video-input').fill(TEST_PROJECT_DIR)
    await page.getByRole('button', { name: 'Start Ingest' }).click()
    await expectToast(page, 'Ingest started', 15_000)

    // Wait for cancel button to appear
    await expect(page.locator('.video-btn-cancel')).toBeVisible({ timeout: 10_000 })

    // Click cancel
    await page.locator('.video-btn-cancel').click()

    // 22a: toast "Ingest cancelled"
    await expectToast(page, 'Ingest cancelled')

    // 22b: progress bar disappears
    await expect(page.locator('.video-progress')).not.toBeVisible({ timeout: 5_000 })

    // 22c: start button re-enables
    await expect(page.getByRole('button', { name: 'Start Ingest' })).toBeEnabled()
  })
})
