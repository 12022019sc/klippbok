import { useNavigate } from 'react-router'
import { useAppStore } from '../stores/appStore'
import UpscaleStep from '../components/Crop/UpscaleStep'

export default function ProcessPage() {
  const navigate = useNavigate()
  const selectedImageIds = useAppStore((s) => s.selectedImageIds)
  const toggleSelectionMode = useAppStore((s) => s.toggleSelectionMode)
  const selectionMode = useAppStore((s) => s.selectionMode)
  const selectedIds = Array.from(selectedImageIds)

  function handleUpscaleComplete() {
    if (selectionMode) toggleSelectionMode()
    void navigate('/')
  }

  function handleUpscaleSkip() {
    void navigate('/')
  }

  return (
    <div className="process-page">
      <UpscaleStep
        selectedImageIds={selectedIds}
        onComplete={handleUpscaleComplete}
        onSkip={handleUpscaleSkip}
      />
    </div>
  )
}
