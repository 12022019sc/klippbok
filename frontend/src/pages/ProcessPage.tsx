import { useNavigate } from 'react-router'
import { useAppStore } from '../stores/appStore'
import UpscaleStep from '../components/Crop/UpscaleStep'

type ProcessStep = 'upscale' | 'crop'

function StepIndicator({ currentStep }: { currentStep: ProcessStep }) {
  const upscaleDone = currentStep === 'crop'
  const upscaleActive = currentStep === 'upscale'

  return (
    <div className="process-steps">
      <div className="process-step-item">
        <div className={`process-step-circle ${upscaleDone ? 'done' : upscaleActive ? 'active' : ''}`}>
          {upscaleDone ? '✓' : '1'}
        </div>
        <span className={`process-step-label ${upscaleDone ? 'done' : upscaleActive ? 'active' : ''}`}>
          Upscale (optional)
        </span>
      </div>

      <div className="process-step-connector" />

      <div className="process-step-item">
        <div className={`process-step-circle ${currentStep === 'crop' ? 'active' : ''}`}>
          2
        </div>
        <span className={`process-step-label ${currentStep === 'crop' ? 'active' : ''}`}>
          Crop
        </span>
      </div>

      <div className="process-step-connector" />

      <div className="process-step-item">
        <div className="process-step-circle">3</div>
        <span className="process-step-label">Save</span>
      </div>
    </div>
  )
}

export default function ProcessPage() {
  const navigate = useNavigate()
  const selectedImageIds = useAppStore((s) => s.selectedImageIds)
  const selectedIds = Array.from(selectedImageIds)

  function handleUpscaleComplete() {
    void navigate('/crop')
  }

  function handleUpscaleSkip() {
    void navigate('/crop')
  }

  return (
    <div className="process-page">
      <StepIndicator currentStep="upscale" />
      <UpscaleStep
        selectedImageIds={selectedIds}
        onComplete={handleUpscaleComplete}
        onSkip={handleUpscaleSkip}
      />
    </div>
  )
}
