import ModelPicker from './ModelPicker'

export interface TrainingConfigValues {
  base_model_path: string
  lora_rank: number
  lora_alpha: number
  epochs: number
  batch_size: number
  learning_rate: number
  resolution: number
}

interface TrainingConfigProps {
  config: TrainingConfigValues
  onChange: (field: keyof TrainingConfigValues, value: string | number) => void
}

/**
 * Form for configuring LoRA training parameters.
 * Includes base model picker and all key hyperparameters.
 */
export default function TrainingConfig({ config, onChange }: TrainingConfigProps) {
  return (
    <div className="training-config">
      <div className="training-config-field">
        <ModelPicker
          selectedModel={config.base_model_path}
          onSelect={(path) => onChange('base_model_path', path)}
        />
      </div>

      <div className="training-config-grid">
        <div className="training-config-field">
          <label className="training-config-label">LoRA Rank</label>
          <input
            type="number"
            className="training-config-input"
            value={config.lora_rank}
            min={1}
            max={256}
            onChange={(e) => onChange('lora_rank', parseInt(e.target.value, 10) || 64)}
          />
        </div>

        <div className="training-config-field">
          <label className="training-config-label">LoRA Alpha</label>
          <input
            type="number"
            className="training-config-input"
            value={config.lora_alpha}
            min={1}
            max={256}
            onChange={(e) => onChange('lora_alpha', parseInt(e.target.value, 10) || 64)}
          />
        </div>

        <div className="training-config-field">
          <label className="training-config-label">Epochs</label>
          <input
            type="number"
            className="training-config-input"
            value={config.epochs}
            min={1}
            max={100}
            onChange={(e) => onChange('epochs', parseInt(e.target.value, 10) || 7)}
          />
        </div>

        <div className="training-config-field">
          <label className="training-config-label">Batch Size</label>
          <input
            type="number"
            className="training-config-input"
            value={config.batch_size}
            min={1}
            max={16}
            onChange={(e) => onChange('batch_size', parseInt(e.target.value, 10) || 2)}
          />
        </div>

        <div className="training-config-field">
          <label className="training-config-label">Learning Rate</label>
          <input
            type="number"
            className="training-config-input"
            value={config.learning_rate}
            min={0.0001}
            step={0.0001}
            onChange={(e) => onChange('learning_rate', parseFloat(e.target.value) || 1.0)}
          />
        </div>

        <div className="training-config-field">
          <label className="training-config-label">Resolution</label>
          <input
            type="number"
            className="training-config-input"
            value={config.resolution}
            min={256}
            max={2048}
            step={64}
            onChange={(e) => onChange('resolution', parseInt(e.target.value, 10) || 768)}
          />
        </div>
      </div>
    </div>
  )
}
