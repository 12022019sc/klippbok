import { useEffect, useRef, useState } from 'react'
import type { TriageProgress } from '../types/triage'

export interface TriageEventState extends TriageProgress {
  error: string | null
  isComplete: boolean
}

const INITIAL_STATE: TriageEventState = {
  current: 0,
  total: 0,
  message: '',
  error: null,
  isComplete: false,
}

/**
 * useTriageEvents subscribes to the SSE progress stream for a CLIP triage operation.
 *
 * Creates an EventSource connection to /api/v1/triage/run/{operationId}/events when
 * operationId is non-null. Listens for "triage_progress", "triage_done", "triage_error"
 * named SSE events.
 *
 * @param operationId - The triage operation ID, or null to skip connection.
 * @returns TriageEventState object with current progress and completion status.
 */
export function useTriageEvents(operationId: string | null): TriageEventState {
  const [state, setState] = useState<TriageEventState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setState(INITIAL_STATE)

    const url = `/api/v1/triage/run/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "triage_progress" -- intermediate progress update
    es.addEventListener('triage_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<TriageProgress>
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

    // "triage_done" -- triage completed successfully
    es.addEventListener('triage_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<TriageProgress>
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Triage complete',
          isComplete: true,
          error: null,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Triage complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "triage_error" -- triage encountered an error
    es.addEventListener('triage_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message?: string }
        setState((prev) => ({
          ...prev,
          error: data.message ?? 'Triage failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Triage failed',
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
        error: 'Triage connection lost. The SSE connection was interrupted.',
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
