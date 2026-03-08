import type { CurationProgress as CurationProgressType } from '../../types/curation'

interface CurationProgressProps {
  progress: CurationProgressType | null
  onCancel: () => void
}

const STAGE_LABELS: Record<string, string> = {
  scoring: 'Scoring images...',
  selecting: 'Selecting diverse subset...',
  clustering: 'Detecting reference face...',
  dedup: 'Removing duplicates...',
  quality: 'Evaluating quality...',
  identity: 'Verifying identity...',
  diversity: 'Optimizing diversity...',
}

export default function CurationProgress({ progress, onCancel }: CurationProgressProps) {
  const pct = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0

  const stageLabel = progress?.stage
    ? STAGE_LABELS[progress.stage] ?? progress.stage
    : 'Starting...'

  return (
    <div className="video-progress">
      <div className="video-progress-header">
        <span className="video-progress-stage">{stageLabel}</span>
        {progress && progress.total > 0 && (
          <span className="video-progress-pct">{pct}%</span>
        )}
      </div>
      <div className="video-progress-track">
        <div className="video-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      {progress && progress.total > 0 && (
        <p className="video-progress-count">
          {progress.current} / {progress.total}
        </p>
      )}
      <div style={{ marginTop: '1rem' }}>
        <button className="video-btn-cancel" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
