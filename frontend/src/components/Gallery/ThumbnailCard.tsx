import type { GalleryItem } from '../../types/image'
import StatusStrip from './StatusStrip'

interface ThumbnailCardProps {
  item: GalleryItem
  width: number
  onClick: () => void
}

export default function ThumbnailCard({ item, width, onClick }: ThumbnailCardProps) {
  const height = Math.round(width * (item.height / item.width))

  return (
    <div
      className="thumbnail-card"
      style={{ width, height }}
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
      {item.media_type === 'video' && <div className="video-indicator" />}
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
