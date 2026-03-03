import { needsUpscale } from '../../types/crop'

interface CropReadoutProps {
  cropWidth: number
  cropHeight: number
  imageWidth: number
  imageHeight: number
  targetBucket: [number, number]
}

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b)
}

function formatAspectRatio(w: number, h: number): string {
  const divisor = gcd(Math.round(w), Math.round(h))
  if (divisor === 0) return `${w}:${h}`
  return `${Math.round(w) / divisor}:${Math.round(h) / divisor}`
}

export default function CropReadout({
  cropWidth,
  cropHeight,
  imageWidth,
  imageHeight,
  targetBucket,
}: CropReadoutProps) {
  const [bucketW, bucketH] = targetBucket
  const upscale = needsUpscale(imageWidth, imageHeight, bucketW, bucketH)

  const resolutionColor = upscale ? '#ef4444' : '#22c55e'
  const arrow = upscale ? '\u2191' : '\u2193'  // up arrow or down arrow
  const arLabel = formatAspectRatio(cropWidth, cropHeight)

  return (
    <div className="crop-readout">
      <span className="crop-readout-resolution" style={{ color: resolutionColor }}>
        {arrow} {bucketW}x{bucketH}
      </span>
      <span className="crop-readout-ar-badge">
        {arLabel}
      </span>
    </div>
  )
}
