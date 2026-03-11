import { test, expect } from '@playwright/test'
import { openProject, navigateTo, expectToast, ensureImagesImported } from './helpers'

test.describe('9. Triage — CLIP Triage Run', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await ensureImagesImported(page)
    await navigateTo(page, 'Triage')
    await expect(page.locator('.triage-layout')).toBeVisible()
  })

  test('steps 50-51: threshold slider controls', async ({ page }) => {
    const slider = page.locator('.threshold-slider')
    await expect(slider).toBeVisible()

    // Step 50: adjust threshold slider
    await slider.fill('0.75')

    // Verify label updates to show the new value
    const label = page.locator('.threshold-label')
    await expect(label).toContainText('0.75')

    // Step 51: verify borderline range label updates
    // Borderline is threshold - 0.1 to threshold
    await expect(label).toContainText('borderline')
  })

  test('steps 52-54: run CLIP triage with SSE', { timeout: 120_000 }, async ({ page }) => {
    // Check if CLIP is available — if not, skip this test
    const clipWarning = page.locator('.triage-warning-banner', { hasText: 'CLIP model not available' })
    const clipUnavailable = await clipWarning.isVisible().catch(() => false)

    if (clipUnavailable) {
      test.skip(true, 'CLIP model not available — skipping triage run test')
      return
    }

    // Step 52: click "Run Triage"
    await page.getByRole('button', { name: 'Run Triage' }).click()

    // 52a: button changes to "Running..." (may be brief for small datasets)
    // For small datasets, triage can complete very quickly — the progress bar
    // may never appear because it completes before the first SSE tick.
    // So we wait for either progress OR results.

    // CLIP model may need to load on first run — allow up to 3 minutes
    await expect(
      page.locator('.triage-progress, .triage-summary-stats').first()
    ).toBeVisible({ timeout: 60_000 })

    // If progress is showing, verify cancel button and wait for results
    const progressVisible = await page.locator('.triage-progress').isVisible().catch(() => false)
    if (progressVisible) {
      // 52c: SSE events stream with current/total
      await expect(page.locator('.triage-progress-label')).not.toBeEmpty({ timeout: 30_000 })

      // 52d: Cancel button appears
      await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible()
    }

    // 52e-f: Wait for completion — triage_done event fires, results appear
    await expect(page.locator('.triage-summary-stats')).toBeVisible({ timeout: 60_000 })

    // Verify result stats: Match/Borderline/No Match/Total
    await expect(page.locator('.triage-stat--match')).toBeVisible()
    await expect(page.locator('.triage-stat--borderline')).toBeVisible()
    await expect(page.locator('.triage-stat--no-match')).toBeVisible()

    // Step 54: click "Reload Results" → verify persisted results reload
    await page.getByRole('button', { name: 'Reload Results' }).click()
    // Results should still be visible after reload
    await expect(page.locator('.triage-summary-stats')).toBeVisible({ timeout: 10_000 })
  })

  test('step 53: cancel triage run', async ({ page }) => {
    const clipWarning = page.locator('.triage-warning-banner', { hasText: 'CLIP model not available' })
    const clipUnavailable = await clipWarning.isVisible().catch(() => false)

    if (clipUnavailable) {
      test.skip(true, 'CLIP model not available — skipping cancel test')
      return
    }

    await page.getByRole('button', { name: 'Run Triage' }).click()

    // Wait for cancel button
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible({ timeout: 10_000 })

    // 53a: click cancel — operation stops
    await page.getByRole('button', { name: 'Cancel' }).click()

    // 53b: cancel button disappears
    await expect(page.getByRole('button', { name: 'Cancel' })).not.toBeVisible({ timeout: 5_000 })

    // 53c: Run Triage button re-enabled
    await expect(page.getByRole('button', { name: 'Run Triage' })).toBeEnabled({ timeout: 5_000 })
  })
})
