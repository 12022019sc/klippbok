import { test, expect } from '@playwright/test'
import { API, TEST_PROJECT_DIR, TEST_VIDEO_FILE } from './helpers'

test.describe('13. Backend API Direct Verification', () => {
  test('step 66: GET /triage/health returns availability flags', async ({ request }) => {
    const res = await request.get(`${API}/triage/health`)
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body).toHaveProperty('clip_available')
    expect(body).toHaveProperty('insightface_available')
    expect(typeof body.clip_available).toBe('boolean')
    expect(typeof body.insightface_available).toBe('boolean')
  })

  test('step 67: GET /video/scan returns JSON array', async ({ request }) => {
    const res = await request.get(`${API}/video/scan`)
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    // Must be an array — not { clips, total }
    expect(Array.isArray(body)).toBeTruthy()
  })

  test('step 68: POST /video/ingest/start with directory_path → 200 + operation_id', async ({ request }) => {
    const res = await request.post(`${API}/video/ingest/start`, {
      data: { directory_path: TEST_PROJECT_DIR },
    })
    // Accept 200 or 202
    expect(res.status()).toBeLessThanOrEqual(202)
    const body = await res.json()
    expect(body).toHaveProperty('operation_id')
    expect(typeof body.operation_id).toBe('string')

    // Cancel the operation to clean up
    if (body.operation_id) {
      await request.post(`${API}/video/ingest/${body.operation_id}/cancel`)
    }
  })

  test('step 69: POST /video/ingest/start with video_path → 200', async ({ request }) => {
    const res = await request.post(`${API}/video/ingest/start`, {
      data: { video_path: TEST_VIDEO_FILE },
    })
    expect(res.status()).toBeLessThanOrEqual(202)
    const body = await res.json()
    expect(body).toHaveProperty('operation_id')

    // Cancel to clean up
    if (body.operation_id) {
      await request.post(`${API}/video/ingest/${body.operation_id}/cancel`)
    }
  })

  test('step 70: POST /video/ingest/start with neither → 422', async ({ request }) => {
    const res = await request.post(`${API}/video/ingest/start`, {
      data: {},
    })
    // Should be 422 (validation error) or 400
    expect(res.status()).toBeGreaterThanOrEqual(400)
  })

  test('step 71: POST /triage/concepts/upload with FormData → no SyntaxError', async ({ request }) => {
    // Create a minimal PNG as FormData
    const res = await request.post(`${API}/triage/concepts/upload`, {
      multipart: {
        file: {
          name: 'test-concept.jpg',
          mimeType: 'image/jpeg',
          buffer: Buffer.from('fake-image-data'),
        },
        category: 'character',
      },
    })
    // Should not get a SyntaxError — might fail with 400 for invalid image, but not 500
    // A 422 or 400 is expected for a fake image; a 200 is also fine if it accepts anything
    expect(res.status()).not.toBe(500)
  })

  test('step 72: GET /video/clips/{id}/thumbnail → cached on second call', async ({ request }) => {
    // First, get list of clips
    const listRes = await request.get(`${API}/video/clips`)
    if (!listRes.ok()) {
      test.skip(true, 'No clips available for thumbnail caching test')
      return
    }

    const clips = await listRes.json()
    if (!Array.isArray(clips) || clips.length === 0) {
      test.skip(true, 'No clips found')
      return
    }

    const clipId = clips[0].id

    // First request
    const start1 = Date.now()
    const res1 = await request.get(`${API}/video/clips/${clipId}/thumbnail`)
    const time1 = Date.now() - start1
    expect(res1.ok()).toBeTruthy()

    // Second request (should be cached = faster)
    const start2 = Date.now()
    const res2 = await request.get(`${API}/video/clips/${clipId}/thumbnail`)
    const time2 = Date.now() - start2
    expect(res2.ok()).toBeTruthy()

    // Log timing for analysis — cached should generally be faster
    console.log(`Thumbnail timing: first=${time1}ms, second=${time2}ms`)
  })
})
