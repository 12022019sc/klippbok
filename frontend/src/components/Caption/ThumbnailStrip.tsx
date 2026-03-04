import type { GalleryItem } from '../../types/image'

interface Props {
  images: GalleryItem[]
  selectedId: string | null
  onSelect: (imageId: string) => void
}

export default function ThumbnailStrip({ images, selectedId, onSelect }: Props) {
  if (images.length === 0) {
    return (
      <div className="thumbnail-strip thumbnail-strip--empty">
        <span>No images in project</span>
      </div>
    )
  }

  return (
    <div className="thumbnail-strip">
      {images.map((img) => {
        const isSelected = img.id === selectedId
        const filename = img.relative_path.split('/').pop() ?? img.relative_path
        const shortName = filename.length > 16 ? filename.slice(0, 14) + '…' : filename

        return (
          <div
            key={img.id}
            className={`thumbnail-strip-item${isSelected ? ' thumbnail-strip-item--selected' : ''}`}
            onClick={() => onSelect(img.id)}
            role="button"
            tabIndex={0}
            title={filename}
            onKeyDown={(e) => e.key === 'Enter' && onSelect(img.id)}
          >
            <img
              src={img.thumbnail_url}
              alt={filename}
              className="thumbnail-strip-img"
            />
            <span className="thumbnail-strip-name">{shortName}</span>
          </div>
        )
      })}
    </div>
  )
}
