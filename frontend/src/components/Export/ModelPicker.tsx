import { useEffect, useState } from 'react'
import { Link } from 'react-router'

interface ModelEntry {
  path: string
  name: string
  subfolder: string
}

interface ModelPickerProps {
  selectedModel: string
  onSelect: (path: string) => void
}

/**
 * Dropdown for selecting a base model from the configured model directory.
 * Groups models by subfolder. Shows a link to Settings if none configured.
 */
export default function ModelPicker({ selectedModel, onSelect }: ModelPickerProps) {
  const [models, setModels] = useState<ModelEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch('/api/v1/export/train/models')
      .then((r) => r.json())
      .then((data: ModelEntry[]) => {
        setModels(data)
        setLoading(false)
      })
      .catch(() => {
        setModels([])
        setLoading(false)
      })
  }, [])

  if (loading) {
    return <p className="model-picker-empty">Loading models...</p>
  }

  if (models.length === 0) {
    return (
      <p className="model-picker-empty">
        No model directory configured.{' '}
        <Link to="/settings" className="model-picker-link">
          Set in Settings
        </Link>
      </p>
    )
  }

  // Group by subfolder
  const grouped: Record<string, ModelEntry[]> = {}
  for (const m of models) {
    const key = m.subfolder || 'Root'
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(m)
  }

  return (
    <div className="model-picker">
      <label className="model-picker-label">Base Model</label>
      <select
        className="model-picker-select"
        value={selectedModel}
        onChange={(e) => onSelect(e.target.value)}
      >
        <option value="">-- Select a base model (optional) --</option>
        {Object.entries(grouped).map(([subfolder, items]) => (
          <optgroup key={subfolder} label={subfolder}>
            {items.map((m) => (
              <option key={m.path} value={m.path}>
                {m.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}
