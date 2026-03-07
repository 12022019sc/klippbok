interface ProcessingProgressProps {
  stage: string
  current: number
  total: number
  message: string
  onCancel: () => void
}

/**
 * Stage-aware progress display for video processing pipeline.
 * Shows current stage name, progress bar, and message.
 */
export default function ProcessingProgress({ stage, current, total, message, onCancel }: ProcessingProgressProps) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0

  return (
    <div className="processing-progress">
      <h3 className="stage-name">{stage || 'Starting...'}</h3>
      <div className="video-progress-track">
        <div className="video-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      {total > 0 && (
        <p className="video-progress-count">{current} / {total} ({pct}%)</p>
      )}
      <p className="video-progress-message">{message}</p>
      <button className="cancel-btn" onClick={onCancel}>
        Cancel
      </button>
    </div>
  )
}
