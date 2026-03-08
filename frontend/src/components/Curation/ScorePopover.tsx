import type { ImageScore } from '../../types/curation'

interface Props {
  score: ImageScore
  visible: boolean
  position: { x: number; y: number }
}

const SIGNAL_LABELS: { key: string; label: string }[] = [
  { key: 'face_confidence', label: 'Face Confidence' },
  { key: 'identity_similarity', label: 'Identity' },
  { key: 'quality_score', label: 'Quality (IQA)' },
  { key: 'aesthetic_score', label: 'Aesthetic' },
  { key: 'sharpness_whole', label: 'Sharpness' },
  { key: 'sharpness_face', label: 'Face Sharpness' },
  { key: 'occlusion_score', label: 'Occlusion' },
]

function barColor(value: number): string {
  if (value >= 0.7) return '#22c55e'
  if (value >= 0.4) return '#eab308'
  return '#ef4444'
}

export default function ScorePopover({ score, visible, position }: Props) {
  if (!visible) return null

  // Clamp position to avoid going off-screen
  const maxX = typeof window !== 'undefined' ? window.innerWidth - 300 : 800
  const maxY = typeof window !== 'undefined' ? window.innerHeight - 280 : 600
  const x = Math.min(position.x + 12, maxX)
  const y = Math.min(position.y + 12, maxY)

  return (
    <div
      className="score-popover"
      style={{ left: x, top: y }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8, fontSize: '0.95em' }}>
        Score: {score.composite_score.toFixed(2)}
      </div>
      {SIGNAL_LABELS.map(({ key, label }) => {
        const value = score.signals[key as keyof typeof score.signals] as number
        return (
          <div className="score-bar-row" key={key}>
            <span className="score-bar-label">{label}</span>
            <div style={{ flex: 1, background: '#2a2a3e', borderRadius: 4, height: 12, position: 'relative' }}>
              <div
                className="score-bar-fill"
                style={{
                  width: `${Math.min(value * 100, 100)}%`,
                  background: barColor(value),
                }}
              />
            </div>
            <span className="score-bar-value">{value.toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}
