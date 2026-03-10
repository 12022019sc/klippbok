import type { ExportProgress as Progress, ExportResult } from '../../hooks/useExportEvents'

interface ExportProgressProps {
  progress: Progress | null
  result: ExportResult | null
  error: string | null
  isExporting: boolean
}

export default function ExportProgress({
  progress,
  result,
  error,
  isExporting,
}: ExportProgressProps) {
  if (!isExporting && !result && !error) {
    return null
  }

  const pct =
    progress && progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : isExporting
        ? 0
        : 100

  return (
    <div className="export-progress-panel">
      {error ? (
        <div className="export-progress-error">
          <span className="export-progress-error-icon">!</span>
          <span>{error}</span>
        </div>
      ) : result ? (
        <div className="export-progress-success">
          <div className="export-progress-success-header">
            Export complete
          </div>
          <div className="export-progress-success-detail">
            <span>{result.image_count} {result.image_count === 1 ? 'image' : 'images'} exported</span>
          </div>
          <div className="export-progress-success-path">
            <span className="export-progress-success-path-label">Output:</span>
            <code className="export-progress-success-path-value">{result.output_dir}</code>
          </div>
          <div className="export-progress-success-path">
            <span className="export-progress-success-path-label">Config:</span>
            <code className="export-progress-success-path-value">{result.config_path}</code>
          </div>
        </div>
      ) : (
        <div className="export-progress-active">
          <div className="export-progress-header">
            <span className="export-progress-label">
              {progress?.message ?? 'Exporting...'}
            </span>
            <span className="export-progress-count">
              {progress && progress.total > 0
                ? `${progress.current} / ${progress.total}`
                : ''}
            </span>
          </div>
          <div className="export-progress-bar-track">
            <div
              className="export-progress-bar-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
