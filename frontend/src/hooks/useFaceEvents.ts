import { useEffect, useRef, useState } from 'react'
import type { FaceProgress } from '../types/triage'

export interface FaceEventState extends FaceProgress {
  error: string | null
  isComplete: boolean
}

const INITIAL_STATE: FaceEventState = {
  current: 0,
  total: 0,
  eta_seconds: 0,
  message: '',
  error: null,
  isComplete: false,
}

/**
 * useFaceEvents subscribes to the SSE progress stream for a face embedding operation.
 *
 * Creates an EventSource connection to /api/v1/triage/face/{operationId}/events when
 * operationId is non-null. Listens for "face_progress", "face_done", "face_error"
 * named SSE events. The face_progress event includes eta_seconds.
 *
 * @param operationId - The face embedding operation ID, or null to skip connection.
 * @returns FaceEventState object with current progress, ETA, and completion status.
 */
export function useFaceEvents(operationId: string | null): FaceEventState {
  const [state, setState] = useState<FaceEventState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setState(INITIAL_STATE)

    const url = `/api/v1/triage/face/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "face_progress" -- intermediate progress update (includes eta_seconds)
    es.addEventListener('face_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<FaceProgress>
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          eta_seconds: data.eta_seconds ?? prev.eta_seconds,
          message: data.message ?? prev.message,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "face_done" -- face embedding completed successfully
    es.addEventListener('face_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<FaceProgress>
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Face embedding complete',
          isComplete: true,
          error: null,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Face embedding complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "face_error" -- face embedding encountered an error
    es.addEventListener('face_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message?: string }
        setState((prev) => ({
          ...prev,
          error: data.message ?? 'Face embedding failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Face embedding failed',
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
        error: 'Face embedding connection lost. The SSE connection was interrupted.',
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
