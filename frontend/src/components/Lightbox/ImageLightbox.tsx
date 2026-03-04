import { useQueryClient } from '@tanstack/react-query'
import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import CaptionPanel from '../Caption/CaptionPanel'
import type { GalleryItem } from '../../types/image'

interface ImageLightboxProps {
  items: GalleryItem[]
  currentIndex: number
  open: boolean
  onClose: () => void
  onCaptionSaved?: () => void
}

export default function ImageLightbox({
  items,
  currentIndex,
  open,
  onClose,
  onCaptionSaved,
}: ImageLightboxProps) {
  const queryClient = useQueryClient()
  const slides = items.map((item) => ({
    src: item.full_url,
    alt: item.relative_path,
    width: item.width,
    height: item.height,
  }))

  function handleCaptionSaved(caption: string, item: GalleryItem) {
    // Update the item's caption locally so re-open shows the new value
    item.caption = caption
    // Invalidate gallery query so the caption updates in thumbnails/status strips
    void queryClient.invalidateQueries({ queryKey: ['images'] })
    onCaptionSaved?.()
  }

  return (
    <Lightbox
      open={open}
      close={onClose}
      slides={slides}
      index={currentIndex}
      render={{
        slide: ({ slide }) => {
          const idx = slides.findIndex((s) => s.src === slide.src)
          const item = idx >= 0 ? items[idx] : null
          if (item?.media_type === 'video' && item.video_url) {
            return (
              <video
                src={item.video_url}
                controls
                autoPlay
                style={{
                  maxWidth: '100%',
                  maxHeight: '80vh',
                  objectFit: 'contain',
                  display: 'block',
                  margin: '0 auto',
                }}
              />
            )
          }
          return undefined
        },
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
              {item.media_type === 'image' && (
                <span
                  title="Quality"
                  style={{ color: item.quality_pass ? '#22c55e' : '#ef4444' }}
                >
                  {item.quality_pass ? 'Sharp' : 'Blurry'}
                </span>
              )}
              {item.media_type === 'video' && (
                <span style={{ color: '#818cf8' }}>Video</span>
              )}
              {item.is_near_duplicate && (
                <span style={{ color: '#f97316' }}>Near-duplicate</span>
              )}
              <div style={{ flexBasis: '100%', marginTop: '0.5rem' }}>
                <CaptionPanel
                  imageId={item.id}
                  initialCaption={item.caption ?? null}
                  onSaved={(caption) => handleCaptionSaved(caption, item)}
                />
              </div>
            </div>
          )
        },
      }}
    />
  )
}
