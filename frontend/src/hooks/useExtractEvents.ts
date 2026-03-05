import { useEffect, useRef, useState } from 'react'

export interface ExtractState {
  current: number
  total: number
  message: string
  error: string | null
  isComplete: boolean
}

const INITIAL_STATE: ExtractState = {
  current: 0,
  total: 0,
  message: '',
  error: null,
  isComplete: false,
}

/**
 * useExtractEvents subscribes to the SSE progress stream for a frame extraction operation.
 *
 * Creates an EventSource connection to /api/v1/video/extract/{operationId}/events when
 * operationId is non-null. Uses named event listeners to handle the SSE event types:
 * "extract_progress", "extract_done", "extract_error".
 *
 * @param operationId - The extract operation ID, or null to skip connection.
 * @returns ExtractState object with current, total, message, error, isComplete.
 */
export function useExtractEvents(operationId: string | null): ExtractState {
  const [state, setState] = useState<ExtractState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts (per [05-04 PROC-02] pattern)
    setState(INITIAL_STATE)

    const url = `/api/v1/video/extract/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "extract_progress" -- intermediate progress update
    es.addEventListener('extract_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { current?: number; total?: number; message?: string }
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? prev.message,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "extract_done" -- extraction completed successfully
    es.addEventListener('extract_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { current?: number; total?: number; message?: string }
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Extraction complete',
          isComplete: true,
          error: null,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Extraction complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "extract_error" -- extraction encountered an error
    es.addEventListener('extract_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { error?: string; message?: string }
        setState((prev) => ({
          ...prev,
          error: data.error ?? data.message ?? 'Extraction failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Extraction failed',
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
      setState((prev) => ({
        ...prev,
        error: 'Extract connection lost. The SSE connection was interrupted.',
        isComplete: false,
      }))
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [operationId])

  return state
}
