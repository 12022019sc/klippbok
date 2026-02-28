import { useQuery } from '@tanstack/react-query'

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

/**
 * SettingsPage displays the current project directory and active model profile.
 * Both fields are read-only in Phase 4 -- profile selection will be wired in
 * a future phase.
 */
export default function SettingsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

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
        </div>
      )}
    </div>
  )
}
