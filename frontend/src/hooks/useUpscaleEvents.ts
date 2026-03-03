import { useEffect, useRef, useState } from 'react'

export interface UpscaleProgress {
  current: number
  total: number
  message: string
  status: string | null
  isComplete: boolean
  error: string | null
}

const INITIAL_STATE: UpscaleProgress = {
  current: 0,
  total: 0,
  message: '',
  status: null,
  isComplete: false,
  error: null,
}

/**
 * useUpscaleEvents subscribes to the SSE progress stream for an upscale operation.
 *
 * Creates an EventSource connection to /api/v1/upscale/{operationId}/events when
 * operationId is non-null. Uses named event listeners to handle the three named
 * SSE event types: "progress", "done", "upscale_error".
 *
 * @param operationId - The upscale operation ID, or null to skip connection.
 * @returns UpscaleProgress state object.
 */
export function useUpscaleEvents(operationId: string | null): UpscaleProgress {
  const [progress, setProgress] = useState<UpscaleProgress>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setProgress(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setProgress(INITIAL_STATE)

    const url = `/api/v1/upscale/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "progress" -- intermediate progress update
    es.addEventListener('progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? prev.message,
          status: data.status ?? prev.status,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "done" -- upscale completed successfully
    es.addEventListener('done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Upscaling complete',
          status: data.status ?? 'done',
          isComplete: true,
          error: null,
        }))
      } catch {
        setProgress((prev) => ({
          ...prev,
          message: 'Upscaling complete',
          status: 'done',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "upscale_error" -- upscale encountered an error
    es.addEventListener('upscale_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          error: data.message ?? 'Upscaling failed',
          status: 'error',
          isComplete: false,
        }))
      } catch {
        setProgress((prev) => ({
          ...prev,
          error: 'Upscaling failed',
          status: 'error',
          isComplete: false,
        }))
      }
      es.close()
      esRef.current = null
    })

    // Network-level error (connection dropped, server unreachable)
    es.onerror = () => {
      es.close()
      esRef.current = null
      setProgress((prev) => ({
        ...prev,
        error: 'Upscale connection lost. The SSE connection was interrupted.',
        status: 'error',
        isComplete: false,
      }))
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [operationId])

  return progress
}
