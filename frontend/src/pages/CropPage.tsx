import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router'

import { useAppStore } from '../stores/appStore'
import { useImages } from '../hooks/useImages'
import { generateBuckets, snapToNearestBucket } from '../types/crop'
import type { BucketSize, CropState, CropCoordinates } from '../types/crop'
import type { GalleryItem } from '../types/image'

import BucketSelector from '../components/Crop/BucketSelector'
import CropCard from '../components/Crop/CropCard'

interface AutoCropResult {
  image_id: string
  left: number
  top: number
  width: number
  height: number
  target_bucket: [number, number]
  detection_type: string
}

export default function CropPage() {
  // Global state
  const selectedImageIds = useAppStore((s) => s.selectedImageIds)
  const cropStates = useAppStore((s) => s.cropStates)
  const setCropState = useAppStore((s) => s.setCropState)
  const removeCropState = useAppStore((s) => s.removeCropState)

  // Local page state
  const [bucketSize, setBucketSize] = useState<BucketSize>(1024)
  const [allowNonSquare, setAllowNonSquare] = useState<boolean>(true)
  const [isCtrlHeld, setIsCtrlHeld] = useState<boolean>(false)
  const [isAutoCropping, setIsAutoCropping] = useState<boolean>(false)
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set())

  // Fetch all images; filter to selected ones
  const { data: galleryData, isLoading } = useImages()

  const selectedIds = Array.from(selectedImageIds)
  const selectedImages: GalleryItem[] = (galleryData?.images ?? []).filter(
    (img) => selectedImageIds.has(img.id) && !excludedIds.has(img.id),
  )

  // Compute buckets from global settings
  const buckets = generateBuckets(bucketSize, allowNonSquare)

  // Document-level CTRL key listener (per RESEARCH Pitfall 2 and 5 — lifted to page level)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Control') setIsCtrlHeld(true)
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Control') setIsCtrlHeld(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [])

  // Initialize crop states for images that don't have one yet
  useEffect(() => {
    for (const img of selectedImages) {
      if (!cropStates.has(img.id)) {
        // Default: center crop at first bucket aspect ratio
        const defaultBucket = buckets[0] ?? [bucketSize, bucketSize]
        const bucketAR = defaultBucket[0] / defaultBucket[1]
        const imgAR = img.width / img.height

        let cropW: number
        let cropH: number
        if (imgAR > bucketAR) {
          // Image is wider — limit by height
          cropH = img.height
          cropW = Math.round(img.height * bucketAR)
        } else {
          // Image is taller — limit by width
          cropW = img.width
          cropH = Math.round(img.width / bucketAR)
        }

        const left = Math.round((img.width - cropW) / 2)
        const top = Math.round((img.height - cropH) / 2)

        const coords: CropCoordinates = { left, top, width: cropW, height: cropH }
        setCropState(img.id, {
          imageId: img.id,
          coordinates: coords,
          rotation: 0,
          flipH: false,
          flipV: false,
          targetBucket: defaultBucket,
          included: true,
        })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedImages.length, buckets.length])

  const handleCropChange = useCallback(
    (imageId: string, state: CropState) => {
      setCropState(imageId, state)
    },
    [setCropState],
  )

  const handleExclude = useCallback(
    (imageId: string) => {
      setExcludedIds((prev) => new Set([...prev, imageId]))
      removeCropState(imageId)
    },
    [removeCropState],
  )

  async function handleAutoCropAll() {
    if (selectedImages.length === 0 || isAutoCropping) return
    setIsAutoCropping(true)
    try {
      const response = await fetch('/api/v1/crop/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_ids: selectedIds.filter((id) => !excludedIds.has(id)),
          bucket_size: bucketSize,
          allow_non_square: allowNonSquare,
        }),
      })

      if (!response.ok) {
        const text = await response.text()
        console.error('Auto-crop failed:', text)
        return
      }

      const results: AutoCropResult[] = await response.json()

      for (const result of results) {
        const snapped = snapToNearestBucket(result.width, result.height, buckets)
        const coords: CropCoordinates = {
          left: result.left,
          top: result.top,
          width: result.width,
          height: result.height,
        }
        const existing = cropStates.get(result.image_id)
        setCropState(result.image_id, {
          imageId: result.image_id,
          coordinates: coords,
          rotation: existing?.rotation ?? 0,
          flipH: existing?.flipH ?? false,
          flipV: existing?.flipV ?? false,
          targetBucket: snapped,
          included: true,
        })
      }
    } catch (err) {
      console.error('Auto-crop error:', err)
    } finally {
      setIsAutoCropping(false)
    }
  }

  // Empty state
  if (!isLoading && selectedImageIds.size === 0) {
    return (
      <div className="crop-page-empty">
        <h2>No images selected</h2>
        <p>
          Go to <Link to="/">Gallery</Link> to select images for cropping.
        </p>
      </div>
    )
  }

  return (
    <div>
      {/* Global controls bar */}
      <div className="crop-page-controls">
        <BucketSelector
          bucketSize={bucketSize}
          onBucketSizeChange={setBucketSize}
          allowNonSquare={allowNonSquare}
          onAllowNonSquareChange={setAllowNonSquare}
        />
        <button
          className="crop-autocrop-btn"
          onClick={handleAutoCropAll}
          disabled={isAutoCropping || selectedImages.length === 0}
        >
          {isAutoCropping ? 'Detecting subjects...' : 'Auto-crop All'}
        </button>
        <span className="crop-page-title">
          Editing {selectedImages.length} image{selectedImages.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Batch grid */}
      {isLoading ? (
        <div className="crop-page-empty">
          <p>Loading images...</p>
        </div>
      ) : (
        <div className="crop-grid">
          {selectedImages.map((img) => (
            <CropCard
              key={img.id}
              item={img}
              buckets={buckets}
              isCtrlHeld={isCtrlHeld}
              onCropChange={handleCropChange}
              onExclude={handleExclude}
              initialCropState={cropStates.get(img.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
