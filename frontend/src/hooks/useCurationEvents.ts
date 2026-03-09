import { useEffect, useRef, useState } from 'react'
import type { CurationProgress, CurationResult } from '../types/curation'

export interface CurationEventState extends CurationProgress {
  error: string | null
  isComplete: boolean
  result: CurationResult | null
}

const INITIAL_STATE: CurationEventState = {
  stage: '',
  current: 0,
  total: 0,
  error: null,
  isComplete: false,
  result: null,
}

/**
 * useCurationEvents subscribes to the SSE progress stream for a curation pipeline operation.
 *
 * Creates an EventSource connection to /api/v1/curation/{operationId}/events when
 * operationId is non-null. Listens for "curation_progress", "curation_done", "curation_error"
 * named SSE events.
 *
 * @param operationId - The curation operation ID, or null to skip connection.
 * @returns CurationEventState object with current progress, completion status, and result.
 */
export function useCurationEvents(operationId: string | null): CurationEventState {
  const [state, setState] = useState<CurationEventState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setState(INITIAL_STATE)

    const url = `/api/v1/curation/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "curation_progress" -- intermediate progress update
    es.addEventListener('curation_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<CurationProgress>
        setState((prev) => ({
          ...prev,
          stage: data.stage ?? prev.stage,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "curation_done" -- curation completed successfully
    es.addEventListener('curation_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { result?: CurationResult }
        setState((prev) => ({
          ...prev,
          isComplete: true,
          error: null,
          result: data.result ?? null,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "curation_error" -- curation encountered an error
    es.addEventListener('curation_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message?: string }
        setState((prev) => ({
          ...prev,
          error: data.message ?? 'Curation pipeline failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Curation pipeline failed',
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
        error: 'Curation connection lost. The SSE connection was interrupted.',
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
