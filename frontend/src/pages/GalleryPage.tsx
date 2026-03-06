import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useImages } from '../hooks/useImages'
import { useAppStore } from '../stores/appStore'
import { toast } from 'sonner'
import MasonryGrid from '../components/Gallery/MasonryGrid'
import SelectionToolbar from '../components/Gallery/SelectionToolbar'
import { GalleryFilter } from '../components/Gallery/GalleryFilter'
import ImageLightbox from '../components/Lightbox/ImageLightbox'
import type { GalleryItem } from '../types/image'

export default function GalleryPage() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useImages()

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const projectDir = useAppStore((s) => s.projectDir)
  const importOperationId = useAppStore((s) => s.importOperationId)
  const importProgress = useAppStore((s) => s.importProgress)
  const setImportOperationId = useAppStore((s) => s.setImportOperationId)
  const [importStarting, setImportStarting] = useState(false)
  const hasAutoImported = useRef(false)

  const selectionMode = useAppStore((s) => s.selectionMode)
  const selectedImageIds = useAppStore((s) => s.selectedImageIds)
  const toggleImageSelection = useAppStore((s) => s.toggleImageSelection)
  const setCleanupAutoStart = useAppStore((s) => s.setCleanupAutoStart)

  const isImporting = importOperationId !== null

  async function handleAutoImport() {
    if (!projectDir || importStarting || isImporting) return
    setImportStarting(true)
    try {
      const res = await fetch('/api/v1/import/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: projectDir, recursive: false }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start import', { description: (err as { detail: string }).detail })
        return
      }
      const data = await res.json() as { operation_id: string }
      setImportOperationId(data.operation_id)
      toast.info('Scanning images...', { description: projectDir })
    } catch (err) {
      toast.error('Failed to start import', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setImportStarting(false)
    }
  }

  const images = data?.images ?? []

  // Auto-import when gallery is empty and a project is selected
  // Must be above early returns to satisfy React's rules of hooks
  useEffect(() => {
    if (!isLoading && images.length === 0 && projectDir && !isImporting && !importStarting && !hasAutoImported.current) {
      hasAutoImported.current = true
      handleAutoImport()
    }
  }, [isLoading, images.length, projectDir, isImporting, importStarting])

  function handleItemClick(item: GalleryItem, index: number) {
    if (selectionMode) {
      toggleImageSelection(item.id)
    } else {
      setSelectedIndex(index)
    }
  }

  function handleLightboxClose() {
    setSelectedIndex(null)
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>
        Loading images...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: '#ef4444' }}>
        Error loading images: {error.message}
      </div>
    )
  }

  // Show import progress when an import is active
  if (isImporting) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem' }}>
        {importProgress ? (
          <div style={{ maxWidth: 480, margin: '0 auto' }}>
            <div className="import-progress">
              <div className="import-progress-header">
                <span className="import-progress-label">Importing images...</span>
                {importProgress.total > 0 && (
                  <span className="import-progress-count">
                    {importProgress.current} / {importProgress.total}
                  </span>
                )}
              </div>
              <div className="import-progress-bar-track">
                <div
                  className="import-progress-bar-fill"
                  style={{
                    width:
                      importProgress.total > 0
                        ? `${Math.round((importProgress.current / importProgress.total) * 100)}%`
                        : '0%',
                  }}
                />
              </div>
              <p className="import-progress-message">{importProgress.message}</p>
            </div>
          </div>
        ) : (
          <p style={{ color: '#9ca3af' }}>Connecting to import stream...</p>
        )}
      </div>
    )
  }

  if (images.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>
        <p>No media found in this project.</p>
      </div>
    )
  }

  return (
    <>
      <div className="gallery-header-bar">
        <SelectionToolbar items={images} />
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            className="video-btn-secondary"
            onClick={() => {
              setCleanupAutoStart(true)
              navigate('/cleanup')
            }}
          >
            Cleanup
          </button>
          <GalleryFilter />
        </div>
      </div>
      <MasonryGrid
        items={images}
        onItemClick={handleItemClick}
        selectionMode={selectionMode}
        selectedIds={selectedImageIds}
      />
      {!selectionMode && selectedIndex !== null && (
        <ImageLightbox
          items={images}
          currentIndex={selectedIndex}
          open={selectedIndex !== null}
          onClose={handleLightboxClose}
        />
      )}
    </>
  )
}
