import type { GalleryItem } from '../../types/image'
import { getDuplicateGroupColor } from '../../utils/duplicateColors'
import StatusStrip from './StatusStrip'

interface ThumbnailCardProps {
  item: GalleryItem
  width: number
  onClick: () => void
}

export default function ThumbnailCard({ item, width, onClick }: ThumbnailCardProps) {
  const height = Math.round(width * (item.height / item.width))

  const duplicateBorderStyle =
    item.is_near_duplicate && item.duplicate_group_id
      ? {
          borderLeft: `3px solid ${getDuplicateGroupColor(item.duplicate_group_id)}`,
        }
      : {}

  return (
    <div
      className="thumbnail-card"
      style={{ width, height, ...duplicateBorderStyle }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick()
        }
      }}
      aria-label={`Open ${item.relative_path}`}
    >
      <img
        src={item.thumbnail_url}
        alt={item.relative_path}
        width={width}
        height={height}
        loading="lazy"
      />
      <StatusStrip
        resolution_ok={item.resolution_ok}
        quality_pass={item.quality_pass}
        bucket={item.bucket}
        width={item.width}
        height={item.height}
        caption={item.caption}
      />
    </div>
  )
}
