import { useAppStore } from '../../stores/appStore'

type FilterOption = 'all' | 'images' | 'videos'

const FILTER_OPTIONS: { value: FilterOption; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'images', label: 'Images' },
  { value: 'videos', label: 'Videos' },
]

export function GalleryFilter() {
  const galleryFilter = useAppStore((s) => s.galleryFilter)
  const setGalleryFilter = useAppStore((s) => s.setGalleryFilter)

  return (
    <div className="gallery-filter" role="group" aria-label="Filter by media type">
      {FILTER_OPTIONS.map(({ value, label }) => (
        <button
          key={value}
          className={`gallery-filter-btn${galleryFilter === value ? ' gallery-filter-btn--active' : ''}`}
          onClick={() => setGalleryFilter(value)}
          aria-pressed={galleryFilter === value}
          type="button"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
