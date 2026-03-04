import { useRef, useState, useEffect, useCallback } from 'react'
import { Cropper, RectangleStencil } from 'react-advanced-cropper'
import type { CropperRef } from 'react-advanced-cropper'
import 'react-advanced-cropper/dist/style.css'

import type { GalleryItem } from '../../types/image'
import type { CropState, CropCoordinates } from '../../types/crop'
import { snapToNearestBucket } from '../../types/crop'
import CropReadout from './CropReadout'

interface CropCardProps {
  item: GalleryItem
  buckets: [number, number][]
  isCtrlHeld: boolean
  onCropChange: (imageId: string, state: CropState) => void
  onExclude: (imageId: string) => void
  initialCropState?: CropState
}

export default function CropCard({
  item,
  buckets,
  isCtrlHeld,
  onCropChange,
  onExclude,
  initialCropState,
}: CropCardProps) {
  const cropperRef = useRef<CropperRef>(null)

  // Derive initial bucket from initial state or snap to first sensible one
  const initialBucket = initialCropState?.targetBucket ?? buckets[0] ?? [1024, 1024]
  const [targetBucket, setTargetBucket] = useState<[number, number]>(initialBucket)
  const [lockedAR, setLockedAR] = useState<number>(initialBucket[0] / initialBucket[1])

  // Track current crop dimensions for the readout
  const [cropWidth, setCropWidth] = useState<number>(item.width)
  const [cropHeight, setCropHeight] = useState<number>(item.height)

  // Per-card rotation and flip state
  const [rotation, setRotation] = useState<number>(initialCropState?.rotation ?? 0)
  const [flipH, setFlipH] = useState<boolean>(initialCropState?.flipH ?? false)
  const [flipV, setFlipV] = useState<boolean>(initialCropState?.flipV ?? false)

  // Zoom factor for range input (stored as 0-100 slider value; 20 = 1x zoom)
  const [zoomValue, setZoomValue] = useState<number>(20)

  // Truncate filename for display
  const filename = item.relative_path.split('/').pop() ?? item.relative_path
  const displayName = filename.length > 30 ? filename.slice(0, 27) + '...' : filename

  // When CTRL is released, snap the current crop to the nearest bucket
  const snapToBucket = useCallback(() => {
    const coords = cropperRef.current?.getCoordinates()
    if (!coords || !buckets.length) return
    const snapped = snapToNearestBucket(coords.width, coords.height, buckets)
    setTargetBucket(snapped)
    setLockedAR(snapped[0] / snapped[1])
    setCropWidth(coords.width)
    setCropHeight(coords.height)
  }, [buckets])

  // React to CTRL release: snap to nearest bucket
  useEffect(() => {
    if (!isCtrlHeld) {
      snapToBucket()
    }
  }, [isCtrlHeld, snapToBucket])

  // When buckets list changes (global bucket size changed), re-snap to nearest bucket
  useEffect(() => {
    if (buckets.length > 0) {
      const snapped = snapToNearestBucket(cropWidth, cropHeight, buckets)
      setTargetBucket(snapped)
      setLockedAR(snapped[0] / snapped[1])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buckets])

  // No imperative setCoordinates needed — autocrop results are applied via
  // key-based remount from CropPage (autocropVersion), so the Cropper mounts
  // fresh with correct defaultCoordinates and aspectRatio in sync.

  function handleChange(cropper: CropperRef) {
    const coords = cropper.getCoordinates()
    if (!coords) return
    setCropWidth(coords.width)
    setCropHeight(coords.height)

    // When not in freeform mode, update readout based on locked AR
    if (!isCtrlHeld) {
      const snapped = snapToNearestBucket(coords.width, coords.height, buckets)
      setTargetBucket(snapped)
    }

    // Propagate crop state up
    const cropCoords: CropCoordinates = {
      left: coords.left,
      top: coords.top,
      width: coords.width,
      height: coords.height,
    }
    const newState: CropState = {
      imageId: item.id,
      coordinates: cropCoords,
      rotation,
      flipH,
      flipV,
      targetBucket,
      included: true,
    }
    onCropChange(item.id, newState)
  }

  function handleRotateCW() {
    cropperRef.current?.rotateImage(90)
    setRotation((r) => (r + 90) % 360)
  }

  function handleRotateCCW() {
    cropperRef.current?.rotateImage(-90)
    setRotation((r) => (r - 90 + 360) % 360)
  }

  function handleFlipH() {
    cropperRef.current?.flipImage(true, false)
    setFlipH((f) => !f)
  }

  function handleFlipV() {
    cropperRef.current?.flipImage(false, true)
    setFlipV((f) => !f)
  }

  function handleZoomChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = Number(e.target.value)
    setZoomValue(value)
    // Map 0-100 slider to zoom factor: 0.5x to 3x
    const factor = 0.5 + (value / 100) * 2.5
    cropperRef.current?.zoomImage(factor, { transitions: false })
  }

  return (
    <div className="crop-card">
      {/* Header */}
      <div className="crop-card-header">
        <span className="crop-card-filename" title={filename}>
          {displayName}
        </span>
        <span className="crop-card-dimensions">
          {item.width}x{item.height}
        </span>
        <span
          className="crop-card-quality-badge"
          style={{
            background: item.quality_pass ? '#166534' : '#7f1d1d',
            color: item.quality_pass ? '#22c55e' : '#ef4444',
          }}
        >
          {item.quality_pass ? 'Sharp' : 'Blurry'}
        </span>
      </div>

      {/* Cropper — onWheelCapture prevents react-advanced-cropper's zoom so the page scrolls normally */}
      <div className="crop-card-cropper-container" onWheelCapture={(e) => e.stopPropagation()}>
        <Cropper
          ref={cropperRef}
          src={item.full_url}
          defaultCoordinates={initialCropState?.coordinates ? {
            left: initialCropState.coordinates.left,
            top: initialCropState.coordinates.top,
            width: initialCropState.coordinates.width,
            height: initialCropState.coordinates.height,
          } : undefined}
          stencilComponent={RectangleStencil}
          stencilProps={{
            aspectRatio: isCtrlHeld ? undefined : lockedAR,
          }}
          onChange={handleChange}
        />
      </div>

      {/* Resolution readout */}
      <CropReadout
        cropWidth={cropWidth}
        cropHeight={cropHeight}
        imageWidth={item.width}
        imageHeight={item.height}
        targetBucket={targetBucket}
      />

      {/* Controls row */}
      <div className="crop-controls">
        <div className="crop-controls-left">
          <button
            className="crop-control-btn"
            onClick={handleRotateCW}
            title="Rotate 90° clockwise"
          >
            &#x27F3;
          </button>
          <button
            className="crop-control-btn"
            onClick={handleRotateCCW}
            title="Rotate 90° counter-clockwise"
          >
            &#x27F2;
          </button>
          <button
            className="crop-control-btn"
            onClick={handleFlipH}
            title="Flip horizontal"
          >
            &#x21D4;
          </button>
          <button
            className="crop-control-btn"
            onClick={handleFlipV}
            title="Flip vertical"
          >
            &#x21D5;
          </button>
        </div>
        <div className="crop-controls-right">
          <label className="crop-zoom-label">Zoom</label>
          <input
            type="range"
            min={0}
            max={100}
            value={zoomValue}
            onChange={handleZoomChange}
            className="crop-zoom-slider"
          />
          <button
            className="crop-control-btn crop-zoom-reset"
            onClick={() => { setZoomValue(20); cropperRef.current?.reset() }}
            title="Reset zoom to 1x"
          >
            1x
          </button>
        </div>
      </div>

      {/* Footer: include/exclude */}
      <div className="crop-card-footer">
        <button
          className="crop-include-btn"
          onClick={() => {
            const coords = cropperRef.current?.getCoordinates()
            if (!coords) return
            const cropCoords: CropCoordinates = {
              left: coords.left,
              top: coords.top,
              width: coords.width,
              height: coords.height,
            }
            onCropChange(item.id, {
              imageId: item.id,
              coordinates: cropCoords,
              rotation,
              flipH,
              flipV,
              targetBucket,
              included: true,
            })
          }}
          title="Include in dataset"
        >
          + Include
        </button>
        <button
          className="crop-exclude-btn"
          onClick={() => onExclude(item.id)}
          title="Exclude from dataset"
        >
          x Exclude
        </button>
      </div>
    </div>
  )
}
