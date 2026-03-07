import { useCallback, useEffect, useState } from 'react'
import type { ExtractedFrame } from '../../hooks/useProcessEvents'
import FrameCandidateLightbox from './FrameCandidateLightbox'

interface FrameReviewGridProps {
  frames: ExtractedFrame[]
  skippedVideos?: Array<{ path: string; reason: string }>
  onConfirm: (selectedPaths: string[]) => void
  onDiscard: (framePaths: string[], removeVideos: boolean) => void
}

/**
 * Frame review grid with click-to-preview and remove button UX.
 * All frames selected by default. Click thumbnail to see full-size preview,
 * or browse candidates if available.
 * "Remove" button below each thumbnail to deselect/exclude a frame.
 */
export default function FrameReviewGrid({ frames, skippedVideos, onConfirm, onDiscard }: FrameReviewGridProps) {
  const [deselected, setDeselected] = useState<Set<string>>(new Set())
  const [showSkipped, setShowSkipped] = useState(false)
  const [showDiscardPrompt, setShowDiscardPrompt] = useState(false)
  const [previewFrame, setPreviewFrame] = useState<ExtractedFrame | null>(null)
  const [candidateFrame, setCandidateFrame] = useState<ExtractedFrame | null>(null)
  // Maps video_path -> user-selected candidate path (override from default winner)
  const [selectedFrames, setSelectedFrames] = useState<Record<string, string>>({})

  function toggleFrame(framePath: string) {
    setDeselected((prev) => {
      const next = new Set(prev)
      if (next.has(framePath)) {
        next.delete(framePath)
      } else {
        next.add(framePath)
      }
      return next
    })
  }

  function handleThumbnailClick(frame: ExtractedFrame) {
    if (frame.candidates && frame.candidates.length > 1) {
      setCandidateFrame(frame)
    } else {
      setPreviewFrame(frame)
    }
  }

  function handleCandidateSelect(frame: ExtractedFrame, candidatePath: string) {
    setSelectedFrames((prev) => ({
      ...prev,
      [frame.video_path]: candidatePath,
    }))
    setCandidateFrame(null)
  }

  function handleCandidateRemove(frame: ExtractedFrame) {
    toggleFrame(frame.frame_path)
    setCandidateFrame(null)
  }

  // Resolve the displayed path for a frame (selected candidate or default winner)
  function resolvedPath(frame: ExtractedFrame): string {
    return selectedFrames[frame.video_path] ?? frame.frame_path
  }

  // Close preview on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setPreviewFrame(null)
  }, [])

  useEffect(() => {
    if (previewFrame) {
      window.addEventListener('keydown', handleKeyDown)
      return () => window.removeEventListener('keydown', handleKeyDown)
    }
  }, [previewFrame, handleKeyDown])

  const selectedCount = frames.length - deselected.size
  const selectedPaths = frames
    .filter((f) => !deselected.has(f.frame_path))
    .map((f) => resolvedPath(f))

  function handleConfirm() {
    onConfirm(selectedPaths)
  }

  function handleDiscard(removeVideos: boolean) {
    setShowDiscardPrompt(false)
    const allPaths = frames.map((f) => f.frame_path)
    onDiscard(allPaths, removeVideos)
  }

  return (
    <div className="frame-review-container">
      {/* Skipped videos warning */}
      {skippedVideos && skippedVideos.length > 0 && (
        <div className="frame-review-skipped">
          <strong>{skippedVideos.length} video{skippedVideos.length !== 1 ? 's' : ''} had no usable frames</strong>
          <button
            className="video-btn-link"
            onClick={() => setShowSkipped((v) => !v)}
            style={{ marginLeft: '0.5rem' }}
          >
            {showSkipped ? 'Hide' : 'Show details'}
          </button>
          {showSkipped && (
            <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem', fontSize: '0.8rem' }}>
              {skippedVideos.map((sv) => (
                <li key={sv.path}>
                  <code>{sv.path.split('/').pop()}</code>: {sv.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Summary bar */}
      <div className="frame-review-summary">
        <span>{selectedCount} of {frames.length} frames selected</span>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="import-button"
            onClick={handleConfirm}
            disabled={selectedCount === 0}
          >
            Import {selectedCount} Frame{selectedCount !== 1 ? 's' : ''}
          </button>
          <button
            className="video-btn-cancel"
            onClick={() => setShowDiscardPrompt(true)}
          >
            Discard All
          </button>
        </div>
      </div>

      {/* Discard confirmation prompt */}
      {showDiscardPrompt && (
        <div className="frame-review-discard-prompt">
          <p>Also remove the source videos from the gallery?</p>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="video-btn-cancel" onClick={() => handleDiscard(true)}>
              Yes, Remove Videos
            </button>
            <button className="video-btn-secondary" onClick={() => handleDiscard(false)}>
              No, Keep Videos
            </button>
            <button className="video-btn-link" onClick={() => setShowDiscardPrompt(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Frame grid */}
      <div className="frame-review-grid">
        {frames.map((frame) => {
          const isDeselected = deselected.has(frame.frame_path)
          const displayPath = resolvedPath(frame)
          const thumbUrl = `/api/v1/video/process/frame?path=${encodeURIComponent(displayPath)}`
          const hasCandidates = frame.candidates && frame.candidates.length > 1
          const isOverridden = selectedFrames[frame.video_path] != null
          return (
            <div
              key={frame.frame_path}
              className={`frame-review-card${isDeselected ? ' deselected' : ''}`}
            >
              {hasCandidates && (
                <span className="frame-review-candidate-badge">
                  {isOverridden ? 'Picked' : `${frame.candidates!.length} candidates`}
                </span>
              )}
              <img
                src={thumbUrl}
                alt={frame.frame_path}
                loading="lazy"
                onClick={() => handleThumbnailClick(frame)}
                style={{ cursor: 'pointer' }}
                title={hasCandidates ? 'Click to browse candidates' : 'Click to preview full size'}
              />
              <span className="frame-review-label">
                {frame.video_path.split('/').pop()}
              </span>
              <button
                className={`frame-review-toggle-btn${isDeselected ? ' removed' : ''}`}
                onClick={() => toggleFrame(frame.frame_path)}
                title={isDeselected ? 'Include this frame' : 'Exclude this frame'}
              >
                {isDeselected ? 'Include' : 'Remove'}
              </button>
            </div>
          )
        })}
      </div>

      {/* Simple full-size preview overlay (no candidates) */}
      {previewFrame && (
        <div
          className="frame-preview-overlay"
          onClick={() => setPreviewFrame(null)}
        >
          <div
            className="frame-preview-content"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={`/api/v1/video/process/frame?path=${encodeURIComponent(resolvedPath(previewFrame))}`}
              alt={previewFrame.frame_path}
            />
            <div className="frame-preview-info">
              <span>{previewFrame.video_path.split('/').pop()}</span>
              <button
                className="frame-preview-close"
                onClick={() => setPreviewFrame(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Candidate lightbox */}
      {candidateFrame && candidateFrame.candidates && (
        <FrameCandidateLightbox
          candidates={candidateFrame.candidates}
          videoName={candidateFrame.video_path.split('/').pop() ?? ''}
          onSelect={(path) => handleCandidateSelect(candidateFrame, path)}
          onRemove={() => handleCandidateRemove(candidateFrame)}
          onClose={() => setCandidateFrame(null)}
        />
      )}
    </div>
  )
}
