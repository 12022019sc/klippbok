import { useState } from 'react'
import { toast } from 'sonner'
import { useAppStore } from '../stores/appStore'
import { useImportEvents } from '../hooks/useImportEvents'

/**
 * ImportPage lets the user select a directory, optionally enable recursive
 * scanning, and start a batch import. Progress is streamed via SSE.
 */
export default function ImportPage() {
  const [directory, setDirectory] = useState('')
  const [recursive, setRecursive] = useState(false)
  const [loading, setLoading] = useState(false)

  const importOperationId = useAppStore((s) => s.importOperationId)
  const importProgress = useAppStore((s) => s.importProgress)
  const setImportOperationId = useAppStore((s) => s.setImportOperationId)

  // Subscribe to SSE events for the active operation
  useImportEvents(importOperationId)

  const isImporting = importOperationId !== null

  async function handleStartImport() {
    if (!directory.trim()) {
      toast.error('Please enter a directory path')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/v1/import/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: directory.trim(), recursive }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start import', { description: err.detail })
        return
      }

      const data = await res.json()
      setImportOperationId(data.operation_id)
      toast.info('Import started', { description: `Scanning: ${directory.trim()}` })
    } catch (err) {
      toast.error('Failed to start import', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="page-title">Import Images</h1>
      <p className="page-subtitle">
        Scan a directory and import images into the project. Progress streams in real time.
      </p>

      <div className="import-form">
        <div className="import-field">
          <label htmlFor="directory" className="import-label">
            Directory Path
          </label>
          <input
            id="directory"
            type="text"
            className="import-input"
            placeholder="/path/to/images"
            value={directory}
            onChange={(e) => setDirectory(e.target.value)}
            disabled={isImporting}
          />
        </div>

        <div className="import-checkbox-row">
          <label className="import-checkbox-label">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              disabled={isImporting}
            />
            <span>Scan subdirectories recursively</span>
          </label>
        </div>

        <button
          className="import-button"
          onClick={handleStartImport}
          disabled={isImporting || loading}
        >
          {loading ? 'Starting...' : isImporting ? 'Importing...' : 'Start Import'}
        </button>
      </div>

      {isImporting && importProgress && (
        <div className="import-progress">
          <div className="import-progress-header">
            <span className="import-progress-label">Import in progress</span>
            {importProgress.total > 0 && (
              <span className="import-progress-count">
                {importProgress.current} / {importProgress.total}
              </span>
            )}
          </div>
          <div className="import-progress-bar-track">
            <div
              className="import-progress-bar-fill"
              style={{
                width:
                  importProgress.total > 0
                    ? `${Math.round((importProgress.current / importProgress.total) * 100)}%`
                    : '0%',
              }}
            />
          </div>
          <p className="import-progress-message">{importProgress.message}</p>
        </div>
      )}

      {isImporting && !importProgress && (
        <div className="import-progress">
          <p className="import-progress-message">Connecting to import stream...</p>
        </div>
      )}
    </div>
  )
}
