interface TrainerOption {
  id: string
  label: string
  description: string
  recommended?: boolean
}

const TRAINERS: TrainerOption[] = [
  {
    id: 'kohya',
    label: 'kohya / sd-scripts',
    description: 'Classic LoRA training. Widely supported, extensive documentation.',
  },
  {
    id: 'aitoolkit',
    label: 'ai-toolkit',
    description: 'Ostris FLUX-focused trainer. YAML config. Good for SDXL/FLUX.',
  },
  {
    id: 'onetrainer',
    label: 'OneTrainer',
    description: 'GUI-based trainer with Prodigy optimizer. Recommended for SD1.5.',
    recommended: true,
  },
]

interface TrainerPickerProps {
  selected: string
  onSelect: (trainer: string) => void
}

export default function TrainerPicker({ selected, onSelect }: TrainerPickerProps) {
  return (
    <div className="trainer-picker">
      {TRAINERS.map((trainer) => (
        <button
          key={trainer.id}
          className={`trainer-card${selected === trainer.id ? ' trainer-card--selected' : ''}${trainer.recommended ? ' trainer-card--recommended' : ''}`}
          onClick={() => onSelect(trainer.id)}
          type="button"
        >
          <div className="trainer-card-header">
            <span className="trainer-card-label">{trainer.label}</span>
            {trainer.recommended && (
              <span className="trainer-card-badge">Recommended</span>
            )}
          </div>
          <p className="trainer-card-desc">{trainer.description}</p>
        </button>
      ))}
    </div>
  )
}
