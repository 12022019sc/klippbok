import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAppStore } from '../stores/appStore'

/**
 * useImportEvents subscribes to the SSE progress stream for an import operation.
 *
 * Creates an EventSource connection to /api/v1/import/{operationId}/events when
 * operationId is non-null. Uses named event listeners (addEventListener) to
 * handle the three named SSE event types: "progress", "done", "import_error".
 *
 * @param operationId - The import operation ID, or null to skip connection.
 */
export function useImportEvents(operationId: string | null): void {
  const queryClient = useQueryClient()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) return

    const url = `/api/v1/import/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    // "progress" -- intermediate progress update
    es.addEventListener('progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        useAppStore.getState().setImportProgress({
          current: data.current,
          total: data.total,
          message: data.message,
        })
      } catch {
        // Ignore malformed events
      }
    })

    // "done" -- import completed successfully
    es.addEventListener('done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        es.close()
        esRef.current = null
        toast.success(
          data.message || 'Import complete',
          { description: `${data.current} of ${data.total} images imported` },
        )
        useAppStore.getState().clearImport()
        queryClient.invalidateQueries({ queryKey: ['images'] })
      } catch {
        es.close()
        esRef.current = null
        toast.success('Import complete')
        useAppStore.getState().clearImport()
        queryClient.invalidateQueries({ queryKey: ['images'] })
      }
    })

    // "import_error" -- import encountered an error
    es.addEventListener('import_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        es.close()
        esRef.current = null
        toast.error('Import failed', { description: data.message })
        useAppStore.getState().clearImport()
      } catch {
        es.close()
        esRef.current = null
        toast.error('Import failed')
        useAppStore.getState().clearImport()
      }
    })

    // Network-level error (connection dropped, server unreachable)
    es.onerror = () => {
      es.close()
      esRef.current = null
      toast.error('Import connection lost', {
        description: 'The SSE connection was interrupted.',
      })
      useAppStore.getState().clearImport()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [operationId, queryClient])
}
