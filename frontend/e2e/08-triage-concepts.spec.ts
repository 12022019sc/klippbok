import { test, expect } from '@playwright/test'
import { openProject, navigateTo, expectToast, TEST_IMAGE_FILE } from './helpers'
import path from 'path'

test.describe('8. Triage — Concept Upload', () => {
  test.beforeEach(async ({ page }) => {
    await openProject(page)
    await navigateTo(page, 'Triage')
    await expect(page.locator('.triage-layout')).toBeVisible()
  })

  test('step 44: concepts sidebar shows', async ({ page }) => {
    await expect(page.locator('.concepts-panel')).toBeVisible()
    await expect(page.locator('.concepts-panel-header')).toHaveText('Concept References')
  })

  test('steps 45-48: upload concept reference image', async ({ page }) => {
    // Step 45: set category to "character"
    const categoryInput = page.locator('.concepts-panel .face-cluster-name-input')
    await categoryInput.fill('character')

    // Step 46: click "Upload Reference" → file chooser
    const fileChooserPromise = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: 'Upload Reference' }).click()
    const fileChooser = await fileChooserPromise

    // Select the test image
    await fileChooser.setFiles(TEST_IMAGE_FILE)

    // Step 47-48: verify concept uploaded — check toast OR concept thumbnail appearing
    // Toast may auto-dismiss quickly, so primarily verify the concept appears in the grid
    await expect(page.locator('.concepts-grid .concept-thumb')).toBeVisible({ timeout: 15_000 })
  })
})
