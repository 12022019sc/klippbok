import { Masonry } from 'masonic'
import type { GalleryItem } from '../../types/image'
import ThumbnailCard from './ThumbnailCard'

interface MasonryGridProps {
  items: GalleryItem[]
  onItemClick: (item: GalleryItem, index: number) => void
  selectionMode?: boolean
  selectedIds?: Set<string>
}

interface RenderProps {
  index: number
  width: number
  data: GalleryItem
}

export default function MasonryGrid({
  items,
  onItemClick,
  selectionMode = false,
  selectedIds,
}: MasonryGridProps) {
  function CardRenderer({ index, width, data }: RenderProps) {
    return (
      <ThumbnailCard
        item={data}
        width={width}
        onClick={() => onItemClick(data, index)}
        isSelected={selectedIds?.has(data.id) ?? false}
        selectionMode={selectionMode}
      />
    )
  }

  return (
    <div className="gallery-container">
      <Masonry
        items={items}
        render={CardRenderer}
        columnGutter={8}
        columnWidth={220}
        overscanBy={2}
      />
    </div>
  )
}
