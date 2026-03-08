import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useUpscaleEvents } from '../../hooks/useUpscaleEvents'

interface UpscalerStatus {
  seedvr2_available: boolean
  nmkd_siax_available: boolean
  seedvr2_path: string | null
  nmkd_siax_path: string | null
}

interface UpscaleStepProps {
  selectedImageIds: string[]
  onComplete: () => void
  onSkip: () => void
}

type UpscalerOption = 'seedvr2' | 'nmkd_siax'
type ScaleFactor = 2 | 4

export default function UpscaleStep({ selectedImageIds, onComplete, onSkip }: UpscaleStepProps) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<UpscalerStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState<boolean>(true)
  const [selectedUpscaler, setSelectedUpscaler] = useState<UpscalerOption>('seedvr2')
  const [scaleFactor, setScaleFactor] = useState<ScaleFactor>(2)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState<boolean>(false)
  const [isCancelling, setIsCancelling] = useState<boolean>(false)
  const [isApplying, setIsApplying] = useState<boolean>(false)

  const upscaleProgress = useUpscaleEvents(operationId)

  // Fetch upscaler availability on mount
  useEffect(() => {
    async function fetchStatus() {
      try {
        const response = await fetch('/api/v1/upscale/status')
        if (response.ok) {
          const data: UpscalerStatus = await response.json()
          setStatus(data)
          // Default to first available upscaler
          if (!data.seedvr2_available && data.nmkd_siax_available) {
            setSelectedUpscaler('nmkd_siax')
          }
        }
      } catch (err) {
        console.error('Failed to fetch upscaler status:', err)
      } finally {
        setStatusLoading(false)
      }
    }
    void fetchStatus()
  }, [])

  async function handleApplyUpscaled() {
    if (!operationId || isApplying) return
    setIsApplying(true)
    try {
      const res = await fetch(`/api/v1/upscale/${operationId}/apply`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to apply upscaled images', { description: err.detail })
        return
      }
      const data = await res.json() as { replaced: number; re_evaluated: number }
      toast.success(`Replaced ${data.replaced} image${data.replaced !== 1 ? 's' : ''} with upscaled versions`, {
        description: data.re_evaluated > 0 ? `Quality re-evaluated for ${data.re_evaluated} image${data.re_evaluated !== 1 ? 's' : ''}` : undefined,
      })
      await queryClient.invalidateQueries({ queryKey: ['images'] })
      onComplete()
    } catch (err) {
      toast.error('Failed to apply upscaled images', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsApplying(false)
    }
  }

  async function handleStartUpscaling() {
    if (isStarting || selectedImageIds.length === 0) return
    setIsStarting(true)
    try {
      const response = await fetch('/api/v1/upscale/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_ids: selectedImageIds,
          upscaler: selectedUpscaler,
          scale_factor: scaleFactor,
        }),
      })
      if (!response.ok) {
        const text = await response.text()
        console.error('Failed to start upscale:', text)
        return
      }
      const data = await response.json()
      setOperationId(data.operation_id as string)
    } catch (err) {
      console.error('Error starting upscale:', err)
    } finally {
      setIsStarting(false)
    }
  }

  async function handleCancel() {
    if (!operationId || isCancelling) return
    setIsCancelling(true)
    try {
      await fetch(`/api/v1/upscale/${operationId}/cancel`, { method: 'POST' })
    } catch (err) {
      console.error('Error cancelling upscale:', err)
    } finally {
      setIsCancelling(false)
    }
  }

  const anyUpscalerAvailable = status
    ? status.seedvr2_available || status.nmkd_siax_available
    : false

  const progressPercent =
    upscaleProgress.total > 0
      ? Math.round((upscaleProgress.current / upscaleProgress.total) * 100)
      : 0

  const isRunning = operationId !== null && !upscaleProgress.isComplete && !upscaleProgress.error

  return (
    <div className="upscale-step">
      <h2 className="upscale-step-title">Upscale Images</h2>
      <p className="upscale-step-subtitle">
        Upscale {selectedImageIds.length} selected image{selectedImageIds.length !== 1 ? 's' : ''}. Originals will be replaced with upscaled versions.
      </p>

      {/* Upscaler status indicators */}
      {statusLoading ? (
        <div className="upscaler-status-loading">Checking upscaler availability...</div>
      ) : (
        <div className="upscaler-status">
          {status ? (
            <>
              <div className={`upscaler-status-badge ${status.seedvr2_available ? 'available' : 'unavailable'}`}>
                <span className="upscaler-status-dot" />
                <span>
                  {status.seedvr2_available
                    ? `SeedVR2 found at ${status.seedvr2_path}`
                    : 'SeedVR2 not found. Configure in Settings or skip this step.'}
                </span>
              </div>
              <div className={`upscaler-status-badge ${status.nmkd_siax_available ? 'available' : 'unavailable'}`}>
                <span className="upscaler-status-dot" />
                <span>
                  {status.nmkd_siax_available
                    ? `NMKD-Siax found at ${status.nmkd_siax_path}`
                    : 'NMKD-Siax not found. Install realesrgan-ncnn-vulkan or skip this step.'}
                </span>
              </div>
            </>
          ) : (
            <div className="upscaler-status-badge unavailable">
              <span className="upscaler-status-dot" />
              <span>Could not determine upscaler availability.</span>
            </div>
          )}
        </div>
      )}

      {/* Upscale controls */}
      {anyUpscalerAvailable && !operationId && (
        <div className="upscale-controls">
          <div className="upscale-control-group">
            <label className="upscale-control-label" htmlFor="upscaler-select">Upscaler</label>
            <select
              id="upscaler-select"
              className="upscale-select"
              value={selectedUpscaler}
              onChange={(e) => setSelectedUpscaler(e.target.value as UpscalerOption)}
            >
              {status?.seedvr2_available && <option value="seedvr2">SeedVR2</option>}
              {status?.nmkd_siax_available && <option value="nmkd_siax">NMKD-Siax</option>}
            </select>
          </div>

          <div className="upscale-control-group">
            <label className="upscale-control-label" htmlFor="scale-factor-select">Scale</label>
            <select
              id="scale-factor-select"
              className="upscale-select"
              value={scaleFactor}
              onChange={(e) => setScaleFactor(Number(e.target.value) as ScaleFactor)}
            >
              <option value={2}>2x</option>
              <option value={4}>4x</option>
            </select>
          </div>

          <button
            className="upscale-start-btn"
            onClick={() => void handleStartUpscaling()}
            disabled={isStarting || selectedImageIds.length === 0}
          >
            {isStarting ? 'Starting...' : 'Start Upscaling'}
          </button>
        </div>
      )}

      {/* Progress section */}
      {operationId && (
        <div className="upscale-progress">
          {upscaleProgress.error ? (
            <div className="upscale-error">
              <p className="upscale-error-msg">Error: {upscaleProgress.error}</p>
              <button
                className="upscale-retry-btn"
                onClick={() => {
                  setOperationId(null)
                }}
              >
                Retry
              </button>
            </div>
          ) : upscaleProgress.isComplete ? (
            <div className="upscale-complete">
              <p className="upscale-complete-msg">
                Upscaling complete! {upscaleProgress.current}/{upscaleProgress.total} images processed.
              </p>
              <button
                className="upscale-continue-btn"
                onClick={() => void handleApplyUpscaled()}
                disabled={isApplying}
              >
                {isApplying ? 'Applying...' : 'Apply & Return to Gallery'}
              </button>
            </div>
          ) : (
            <>
              <p className="upscale-progress-text">
                {isRunning
                  ? `Upscaling ${upscaleProgress.current}/${upscaleProgress.total} images...`
                  : 'Preparing upscaler...'}
              </p>
              <div className="import-progress-bar-track">
                <div
                  className="import-progress-bar-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="upscale-progress-percent">{progressPercent}%</p>
              {upscaleProgress.message && (
                <p className="upscale-progress-message">{upscaleProgress.message}</p>
              )}
              <button
                className="upscale-cancel-btn"
                onClick={() => void handleCancel()}
                disabled={isCancelling}
              >
                {isCancelling ? 'Cancelling...' : 'Cancel Upscale'}
              </button>
            </>
          )}
        </div>
      )}

      {/* Skip button -- always visible */}
      {!upscaleProgress.isComplete && (
        <div className="upscale-skip-row">
          <button className="upscale-skip-btn" onClick={onSkip}>
            Cancel
          </button>
          <span className="upscale-skip-hint">Return to gallery without upscaling</span>
        </div>
      )}
    </div>
  )
}
