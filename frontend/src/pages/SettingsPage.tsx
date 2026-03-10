import { useState, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import { toast } from 'sonner'
import ProviderConfigSection from '../components/Caption/ProviderConfigSection'

interface ToolSettings {
  onetrainer_path: string | null
  model_dir: string | null
}

interface TrainStatusForDetect {
  onetrainer_detected: boolean
  onetrainer_path: string | null
}

interface CaptionProviderConfig {
  provider: string
  lm_studio_base_url: string
  lm_studio_model: string
  nanogpt_api_key: string
  nanogpt_model: string
  gemini_api_key: string
  gemini_model: string
  joycaption_path: string
  custom_prompt: string | null
}

const DEFAULT_CAPTION_CONFIG: CaptionProviderConfig = {
  provider: 'lm_studio',
  lm_studio_base_url: 'http://localhost:1234/v1',
  lm_studio_model: '',
  nanogpt_api_key: '',
  nanogpt_model: '',
  gemini_api_key: '',
  gemini_model: 'gemini-2.5-flash',
  joycaption_path: '',
  custom_prompt: null,
}

interface SettingsResponse {
  project_dir: string | null
  active_profile: string | null
  anchor_word?: string
}

interface ProfileInfo {
  name: string
  display_name: string
  caption_style: string
  base_resolution: number
}

async function fetchSettings(): Promise<SettingsResponse> {
  const res = await fetch('/api/v1/settings/')
  if (!res.ok) {
    throw new Error(`Failed to load settings: ${res.statusText}`)
  }
  return res.json()
}

async function fetchProfiles(): Promise<ProfileInfo[]> {
  const res = await fetch('/api/v1/settings/profiles')
  if (!res.ok) {
    throw new Error(`Failed to load profiles: ${res.statusText}`)
  }
  return res.json()
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })
  const { data: profiles } = useQuery({
    queryKey: ['profiles'],
    queryFn: fetchProfiles,
  })

  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false)
  const didAutoSelect = useRef(false)

  // Auto-select sd15 if no profile is set
  useEffect(() => {
    if (didAutoSelect.current || !data || data.active_profile || !profiles?.length) return
    didAutoSelect.current = true
    const hasSd15 = profiles.some((p) => p.name === 'sd15')
    if (!hasSd15) return

    // Silently set default profile (no toast)
    fetch('/api/v1/settings/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_profile: 'sd15' }),
    })
      .then((res) => {
        if (res.ok) void queryClient.invalidateQueries({ queryKey: ['settings'] })
      })
      .catch(() => {})
  }, [data, profiles, queryClient])

  const { data: captionConfig = DEFAULT_CAPTION_CONFIG } = useQuery<CaptionProviderConfig>({
    queryKey: ['caption-config'],
    queryFn: async () => {
      const res = await fetch('/api/v1/captions/config')
      if (!res.ok) throw new Error('Failed to fetch caption config')
      return res.json() as Promise<CaptionProviderConfig>
    },
  })

  const triggerWord = data?.anchor_word ?? ''

  // Tool settings state
  const [toolSettings, setToolSettings] = useState<ToolSettings>({ onetrainer_path: null, model_dir: null })
  const [toolSettingsLoaded, setToolSettingsLoaded] = useState(false)
  const [onetrainerDetected, setOnetrainerDetected] = useState<boolean | null>(null)
  const [isSavingTools, setIsSavingTools] = useState(false)
  const [isAutoDetecting, setIsAutoDetecting] = useState(false)

  // Load tool settings on mount
  useEffect(() => {
    fetch('/api/v1/settings/tools')
      .then((r) => r.json())
      .then((d: ToolSettings) => {
        setToolSettings(d)
        setToolSettingsLoaded(true)
      })
      .catch(() => setToolSettingsLoaded(true))
  }, [])

  async function handleAutoDetect() {
    setIsAutoDetecting(true)
    try {
      const res = await fetch('/api/v1/export/train/status')
      if (!res.ok) return
      const data = (await res.json()) as TrainStatusForDetect
      setOnetrainerDetected(data.onetrainer_detected)
      if (data.onetrainer_path) {
        setToolSettings((prev) => ({ ...prev, onetrainer_path: data.onetrainer_path }))
        toast.success('OneTrainer detected', { description: data.onetrainer_path ?? undefined })
      } else {
        toast.info('OneTrainer not found at common paths. Set path manually.')
      }
    } catch {
      toast.error('Auto-detect failed')
    } finally {
      setIsAutoDetecting(false)
    }
  }

  async function handleSaveTools() {
    setIsSavingTools(true)
    try {
      const res = await fetch('/api/v1/settings/tools', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          onetrainer_path: toolSettings.onetrainer_path || null,
          model_dir: toolSettings.model_dir || null,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Save failed' }))
        toast.error('Failed to save tool settings', { description: (err as { detail: string }).detail })
        return
      }
      toast.success('Tool settings saved')
    } catch (err) {
      toast.error('Failed to save tool settings', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsSavingTools(false)
    }
  }

  const setProjectDir = useAppStore((s) => s.setProjectDir)
  const clearImport = useAppStore((s) => s.clearImport)

  function handleChangeProject() {
    clearImport()
    setProjectDir(null)
  }

  async function handleProfileChange(profileName: string) {
    if (isUpdatingProfile) return
    setIsUpdatingProfile(true)
    try {
      const res = await fetch('/api/v1/settings/', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_profile: profileName }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to update profile', { description: err.detail })
        return
      }
      const selectedProfile = profiles?.find((p) => p.name === profileName)
      const displayName = selectedProfile?.display_name ?? profileName
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.success(`Profile updated to ${displayName}`)
    } catch (err) {
      toast.error('Failed to update profile', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsUpdatingProfile(false)
    }
  }

  async function handleShutdown() {
    const confirmed = window.confirm(
      'Shut down the klippbok server?\n\nThis will stop the server and any running upscale processes.'
    )
    if (!confirmed) return

    try {
      await fetch('/api/v1/settings/shutdown', { method: 'POST' })
      toast.success('Server is shutting down')
    } catch {
      // Expected — server dies before response completes
      toast.success('Server is shutting down')
    }
  }

  async function handleDeleteProject() {
    const confirmed = window.confirm(
      'Delete project data (.klippbok/)?\n\nThis removes thumbnails, manifest, and cache. Your original files are NOT affected.'
    )
    if (!confirmed) return

    try {
      const res = await fetch('/api/v1/settings/project', { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to delete project', { description: err.detail })
        return
      }
      toast.success('Project data deleted')
      clearImport()
      setProjectDir(null)
    } catch (err) {
      toast.error('Failed to delete project', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const activeProfile = profiles?.find((p) => p.name === data?.active_profile)

  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <p className="page-subtitle">Project configuration and model profile selection.</p>

      {isLoading && <p className="settings-loading">Loading settings...</p>}

      {isError && (
        <p className="settings-error">
          Failed to load settings: {error instanceof Error ? error.message : 'Unknown error'}
        </p>
      )}

      {data && (
        <div className="settings-form">
          <div className="settings-info">
            <div className="settings-field">
              <span className="settings-label">Project Directory</span>
              <span className="settings-value settings-value--mono">{data.project_dir}</span>
            </div>

            <div className="settings-field">
              <span className="settings-label">Model Profile</span>
              {profiles && profiles.length > 0 ? (
                <div className="settings-profile-selector">
                  <select
                    className="settings-select"
                    value={data.active_profile ?? ''}
                    onChange={(e) => void handleProfileChange(e.target.value)}
                    disabled={isUpdatingProfile}
                  >
                    <option value="" disabled>
                      Select a profile...
                    </option>
                    {profiles.map((profile) => (
                      <option key={profile.name} value={profile.name}>
                        {profile.display_name}
                      </option>
                    ))}
                  </select>
                  {activeProfile && (
                    <div className="settings-profile-details">
                      <span className="settings-profile-detail">
                        Style: {activeProfile.caption_style}
                      </span>
                      <span className="settings-profile-detail">
                        Base resolution: {activeProfile.base_resolution}px
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <span className="settings-value">
                  {data.active_profile ?? (
                    <span className="settings-value--muted">None selected</span>
                  )}
                </span>
              )}
            </div>
          </div>

          <div className="settings-section-divider" />

          <h2 className="settings-section-title">Caption Provider</h2>
          <ProviderConfigSection
            config={captionConfig}
            onSave={() => void queryClient.invalidateQueries({ queryKey: ['caption-config'] })}
            triggerWord={triggerWord}
            onTriggerWordSave={() => void queryClient.invalidateQueries({ queryKey: ['settings'] })}
          />

          <div className="settings-section-divider" />

          <h2 className="settings-section-title">External Tools</h2>
          {toolSettingsLoaded && (
            <div className="settings-tools">
              <div className="settings-field">
                <span className="settings-label">OneTrainer Install Path</span>
                <div className="settings-tool-input-row">
                  <input
                    type="text"
                    className="settings-tool-input"
                    value={toolSettings.onetrainer_path ?? ''}
                    onChange={(e) =>
                      setToolSettings((prev) => ({ ...prev, onetrainer_path: e.target.value || null }))
                    }
                    placeholder="e.g. C:\OneTrainer"
                  />
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => void handleAutoDetect()}
                    disabled={isAutoDetecting}
                    style={{ flexShrink: 0 }}
                  >
                    {isAutoDetecting ? 'Detecting...' : 'Auto-detect'}
                  </button>
                  {onetrainerDetected === true && (
                    <span className="settings-tool-status settings-tool-status--ok">Detected</span>
                  )}
                  {onetrainerDetected === false && (
                    <span className="settings-tool-status settings-tool-status--err">Not found</span>
                  )}
                </div>
              </div>

              <div className="settings-field">
                <span className="settings-label">Model Directory</span>
                <div className="settings-tool-input-row">
                  <input
                    type="text"
                    className="settings-tool-input"
                    value={toolSettings.model_dir ?? ''}
                    onChange={(e) =>
                      setToolSettings((prev) => ({ ...prev, model_dir: e.target.value || null }))
                    }
                    placeholder="e.g. C:\GenAI\Models"
                  />
                </div>
              </div>

              <div className="settings-actions" style={{ marginTop: '0.75rem' }}>
                <button
                  className="settings-btn settings-btn--primary"
                  onClick={() => void handleSaveTools()}
                  disabled={isSavingTools}
                >
                  {isSavingTools ? 'Saving...' : 'Save Tool Settings'}
                </button>
              </div>
            </div>
          )}

          <div className="settings-section-divider" />

          <div className="settings-actions">
            <button
              className="settings-btn settings-btn--secondary"
              onClick={handleChangeProject}
            >
              Change Project
            </button>
            <button
              className="settings-btn settings-btn--danger"
              onClick={handleDeleteProject}
            >
              Delete Project Data
            </button>
          </div>

          <div className="settings-section-divider" />

          <div className="settings-actions">
            <button
              className="settings-btn settings-btn--danger"
              onClick={() => void handleShutdown()}
            >
              Shut Down Server
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
