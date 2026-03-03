import type { BucketSize } from '../../types/crop'

interface BucketSelectorProps {
  bucketSize: BucketSize
  onBucketSizeChange: (size: BucketSize) => void
  allowNonSquare: boolean
  onAllowNonSquareChange: (allow: boolean) => void
}

export default function BucketSelector({
  bucketSize,
  onBucketSizeChange,
  allowNonSquare,
  onAllowNonSquareChange,
}: BucketSelectorProps) {
  return (
    <div className="bucket-selector">
      <div className="bucket-selector-group">
        <label className="bucket-selector-label" htmlFor="bucket-size-select">
          Bucket Size
        </label>
        <select
          id="bucket-size-select"
          className="bucket-selector-select"
          value={bucketSize}
          onChange={(e) => onBucketSizeChange(Number(e.target.value) as BucketSize)}
        >
          <option value={512}>512</option>
          <option value={768}>768</option>
          <option value={1024}>1024</option>
        </select>
      </div>
      <div className="bucket-selector-group">
        <input
          id="allow-non-square"
          type="checkbox"
          className="bucket-selector-checkbox"
          checked={allowNonSquare}
          onChange={(e) => onAllowNonSquareChange(e.target.checked)}
        />
        <label className="bucket-selector-label" htmlFor="allow-non-square">
          Allow Non-Square
        </label>
      </div>
    </div>
  )
}
