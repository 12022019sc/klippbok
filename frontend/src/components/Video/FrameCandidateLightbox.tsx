import { useCallback, useEffect, useState } from 'react'
import type { FrameCandidate } from '../../hooks/useProcessEvents'

interface FrameCandidateLightboxProps {
  candidates: FrameCandidate[]
  videoName: string
  onSelect: (candidatePath: string) => void
  onRemove: () => void
  onClose: () => void
}

/**
 * Full-screen lightbox for browsing ranked frame candidates.
 * Arrow keys / buttons to navigate, click "Select" to override the default pick.
 */
export default function FrameCandidateLightbox({
  candidates,
  videoName,
  onSelect,
  onRemove,
  onClose,
}: FrameCandidateLightboxProps) {
  const [index, setIndex] = useState(0)
  const current = candidates[index]

  const goPrev = useCallback(() => {
    setIndex((i) => (i > 0 ? i - 1 : candidates.length - 1))
  }, [candidates.length])

  const goNext = useCallback(() => {
    setIndex((i) => (i < candidates.length - 1 ? i + 1 : 0))
  }, [candidates.length])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === 'ArrowRight') goNext()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, goPrev, goNext])

  // Scroll wheel navigation
  function handleWheel(e: React.WheelEvent) {
    if (e.deltaY > 0) goNext()
    else if (e.deltaY < 0) goPrev()
  }

  const thumbUrl = (path: string) =>
    `/api/v1/video/process/frame?path=${encodeURIComponent(path)}`

  return (
    <div className="frame-preview-overlay" onClick={onClose} onWheel={handleWheel}>
      <div className="candidate-lightbox" onClick={(e) => e.stopPropagation()}>
        {/* Navigation arrow left */}
        <button className="candidate-nav candidate-nav--left" onClick={goPrev}>
          &#8249;
        </button>

        {/* Main image */}
        <div className="candidate-main">
          <img
            src={thumbUrl(current.path)}
            alt={`Candidate rank ${current.rank}`}
          />
          <div className="candidate-info-bar">
            <span className="candidate-video-name">{videoName}</span>
            <span className="candidate-rank-label">
              Rank {current.rank} / {candidates.length}
            </span>
            <span className="candidate-score-badge">
              Score: {current.score.toFixed(3)}
            </span>
          </div>

          {/* Thumbnail strip */}
          <div className="candidate-strip">
            {candidates.map((c, i) => (
              <img
                key={c.path}
                src={thumbUrl(c.path)}
                alt={`Rank ${c.rank}`}
                className={`candidate-strip-thumb${i === index ? ' active' : ''}`}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>

          <div className="candidate-actions">
            <button
              className="video-btn-primary"
              onClick={() => onSelect(current.path)}
            >
              Select This Frame
            </button>
            <button className="video-btn-cancel" onClick={onRemove}>
              Remove Frame
            </button>
            <button className="frame-preview-close" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>

        {/* Navigation arrow right */}
        <button className="candidate-nav candidate-nav--right" onClick={goNext}>
          &#8250;
        </button>
      </div>
    </div>
  )
}
