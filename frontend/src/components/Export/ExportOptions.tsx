interface ExportOptionsConfig {
  repeats: number
  trigger_word: string
  class_name: string
  concept_name: string
  output_path: string
}

interface ExportOptionsProps {
  config: ExportOptionsConfig
  trainer: string
  onChange: (field: keyof ExportOptionsConfig, value: string | number) => void
}

export default function ExportOptions({ config, trainer, onChange }: ExportOptionsProps) {
  return (
    <div className="export-options">
      <div className="export-option-row">
        <label className="export-option-label" htmlFor="export-repeats">
          Repeats
        </label>
        <input
          id="export-repeats"
          type="number"
          className="export-option-input"
          value={config.repeats}
          min={1}
          max={100}
          onChange={(e) => onChange('repeats', parseInt(e.target.value, 10) || 1)}
        />
        <span className="export-option-hint">Training repeat count for this dataset</span>
      </div>

      <div className="export-option-row">
        <label className="export-option-label" htmlFor="export-trigger">
          Trigger Word
        </label>
        <input
          id="export-trigger"
          type="text"
          className="export-option-input"
          value={config.trigger_word}
          placeholder="sks"
          onChange={(e) => onChange('trigger_word', e.target.value)}
        />
        <span className="export-option-hint">Anchor word to activate the LoRA concept</span>
      </div>

      <div className="export-option-row">
        <label className="export-option-label" htmlFor="export-class">
          Class Name
        </label>
        <input
          id="export-class"
          type="text"
          className="export-option-input"
          value={config.class_name}
          placeholder="person"
          onChange={(e) => onChange('class_name', e.target.value)}
        />
        <span className="export-option-hint">
          {trainer === 'kohya'
            ? 'Used in kohya folder name: {repeats}_{trigger} {class}'
            : 'Class descriptor for the subject'}
        </span>
      </div>

      {(trainer === 'onetrainer' || trainer === 'aitoolkit') && (
        <div className="export-option-row">
          <label className="export-option-label" htmlFor="export-concept">
            Concept Name
          </label>
          <input
            id="export-concept"
            type="text"
            className="export-option-input"
            value={config.concept_name}
            placeholder="my_concept"
            onChange={(e) => onChange('concept_name', e.target.value)}
          />
          <span className="export-option-hint">Used in concept.json and output filename</span>
        </div>
      )}

      <div className="export-option-row">
        <label className="export-option-label" htmlFor="export-output">
          Output Path
        </label>
        <input
          id="export-output"
          type="text"
          className="export-option-input export-option-input--wide"
          value={config.output_path}
          placeholder={`./export/${trainer}/`}
          onChange={(e) => onChange('output_path', e.target.value)}
        />
        <span className="export-option-hint">Destination directory for exported files</span>
      </div>
    </div>
  )
}
