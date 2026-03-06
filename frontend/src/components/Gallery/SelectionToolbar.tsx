import { useNavigate } from 'react-router'
import { useAppStore } from '../../stores/appStore'
import type { GalleryItem } from '../../types/image'

interface SelectionToolbarProps {
  items: GalleryItem[]
}

export default function SelectionToolbar({ items }: SelectionToolbarProps) {
  const navigate = useNavigate()
  const selectionMode = useAppStore((s) => s.selectionMode)
  const selectedImageIds = useAppStore((s) => s.selectedImageIds)
  const toggleSelectionMode = useAppStore((s) => s.toggleSelectionMode)
  const selectAll = useAppStore((s) => s.selectAll)
  const deselectAll = useAppStore((s) => s.deselectAll)
  const selectByFilter = useAppStore((s) => s.selectByFilter)

  function handleSelectAll() {
    selectAll(items.map((item) => item.id))
  }

  function handleSelectQualityPassing() {
    selectByFilter(items.filter((item) => item.quality_pass).map((item) => item.id))
  }

  function handleSelectNonDuplicates() {
    selectByFilter(items.filter((item) => !item.is_near_duplicate).map((item) => item.id))
  }

  function handleProcess() {
    navigate('/process')
  }

  // Detect selected videos for "Process Videos" action
  const selectedVideos = items.filter(
    (item) => selectedImageIds.has(item.id) && item.media_type === 'video'
  )

  function handleProcessSelectedVideos() {
    if (selectedVideos.length === 0) return
    navigate('/process-videos', {
      state: { videoPaths: selectedVideos.map((v) => v.relative_path) },
    })
    toggleSelectionMode()
  }

  const selectedCount = selectedImageIds.size

  return (
    <div className="selection-toolbar">
      <div className="selection-toolbar-controls">
        <button
          className={`selection-toggle-btn${selectionMode ? ' active' : ''}`}
          onClick={toggleSelectionMode}
          title={selectionMode ? 'Exit selection mode' : 'Enter selection mode'}
        >
          {selectionMode ? 'Exit Select Mode' : 'Select Mode'}
        </button>

        {selectionMode && (
          <>
            <div className="selection-filter-btns">
              <button className="selection-filter-btn" onClick={handleSelectAll}>
                Select All
              </button>
              <button className="selection-filter-btn" onClick={deselectAll}>
                Deselect All
              </button>
              <button className="selection-filter-btn" onClick={handleSelectQualityPassing}>
                Select Passing Quality
              </button>
              <button className="selection-filter-btn" onClick={handleSelectNonDuplicates}>
                Select Non-Duplicates
              </button>
            </div>

            <span className="selection-count">
              {selectedCount} selected
            </span>

            {selectedCount >= 1 && (
              <button className="selection-process-btn" onClick={handleProcess}>
                Process ({selectedCount})
              </button>
            )}

            {selectedVideos.length > 0 && (
              <button className="selection-process-btn" onClick={handleProcessSelectedVideos}>
                Process Videos ({selectedVideos.length})
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
