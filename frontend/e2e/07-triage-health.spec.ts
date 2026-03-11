import { test, expect } from '@playwright/test'
import { openProject, navigateTo } from './helpers'

test.describe('7. Triage — Health Check', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await navigateTo(page, 'Triage')
  })

  test('steps 40-43: triage page health check banners', async ({ page }) => {
    // Step 40: verify triage page loads
    await expect(page.locator('.triage-layout')).toBeVisible()
    await expect(page.locator('.page-title')).toHaveText('Triage')

    // Wait a moment for health check to complete
    await page.waitForTimeout(2000)

    // Steps 41-43: check banner state
    // If CLIP is available, no warning banner in CLIP section
    // If CLIP is unavailable, warning banner shows "CLIP model not available"
    const clipWarning = page.locator('.triage-warning-banner', { hasText: 'CLIP model not available' })
    const clipWarningVisible = await clipWarning.isVisible().catch(() => false)

    if (clipWarningVisible) {
      // Step 43: if CLIP unavailable, verify correct warning
      await expect(clipWarning).toContainText('pip install torch transformers')
    }
    // Step 41: if no warning, CLIP is available — that's the expected good state

    // Similarly for InsightFace
    const insightWarning = page.locator('.triage-info-banner', { hasText: 'InsightFace not installed' })
    const insightWarningVisible = await insightWarning.isVisible().catch(() => false)

    if (insightWarningVisible) {
      await expect(insightWarning).toContainText('pip install insightface onnxruntime')
    }
  })
})
