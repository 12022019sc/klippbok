import { useEffect, useRef, useState } from 'react'

export interface CaptionProgress {
  operationId: string
  current: number
  total: number
  message: string
  status: string | null
  isComplete: boolean
  error: string | null
}

const INITIAL_STATE: CaptionProgress = {
  operationId: '',
  current: 0,
  total: 0,
  message: '',
  status: null,
  isComplete: false,
  error: null,
}

/**
 * useCaptionEvents subscribes to the SSE progress stream for a caption operation.
 *
 * Creates an EventSource connection to /api/v1/captions/{operationId}/events when
 * operationId is non-null. Uses named event listeners to handle the three named
 * SSE event types: "progress", "done", "caption_error".
 *
 * Mirrors the useUpscaleEvents pattern.
 *
 * @param operationId - The caption operation ID, or null to skip connection.
 * @returns CaptionProgress state object.
 */
export function useCaptionEvents(operationId: string | null): CaptionProgress {
  const [progress, setProgress] = useState<CaptionProgress>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setProgress(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setProgress({ ...INITIAL_STATE, operationId })

    const url = `/api/v1/captions/${operationId}/events`
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

    // "done" -- caption generation completed successfully
    es.addEventListener('done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Captioning complete',
          status: data.status ?? 'done',
          isComplete: true,
          error: null,
        }))
      } catch {
        setProgress((prev) => ({
          ...prev,
          message: 'Captioning complete',
          status: 'done',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "caption_error" -- caption generation encountered an error
    es.addEventListener('caption_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          error: data.message ?? 'Captioning failed',
          status: 'error',
          isComplete: false,
        }))
      } catch {
        setProgress((prev) => ({
          ...prev,
          error: 'Captioning failed',
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
        error: 'Caption connection lost. The SSE connection was interrupted.',
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
