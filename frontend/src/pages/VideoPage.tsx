import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useIngestEvents } from '../hooks/useIngestEvents'
import { useExtractEvents } from '../hooks/useExtractEvents'
import type { ScanResultItem, VideoClip } from '../types/video'

type ActiveTab = 'ingest' | 'scan' | 'extract'
type InputMode = 'file' | 'directory'

/**
 * VideoPage provides three tabs for the video pipeline:
 * - Ingest: upload or directory-path ingest with smart defaults and progress
 * - Scan: display project-wide auto-scan results per clip
 * - Extract: start reference frame extraction with progress and thumbnail grid
 */
export default function VideoPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('ingest')

  // ---- Ingest tab state ----
  const [inputMode, setInputMode] = useState<InputMode>('directory')
  const [videoFilePath, setVideoFilePath] = useState('')
  const [directoryPath, setDirectoryPath] = useState('')
  const [fps, setFps] = useState(16)
  const [resolution, setResolution] = useState(720)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [threshold, setThreshold] = useState(27.0)
  const [maxFrames, setMaxFrames] = useState<number | ''>('')
  const [ingestOperationId, setIngestOperationId] = useState<string | null>(null)
  const [isStartingIngest, setIsStartingIngest] = useState(false)
  const [ingestClipCount, setIngestClipCount] = useState<number | null>(null)

  const ingestProgress = useIngestEvents(ingestOperationId)
  const ingestInProgress = ingestOperationId !== null && !ingestProgress.isComplete && !ingestProgress.error

  // ---- Scan tab state ----
  const [scanResults, setScanResults] = useState<ScanResultItem[]>([])
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const scanLoadedRef = useRef(false)

  // ---- Extract tab state ----
  const [framesPerClip, setFramesPerClip] = useState(1)
  const [extractOperationId, setExtractOperationId] = useState<string | null>(null)
  const [isStartingExtract, setIsStartingExtract] = useState(false)
  const [extractedClips, setExtractedClips] = useState<VideoClip[]>([])

  const extractProgress = useExtractEvents(extractOperationId)
  const extractInProgress = extractOperationId !== null && !extractProgress.isComplete && !extractProgress.error

  // Load scan results when scan tab is activated
  useEffect(() => {
    if (activeTab === 'scan' && !scanLoadedRef.current) {
      void fetchScan()
      scanLoadedRef.current = true
    }
  }, [activeTab])

  // Refresh scan after successful ingest
  useEffect(() => {
    if (ingestProgress.isComplete && activeTab === 'scan') {
      void fetchScan()
    }
  }, [ingestProgress.isComplete, activeTab])

  // Load extracted clips after extraction completes
  useEffect(() => {
    if (extractProgress.isComplete) {
      void fetchClips()
    }
  }, [extractProgress.isComplete])

  async function fetchScan() {
    setScanLoading(true)
    setScanError(null)
    try {
      const res = await fetch('/api/v1/video/scan')
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        setScanError(err.detail)
        return
      }
      const data = await res.json() as ScanResultItem[]
      setScanResults(data)
    } catch (err) {
      setScanError(err instanceof Error ? err.message : String(err))
    } finally {
      setScanLoading(false)
    }
  }

  async function fetchClips() {
    try {
      const res = await fetch('/api/v1/video/clips')
      if (!res.ok) return
      const data = await res.json() as VideoClip[]
      setExtractedClips(data)
    } catch {
      // Non-fatal: clips grid will just be empty
    }
  }

  async function handleStartIngest() {
    if (inputMode === 'file' && !videoFilePath.trim()) {
      toast.error('Please enter a video file path')
      return
    }
    if (inputMode === 'directory' && !directoryPath.trim()) {
      toast.error('Please enter a directory path')
      return
    }

    setIsStartingIngest(true)
    setIngestClipCount(null)
    try {
      const body: Record<string, unknown> = { fps, resolution, threshold }
      if (inputMode === 'file') {
        body.video_path = videoFilePath.trim()
      } else {
        body.directory_path = directoryPath.trim()
      }
      if (maxFrames !== '') body.max_frames = maxFrames

      const res = await fetch('/api/v1/video/ingest/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string | unknown[] }
        const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)
        toast.error('Failed to start ingest', { description: detail })
        return
      }

      const data = await res.json() as { operation_id: string }
      setIngestOperationId(data.operation_id)
      toast.info('Ingest started')
    } catch (err) {
      toast.error('Failed to start ingest', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsStartingIngest(false)
    }
  }

  async function handleCancelIngest() {
    if (!ingestOperationId) return
    try {
      await fetch(`/api/v1/video/ingest/${ingestOperationId}/cancel`, { method: 'POST' })
      setIngestOperationId(null)
      toast.info('Ingest cancelled')
    } catch {
      toast.error('Failed to cancel ingest')
    }
  }

  // Track completion and clip count
  useEffect(() => {
    if (ingestProgress.isComplete && ingestOperationId) {
      setIngestClipCount(ingestProgress.total > 0 ? ingestProgress.total : null)
      toast.success('Ingest complete', {
        description: ingestProgress.message || 'Video clips are ready',
      })
      // Reset operation ID to allow starting a new ingest
      setIngestOperationId(null)
      // Invalidate scan cache so next tab visit re-fetches
      scanLoadedRef.current = false
    }
  }, [ingestProgress.isComplete, ingestProgress.total, ingestProgress.message, ingestOperationId])

  useEffect(() => {
    if (ingestProgress.error) {
      toast.error('Ingest failed', { description: ingestProgress.error })
      setIngestOperationId(null)
    }
  }, [ingestProgress.error, ingestOperationId])

  async function handleStartExtract() {
    setIsStartingExtract(true)
    setExtractedClips([])
    try {
      const res = await fetch('/api/v1/video/extract/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frames_per_clip: framesPerClip }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to start extraction', { description: err.detail })
        return
      }

      const data = await res.json() as { operation_id: string }
      setExtractOperationId(data.operation_id)
      toast.info('Frame extraction started')
    } catch (err) {
      toast.error('Failed to start extraction', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsStartingExtract(false)
    }
  }

  async function handleCancelExtract() {
    if (!extractOperationId) return
    try {
      await fetch(`/api/v1/video/extract/${extractOperationId}/cancel`, { method: 'POST' })
      setExtractOperationId(null)
      toast.info('Extraction cancelled')
    } catch {
      toast.error('Failed to cancel extraction')
    }
  }

  useEffect(() => {
    if (extractProgress.isComplete && extractOperationId) {
      toast.success('Extraction complete', { description: extractProgress.message })
      setExtractOperationId(null)
    }
  }, [extractProgress.isComplete, extractProgress.message, extractOperationId])

  useEffect(() => {
    if (extractProgress.error) {
      toast.error('Extraction failed', { description: extractProgress.error })
      setExtractOperationId(null)
    }
  }, [extractProgress.error, extractOperationId])

  // Progress percentage helpers
  function ingestPercent(): number {
    if (!ingestProgress.total) return 0
    return Math.round((ingestProgress.current / ingestProgress.total) * 100)
  }

  function extractPercent(): number {
    if (!extractProgress.total) return 0
    return Math.round((extractProgress.current / extractProgress.total) * 100)
  }

  function formatDuration(seconds: number): string {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="video-page">
      <h1 className="page-title">Video Pipeline</h1>
      <p className="page-subtitle">
        Ingest raw video footage, scan clip metadata, and extract reference frames for training.
      </p>

      {/* Tab bar */}
      <div className="video-tabs">
        {(['ingest', 'scan', 'extract'] as ActiveTab[]).map((tab) => (
          <button
            key={tab}
            className={`video-tab${activeTab === tab ? ' active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* ---- INGEST TAB ---- */}
      {activeTab === 'ingest' && (
        <div className="video-tab-panel">
          {/* Input mode toggle */}
          <div className="video-input-mode">
            <button
              className={`video-mode-btn${inputMode === 'directory' ? ' active' : ''}`}
              onClick={() => setInputMode('directory')}
              disabled={ingestInProgress}
            >
              Directory
            </button>
            <button
              className={`video-mode-btn${inputMode === 'file' ? ' active' : ''}`}
              onClick={() => setInputMode('file')}
              disabled={ingestInProgress}
            >
              Single File
            </button>
          </div>

          {inputMode === 'directory' ? (
            <div className="video-field">
              <label className="video-label">Directory path</label>
              <input
                type="text"
                className="video-input"
                placeholder="C:\Videos\raw-footage"
                value={directoryPath}
                onChange={(e) => setDirectoryPath(e.target.value)}
                disabled={ingestInProgress}
              />
              <span className="video-hint">Path to directory containing raw video files (.mp4, .mov, .avi, .mkv, .webm)</span>
            </div>
          ) : (
            <div className="video-field">
              <label className="video-label">Video file path</label>
              <input
                type="text"
                className="video-input"
                placeholder="C:\Videos\my-video.mp4"
                value={videoFilePath}
                onChange={(e) => setVideoFilePath(e.target.value)}
                disabled={ingestInProgress}
              />
              <span className="video-hint">Full path to a single video file</span>
            </div>
          )}

          {/* Smart defaults display */}
          <div className="video-defaults">
            <span className="video-defaults-label">Defaults:</span>
            <span className="video-defaults-value">fps={fps}, resolution={resolution}p</span>
          </div>

          {/* Advanced toggle */}
          <button
            className="video-advanced-toggle"
            onClick={() => setShowAdvanced((v) => !v)}
            disabled={ingestInProgress}
          >
            {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
          </button>

          {showAdvanced && (
            <div className="video-advanced">
              <div className="video-field">
                <label className="video-label">FPS</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={fps}
                  min={1}
                  max={60}
                  onChange={(e) => setFps(Number(e.target.value))}
                  disabled={ingestInProgress}
                />
              </div>
              <div className="video-field">
                <label className="video-label">Resolution (height px)</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={resolution}
                  min={360}
                  max={4320}
                  step={180}
                  onChange={(e) => setResolution(Number(e.target.value))}
                  disabled={ingestInProgress}
                />
              </div>
              <div className="video-field">
                <label className="video-label">Scene threshold</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={threshold}
                  min={1}
                  max={100}
                  step={0.5}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  disabled={ingestInProgress}
                />
                <span className="video-hint">Sensitivity for scene detection (default 27.0)</span>
              </div>
              <div className="video-field">
                <label className="video-label">Max frames per clip (optional)</label>
                <input
                  type="number"
                  className="video-input-sm"
                  value={maxFrames}
                  min={1}
                  placeholder="Unlimited"
                  onChange={(e) => setMaxFrames(e.target.value === '' ? '' : Number(e.target.value))}
                  disabled={ingestInProgress}
                />
              </div>
            </div>
          )}

          {/* Start / Cancel buttons */}
          <div className="video-actions">
            <button
              className="video-btn-primary"
              onClick={() => void handleStartIngest()}
              disabled={ingestInProgress || isStartingIngest}
            >
              {isStartingIngest ? 'Starting...' : ingestInProgress ? 'Ingesting...' : 'Start Ingest'}
            </button>
            {ingestInProgress && (
              <button
                className="video-btn-cancel"
                onClick={() => void handleCancelIngest()}
              >
                Cancel
              </button>
            )}
          </div>

          {/* Progress bar */}
          {ingestInProgress && (
            <div className="video-progress">
              <div className="video-progress-header">
                <span className="video-progress-stage">{ingestProgress.stage || 'Processing...'}</span>
                <span className="video-progress-pct">{ingestPercent()}%</span>
              </div>
              <div className="video-progress-track">
                <div
                  className="video-progress-fill"
                  style={{ width: `${ingestPercent()}%` }}
                />
              </div>
              <p className="video-progress-message">{ingestProgress.message}</p>
              {ingestProgress.total > 0 && (
                <p className="video-progress-count">
                  {ingestProgress.current} / {ingestProgress.total}
                </p>
              )}
            </div>
          )}

          {/* Success message */}
          {ingestClipCount !== null && !ingestInProgress && (
            <div className="video-success">
              Ingest complete — {ingestClipCount} clips ready.
              <button
                className="video-btn-link"
                onClick={() => { setActiveTab('scan'); void fetchScan() }}
              >
                View in Scan tab
              </button>
            </div>
          )}
        </div>
      )}

      {/* ---- SCAN TAB ---- */}
      {activeTab === 'scan' && (
        <div className="video-tab-panel">
          <div className="video-scan-header">
            <h2 className="video-section-title">Project Video Clips</h2>
            <button
              className="video-btn-secondary"
              onClick={() => { scanLoadedRef.current = false; void fetchScan() }}
              disabled={scanLoading}
            >
              {scanLoading ? 'Scanning...' : 'Refresh'}
            </button>
          </div>

          {scanError && (
            <div className="video-error">Error: {scanError}</div>
          )}

          {!scanLoading && !scanError && scanResults.length === 0 && (
            <div className="video-empty">
              No video clips found in project. Use Ingest to process videos.
            </div>
          )}

          {scanResults.length > 0 && (
            <div className="video-table-wrapper">
              <table className="video-table">
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Resolution</th>
                    <th>FPS</th>
                    <th>Duration</th>
                    <th>Codec</th>
                    <th>Frames</th>
                    <th>Issues</th>
                  </tr>
                </thead>
                <tbody>
                  {scanResults.map((clip) => (
                    <tr key={clip.filename}>
                      <td className="video-table-filename">{clip.filename}</td>
                      <td>{clip.width}x{clip.height}</td>
                      <td>{clip.fps.toFixed(2)}</td>
                      <td>{formatDuration(clip.duration)}</td>
                      <td>{clip.codec}</td>
                      <td>{clip.frame_count}</td>
                      <td>
                        {clip.issues.length > 0 ? (
                          <span className="video-issues">{clip.issues.join(', ')}</span>
                        ) : (
                          <span className="video-ok">OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---- EXTRACT TAB ---- */}
      {activeTab === 'extract' && (
        <div className="video-tab-panel">
          <div className="video-field">
            <label className="video-label">Frames per clip</label>
            <input
              type="number"
              className="video-input-sm"
              value={framesPerClip}
              min={1}
              max={50}
              onChange={(e) => setFramesPerClip(Number(e.target.value))}
              disabled={extractInProgress}
            />
            <span className="video-hint">Number of reference frames to extract from each clip</span>
          </div>

          <div className="video-actions">
            <button
              className="video-btn-primary"
              onClick={() => void handleStartExtract()}
              disabled={extractInProgress || isStartingExtract}
            >
              {isStartingExtract ? 'Starting...' : extractInProgress ? 'Extracting...' : 'Extract Frames'}
            </button>
            {extractInProgress && (
              <button
                className="video-btn-cancel"
                onClick={() => void handleCancelExtract()}
              >
                Cancel
              </button>
            )}
          </div>

          {/* Progress bar */}
          {extractInProgress && (
            <div className="video-progress">
              <div className="video-progress-header">
                <span className="video-progress-stage">Extracting frames...</span>
                <span className="video-progress-pct">{extractPercent()}%</span>
              </div>
              <div className="video-progress-track">
                <div
                  className="video-progress-fill"
                  style={{ width: `${extractPercent()}%` }}
                />
              </div>
              <p className="video-progress-message">{extractProgress.message}</p>
              {extractProgress.total > 0 && (
                <p className="video-progress-count">
                  {extractProgress.current} / {extractProgress.total}
                </p>
              )}
            </div>
          )}

          {/* Extracted frames thumbnail grid */}
          {extractedClips.length > 0 && (
            <div className="video-clips-grid">
              <h3 className="video-section-title">Extracted Reference Frames</h3>
              <div className="video-clips-thumbnails">
                {extractedClips.map((clip) => (
                  <div key={clip.id} className="video-clip-card">
                    <img
                      src={clip.thumbnail_url}
                      alt={clip.relative_path}
                      className="video-clip-thumb"
                    />
                    <p className="video-clip-name">
                      {clip.relative_path.split('/').pop()}
                    </p>
                    <p className="video-clip-meta">
                      {clip.width}x{clip.height} &bull; {clip.fps.toFixed(1)} fps &bull; {formatDuration(clip.duration)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
