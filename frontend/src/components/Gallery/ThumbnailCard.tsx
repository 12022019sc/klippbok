import { useAppStore } from '../../stores/appStore'
import type { GalleryItem } from '../../types/image'
import StatusStrip from './StatusStrip'

interface ThumbnailCardProps {
  item: GalleryItem
  width: number
  onClick: () => void
  isSelected?: boolean
  selectionMode?: boolean
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`
  }
  const min = Math.floor(seconds / 60)
  const sec = seconds % 60
  return `${min}:${sec.toFixed(0).padStart(2, '0')}`
}

export default function ThumbnailCard({
  item,
  width,
  onClick,
  isSelected = false,
  selectionMode = false,
}: ThumbnailCardProps) {
  const height = Math.round(width * (item.height / item.width))

  // Read triage score for this item from the store
  const triageScore = useAppStore((s) => s.triageResults[item.id])

  // Badge color by classification
  const badgeStyle: Record<string, string> = {
    match: '#22c55e',
    borderline: '#eab308',
    no_match: '#6b7280',
  }

  return (
    <div
      className={`thumbnail-card${isSelected ? ' thumbnail-card--selected' : ''}`}
      style={{
        width,
        height,
        outline: isSelected ? '3px solid #3b82f6' : undefined,
        outlineOffset: isSelected ? '-3px' : undefined,
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick()
        }
      }}
      aria-label={
        selectionMode
          ? `${isSelected ? 'Deselect' : 'Select'} ${item.relative_path}`
          : `Open ${item.relative_path}`
      }
      aria-pressed={selectionMode ? isSelected : undefined}
    >
      <img
        src={item.thumbnail_url}
        alt={item.relative_path}
        width={width}
        height={height}
        loading="lazy"
      />

      {/* Video play button overlay */}
      {item.media_type === 'video' && (
        <div className="video-play-overlay" aria-hidden="true">
          <div className="video-play-btn">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="white">
              <polygon points="5,3 19,12 5,21" />
            </svg>
          </div>
        </div>
      )}

      {/* Video duration badge (bottom-right) */}
      {item.media_type === 'video' && (item as GalleryItem & { duration?: number }).duration !== undefined && (
        <div className="video-duration-badge" aria-hidden="true">
          {formatDuration((item as GalleryItem & { duration?: number }).duration!)}
        </div>
      )}

      {/* Triage score badge (top-right) */}
      {triageScore && (
        <div
          className="triage-score-badge"
          style={{
            backgroundColor: badgeStyle[triageScore.classification] ?? '#6b7280',
          }}
          title={`${triageScore.classification}: ${triageScore.best_score.toFixed(2)}`}
          aria-hidden="true"
        >
          {triageScore.best_score.toFixed(2)}
        </div>
      )}

      {isSelected && (
        <div className="thumbnail-selection-badge" aria-hidden="true">
          ✓
        </div>
      )}
      <StatusStrip
        resolution_ok={item.resolution_ok}
        quality_pass={item.quality_pass}
        bucket={item.bucket}
        width={item.width}
        height={item.height}
        caption={item.caption}
        is_near_duplicate={item.is_near_duplicate}
        duplicate_group_id={item.duplicate_group_id}
      />
    </div>
  )
}
