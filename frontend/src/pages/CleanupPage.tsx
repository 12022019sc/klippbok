import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useCleanupEvents } from '../hooks/useCleanupEvents'
import { useAppStore } from '../stores/appStore'
import { useGpuStatus } from '../hooks/useGpuStatus'
import type { CleanupClassification } from '../types/cleanup'

export default function CleanupPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [operationId, setOperationId] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const hasAutoStarted = useRef(false)

  const [mode, setMode] = useState<'text' | 'reference'>('text')
  const [subjectDescription, setSubjectDescription] = useState('')
  const [selectedRefIds, setSelectedRefIds] = useState<string[]>([])
  const [galleryImages, setGalleryImages] = useState<Array<{ id: string; thumbnail_url: string; relative_path: string }>>([])
  const [loadingGallery, setLoadingGallery] = useState(false)
  const [clipThreshold, setClipThreshold] = useState(0.65)

  const cleanupAutoStart = useAppStore((s) => s.cleanupAutoStart)
  const setCleanupAutoStart = useAppStore((s) => s.setCleanupAutoStart)
  const cleanupResults = useAppStore((s) => s.cleanupResults)
  const setCleanupResults = useAppStore((s) => s.setCleanupResults)
  const cleanupUnflaggedIds = useAppStore((s) => s.cleanupUnflaggedIds)
  const toggleCleanupUnflag = useAppStore((s) => s.toggleCleanupUnflag)
  const clearCleanup = useAppStore((s) => s.clearCleanup)

  const events = useCleanupEvents(operationId)
  const { gpuBusy, trainingActive } = useGpuStatus()
  const gpuInUse = gpuBusy || trainingActive

  // Store results when scan completes
  useEffect(() => {
    if (events.isComplete && events.results.length > 0) {
      setCleanupResults(events.results)
      setOperationId(null) // disconnect SSE
    } else if (events.isComplete && events.results.length === 0 && operationId) {
      // Fallback: fetch results from GET endpoint if SSE payload was empty/too large
      fetch(`/api/v1/cleanup/results/${operationId}`)
        .then((res) => res.json())
        .then((data: CleanupClassification[]) => {
          if (data.length > 0) {
            setCleanupResults(data)
          }
        })
        .catch(() => {}) // Results endpoint is best-effort fallback
        .finally(() => setOperationId(null))
    }
  }, [events.isComplete, events.results, operationId, setCleanupResults])

  const canStart =
    mode === 'text' ? subjectDescription.trim().length > 0 : selectedRefIds.length > 0

  // Auto-start behavior — only fires if the form is already filled in
  useEffect(() => {
    if (hasAutoStarted.current) return
    const shouldAutoStart = cleanupAutoStart || searchParams.get('autostart') === 'true'
    if (shouldAutoStart) {
      hasAutoStarted.current = true
      setCleanupAutoStart(false)
      if (canStart) {
        startScan()
      }
    }
  }, [cleanupAutoStart, searchParams, setCleanupAutoStart])

  useEffect(() => {
    setClipThreshold(mode === 'reference' ? 0.65 : 0.25)
  }, [mode])

  useEffect(() => {
    if (mode === 'reference' && galleryImages.length === 0 && !loadingGallery) {
      setLoadingGallery(true)
      fetch('/api/v1/images/')
        .then((res) => res.json())
        .then((data: { total: number; images: Array<{ id: string; thumbnail_url: string; relative_path: string }> }) => {
          setGalleryImages(data.images)
        })
        .catch(() => toast.error('Failed to load gallery'))
        .finally(() => setLoadingGallery(false))
    }
  }, [mode, galleryImages.length, loadingGallery])

  function toggleRef(id: string) {
    setSelectedRefIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 3 ? [...prev, id] : prev,
    )
  }

  async function startScan() {
    clearCleanup()
    const body: Record<string, unknown> =
      mode === 'text'
        ? { mode: 'text', subject_description: subjectDescription.trim(), clip_threshold: clipThreshold }
        : { mode: 'reference', reference_image_ids: selectedRefIds, clip_threshold: clipThreshold }

    try {
      const res = await fetch('/api/v1/cleanup/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
        <p className="page-subtitle">Scanning media for items matching your subject...</p>
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
    <div style={{ padding: '2rem', maxWidth: 700 }}>
      <h1 className="page-title">Cleanup</h1>
      <p className="page-subtitle">Define the subject to keep, then scan.</p>

      {gpuInUse && (
        <div className="gpu-busy-banner">
          GPU is currently in use for training. GPU-intensive features are temporarily disabled.
        </div>
      )}

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <button
          className={`cleanup-mode-btn ${mode === 'text' ? 'cleanup-mode-active' : ''}`}
          onClick={() => setMode('text')}
        >
          Describe Subject
        </button>
        <button
          className={`cleanup-mode-btn ${mode === 'reference' ? 'cleanup-mode-active' : ''}`}
          onClick={() => setMode('reference')}
        >
          Reference Images
        </button>
      </div>

      {/* Text mode */}
      {mode === 'text' && (
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
            Describe the subject to keep (e.g., "woman with dark hair", "golden retriever")
          </label>
          <input
            type="text"
            value={subjectDescription}
            onChange={(e) => setSubjectDescription(e.target.value)}
            placeholder="woman with dark hair"
            className="cleanup-text-input"
            onKeyDown={(e) => { if (e.key === 'Enter' && canStart) startScan() }}
          />
        </div>
      )}

      {/* Reference mode */}
      {mode === 'reference' && (
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
            Pick 1-3 reference images of your target subject
          </label>
          {loadingGallery ? (
            <p style={{ color: '#9ca3af' }}>Loading gallery...</p>
          ) : galleryImages.length === 0 ? (
            <p style={{ color: '#9ca3af' }}>No images in gallery. Import images first.</p>
          ) : (
            <>
              <p style={{ color: '#9ca3af', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                Selected: {selectedRefIds.length}/3
              </p>
              <div className="cleanup-ref-grid">
                {galleryImages.map((img) => (
                  <div
                    key={img.id}
                    className={`cleanup-ref-card ${selectedRefIds.includes(img.id) ? 'cleanup-ref-selected' : ''}`}
                    onClick={() => toggleRef(img.id)}
                    title={img.relative_path}
                  >
                    <img src={img.thumbnail_url} alt={img.relative_path} loading="lazy" />
                    {selectedRefIds.includes(img.id) && (
                      <span className="cleanup-ref-check">&#10003;</span>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Threshold slider */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
          CLIP threshold: <strong style={{ color: '#f3f4f6' }}>{clipThreshold.toFixed(2)}</strong>
        </label>
        <input
          type="range"
          min={mode === 'reference' ? 0.4 : 0.1}
          max={mode === 'reference' ? 0.9 : 0.5}
          step={0.05}
          value={clipThreshold}
          onChange={(e) => setClipThreshold(parseFloat(e.target.value))}
          className="cleanup-threshold-slider"
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#6b7280' }}>
          <span>Fewer items removed</span>
          <span>More items removed</span>
        </div>
      </div>

      <button
        className="import-button"
        onClick={startScan}
        disabled={!canStart || gpuInUse}
        title={gpuInUse ? 'GPU in use for training' : undefined}
      >
        Start Cleanup Scan
      </button>
      <p style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: '0.5rem' }}>
        CLIP {mode === 'reference' ? 'image-to-image' : 'text-to-image'} + InsightFace
      </p>
    </div>
  )
}
