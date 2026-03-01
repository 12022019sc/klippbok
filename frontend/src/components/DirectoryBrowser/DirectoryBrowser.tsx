import { useCallback, useEffect, useState } from 'react'

interface DirEntry {
  name: string
  path: string
}

interface Props {
  onSelect: (path: string) => void
  disabled: boolean
}

export default function DirectoryBrowser({ onSelect, disabled }: Props) {
  const [currentPath, setCurrentPath] = useState<string | null>(null)
  const [entries, setEntries] = useState<DirEntry[]>([])
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [roots, setRoots] = useState<DirEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // New folder state
  const [showNewFolder, setShowNewFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingFolder, setCreatingFolder] = useState(false)

  // Manual input toggle
  const [showManualInput, setShowManualInput] = useState(false)
  const [manualPath, setManualPath] = useState('')

  const fetchDirectory = useCallback(async (path: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/browse/list?path=${encodeURIComponent(path)}`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || 'Failed to list directory')
      }
      const data = await res.json()
      setCurrentPath(data.current_path)
      setParentPath(data.parent_path)
      setEntries(data.entries)
      if (data.error) setError(data.error)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to browse directory')
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch roots on mount, then navigate to home_dir
  useEffect(() => {
    async function init() {
      setLoading(true)
      try {
        const res = await fetch('/api/v1/browse/roots')
        if (!res.ok) throw new Error('Failed to fetch roots')
        const data = await res.json()
        setRoots(data.roots)
        // Auto-navigate to home directory
        await fetchDirectory(data.home_dir)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to initialize browser')
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [fetchDirectory])

  function handleCreateFolder() {
    if (!newFolderName.trim() || !currentPath || creatingFolder) return
    setCreatingFolder(true)
    fetch('/api/v1/browse/mkdir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_path: currentPath, name: newFolderName.trim() }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          throw new Error(err.detail || 'Failed to create folder')
        }
        const data = await res.json()
        setEntries(data.entries)
        setNewFolderName('')
        setShowNewFolder(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to create folder')
      })
      .finally(() => setCreatingFolder(false))
  }

  // Build breadcrumb segments from current path
  function getBreadcrumbs(): { label: string; path: string }[] {
    if (!currentPath) return []
    const normalized = currentPath.replace(/\\/g, '/')
    const parts = normalized.split('/').filter(Boolean)

    // Windows drive: first part is like "C:"
    const isWindows = /^[A-Z]:$/i.test(parts[0] ?? '')
    const crumbs: { label: string; path: string }[] = []

    for (let i = 0; i < parts.length; i++) {
      let crumbPath: string
      if (isWindows) {
        crumbPath = parts.slice(0, i + 1).join('/') + (i === 0 ? '/' : '')
      } else {
        crumbPath = '/' + parts.slice(0, i + 1).join('/')
      }
      crumbs.push({ label: parts[i], path: crumbPath })
    }
    return crumbs
  }

  // Manual input mode
  if (showManualInput) {
    return (
      <div className="browse-container">
        <label className="picker-label" htmlFor="manual-dir">
          Project Directory
        </label>
        <p className="picker-hint">
          Enter the path to a folder containing your images. A <code>.klippbok/</code> subdirectory will be created for project data.
        </p>
        <input
          id="manual-dir"
          className="import-input"
          type="text"
          placeholder="C:\Users\you\datasets\my-character"
          value={manualPath}
          onChange={(e) => setManualPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && manualPath.trim() && onSelect(manualPath.trim())}
          disabled={disabled}
          autoFocus
        />
        <div className="browse-actions">
          <button
            className="import-button"
            onClick={() => manualPath.trim() && onSelect(manualPath.trim())}
            disabled={!manualPath.trim() || disabled}
          >
            Open Project
          </button>
          <button
            className="browse-toggle-manual"
            onClick={() => setShowManualInput(false)}
            disabled={disabled}
          >
            Browse folders instead
          </button>
        </div>
      </div>
    )
  }

  const breadcrumbs = getBreadcrumbs()

  return (
    <div className="browse-container">
      {/* Path breadcrumb bar */}
      <div className="browse-path-bar">
        {breadcrumbs.length > 0 ? (
          breadcrumbs.map((crumb, i) => (
            <span key={crumb.path}>
              {i > 0 && <span className="browse-separator">/</span>}
              <button
                className="browse-crumb"
                onClick={() => fetchDirectory(crumb.path)}
                disabled={disabled || loading}
              >
                {crumb.label}
              </button>
            </span>
          ))
        ) : (
          <span className="browse-crumb-placeholder">Select a drive...</span>
        )}
      </div>

      {/* Drive letter buttons */}
      {roots.length > 0 && (
        <div className="browse-drives">
          {roots.map((root) => (
            <button
              key={root.path}
              className={`browse-drive-btn${currentPath?.startsWith(root.path) ? ' active' : ''}`}
              onClick={() => fetchDirectory(root.path)}
              disabled={disabled || loading}
            >
              {root.name}
            </button>
          ))}
        </div>
      )}

      {/* Error message */}
      {error && <p className="browse-error">{error}</p>}

      {/* Folder list */}
      <div className="browse-folder-list">
        {loading && entries.length === 0 && (
          <div className="browse-folder-empty">Loading...</div>
        )}
        {/* Parent directory button */}
        {parentPath && (
          <button
            className="browse-folder-item browse-folder-parent"
            onClick={() => fetchDirectory(parentPath)}
            disabled={disabled || loading}
          >
            ..
          </button>
        )}
        {entries.map((entry) => (
          <button
            key={entry.path}
            className="browse-folder-item"
            onClick={() => fetchDirectory(entry.path)}
            disabled={disabled || loading}
          >
            {entry.name}
          </button>
        ))}
        {!loading && entries.length === 0 && currentPath && !error && (
          <div className="browse-folder-empty">No subdirectories</div>
        )}
      </div>

      {/* New folder + Select actions */}
      <div className="browse-actions">
        {showNewFolder ? (
          <div className="browse-new-folder-row">
            <input
              className="import-input browse-new-folder-input"
              type="text"
              placeholder="New folder name"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
              disabled={creatingFolder || disabled}
              autoFocus
            />
            <button
              className="browse-new-folder-btn"
              onClick={handleCreateFolder}
              disabled={!newFolderName.trim() || creatingFolder || disabled}
            >
              {creatingFolder ? '...' : 'Create'}
            </button>
            <button
              className="browse-new-folder-cancel"
              onClick={() => { setShowNewFolder(false); setNewFolderName('') }}
              disabled={creatingFolder || disabled}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            className="browse-new-folder-toggle"
            onClick={() => setShowNewFolder(true)}
            disabled={!currentPath || disabled}
          >
            + New Folder
          </button>
        )}

        <button
          className="import-button browse-select-btn"
          onClick={() => currentPath && onSelect(currentPath)}
          disabled={!currentPath || disabled}
        >
          Select This Folder
        </button>
      </div>

      {/* Manual input toggle */}
      <button
        className="browse-toggle-manual"
        onClick={() => setShowManualInput(true)}
        disabled={disabled}
      >
        Or type a path manually...
      </button>
    </div>
  )
}
