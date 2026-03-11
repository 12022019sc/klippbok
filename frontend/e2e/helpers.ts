import fs from 'node:fs'
import path from 'node:path'
import { type Page, expect } from '@playwright/test'

// ── Test data paths ──────────────────────────────────────────────────
export const TEST_PROJECT_DIR = 'C:\\GenAI\\Training\\Instagram\\saskialesterr\\training'
export const TEST_PROJECT_DIR_UNIX = 'C:/GenAI/Training/Instagram/saskialesterr/training'

// A known .mp4 in the test directory
export const TEST_VIDEO_FILE = `${TEST_PROJECT_DIR}\\saskialesterr_1765394212_3784723100785769341_707707417.mp4`

// A known .jpg for concept upload
export const TEST_IMAGE_FILE = `${TEST_PROJECT_DIR}\\saskialesterr_1716031418_3370638293621434272_707707417.jpg`

// ── Base URL ─────────────────────────────────────────────────────────
export const BASE_URL = 'http://localhost:9000'
export const API = `${BASE_URL}/api/v1`

// ── Reusable navigation helpers ──────────────────────────────────────

/**
 * Opens the project picker, types a manual path, and opens the project.
 * After this, the navbar should be visible and the gallery loading.
 *
 * Handles the case where a previous test already opened a project —
 * we first clear project state via the settings API, then re-open.
 */
export async function openProject(page: Page, projectPath: string = TEST_PROJECT_DIR) {
  // Set project via API — most reliable path, avoids picker race conditions
  await page.request.put(`${BASE_URL}/api/v1/settings/`, {
    data: { project_dir: projectPath },
  })

  await page.goto('/')

  const navbar = page.locator('.navbar')

  // Wait for navbar — API-set project should load directly.
  // The picker may flash briefly during React hydration; expect() auto-retries
  // so it will wait through any transient picker flash.
  try {
    await expect(navbar).toBeVisible({ timeout: 10_000 })
  } catch {
    // Navbar didn't appear after 10s — picker is genuinely showing.
    // Use manual input as fallback.
    await page.getByText('Or type a path manually').click()
    await page.locator('#manual-dir').fill(projectPath)
    await page.getByRole('button', { name: 'Open Project' }).click()
    await expect(navbar).toBeVisible({ timeout: 15_000 })
  }
}

/**
 * Navigate to a page via the navbar link text.
 */
export async function navigateTo(page: Page, linkText: string) {
  await page.locator('.nav-links').getByText(linkText, { exact: true }).click()
}

/**
 * Wait for a Sonner toast with matching text to appear.
 */
export async function expectToast(page: Page, text: string | RegExp, timeout = 10_000) {
  const toast = page.locator('[data-sonner-toast]').filter({ hasText: text })
  await expect(toast.first()).toBeVisible({ timeout })
}

/**
 * Wait for a Sonner toast to appear and then dismiss it.
 */
export async function expectAndDismissToast(page: Page, text: string | RegExp, timeout = 10_000) {
  await expectToast(page, text, timeout)
}

/**
 * Ensure the project has a clean, fresh image manifest.
 *
 * Deletes the existing manifest to prevent duplicate accumulation across
 * test runs, then triggers a fresh import and waits for completion.
 */
export async function ensureImagesImported(page: Page, projectPath: string = TEST_PROJECT_DIR) {
  // Nuke stale manifest so imports don't pile up across runs
  const manifestPath = path.join(projectPath, '.klippbok', 'manifest.json')
  try { fs.unlinkSync(manifestPath) } catch { /* doesn't exist yet — fine */ }

  // Clean up scene clip duplicates from prior video ingest test runs
  try {
    for (const f of fs.readdirSync(projectPath)) {
      if (f.includes('_scene')) fs.unlinkSync(path.join(projectPath, f))
    }
  } catch { /* best effort */ }

  // Trigger fresh import via API
  const importRes = await page.request.post(`${API}/import/`, {
    data: { directory: projectPath, recursive: false },
  })
  const { operation_id } = await importRes.json() as { operation_id: string }

  // Wait for import to complete via SSE
  await page.evaluate(async (opId: string) => {
    return new Promise<void>((resolve, reject) => {
      const es = new EventSource(`/api/v1/import/${opId}/events`)
      const timeout = setTimeout(() => { es.close(); reject(new Error('Import timeout')) }, 120_000)
      es.addEventListener('done', () => { clearTimeout(timeout); es.close(); resolve() })
      es.addEventListener('import_error', (e) => {
        clearTimeout(timeout); es.close()
        reject(new Error((e as MessageEvent).data))
      })
      es.onerror = () => { clearTimeout(timeout); es.close(); reject(new Error('Import SSE error')) }
    })
  }, operation_id)
}
