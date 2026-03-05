import { useEffect, useRef, useState } from 'react'

export interface CaptionProgress {
  operationId: string
  current: number
  total: number
  message: string
  status: string | null
  isComplete: boolean
  error: string | null
  /** First per-image error message encountered during generation. */
  firstError: string | null
  /** Count of per-image errors reported during generation. */
  errorCount: number
  /** Image IDs that failed all retry attempts (populated on completion). */
  failedImageIds: string[]
}

const INITIAL_STATE: CaptionProgress = {
  operationId: '',
  current: 0,
  total: 0,
  message: '',
  status: null,
  isComplete: false,
  error: null,
  firstError: null,
  errorCount: 0,
  failedImageIds: [],
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
        const msg: string = data.message ?? ''
        const isPerImageError = msg.startsWith('Error captioning ')
        setProgress((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: msg || prev.message,
          status: data.status ?? prev.status,
          // Track per-image errors for surfacing in the completion toast
          firstError: isPerImageError && !prev.firstError ? msg : prev.firstError,
          errorCount: isPerImageError ? prev.errorCount + 1 : prev.errorCount,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "done" -- caption generation completed successfully
    es.addEventListener('done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        const failedIds: string[] = Array.isArray(data.failed_image_ids) ? data.failed_image_ids : []
        setProgress((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Captioning complete',
          status: data.status ?? 'done',
          isComplete: true,
          error: null,
          failedImageIds: failedIds,
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
    // EventSource auto-reconnects by default (readyState goes to CONNECTING).
    // Only treat it as fatal if the connection is fully closed.
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        es.close()
        esRef.current = null
        setProgress((prev) => {
          // If we already received progress, the backend may still be running —
          // mark as complete rather than error so the UI doesn't show a false failure.
          if (prev.current > 0 && prev.current >= prev.total && prev.total > 0) {
            return { ...prev, isComplete: true, status: 'done' }
          }
          return {
            ...prev,
            error: 'Caption connection lost. Check server logs for results.',
            status: 'error',
            isComplete: false,
          }
        })
      }
      // If readyState is CONNECTING, EventSource is auto-reconnecting — do nothing.
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [operationId])

  return progress
}
