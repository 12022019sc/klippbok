import { useEffect, useRef, useState } from 'react'

interface TrainingResult {
  lora_path: string | null
  epochs: number
  duration_seconds: number
}

interface TrainingEventsState {
  epoch: number
  totalEpochs: number
  isTraining: boolean
  error: string | null
  logSnippet: string | null
  result: TrainingResult | null
}

const initialState: TrainingEventsState = {
  epoch: 0,
  totalEpochs: 0,
  isTraining: false,
  error: null,
  logSnippet: null,
  result: null,
}

/**
 * SSE hook for OneTrainer training progress events.
 *
 * Connects to /api/v1/export/train/{opId}/events when opId is provided.
 * Handles training_progress, training_error, and training_done events.
 */
export function useTrainingEvents(opId: string | null): TrainingEventsState {
  const [state, setState] = useState<TrainingEventsState>(initialState)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!opId) {
      setState(initialState)
      return
    }

    setState((prev) => ({ ...prev, isTraining: true, error: null, result: null }))

    const es = new EventSource(`/api/v1/export/train/${opId}/events`)
    esRef.current = es

    es.addEventListener('training_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as {
          epoch: number
          total_epochs: number
          message?: string
        }
        setState((prev) => ({
          ...prev,
          epoch: data.epoch,
          totalEpochs: data.total_epochs,
          isTraining: true,
        }))
      } catch {
        // Ignore parse errors
      }
    })

    es.addEventListener('training_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as {
          message: string
          log_snippet?: string
        }
        setState((prev) => ({
          ...prev,
          isTraining: false,
          error: data.message,
          logSnippet: data.log_snippet ?? data.message,
        }))
        es.close()
      } catch {
        // Ignore parse errors
      }
    })

    es.addEventListener('training_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as {
          lora_path: string | null
          epochs: number
          duration_seconds: number
        }
        setState((prev) => ({
          ...prev,
          isTraining: false,
          result: {
            lora_path: data.lora_path,
            epochs: data.epochs,
            duration_seconds: data.duration_seconds,
          },
        }))
        es.close()
      } catch {
        // Ignore parse errors
      }
    })

    es.onerror = () => {
      setState((prev) => ({
        ...prev,
        isTraining: false,
        error: prev.error ?? 'Training connection lost.',
      }))
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [opId])

  return state
}
