import { useState, useEffect, useRef } from 'react'
import type { CurationConfig as CurationConfigType, CurationMode } from '../../types/curation'
import { MODEL_TARGET_DEFAULTS } from '../../types/curation'
import { useAppStore } from '../../stores/appStore'

interface CurationConfigProps {
  onStart: (config: CurationConfigType & { selected_ids?: string[] }) => void
}

const MODEL_PROFILES: { value: string; label: string; hint: string }[] = [
  { value: 'sd15', label: 'SD 1.5', hint: 'Sweet spot 20-50, default 40' },
  { value: 'sdxl', label: 'SDXL', hint: 'Sweet spot 50-120, default 80' },
  { value: 'flux', label: 'Flux', hint: 'Sweet spot 60-150, default 100' },
  { value: 'pony', label: 'Pony', hint: 'Sweet spot 40-100, default 70' },
  { value: 'custom', label: 'Custom', hint: 'Sweet spot 30-100, default 60' },
]

export default function CurationConfig({ onStart }: CurationConfigProps) {
  const curationSelectedIds = useAppStore((s) => s.curationSelectedIds)
  const [mode, setMode] = useState<CurationMode>('character')
  const [modelProfile, setModelProfile] = useState('sd15')
  const [targetCount, setTargetCount] = useState(MODEL_TARGET_DEFAULTS['sd15'])
  const didFetchProfile = useRef(false)

  // On mount, fetch active profile from settings and use it if valid
  useEffect(() => {
    if (didFetchProfile.current) return
    didFetchProfile.current = true

    fetch('/api/v1/settings/')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { active_profile?: string } | null) => {
        if (!data?.active_profile) return
        const valid = MODEL_PROFILES.some((p) => p.value === data.active_profile)
        if (valid) {
          handleProfileChange(data.active_profile!)
        }
      })
      .catch(() => {})
  }, [])
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [qualityFloor, setQualityFloor] = useState(30)
  const [faceConfidence, setFaceConfidence] = useState(0.5)
  const [poseAngleLimit, setPoseAngleLimit] = useState(45)
  const [identityThreshold, setIdentityThreshold] = useState(0.4)

  const selectedProfile = MODEL_PROFILES.find((p) => p.value === modelProfile)

  function handleProfileChange(value: string) {
    setModelProfile(value)
    const defaultCount = MODEL_TARGET_DEFAULTS[value]
    if (defaultCount !== undefined) {
      setTargetCount(defaultCount)
    }
  }

  function handleStart() {
    const config: CurationConfigType & { selected_ids?: string[] } = {
      mode,
      target_count: targetCount,
      quality_floor_pct: qualityFloor / 100,  // Convert percentage to 0.0-1.0
      face_confidence_threshold: faceConfidence,
      pose_angle_limit: poseAngleLimit,
      identity_threshold: identityThreshold,
      reference_image_id: null,
      model_profile: modelProfile,
    }
    if (curationSelectedIds && curationSelectedIds.length > 0) {
      config.selected_ids = curationSelectedIds
    }
    onStart(config)
  }

  return (
    <div className="curation-config">
      {/* Mode Selector */}
      <div className="curation-mode-selector" style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <button
          className={`cleanup-mode-btn ${mode === 'character' ? 'cleanup-mode-active' : ''}`}
          onClick={() => setMode('character')}
        >
          <strong>Character</strong>
          <br />
          <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>Identity-anchored, face-focused</span>
        </button>
        <button
          className={`cleanup-mode-btn ${mode === 'style' ? 'cleanup-mode-active' : ''}`}
          onClick={() => setMode('style')}
        >
          <strong>Style</strong>
          <br />
          <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>Aesthetic-focused, no face anchor</span>
        </button>
      </div>

      {/* Model Profile */}
      <div style={{ marginBottom: '1.25rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
          Model Profile
        </label>
        <select
          className="cleanup-text-input"
          value={modelProfile}
          onChange={(e) => handleProfileChange(e.target.value)}
          style={{ width: '100%' }}
        >
          {MODEL_PROFILES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        {selectedProfile && (
          <p style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            {selectedProfile.hint}
          </p>
        )}
      </div>

      {/* Target Count */}
      <div style={{ marginBottom: '1.25rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: '#d1d5db', fontSize: '0.85rem' }}>
          Target Image Count
        </label>
        <input
          type="number"
          className="cleanup-text-input"
          value={targetCount}
          onChange={(e) => setTargetCount(Number(e.target.value))}
          min={1}
          max={1000}
          style={{ width: '120px' }}
        />
      </div>

      {/* Reference Face Indicator (character mode only) */}
      {mode === 'character' && (
        <div style={{ marginBottom: '1.25rem', padding: '0.75rem', background: '#1f2937', borderRadius: '0.375rem', fontSize: '0.85rem', color: '#9ca3af' }}>
          Reference face: Auto-detected from face clusters
        </div>
      )}

      {/* Advanced Settings Toggle */}
      <div className="curation-advanced-toggle" style={{ marginBottom: '1.25rem' }}>
        <button
          className="video-btn-link"
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{ fontSize: '0.85rem' }}
        >
          {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
        </button>
      </div>

      {showAdvanced && (
        <div style={{ marginBottom: '1.5rem', padding: '1rem', background: '#111827', borderRadius: '0.375rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', color: '#d1d5db', fontSize: '0.8rem' }}>
              Quality Floor (%)
            </label>
            <input
              type="number"
              className="cleanup-text-input"
              value={qualityFloor}
              onChange={(e) => setQualityFloor(Number(e.target.value))}
              min={0}
              max={100}
              style={{ width: '100px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', color: '#d1d5db', fontSize: '0.8rem' }}>
              Face Confidence Threshold
            </label>
            <input
              type="number"
              className="cleanup-text-input"
              value={faceConfidence}
              onChange={(e) => setFaceConfidence(Number(e.target.value))}
              min={0}
              max={1}
              step={0.05}
              style={{ width: '100px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', color: '#d1d5db', fontSize: '0.8rem' }}>
              Pose Angle Limit (degrees)
            </label>
            <input
              type="number"
              className="cleanup-text-input"
              value={poseAngleLimit}
              onChange={(e) => setPoseAngleLimit(Number(e.target.value))}
              min={0}
              max={180}
              style={{ width: '100px' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.25rem', color: '#d1d5db', fontSize: '0.8rem' }}>
              Identity Threshold
            </label>
            <input
              type="number"
              className="cleanup-text-input"
              value={identityThreshold}
              onChange={(e) => setIdentityThreshold(Number(e.target.value))}
              min={0}
              max={1}
              step={0.05}
              style={{ width: '100px' }}
            />
          </div>
        </div>
      )}

      {/* Selection Indicator */}
      {curationSelectedIds && curationSelectedIds.length > 0 ? (
        <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#1e3a5f', borderRadius: '0.375rem', fontSize: '0.85rem', color: '#93c5fd' }}>
          Curating {curationSelectedIds.length} selected images
        </div>
      ) : (
        <div style={{ marginBottom: '1rem', padding: '0.75rem', background: '#1f2937', borderRadius: '0.375rem', fontSize: '0.85rem', color: '#9ca3af' }}>
          Curating all images in project
        </div>
      )}

      {/* Start Button */}
      <button className="import-button" onClick={handleStart}>
        Start Curation
      </button>
    </div>
  )
}
