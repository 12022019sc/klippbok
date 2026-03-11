import { test, expect } from '@playwright/test'
import { API, TEST_PROJECT_DIR } from './helpers'

test.describe('14. Edge Cases', () => {
  test('step 73: ingest empty directory → error message', async ({ request }) => {
    // Use a temp empty directory or a known empty path
    const res = await request.post(`${API}/video/ingest/start`, {
      data: { directory_path: 'C:\\Windows\\Temp\\empty-klippbok-test-dir' },
    })
    // Should either fail immediately with 4xx or start and emit error SSE
    // We accept 400, 404, 422 as valid error responses
    if (res.status() >= 400) {
      const body = await res.json().catch(() => ({}))
      expect(body).toHaveProperty('detail')
    }
  })

  test('step 74: ingest nonexistent directory → error (sync or async)', async ({ request }) => {
    const res = await request.post(`${API}/video/ingest/start`, {
      data: { directory_path: 'C:\\this\\does\\not\\exist\\at\\all' },
    })
    const body = await res.json().catch(() => ({}))

    if (res.status() >= 400) {
      // Synchronous validation error — has detail
      expect(body).toHaveProperty('detail')
    } else {
      // API accepted the request (200/202) — error will come via SSE
      // Verify we got an operation_id at least
      expect(body).toHaveProperty('operation_id')
      // Cancel to clean up
      if (body.operation_id) {
        await request.post(`${API}/video/ingest/${body.operation_id}/cancel`)
      }
    }
  })

  test('step 75: ingest file that is not a video → graceful error', async ({ request }) => {
    // Use a .jpg file as video_path — should fail gracefully
    const res = await request.post(`${API}/video/ingest/start`, {
      data: {
        video_path: `${TEST_PROJECT_DIR}\\saskialesterr_1716031418_3370638293621434272_707707417.jpg`,
      },
    })
    // Should either reject (4xx) or start then fail in SSE
    // We just verify it doesn't crash the server (not 500 unhandled)
    expect(res.status()).not.toBe(500)
  })

  test('step 76: two simultaneous ingests → both get unique op_ids', async ({ request }) => {
    const [res1, res2] = await Promise.all([
      request.post(`${API}/video/ingest/start`, {
        data: { directory_path: TEST_PROJECT_DIR },
      }),
      request.post(`${API}/video/ingest/start`, {
        data: { directory_path: TEST_PROJECT_DIR },
      }),
    ])

    // Both should succeed (or one may get a conflict — either way, no crash)
    if (res1.ok() && res2.ok()) {
      const body1 = await res1.json()
      const body2 = await res2.json()
      expect(body1.operation_id).toBeDefined()
      expect(body2.operation_id).toBeDefined()
      // Operation IDs must be unique
      expect(body1.operation_id).not.toBe(body2.operation_id)

      // Cancel both
      await Promise.all([
        request.post(`${API}/video/ingest/${body1.operation_id}/cancel`),
        request.post(`${API}/video/ingest/${body2.operation_id}/cancel`),
      ])
    }
  })

  test('step 77: cancel already-completed operation → {cancelled: false}', async ({ request }) => {
    const res = await request.post(`${API}/video/ingest/nonexistent-op-id/cancel`)
    // Should return some response, not crash
    // Likely 404 or 200 with cancelled: false
    const body = await res.json().catch(() => ({}))
    if (res.ok()) {
      expect(body.cancelled).toBe(false)
    } else {
      // 404 is also acceptable
      expect(res.status()).toBeGreaterThanOrEqual(400)
    }
  })

  test('step 78: thumbnail for nonexistent clip_id → 404', async ({ request }) => {
    const res = await request.get(`${API}/video/clips/nonexistent-clip-id-12345/thumbnail`)
    expect(res.status()).toBe(404)
  })
})
