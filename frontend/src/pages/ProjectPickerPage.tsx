import { useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { toast } from 'sonner'
import DirectoryBrowser from '../components/DirectoryBrowser/DirectoryBrowser'

/**
 * ProjectPickerPage is shown when no project directory is active.
 * Users browse folders visually or type a path manually to open a project.
 */
export default function ProjectPickerPage() {
  const [loading, setLoading] = useState(false)
  const setProjectDir = useAppStore((s) => s.setProjectDir)

  async function handleSelectDirectory(path: string) {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/settings/', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_dir: path }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || 'Failed to set project directory')
      }

      const data = await res.json()
      setProjectDir(data.project_dir)
      toast.success(`Project opened: ${data.project_dir}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to open project')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="picker-container">
      <div className="picker-card picker-card-wide">
        <h1 className="picker-title">klippbok</h1>
        <p className="picker-subtitle">
          Dataset preparation for LoRA training
        </p>

        <DirectoryBrowser
          onSelect={handleSelectDirectory}
          disabled={loading}
        />
      </div>
    </div>
  )
}
