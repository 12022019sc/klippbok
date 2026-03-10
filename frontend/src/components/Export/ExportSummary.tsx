import { Link } from 'react-router'

interface ValidationIssue {
  path: string
  issue: string
}

interface ExportSummaryProps {
  candidateCount: number
  issues: ValidationIssue[]
  isLoading: boolean
  onProceed: () => void
}

function issueLabel(issue: string): string {
  if (issue === 'missing_caption') return 'Missing caption'
  if (issue === 'empty_caption') return 'Empty caption'
  return issue
}

export default function ExportSummary({
  candidateCount,
  issues,
  isLoading,
  onProceed,
}: ExportSummaryProps) {
  if (isLoading) {
    return (
      <div className="export-summary export-summary--loading">
        <span className="export-summary-loading-text">Checking export candidates...</span>
      </div>
    )
  }

  // Empty state — no cropped images
  if (candidateCount === 0) {
    return (
      <div className="export-summary export-summary--empty">
        <p className="export-summary-empty-text">
          No cropped images found. Go to{' '}
          <Link to="/crop" className="export-summary-link">
            Crop
          </Link>{' '}
          to prepare your images first.
        </p>
      </div>
    )
  }

  return (
    <div className="export-summary">
      <div className="export-summary-count">
        <span className="export-summary-count-num">{candidateCount}</span>
        <span className="export-summary-count-label">
          {candidateCount === 1 ? 'image' : 'images'} ready for export
        </span>
      </div>

      {issues.length > 0 && (
        <div className="export-summary-warnings">
          <div className="export-summary-warning-header">
            <span className="export-summary-warning-icon">!</span>
            <strong>{issues.length} caption {issues.length === 1 ? 'issue' : 'issues'} found</strong>
          </div>
          <ul className="export-summary-issue-list">
            {issues.slice(0, 5).map((issue, idx) => (
              <li key={idx} className="export-summary-issue-item">
                <span className="export-summary-issue-type">{issueLabel(issue.issue)}</span>
                <span className="export-summary-issue-path">{issue.path}</span>
              </li>
            ))}
            {issues.length > 5 && (
              <li className="export-summary-issue-item export-summary-issue-more">
                ... and {issues.length - 5} more
              </li>
            )}
          </ul>
          <div className="export-summary-warning-actions">
            <Link to="/caption" className="export-summary-link">
              Go fix captions
            </Link>
            <button
              type="button"
              className="export-summary-proceed-btn"
              onClick={onProceed}
            >
              Proceed anyway
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
