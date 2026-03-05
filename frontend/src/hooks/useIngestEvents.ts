import { useEffect, useRef, useState } from 'react'

export interface IngestState {
  stage: string
  current: number
  total: number
  message: string
  error: string | null
  isComplete: boolean
}

const INITIAL_STATE: IngestState = {
  stage: '',
  current: 0,
  total: 0,
  message: '',
  error: null,
  isComplete: false,
}

/**
 * useIngestEvents subscribes to the SSE progress stream for a video ingest operation.
 *
 * Creates an EventSource connection to /api/v1/video/ingest/{operationId}/events when
 * operationId is non-null. Uses named event listeners to handle the SSE event types:
 * "ingest_progress", "ingest_done", "ingest_error".
 *
 * @param operationId - The ingest operation ID, or null to skip connection.
 * @returns IngestState object with stage, current, total, message, error, isComplete.
 */
export function useIngestEvents(operationId: string | null): IngestState {
  const [state, setState] = useState<IngestState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts (per [05-04 PROC-02] pattern)
    setState(INITIAL_STATE)

    const url = `/api/v1/video/ingest/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "ingest_progress" -- intermediate progress update
    es.addEventListener('ingest_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { stage?: string; current?: number; total?: number; message?: string }
        setState((prev) => ({
          ...prev,
          stage: data.stage ?? prev.stage,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? prev.message,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "ingest_done" -- ingest completed successfully
    es.addEventListener('ingest_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { stage?: string; current?: number; total?: number; message?: string }
        setState((prev) => ({
          ...prev,
          stage: data.stage ?? prev.stage,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Ingest complete',
          isComplete: true,
          error: null,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Ingest complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "ingest_error" -- ingest encountered an error
    es.addEventListener('ingest_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { error?: string; message?: string }
        setState((prev) => ({
          ...prev,
          error: data.error ?? data.message ?? 'Ingest failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Ingest failed',
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
        error: 'Ingest connection lost. The SSE connection was interrupted.',
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
