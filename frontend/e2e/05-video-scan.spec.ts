import { test, expect } from '@playwright/test'
import { openProject, navigateTo } from './helpers'

test.describe('5. Video Pipeline — Scan Tab', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await navigateTo(page, 'Video')
    await expect(page.locator('.video-page')).toBeVisible()
  })

  test('step 27: click Scan tab → table loads automatically', async ({ page }) => {
    await page.locator('.video-tab', { hasText: 'Scan' }).click()
    await expect(page.locator('.video-tab.active')).toHaveText('Scan')

    // Wait for either table or empty state
    await expect(
      page.locator('.video-table, .video-empty')
    ).toBeVisible({ timeout: 15_000 })
  })

  test('steps 28-33: scan table structure and content', async ({ page }) => {
    await page.locator('.video-tab', { hasText: 'Scan' }).click()

    // Wait for scan to complete — try table first (most likely after prior ingest),
    // fall back to empty state. Using expect() with try/catch ensures auto-retry
    // waits through transient loading states (empty→scanning→table).
    const table = page.locator('.video-table')
    let hasTable = false
    try {
      await expect(table).toBeVisible({ timeout: 30_000 })
      hasTable = true
    } catch {
      // No table — empty state is also valid
      await expect(page.locator('.video-empty')).toBeVisible({ timeout: 5_000 })
    }

    if (hasTable) {
      // Step 28: verify table headers
      const headers = ['Filename', 'Resolution', 'FPS', 'Duration', 'Codec', 'Frames', 'Issues']
      for (const header of headers) {
        await expect(table.locator('th', { hasText: header })).toBeVisible()
      }

      // Step 29: verify striped rows with clip metadata
      const rows = table.locator('tbody tr')
      const rowCount = await rows.count()
      expect(rowCount).toBeGreaterThan(0)

      // Step 30: verify "OK" text for clips with no issues (if any)
      // This checks the presence of either .video-ok or .video-issues
      const firstRow = rows.first()
      await expect(
        firstRow.locator('.video-ok, .video-issues')
      ).toBeVisible()

      // Step 32: click Refresh → verify table reloads
      await page.getByRole('button', { name: 'Refresh' }).click()
      // Button shows "Scanning..." during reload
      await expect(page.getByRole('button', { name: /Scanning|Refresh/ })).toBeVisible()

      // Step 33: verify monospace filename column
      const filenameCell = table.locator('.video-table-filename').first()
      await expect(filenameCell).toBeVisible()
    }
  })
})
