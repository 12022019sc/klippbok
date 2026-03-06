import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useCleanupEvents } from '../hooks/useCleanupEvents'
import { useAppStore } from '../stores/appStore'
import type { CleanupClassification } from '../types/cleanup'

export default function CleanupPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [operationId, setOperationId] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const hasAutoStarted = useRef(false)

  const cleanupAutoStart = useAppStore((s) => s.cleanupAutoStart)
  const setCleanupAutoStart = useAppStore((s) => s.setCleanupAutoStart)
  const cleanupResults = useAppStore((s) => s.cleanupResults)
  const setCleanupResults = useAppStore((s) => s.setCleanupResults)
  const cleanupUnflaggedIds = useAppStore((s) => s.cleanupUnflaggedIds)
  const toggleCleanupUnflag = useAppStore((s) => s.toggleCleanupUnflag)
  const clearCleanup = useAppStore((s) => s.clearCleanup)

  const events = useCleanupEvents(operationId)

  // Store results when scan completes
  useEffect(() => {
    if (events.isComplete && events.results.length > 0) {
      setCleanupResults(events.results)
      setOperationId(null) // disconnect SSE
    }
  }, [events.isComplete, events.results, setCleanupResults])

  // Auto-start behavior
  useEffect(() => {
    if (hasAutoStarted.current) return
    const shouldAutoStart = cleanupAutoStart || searchParams.get('autostart') === 'true'
    if (shouldAutoStart) {
      hasAutoStarted.current = true
      setCleanupAutoStart(false)
      startScan()
    }
  }, [cleanupAutoStart, searchParams, setCleanupAutoStart])

  async function startScan() {
    clearCleanup()
    try {
      const res = await fetch('/api/v1/cleanup/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start cleanup scan', { description: (err as { detail: string }).detail })
        return
      }
      const data = (await res.json()) as { operation_id: string }
      setOperationId(data.operation_id)
    } catch (err) {
      toast.error('Failed to start cleanup scan', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  async function handleCancel() {
    if (!operationId) return
    try {
      await fetch(`/api/v1/cleanup/${operationId}/cancel`, { method: 'POST' })
    } catch {
      // best-effort cancel
    }
    setOperationId(null)
  }

  async function handleConfirm() {
    const flaggedPaths = getFlaggedItems().map((item) => item.item_path)
    if (flaggedPaths.length === 0) {
      toast.info('No items to remove')
      return
    }

    setConfirming(true)
    try {
      const res = await fetch('/api/v1/cleanup/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_paths: flaggedPaths }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to confirm removal', { description: (err as { detail: string }).detail })
        return
      }
      const data = (await res.json()) as { moved: number; review_dir: string }
      toast.success(`${data.moved} items moved to _review/`, { description: data.review_dir })
      clearCleanup()
      navigate('/')
    } catch (err) {
      toast.error('Failed to confirm removal', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setConfirming(false)
    }
  }

  function getFlaggedItems(): CleanupClassification[] {
    return cleanupResults.filter(
      (item) =>
        (item.label === 'review' || item.label === 'remove') &&
        !cleanupUnflaggedIds.has(item.item_id),
    )
  }

  const isScanning = operationId !== null && !events.isComplete
  const hasResults = cleanupResults.length > 0
  const flaggedItems = getFlaggedItems()
  const keptCount = cleanupResults.length - flaggedItems.length
  const pct = events.total > 0 ? Math.round((events.current / events.total) * 100) : 0

  // Error state
  if (events.error && !hasResults) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1 className="page-title">Cleanup</h1>
        <div className="video-error" style={{ marginBottom: '1rem' }}>
          {events.error}
        </div>
        <button className="import-button" onClick={startScan}>
          Retry Scan
        </button>
      </div>
    )
  }

  // Scanning state
  if (isScanning) {
    return (
      <div style={{ padding: '2rem', maxWidth: 600 }}>
        <h1 className="page-title">Cleanup Scan</h1>
        <p className="page-subtitle">Scanning media for items without a clear human subject...</p>
        <div className="video-progress">
          <div className="video-progress-header">
            <span className="video-progress-stage">Classifying items</span>
            {events.total > 0 && (
              <span className="video-progress-pct">{pct}%</span>
            )}
          </div>
          <div className="video-progress-track">
            <div className="video-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {events.total > 0 && (
            <p className="video-progress-count">
              {events.current} / {events.total}
            </p>
          )}
          <p className="video-progress-message">{events.message}</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <button className="video-btn-cancel" onClick={handleCancel}>
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // Review state (results available)
  if (hasResults) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1 className="page-title">Cleanup Results</h1>
        <p className="page-subtitle">Click on a flagged item to rescue it from removal.</p>

        <div className="cleanup-stats-bar">
          <span className="cleanup-stat">
            <span className="cleanup-stat-value" style={{ color: '#e53e3e' }}>
              {flaggedItems.length}
            </span>{' '}
            flagged
          </span>
          <span className="cleanup-stat">
            <span className="cleanup-stat-value" style={{ color: '#22c55e' }}>
              {keptCount}
            </span>{' '}
            kept
          </span>
          <span className="cleanup-stat">
            <span className="cleanup-stat-value">{cleanupResults.length}</span> total
          </span>
        </div>

        {flaggedItems.length === 0 ? (
          <p style={{ color: '#9ca3af', fontStyle: 'italic' }}>
            All items have been rescued. Nothing to remove.
          </p>
        ) : (
          <div className="cleanup-grid">
            {flaggedItems.map((item) => (
              <div
                key={item.item_id}
                className="cleanup-card"
                onClick={() => toggleCleanupUnflag(item.item_id)}
                title={`Click to rescue: ${item.item_path}`}
              >
                <img
                  src={`/api/v1/images/${item.item_id}/thumbnail`}
                  alt={item.item_path}
                  loading="lazy"
                />
                <span
                  className={`cleanup-badge ${
                    item.label === 'remove' ? 'cleanup-badge-remove' : 'cleanup-badge-review'
                  }`}
                >
                  {item.label}
                </span>
                <span className="cleanup-confidence">{item.confidence.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="cleanup-actions">
          <button
            className="import-button"
            onClick={handleConfirm}
            disabled={confirming || flaggedItems.length === 0}
          >
            {confirming ? 'Removing...' : `Confirm Removal (${flaggedItems.length})`}
          </button>
          <button className="video-btn-secondary" onClick={startScan}>
            Re-scan
          </button>
          <button
            className="video-btn-link"
            onClick={() => {
              clearCleanup()
              navigate('/')
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // Idle state (no scan running, no results)
  return (
    <div style={{ padding: '2rem', maxWidth: 600 }}>
      <h1 className="page-title">Cleanup</h1>
      <p className="page-subtitle">
        Scan all imported media to identify items without a clear human subject.
      </p>
      <p style={{ color: '#9ca3af', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
        The scan uses CLIP text-to-image similarity and InsightFace detection to classify each item.
        Flagged items can be reviewed before removal.
      </p>
      <button className="import-button" onClick={startScan}>
        Start Cleanup Scan
      </button>
    </div>
  )
}
