import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import { toast } from 'sonner'

interface SettingsResponse {
  project_dir: string | null
  active_profile: string | null
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
