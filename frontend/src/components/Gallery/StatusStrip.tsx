interface StatusStripProps {
  resolution_ok: boolean
  quality_pass: boolean
  bucket: string | null
  width: number
  height: number
  caption: string | null
}

export default function StatusStrip({
  resolution_ok,
  quality_pass,
  bucket,
  width,
  height,
  caption,
}: StatusStripProps) {
  const captionPreview =
    caption && caption.length > 0
      ? caption.length > 40
        ? caption.slice(0, 40) + '...'
        : caption
      : null

  return (
    <div className="status-strip">
      <div className="status-strip-row">
        <span
          className={`status-dot ${resolution_ok ? 'ok' : 'fail'}`}
          title={resolution_ok ? 'Resolution OK' : 'Resolution too low'}
        />
        <span>{width}x{height}</span>
        <span
          className={`status-dot ${quality_pass ? 'ok' : 'fail'}`}
          title={quality_pass ? 'Sharp' : 'Blurry'}
        />
        <span style={{ color: quality_pass ? '#22c55e' : '#ef4444' }}>
          {quality_pass ? 'Sharp' : 'Blur'}
        </span>
        {bucket && (
          <span style={{ color: '#9ca3af', marginLeft: 'auto' }}>{bucket}</span>
        )}
      </div>
      {captionPreview && (
        <div className="status-caption">{captionPreview}</div>
      )}
    </div>
  )
}
