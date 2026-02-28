import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import type { GalleryItem } from '../../types/image'

interface ImageLightboxProps {
  items: GalleryItem[]
  currentIndex: number
  open: boolean
  onClose: () => void
}

export default function ImageLightbox({
  items,
  currentIndex,
  open,
  onClose,
}: ImageLightboxProps) {
  const slides = items.map((item) => ({
    src: item.thumbnail_url,
    alt: item.relative_path,
    width: item.width,
    height: item.height,
  }))

  return (
    <Lightbox
      open={open}
      close={onClose}
      slides={slides}
      index={currentIndex}
      render={{
        slideFooter: ({ slide }) => {
          const idx = slides.findIndex((s) => s.src === slide.src)
          const item = idx >= 0 ? items[idx] : null
          if (!item) return null

          return (
            <div className="lightbox-footer">
              <span title="Path" style={{ flexBasis: '100%', color: '#d1d5db' }}>
                {item.relative_path}
              </span>
              <span title="Resolution">
                {item.width} x {item.height}
              </span>
              {item.bucket && (
                <span title="Bucket" style={{ color: '#9ca3af' }}>
                  Bucket: {item.bucket}
                </span>
              )}
              <span
                title="Quality"
                style={{ color: item.quality_pass ? '#22c55e' : '#ef4444' }}
              >
                {item.quality_pass ? 'Sharp' : 'Blurry'}
              </span>
              {item.is_near_duplicate && (
                <span style={{ color: '#f97316' }}>Near-duplicate</span>
              )}
              {item.caption && (
                <span
                  title="Caption"
                  style={{ flexBasis: '100%', color: '#9ca3af', fontStyle: 'italic' }}
                >
                  {item.caption}
                </span>
              )}
            </div>
          )
        },
      }}
    />
  )
}
