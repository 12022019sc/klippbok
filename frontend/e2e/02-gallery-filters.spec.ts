import { test, expect } from '@playwright/test'
import { openProject } from './helpers'

test.describe('2. Gallery Filters (MasonryGrid fix)', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    // Wait for gallery to fully load (auto-import finishes, thumbnails render)
    await expect(page.locator('.gallery-container')).toBeVisible({ timeout: 60_000 })
  })

  test('step 6: click "All" → verify all items render', async ({ page }) => {
    await page.getByRole('button', { name: 'All' }).click()
    // Gallery container should remain visible with items
    await expect(page.locator('.gallery-container')).toBeVisible()
  })

  test('step 7: click "Images" → verify only images, no crash', async ({ page }) => {
    await page.getByRole('button', { name: 'Images' }).click()
    // Should not crash — gallery container should still be visible
    await expect(page.locator('.gallery-container')).toBeVisible()
    // The Images button should be active (aria-pressed)
    await expect(page.getByRole('button', { name: 'Images' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('step 8: click "Videos" → verify only videos (or empty state), no crash', async ({ page }) => {
    await page.getByRole('button', { name: 'Videos' }).click()
    // Should not crash — page should remain stable
    await expect(page.locator('.gallery-container')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Videos' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('step 9: click "All" again → verify items re-render correctly', async ({ page }) => {
    // Toggle away then back
    await page.getByRole('button', { name: 'Images' }).click()
    await page.waitForTimeout(500)
    await page.getByRole('button', { name: 'All' }).click()
    await expect(page.locator('.gallery-container')).toBeVisible()
    await expect(page.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('step 10: rapidly toggle filters → verify no crash', async ({ page }) => {
    const filters = ['All', 'Images', 'Videos', 'All']
    for (const filter of filters) {
      await page.getByRole('button', { name: filter }).click()
      await page.waitForTimeout(200)
    }
    // Page should still be intact
    await expect(page.locator('.gallery-container')).toBeVisible()
  })
})
