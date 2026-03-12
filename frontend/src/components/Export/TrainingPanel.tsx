import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import TrainingConfig, { type TrainingConfigValues } from './TrainingConfig'
import { useTrainingEvents } from '../../hooks/useTrainingEvents'
import { useGpuStatus } from '../../hooks/useGpuStatus'

interface TrainingPanelProps {
  presetPath: string
}

interface TrainStatus {
  onetrainer_detected: boolean
  onetrainer_path: string | null
  training_active: boolean
  gpu_vram_used_mb: number | null
  gpu_busy: boolean
}

const DEFAULT_CONFIG: TrainingConfigValues = {
  base_model_path: '',
  lora_rank: 64,
  lora_alpha: 64,
  epochs: 7,
  batch_size: 2,
  learning_rate: 1.0,
  resolution: 768,
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

/**
 * Post-export training panel component.
 *
 * Shows ONLY after a successful export. Detects OneTrainer, shows training
 * configuration form, launches headless training or GUI, monitors progress
 * via SSE, embeds TensorBoard iframe, and displays completion/error state.
 */
export default function TrainingPanel({ presetPath }: TrainingPanelProps) {
  const [trainStatus, setTrainStatus] = useState<TrainStatus | null>(null)
  const [config, setConfig] = useState<TrainingConfigValues>(DEFAULT_CONFIG)
  const [opId, setOpId] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isLaunchingGui, setIsLaunchingGui] = useState(false)
  const [isStopping, setIsStopping] = useState(false)

  const { gpuBusy, vramUsedMb } = useGpuStatus()
  const { epoch, totalEpochs, isTraining, error, logSnippet, result } = useTrainingEvents(opId)

  // Fetch training status on mount
  useEffect(() => {
    fetch('/api/v1/export/train/status')
      .then((r) => r.json())
      .then((data: TrainStatus) => setTrainStatus(data))
      .catch(() => setTrainStatus(null))
  }, [])

  function handleConfigChange(field: keyof TrainingConfigValues, value: string | number) {
    setConfig((prev) => ({ ...prev, [field]: value }))
  }

  async function handleStartTraining() {
    if (isStarting) return
    setIsStarting(true)
    try {
      const resp = await fetch('/api/v1/export/train/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preset_path: presetPath,
          base_model_path: config.base_model_path || null,
          lora_rank: config.lora_rank,
          lora_alpha: config.lora_alpha,
          epochs: config.epochs,
          batch_size: config.batch_size,
          learning_rate: config.learning_rate,
          resolution: config.resolution,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed to start training' }))
        console.error('Training start failed:', err)
        return
      }
      const data = (await resp.json()) as { op_id: string }
      setOpId(data.op_id)
    } catch (err) {
      console.error('Training request error:', err)
    } finally {
      setIsStarting(false)
    }
  }

  async function handleLaunchGui() {
    setIsLaunchingGui(true)
    try {
      await fetch('/api/v1/export/train/launch-gui', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset_path: presetPath }),
      })
    } catch (err) {
      console.error('Launch GUI error:', err)
    } finally {
      setIsLaunchingGui(false)
    }
  }

  async function handleStop() {
    if (!opId || isStopping) return
    setIsStopping(true)
    try {
      await fetch(`/api/v1/export/train/${opId}/stop`, { method: 'POST' })
    } catch (err) {
      console.error('Stop training error:', err)
    } finally {
      setIsStopping(false)
    }
  }

  function handleNewTraining() {
    setOpId(null)
    setConfig(DEFAULT_CONFIG)
  }

  const progressPct =
    totalEpochs > 0 ? Math.round((epoch / totalEpochs) * 100) : 0

  return (
    <div className="training-panel">
      <h2 className="training-panel-title">Training</h2>

      {/* GPU Busy Warning */}
      {gpuBusy && !isTraining && (
        <div className="gpu-warning-banner">
          GPU is busy
          {vramUsedMb !== null ? ` (VRAM: ${vramUsedMb}MB)` : ''}.
          Another GPU operation may be running.
        </div>
      )}

      {/* State A: OneTrainer not found */}
      {trainStatus && !trainStatus.onetrainer_detected && !isTraining && !result && !error && (
        <div className="training-not-configured">
          <p>
            OneTrainer not detected. Configure the install path in{' '}
            <Link to="/settings" className="training-settings-link">
              Settings
            </Link>
            .
          </p>
          <p className="training-not-configured-hint">
            Download OneTrainer from{' '}
            <a
              href="https://github.com/Nerogar/OneTrainer"
              target="_blank"
              rel="noreferrer"
              className="training-settings-link"
            >
              github.com/Nerogar/OneTrainer
            </a>
          </p>
        </div>
      )}

      {/* State B: Ready to train */}
      {trainStatus?.onetrainer_detected && !isTraining && !result && !error && !opId && (
        <div className="training-ready">
          <TrainingConfig config={config} onChange={handleConfigChange} />

          <div className="training-action-row">
            <button
              type="button"
              className="training-btn training-btn--primary"
              onClick={() => void handleStartTraining()}
              disabled={isStarting || gpuBusy}
              title={gpuBusy ? 'GPU in use for training' : undefined}
            >
              {isStarting ? 'Starting...' : 'Start Headless Training'}
            </button>

            <button
              type="button"
              className="training-btn training-btn--secondary"
              onClick={() => void handleLaunchGui()}
              disabled={isLaunchingGui}
            >
              {isLaunchingGui ? 'Launching...' : 'Open OneTrainer GUI'}
            </button>
          </div>
        </div>
      )}

      {/* State C: Training in progress */}
      {isTraining && (
        <div className="training-in-progress">
          <div className="training-progress-header">
            <span className="training-epoch-label">
              Epoch {epoch}/{totalEpochs}
            </span>
            <span className="training-pct">{progressPct}%</span>
          </div>
          <div className="training-progress-track">
            <div className="training-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>

          {/* TensorBoard iframe */}
          <div className="tensorboard-container">
            <p className="tensorboard-label">TensorBoard</p>
            <iframe
              src="http://localhost:6006"
              className="tensorboard-iframe"
              title="TensorBoard"
            />
          </div>

          <button
            type="button"
            className="training-btn training-btn--stop"
            onClick={() => void handleStop()}
            disabled={isStopping}
          >
            {isStopping ? 'Stopping...' : 'Stop Training'}
          </button>
        </div>
      )}

      {/* State D: Training complete */}
      {result && !isTraining && (
        <div className="training-complete">
          <div className="completion-banner">
            <h3 className="completion-banner-title">Training Complete</h3>
            {result.lora_path && (
              <p className="completion-banner-detail">
                <span className="completion-banner-label">LoRA:</span>{' '}
                <span className="completion-banner-path">{result.lora_path}</span>
              </p>
            )}
            <p className="completion-banner-detail">
              <span className="completion-banner-label">Epochs:</span> {result.epochs}
            </p>
            <p className="completion-banner-detail">
              <span className="completion-banner-label">Duration:</span>{' '}
              {formatDuration(result.duration_seconds)}
            </p>
          </div>

          {/* TensorBoard remains visible after training */}
          <div className="tensorboard-container">
            <p className="tensorboard-label">TensorBoard</p>
            <iframe
              src="http://localhost:6006"
              className="tensorboard-iframe"
              title="TensorBoard"
            />
          </div>

          <button
            type="button"
            className="training-btn training-btn--secondary"
            onClick={handleNewTraining}
          >
            Start New Training
          </button>
        </div>
      )}

      {/* State E: Error */}
      {error && !isTraining && (
        <div className="training-error-panel">
          <p className="training-error-message">{error}</p>
          {logSnippet && (
            <pre className="training-error-log">{logSnippet}</pre>
          )}
          <button
            type="button"
            className="training-btn training-btn--secondary"
            onClick={handleNewTraining}
          >
            Retry
          </button>
        </div>
      )}
    </div>
  )
}
