import { useEffect, useRef, useState } from 'react'

export interface ExportProgress {
  current: number
  total: number
  message: string
}

export interface ExportResult {
  image_count: number
  config_path: string
  output_dir: string
  preset_path: string | null
}

export interface ExportEventState {
  progress: ExportProgress | null
  result: ExportResult | null
  error: string | null
  isExporting: boolean
}

const INITIAL_STATE: ExportEventState = {
  progress: null,
  result: null,
  error: null,
  isExporting: false,
}

/**
 * useExportEvents subscribes to the SSE progress stream for an export operation.
 *
 * Creates an EventSource connection to /api/v1/export/{opId}/events when
 * opId is non-null. Listens for "export_progress", "export_done", "export_error"
 * named SSE events.
 *
 * @param opId - The export operation ID, or null to skip connection.
 * @returns ExportEventState with progress, result, error, and isExporting flag.
 */
export function useExportEvents(opId: string | null): ExportEventState {
  const [state, setState] = useState<ExportEventState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!opId) {
      setState(INITIAL_STATE)
      return
    }

    // Reset state when a new operation starts
    setState({
      progress: { current: 0, total: 0, message: 'Starting export...' },
      result: null,
      error: null,
      isExporting: true,
    })

    const url = `/api/v1/export/${opId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "export_progress" — intermediate progress update
    es.addEventListener('export_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as Partial<ExportProgress>
        setState((prev) => ({
          ...prev,
          isExporting: true,
          progress: {
            current: data.current ?? prev.progress?.current ?? 0,
            total: data.total ?? prev.progress?.total ?? 0,
            message: data.message ?? prev.progress?.message ?? '',
          },
        }))
      } catch {
        // Ignore malformed events
      }
    })

    // "export_done" — export completed successfully
    es.addEventListener('export_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as {
          current?: number
          total?: number
          message?: string
          image_count?: number
          config_path?: string
          output_dir?: string
          preset_path?: string | null
        }
        setState({
          progress: {
            current: data.current ?? data.image_count ?? 0,
            total: data.total ?? data.image_count ?? 0,
            message: data.message ?? 'Export complete',
          },
          result: {
            image_count: data.image_count ?? 0,
            config_path: data.config_path ?? '',
            output_dir: data.output_dir ?? '',
            preset_path: data.preset_path ?? null,
          },
          error: null,
          isExporting: false,
        })
      } catch {
        setState((prev) => ({
          ...prev,
          isExporting: false,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    // "export_error" — export encountered an error
    es.addEventListener('export_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message?: string }
        setState((prev) => ({
          ...prev,
          error: data.message ?? 'Export failed',
          isExporting: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Export failed',
          isExporting: false,
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
        error: 'Export connection lost. The SSE connection was interrupted.',
        isExporting: false,
      }))
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [opId])

  return state
}
