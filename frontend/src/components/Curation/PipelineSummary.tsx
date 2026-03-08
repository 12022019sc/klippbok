import type { PipelineSummary as PipelineSummaryType } from '../../types/curation'

interface Props {
  summary: PipelineSummaryType
}

export default function PipelineSummary({ summary }: Props) {
  return (
    <div className="pipeline-summary">
      <div className="pipeline-funnel">
        <div className="pipeline-stat">
          <div className="pipeline-stat-value">{summary.total_scanned}</div>
          <div className="pipeline-stat-label">Scanned</div>
        </div>
        <div className="pipeline-arrow">&rarr;</div>
        <div className="pipeline-stat">
          <div className="pipeline-stat-value">{summary.passed_quality}</div>
          <div className="pipeline-stat-label">Passed Quality</div>
        </div>
        <div className="pipeline-arrow">&rarr;</div>
        <div className="pipeline-stat">
          <div className="pipeline-stat-value">{summary.selected}</div>
          <div className="pipeline-stat-label">Selected</div>
        </div>
      </div>
      {summary.diversity_metrics && (
        <div className="pipeline-diversity">
          Pose Variety: {summary.diversity_metrics.pose_variety.toFixed(1)}
          {' | '}
          Unique Backgrounds: {summary.diversity_metrics.unique_backgrounds}
          {' | '}
          Expression Spread: {summary.diversity_metrics.expression_spread.toFixed(1)}
        </div>
      )}
    </div>
  )
}
