import { useEffect, useRef, useState } from 'react'
import type { CleanupClassification, CleanupProgress } from '../types/cleanup'

export interface CleanupEventState extends CleanupProgress {
  error: string | null
  isComplete: boolean
  results: CleanupClassification[]
}

const INITIAL_STATE: CleanupEventState = {
  current: 0,
  total: 0,
  message: '',
  error: null,
  isComplete: false,
  results: [],
}

/**
 * useCleanupEvents subscribes to the SSE progress stream for a cleanup scan operation.
 *
 * Creates an EventSource connection to /api/v1/cleanup/{operationId}/events when
 * operationId is non-null. Listens for "cleanup_progress", "cleanup_done", "cleanup_error"
 * named SSE events.
 *
 * @param operationId - The cleanup operation ID, or null to skip connection.
 * @returns CleanupEventState object with current progress, completion status, and results.
 */
export function useCleanupEvents(operationId: string | null): CleanupEventState {
  const [state, setState] = useState<CleanupEventState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setState(INITIAL_STATE)

    const url = `/api/v1/cleanup/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "cleanup_progress" -- intermediate progress update
    es.addEventListener('cleanup_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<CleanupProgress>
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

    // "cleanup_done" -- cleanup completed successfully
    es.addEventListener('cleanup_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as {
          current?: number
          total?: number
          message?: string
          results?: CleanupClassification[]
        }
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Cleanup scan complete',
          isComplete: true,
          error: null,
          results: data.results ?? prev.results,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Cleanup scan complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "cleanup_error" -- cleanup encountered an error
    es.addEventListener('cleanup_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message?: string }
        setState((prev) => ({
          ...prev,
          error: data.message ?? 'Cleanup scan failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Cleanup scan failed',
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
        error: 'Cleanup connection lost. The SSE connection was interrupted.',
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
