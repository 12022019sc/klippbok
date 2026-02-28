import { useState } from 'react'
import { useImages } from '../hooks/useImages'
import MasonryGrid from '../components/Gallery/MasonryGrid'
import ImageLightbox from '../components/Lightbox/ImageLightbox'
import type { GalleryItem } from '../types/image'

export default function GalleryPage() {
  const { data, isLoading, error } = useImages()
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  function handleItemClick(_item: GalleryItem, index: number) {
    setSelectedIndex(index)
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

  const images = data?.images ?? []

  if (images.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>
        No images imported yet.
      </div>
    )
  }

  return (
    <>
      <MasonryGrid items={images} onItemClick={handleItemClick} />
      {selectedIndex !== null && (
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
