import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useProcessEvents } from '../hooks/useProcessEvents'
import type { ExtractedFrame } from '../hooks/useProcessEvents'
import type { GalleryItem } from '../types/image'

export default function ProcessVideosPage() {
  const navigate = useNavigate()
  const location = useLocation()

  // Navigation state: optional pre-selected video paths
  const navState = location.state as { videoPaths?: string[] } | null
  const filterPaths = navState?.videoPaths ?? null

  // Component-local state
  const [videos, setVideos] = useState<GalleryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [discarding, setDiscarding] = useState(false)

  // Extraction results (populated from SSE or fallback GET)
  const [extractedFrames, setExtractedFrames] = useState<ExtractedFrame[]>([])
  const [processedVideoPaths, setProcessedVideoPaths] = useState<string[]>([])
  const [extractionDone, setExtractionDone] = useState(false)

  const processState = useProcessEvents(operationId)

  // Fetch video items on mount
  useEffect(() => {
    fetch('/api/v1/images/')
      .then((res) => res.json())
      .then((data: { images: GalleryItem[] }) => {
        let vids = data.images.filter((i) => i.media_type === 'video')
        if (filterPaths) {
          const pathSet = new Set(filterPaths)
          vids = vids.filter((v) => pathSet.has(v.relative_path))
        }
        setVideos(vids)
      })
      .catch(() => toast.error('Failed to load gallery'))
      .finally(() => setLoading(false))
  }, [])

  // Handle extraction completion
  useEffect(() => {
    if (processState.isComplete && operationId) {
      if (processState.extractedFrames.length > 0) {
        setExtractedFrames(processState.extractedFrames)
        setProcessedVideoPaths(processState.processedVideoPaths)
        setExtractionDone(true)
        setOperationId(null)
      } else {
        // Fallback: fetch results from GET endpoint
        fetch(`/api/v1/video/process/results/${operationId}`)
          .then((res) => res.json())
          .then((data: { extracted_frames: ExtractedFrame[]; processed_video_paths: string[] }) => {
            setExtractedFrames(data.extracted_frames)
            setProcessedVideoPaths(data.processed_video_paths)
            setExtractionDone(true)
          })
          .catch(() => toast.error('Failed to retrieve results'))
          .finally(() => setOperationId(null))
      }
    }
    if (processState.error) {
      toast.error('Extraction failed', { description: processState.error })
      setOperationId(null)
    }
  }, [processState.isComplete, processState.error])

  async function handleStart() {
    const videoPaths = filterPaths ?? null
    try {
      const res = await fetch('/api/v1/video/process/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_paths: videoPaths }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start processing', { description: (err as { detail: string }).detail })
        return
      }
      const data = await res.json() as { operation_id: string }
      setOperationId(data.operation_id)
    } catch (err) {
      toast.error('Failed to start processing', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  async function handleCancel() {
    if (!operationId) return
    try {
      await fetch(`/api/v1/video/process/${operationId}/cancel`, { method: 'POST' })
    } catch {
      // best-effort cancel
    }
    setOperationId(null)
  }

  async function handleConfirm() {
    if (processedVideoPaths.length === 0) return
    setConfirming(true)
    try {
      const res = await fetch('/api/v1/video/process/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_paths: processedVideoPaths }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to confirm', { description: (err as { detail: string }).detail })
        return
      }
      const data = await res.json() as { imported: number; removed: number }
      toast.success(`Imported ${data.imported} frames, removed ${data.removed} video entries`)
      navigate('/')
    } catch (err) {
      toast.error('Failed to confirm', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setConfirming(false)
    }
  }

  async function handleDiscard() {
    setDiscarding(true)
    try {
      const framePaths = extractedFrames.map((f) => f.frame_path)
      const res = await fetch('/api/v1/video/process/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame_paths: framePaths }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to discard', { description: (err as { detail: string }).detail })
        return
      }
      const data = await res.json() as { deleted: number }
      toast.info(`Discarded ${data.deleted} frames`)
      navigate('/')
    } catch (err) {
      toast.error('Failed to discard', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setDiscarding(false)
    }
  }

  const isExtracting = operationId !== null && !processState.isComplete
  const pct = processState.total > 0 ? Math.round((processState.current / processState.total) * 100) : 0

  // Loading state
  if (loading) {
    return (
      <div style={{ padding: '2rem', color: '#9ca3af' }}>Loading videos...</div>
    )
  }

  // State 3: Review (extraction done, results available)
  if (extractionDone) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1 className="page-title">Review Extracted Frames</h1>
        <p className="page-subtitle">
          {extractedFrames.length} frames extracted from {processedVideoPaths.length} videos
        </p>

        <div className="cleanup-stats-bar">
          <span className="cleanup-stat">
            <span className="cleanup-stat-value" style={{ color: '#6366f1' }}>
              {extractedFrames.length}
            </span>{' '}
            frames
          </span>
          <span className="cleanup-stat">
            <span className="cleanup-stat-value">{processedVideoPaths.length}</span>{' '}
            videos
          </span>
        </div>

        {extractedFrames.length === 0 ? (
          <p style={{ color: '#9ca3af', fontStyle: 'italic' }}>
            No frames were extracted. Check your video files.
          </p>
        ) : (
          <div className="process-videos-grid">
            {extractedFrames.map((frame) => (
              <div key={frame.frame_path} className="process-videos-card">
                <img
                  src={`/api/v1/video/process/frame?path=${encodeURIComponent(frame.frame_path)}`}
                  alt={frame.frame_path}
                  loading="lazy"
                />
                <span className="process-videos-label">
                  {frame.video_path.split('/').pop()}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="cleanup-actions">
          <button
            className="import-button"
            onClick={handleConfirm}
            disabled={confirming || extractedFrames.length === 0}
          >
            {confirming ? 'Importing...' : `Confirm Import (${extractedFrames.length})`}
          </button>
          <button
            className="video-btn-cancel"
            onClick={handleDiscard}
            disabled={discarding}
          >
            {discarding ? 'Discarding...' : 'Discard'}
          </button>
          <button className="video-btn-link" onClick={() => navigate('/')}>
            Back to Gallery
          </button>
        </div>
      </div>
    )
  }

  // State 2: Extracting (SSE connected, progress)
  if (isExtracting) {
    return (
      <div style={{ padding: '2rem', maxWidth: 600 }}>
        <h1 className="page-title">Processing Videos</h1>
        <p className="page-subtitle">Extracting reference frames...</p>
        <div className="video-progress">
          <div className="video-progress-header">
            <span className="video-progress-stage">
              {processState.stage || 'Starting...'}
            </span>
            {processState.total > 0 && (
              <span className="video-progress-pct">{pct}%</span>
            )}
          </div>
          <div className="video-progress-track">
            <div className="video-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {processState.total > 0 && (
            <p className="video-progress-count">
              {processState.current} / {processState.total}
            </p>
          )}
          <p className="video-progress-message">{processState.message}</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <button className="video-btn-cancel" onClick={handleCancel}>
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // State 1: Setup (no operation, no results)
  if (videos.length === 0) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1 className="page-title">Process Videos</h1>
        <p style={{ color: '#9ca3af' }}>No videos to process in this project.</p>
        <button className="video-btn-link" onClick={() => navigate('/')}>
          Back to Gallery
        </button>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem' }}>
      <h1 className="page-title">Process Videos</h1>
      <p className="page-subtitle">
        Extract reference frames from {videos.length} video{videos.length !== 1 ? 's' : ''}.
      </p>

      <div className="process-videos-grid">
        {videos.map((video) => (
          <div key={video.id} className="process-videos-card">
            <img
              src={video.thumbnail_url}
              alt={video.relative_path}
              loading="lazy"
            />
            <span className="process-videos-label">
              {video.relative_path.split('/').pop()}
            </span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <button className="import-button" onClick={handleStart}>
          Start Processing
        </button>
        <button className="video-btn-link" onClick={() => navigate('/')}>
          Back to Gallery
        </button>
      </div>
    </div>
  )
}
