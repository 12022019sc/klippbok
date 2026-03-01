import { useQuery } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import { toast } from 'sonner'

interface SettingsResponse {
  project_dir: string
  active_profile: string | null
}

async function fetchSettings(): Promise<SettingsResponse> {
  const res = await fetch('/api/v1/settings/')
  if (!res.ok) {
    throw new Error(`Failed to load settings: ${res.statusText}`)
  }
  return res.json()
}

export default function SettingsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const setProjectDir = useAppStore((s) => s.setProjectDir)
  const clearImport = useAppStore((s) => s.clearImport)

  function handleChangeProject() {
    clearImport()
    setProjectDir(null)
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
              <span className="settings-label">Active Model Profile</span>
              <span className="settings-value">
                {data.active_profile ?? (
                  <span className="settings-value--muted">None selected</span>
                )}
              </span>
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
        </div>
      )}
    </div>
  )
}
