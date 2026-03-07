import { useState } from 'react'
import type { ExtractedFrame } from '../../hooks/useProcessEvents'

interface FrameReviewGridProps {
  frames: ExtractedFrame[]
  skippedVideos?: Array<{ path: string; reason: string }>
  onConfirm: (selectedPaths: string[]) => void
  onDiscard: (framePaths: string[], removeVideos: boolean) => void
}

/**
 * Frame review grid with toggle-select UX.
 * All frames selected by default; clicking toggles off (dimmed/crossed out).
 */
export default function FrameReviewGrid({ frames, skippedVideos, onConfirm, onDiscard }: FrameReviewGridProps) {
  const [deselected, setDeselected] = useState<Set<string>>(new Set())
  const [showSkipped, setShowSkipped] = useState(false)
  const [showDiscardPrompt, setShowDiscardPrompt] = useState(false)

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

  const selectedCount = frames.length - deselected.size
  const selectedPaths = frames
    .filter((f) => !deselected.has(f.frame_path))
    .map((f) => f.frame_path)

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
          return (
            <div
              key={frame.frame_path}
              className={`frame-review-card${isDeselected ? ' deselected' : ''}`}
              onClick={() => toggleFrame(frame.frame_path)}
            >
              <img
                src={`/api/v1/video/process/frame?path=${encodeURIComponent(frame.frame_path)}`}
                alt={frame.frame_path}
                loading="lazy"
              />
              <span className="frame-review-label">
                {frame.video_path.split('/').pop()}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
