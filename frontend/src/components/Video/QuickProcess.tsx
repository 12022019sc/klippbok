import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useProcessEvents } from '../../hooks/useProcessEvents'
import ProcessingProgress from './ProcessingProgress'
import FrameReviewGrid from './FrameReviewGrid'

type ViewState = 'setup' | 'processing' | 'review'

interface QuickProcessProps {
  queuedPaths?: string[] | null
}

/**
 * Three-state Quick Process component following CleanupPage pattern.
 * setup -> processing -> review
 */
export default function QuickProcess({ queuedPaths }: QuickProcessProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [viewState, setViewState] = useState<ViewState>('setup')
  const [operationId, setOperationId] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // Settings (collapsed by default)
  const [showSettings, setShowSettings] = useState(false)
  const [sceneThreshold, setSceneThreshold] = useState(27.0)
  const [longVideoThreshold, setLongVideoThreshold] = useState(30)
  const [framesPerClip, setFramesPerClip] = useState(1)

  const processState = useProcessEvents(operationId)

  // Transition to review when processing completes
  useEffect(() => {
    if (processState.isComplete && operationId) {
      setViewState('review')
      setOperationId(null)
    }
  }, [processState.isComplete, operationId])

  // Handle processing errors
  useEffect(() => {
    if (processState.error) {
      toast.error('Processing failed', { description: processState.error })
      setOperationId(null)
      setViewState('setup')
    }
  }, [processState.error])

  async function handleStart() {
    setIsStarting(true)
    try {
      const body: Record<string, unknown> = {
        scene_threshold: sceneThreshold,
        long_video_threshold: longVideoThreshold,
        frames_per_clip: framesPerClip,
      }
      if (queuedPaths && queuedPaths.length > 0) {
        body.video_paths = queuedPaths
      }

      const res = await fetch('/api/v1/video/process/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to start processing', { description: err.detail })
        return
      }

      const data = await res.json() as { operation_id: string }
      setOperationId(data.operation_id)
      setViewState('processing')
    } catch (err) {
      toast.error('Failed to start processing', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsStarting(false)
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
    setViewState('setup')
  }

  async function handleConfirm(selectedFramePaths: string[]) {
    setConfirming(true)
    try {
      const res = await fetch('/api/v1/video/process/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_paths: processState.processedVideoPaths,
          frame_paths: selectedFramePaths,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to confirm import', { description: err.detail })
        return
      }

      const data = await res.json() as { imported: number; removed: number }
      toast.success(`Imported ${data.imported} frames, removed ${data.removed} video entries`)
      await queryClient.invalidateQueries({ queryKey: ['images'] })
      navigate('/')
    } catch (err) {
      toast.error('Failed to confirm import', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setConfirming(false)
    }
  }

  async function handleDiscard(framePaths: string[], removeVideos: boolean) {
    try {
      const body: Record<string, unknown> = { frame_paths: framePaths }
      if (removeVideos) {
        body.remove_videos = true
        body.video_paths = processState.processedVideoPaths
      }

      const res = await fetch('/api/v1/video/process/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to discard', { description: err.detail })
        return
      }

      const data = await res.json() as { deleted: number }
      toast.info(`Discarded ${data.deleted} frames`)
      if (removeVideos) {
        await queryClient.invalidateQueries({ queryKey: ['images'] })
      }
      setViewState('setup')
    } catch (err) {
      toast.error('Failed to discard', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  // ---- SETUP STATE ----
  if (viewState === 'setup') {
    return (
      <div className="quick-process">
        <div className="quick-process-setup">
          <p style={{ color: '#d1d5db', fontSize: '0.9rem', margin: '0 0 1rem' }}>
            {queuedPaths && queuedPaths.length > 0
              ? `Processing ${queuedPaths.length} selected video${queuedPaths.length !== 1 ? 's' : ''}`
              : 'Processing all videos in project'}
          </p>

          {queuedPaths && queuedPaths.length > 0 && (
            <div style={{ marginBottom: '1rem', fontSize: '0.8rem', color: '#6b7280' }}>
              {queuedPaths.map((p) => (
                <div key={p} style={{ fontFamily: 'monospace' }}>{p.split('/').pop()}</div>
              ))}
            </div>
          )}

          <button
            className="video-advanced-toggle"
            onClick={() => setShowSettings((v) => !v)}
          >
            {showSettings ? 'Hide Settings' : 'Settings'}
          </button>

          {showSettings && (
            <div className="quick-process-settings">
              <div className="video-field">
                <label className="video-label">Scene threshold</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={sceneThreshold}
                  min={1}
                  max={100}
                  step={0.5}
                  onChange={(e) => setSceneThreshold(Number(e.target.value))}
                />
                <span className="video-hint">Sensitivity for scene detection (default 27.0)</span>
              </div>
              <div className="video-field">
                <label className="video-label">Long video threshold (seconds)</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={longVideoThreshold}
                  min={5}
                  max={600}
                  onChange={(e) => setLongVideoThreshold(Number(e.target.value))}
                />
                <span className="video-hint">Videos longer than this get scene detection + split (default 30s)</span>
              </div>
              <div className="video-field">
                <label className="video-label">Frames per clip</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={framesPerClip}
                  min={1}
                  max={50}
                  onChange={(e) => setFramesPerClip(Number(e.target.value))}
                />
                <span className="video-hint">Reference frames to extract from each video/clip</span>
              </div>
            </div>
          )}

          <button
            className="process-btn"
            onClick={() => void handleStart()}
            disabled={isStarting}
          >
            {isStarting ? 'Starting...' : 'Process Videos'}
          </button>
        </div>
      </div>
    )
  }

  // ---- PROCESSING STATE ----
  if (viewState === 'processing') {
    return (
      <div className="quick-process">
        <ProcessingProgress
          stage={processState.stage}
          current={processState.current}
          total={processState.total}
          message={processState.message}
          onCancel={() => void handleCancel()}
        />
      </div>
    )
  }

  // ---- REVIEW STATE ----
  return (
    <div className="quick-process">
      <h3 style={{ color: '#f9fafb', margin: '0 0 0.75rem' }}>Review Extracted Frames</h3>
      <p className="page-subtitle">
        {processState.extractedFrames.length} frames extracted from {processState.processedVideoPaths.length} video{processState.processedVideoPaths.length !== 1 ? 's' : ''}
      </p>
      {confirming && <p style={{ color: '#9ca3af' }}>Importing frames...</p>}
      <FrameReviewGrid
        frames={processState.extractedFrames}
        skippedVideos={processState.skippedVideos}
        onConfirm={(selected) => void handleConfirm(selected)}
        onDiscard={(paths, removeVids) => void handleDiscard(paths, removeVids)}
      />
    </div>
  )
}
