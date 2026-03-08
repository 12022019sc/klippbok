import { useAppStore } from '../../stores/appStore'
import type { GallerySortKey } from '../../types/image'

const SORT_OPTIONS: { value: GallerySortKey; label: string }[] = [
  { value: 'name', label: 'Name' },
  { value: 'quality', label: 'Quality' },
  { value: 'dimensions', label: 'Dimensions' },
  { value: 'size', label: 'File Size' },
  { value: 'type', label: 'Type' },
  { value: 'date', label: 'Date' },
]

export function GallerySort() {
  const sortKey = useAppStore((s) => s.gallerySortKey)
  const sortDir = useAppStore((s) => s.gallerySortDir)
  const setGallerySort = useAppStore((s) => s.setGallerySort)

  function handleKeyChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setGallerySort(e.target.value as GallerySortKey, sortDir)
  }

  function toggleDir() {
    setGallerySort(sortKey, sortDir === 'asc' ? 'desc' : 'asc')
  }

  return (
    <div className="gallery-sort" role="group" aria-label="Sort gallery">
      <select
        className="gallery-sort-select"
        value={sortKey}
        onChange={handleKeyChange}
        aria-label="Sort by"
      >
        {SORT_OPTIONS.map(({ value, label }) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
      <button
        className="gallery-sort-dir-btn"
        onClick={toggleDir}
        aria-label={sortDir === 'asc' ? 'Sort ascending' : 'Sort descending'}
        title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
        type="button"
      >
        {sortDir === 'asc' ? '\u2191' : '\u2193'}
      </button>
    </div>
  )
}
