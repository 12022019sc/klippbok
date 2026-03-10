import { useEffect, useState, useCallback } from 'react'
import TrainerPicker from '../components/Export/TrainerPicker'
import ExportOptions from '../components/Export/ExportOptions'
import ExportSummary from '../components/Export/ExportSummary'
import ExportProgress from '../components/Export/ExportProgress'
import { useExportEvents } from '../hooks/useExportEvents'

interface ExportDefaults {
  resolution: number
  default_repeats: number
  trigger_word: string
  class_name: string
  concept_name: string
}

interface ValidationData {
  candidates: number
  issues: Array<{ path: string; issue: string }>
}

interface ExportConfig {
  repeats: number
  trigger_word: string
  class_name: string
  concept_name: string
  output_path: string
}

function defaultOutputPath(trainer: string): string {
  return `./export/${trainer}/`
}

export default function ExportPage() {
  const [trainer, setTrainer] = useState<string>('onetrainer')
  const [config, setConfig] = useState<ExportConfig>({
    repeats: 5,
    trigger_word: 'sks',
    class_name: 'person',
    concept_name: '',
    output_path: defaultOutputPath('onetrainer'),
  })
  const [validation, setValidation] = useState<ValidationData | null>(null)
  const [isValidating, setIsValidating] = useState(false)
  const [proceedWithIssues, setProceedWithIssues] = useState(false)
  const [opId, setOpId] = useState<string | null>(null)

  const { progress, result, error, isExporting } = useExportEvents(opId)

  // Fetch defaults on mount
  useEffect(() => {
    fetch('/api/v1/export/defaults')
      .then((r) => r.json())
      .then((data: ExportDefaults) => {
        setConfig((prev) => ({
          ...prev,
          trigger_word: data.trigger_word || 'sks',
          repeats: data.default_repeats || 5,
          class_name: data.class_name || 'person',
          concept_name: data.concept_name || '',
        }))
      })
      .catch(() => {
        // Use defaults if fetch fails
      })
  }, [])

  // Fetch validation on mount and when trainer changes
  const fetchValidation = useCallback(() => {
    setIsValidating(true)
    setProceedWithIssues(false)
    fetch('/api/v1/export/validate')
      .then((r) => r.json())
      .then((data: ValidationData) => {
        setValidation(data)
        setIsValidating(false)
      })
      .catch(() => {
        setIsValidating(false)
      })
  }, [])

  useEffect(() => {
    fetchValidation()
  }, [fetchValidation])

  // Update output path default when trainer changes
  const handleTrainerChange = (newTrainer: string) => {
    setTrainer(newTrainer)
    setConfig((prev) => ({
      ...prev,
      output_path: defaultOutputPath(newTrainer),
    }))
  }

  const handleConfigChange = (field: keyof ExportConfig, value: string | number) => {
    setConfig((prev) => ({ ...prev, [field]: value }))
  }

  const hasIssues = (validation?.issues.length ?? 0) > 0
  const hasNoCandiates = (validation?.candidates ?? 0) === 0
  const canExport =
    !isExporting &&
    !hasNoCandiates &&
    !isValidating &&
    (proceedWithIssues || !hasIssues)

  const handleExport = async () => {
    if (!canExport) return

    try {
      const resp = await fetch('/api/v1/export/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trainer,
          repeats: config.repeats,
          trigger_word: config.trigger_word,
          class_name: config.class_name,
          concept_name: config.concept_name,
          output_path: config.output_path,
        }),
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Export failed' }))
        console.error('Export start failed:', err)
        return
      }

      const data = await resp.json()
      setOpId(data.op_id)
    } catch (err) {
      console.error('Export request failed:', err)
    }
  }

  return (
    <div className="page-container">
      <h1 className="page-title">Export</h1>
      <p className="page-subtitle">
        Package your cropped, captioned images into trainer-ready format.
      </p>

      <div className="export-page">
        {/* Section: Trainer Picker */}
        <section className="export-section">
          <h2 className="export-section-title">Trainer Format</h2>
          <TrainerPicker selected={trainer} onSelect={handleTrainerChange} />
        </section>

        {/* Section: Export Options */}
        <section className="export-section">
          <h2 className="export-section-title">Export Options</h2>
          <ExportOptions
            config={config}
            trainer={trainer}
            onChange={handleConfigChange}
          />
        </section>

        {/* Section: Pre-export Summary */}
        <section className="export-section">
          <h2 className="export-section-title">Dataset Summary</h2>
          <ExportSummary
            candidateCount={validation?.candidates ?? 0}
            issues={validation?.issues ?? []}
            isLoading={isValidating}
            onProceed={() => setProceedWithIssues(true)}
          />
        </section>

        {/* Export button */}
        <div className="export-action-row">
          <button
            type="button"
            className="export-btn"
            disabled={!canExport}
            onClick={handleExport}
          >
            {isExporting ? 'Exporting...' : 'Export Dataset'}
          </button>
          {hasIssues && !proceedWithIssues && (
            <span className="export-btn-hint">
              Fix caption issues above or click "Proceed anyway" to export with warnings.
            </span>
          )}
        </div>

        {/* Section: Progress */}
        {(isExporting || result || error) && (
          <section className="export-section">
            <ExportProgress
              progress={progress}
              result={result}
              error={error}
              isExporting={isExporting}
            />
          </section>
        )}
      </div>
    </div>
  )
}
