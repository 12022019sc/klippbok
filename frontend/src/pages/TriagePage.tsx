import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useAppStore } from '../stores/appStore'
import { useTriageEvents } from '../hooks/useTriageEvents'
import { useFaceEvents } from '../hooks/useFaceEvents'
import type { ConceptRef, FaceCluster, TriageScore } from '../types/triage'

interface HealthStatus {
  clip_available: boolean
  insightface_available: boolean
}

interface TriageResult {
  item_path: string
  item_id: string
  best_score: number
  matches: { concept_name: string; score: number }[]
  classification: 'match' | 'borderline' | 'no_match'
}

export default function TriagePage() {
  const projectDir = useAppStore((s) => s.projectDir)
  const triageThreshold = useAppStore((s) => s.triageThreshold)
  const setTriageThreshold = useAppStore((s) => s.setTriageThreshold)
  const setTriageResults = useAppStore((s) => s.setTriageResults)
  const clearTriageResults = useAppStore((s) => s.clearTriageResults)
  const triageResults = useAppStore((s) => s.triageResults)

  // Health check state
  const [health, setHealth] = useState<HealthStatus | null>(null)

  // Concepts panel
  const [concepts, setConcepts] = useState<ConceptRef[]>([])
  const [conceptCategory, setConceptCategory] = useState('character')
  const conceptFileInputRef = useRef<HTMLInputElement>(null)

  // CLIP triage state
  const [triageOpId, setTriageOpId] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const triageProgress = useTriageEvents(triageOpId)

  // Face embedding state
  const [faceOpId, setFaceOpId] = useState<string | null>(null)
  const [isCancellingFace, setIsCancellingFace] = useState(false)
  const faceProgress = useFaceEvents(faceOpId)
  const [faceClusters, setFaceClusters] = useState<FaceCluster[]>([])
  const [clusterNames, setClusterNames] = useState<Record<number, string>>({})

  // Results display
  const [resultsList, setResultsList] = useState<TriageResult[]>([])
  // Track broken concept images for triage warning
  const [brokenConcepts, setBrokenConcepts] = useState(0)

  // Fetch health check on mount
  useEffect(() => {
    fetch('/api/v1/triage/health')
      .then((r) => r.json())
      .then((d) => setHealth(d as HealthStatus))
      .catch(() => setHealth({ clip_available: false, insightface_available: false }))
  }, [])

  // Fetch concepts on mount
  useEffect(() => {
    fetchConcepts()
  }, [])

  function fetchConcepts() {
    fetch('/api/v1/triage/concepts')
      .then((r) => r.json())
      .then((d) => setConcepts(d as ConceptRef[]))
      .catch(() => setConcepts([]))
  }

  // When triage completes, load results into store
  useEffect(() => {
    if (triageProgress.isComplete && triageOpId) {
      setTriageOpId(null)
      fetchTriageResults()
    }
  }, [triageProgress.isComplete, triageOpId])

  // When face embedding completes, load clusters
  useEffect(() => {
    if (faceProgress.isComplete && faceOpId) {
      setFaceOpId(null)
      fetchFaceClusters()
    }
  }, [faceProgress.isComplete, faceOpId])

  function fetchTriageResults() {
    fetch('/api/v1/triage/results')
      .then((r) => r.json())
      .then((d) => {
        const results = d as TriageResult[]
        setResultsList(results)
        // Convert to Record<item_id, TriageScore> for store
        const scoreMap: Record<string, TriageScore> = {}
        for (const r of results) {
          scoreMap[r.item_id] = {
            item_id: r.item_id,
            best_score: r.best_score,
            classification: r.classification,
            matches: r.matches,
          }
        }
        setTriageResults(scoreMap)
      })
      .catch(() => {
        setResultsList([])
      })
  }

  function fetchFaceClusters() {
    fetch('/api/v1/triage/face/clusters')
      .then((r) => r.json())
      .then((d) => {
        const clusters = d as FaceCluster[]
        setFaceClusters(clusters)
        // Initialize name inputs
        const names: Record<number, string> = {}
        for (const c of clusters) {
          names[c.cluster_id] = c.suggested_name ?? ''
        }
        setClusterNames(names)
      })
      .catch(() => setFaceClusters([]))
  }

  async function handleRunTriage() {
    if (!projectDir) return
    if (brokenConcepts > 0) {
      const ok = window.confirm(
        `${brokenConcepts} concept reference image(s) failed to load. Triage results may be incomplete. Continue anyway?`
      )
      if (!ok) return
    }
    try {
      const res = await fetch('/api/v1/triage/run/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: triageThreshold }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to start triage', { description: err.detail })
        return
      }
      const data = await res.json() as { operation_id: string }
      clearTriageResults()
      setResultsList([])
      setTriageOpId(data.operation_id)
    } catch (err) {
      toast.error('Failed to start triage', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  async function handleCancelTriage() {
    if (!triageOpId) return
    setIsCancelling(true)
    try {
      await fetch(`/api/v1/triage/run/${triageOpId}/cancel`, { method: 'POST' })
      setTriageOpId(null)
    } catch (err) {
      toast.error('Failed to cancel triage', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsCancelling(false)
    }
  }

  async function handleRunFaceEmbedding() {
    if (!projectDir) return
    try {
      const res = await fetch('/api/v1/triage/face/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to start face embedding', { description: err.detail })
        return
      }
      const data = await res.json() as { operation_id: string }
      setFaceOpId(data.operation_id)
      setFaceClusters([])
    } catch (err) {
      toast.error('Failed to start face embedding', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  async function handleCancelFace() {
    if (!faceOpId) return
    setIsCancellingFace(true)
    try {
      await fetch(`/api/v1/triage/face/${faceOpId}/cancel`, { method: 'POST' })
      setFaceOpId(null)
    } catch (err) {
      toast.error('Failed to cancel face embedding', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsCancellingFace(false)
    }
  }

  async function handleConfirmCluster(clusterId: number) {
    const name = clusterNames[clusterId] ?? ''
    if (!name.trim()) return
    try {
      const res = await fetch(`/api/v1/triage/face/clusters/${clusterId}/name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), confirmed: true }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Failed to confirm cluster', { description: err.detail })
        return
      }
      toast.success(`Cluster named "${name.trim()}"`)
      fetchConcepts()
    } catch (err) {
      toast.error('Failed to confirm cluster', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  function handleSwapPrimary(cluster: FaceCluster, imagePath: string) {
    setFaceClusters((prev) =>
      prev.map((c) =>
        c.cluster_id === cluster.cluster_id
          ? { ...c, primary_reference: imagePath }
          : c
      )
    )
  }

  async function handleConceptUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('category', conceptCategory)
    try {
      const res = await fetch('/api/v1/triage/concepts/upload', {
        method: 'POST',
        body: formData,
      })
      if (res.ok) {
        toast.success('Concept uploaded')
        fetchConcepts()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' })) as { detail: string }
        toast.error('Upload failed', { description: err.detail })
      }
    } catch (err) {
      toast.error('Upload failed', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
    // Reset input
    if (conceptFileInputRef.current) {
      conceptFileInputRef.current.value = ''
    }
  }

  // Compute summary stats
  const matchItems = resultsList.filter((r) => r.classification === 'match')
  const borderlineItems = resultsList.filter((r) => r.classification === 'borderline')
  const noMatchItems = resultsList.filter((r) => r.classification === 'no_match')
  const totalItems = resultsList.length

  const isTriageRunning = triageOpId !== null
  const isFaceRunning = faceOpId !== null

  const borderlineLow = Math.max(0, triageThreshold - 0.1)

  return (
    <div className="triage-layout">
      {/* Left: Concepts Panel */}
      <aside className="concepts-panel">
        <h2 className="concepts-panel-header">Concept References</h2>

        {concepts.length === 0 ? (
          <p className="concepts-empty">
            No concepts yet. Add images as references from the Gallery, or upload here.
          </p>
        ) : (
          <div className="concepts-grid">
            {concepts.map((c, idx) => (
              <div key={idx} className="concept-thumb" title={c.name}>
                <img
                  src={`/api/v1/images/file?path=${encodeURIComponent(c.image_path)}`}
                  alt={c.name}
                  loading="lazy"
                  onError={(e) => {
                    e.currentTarget.style.background = '#374151'
                    e.currentTarget.style.objectFit = 'contain'
                    e.currentTarget.src = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%236b7280"><rect width="24" height="24" fill="%231f2937"/><path d="M12 4a4 4 0 100 8 4 4 0 000-8zm-6 14c0-3.31 4.03-5 6-5s6 1.69 6 5v1H6v-1z"/></svg>')
                    setBrokenConcepts((n) => n + 1)
                  }}
                />
                <div className="concept-thumb-label">{c.name}</div>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: '0.5rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
            <label style={{ color: '#9ca3af', fontSize: '0.78rem' }}>Category:</label>
            <input
              type="text"
              value={conceptCategory}
              onChange={(e) => setConceptCategory(e.target.value)}
              className="face-cluster-name-input"
              style={{ flex: 1, fontSize: '0.78rem' }}
              placeholder="character"
            />
          </div>
          <input
            ref={conceptFileInputRef}
            type="file"
            accept="image/*"
            onChange={handleConceptUpload}
            style={{ display: 'none' }}
          />
          <button
            className="triage-btn triage-btn--secondary"
            style={{ width: '100%', fontSize: '0.8rem' }}
            onClick={() => conceptFileInputRef.current?.click()}
            type="button"
          >
            Upload Reference
          </button>
        </div>
      </aside>

      {/* Right: Main Content */}
      <main className="triage-main">
        <h1 className="page-title">Triage</h1>

        {/* Section 1: CLIP Triage Controls */}
        <section className="triage-section">
          <h2 className="triage-section-title">CLIP Triage</h2>

          {health && !health.clip_available && (
            <div className="triage-warning-banner">
              CLIP model not available. Install with: pip install torch transformers
            </div>
          )}

          <div className="threshold-row">
            <label className="threshold-label">
              Threshold: <strong>{triageThreshold.toFixed(2)}</strong>
              <span style={{ color: '#9ca3af', marginLeft: '0.5rem' }}>
                (borderline: {borderlineLow.toFixed(2)}–{triageThreshold.toFixed(2)})
              </span>
            </label>
            <input
              type="range"
              className="threshold-slider"
              min={0.5}
              max={1.0}
              step={0.01}
              value={triageThreshold}
              onChange={(e) => setTriageThreshold(parseFloat(e.target.value))}
            />
          </div>

          {isTriageRunning && triageProgress.total > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div className="triage-progress">
                <div
                  className="triage-progress-fill"
                  style={{
                    width: `${Math.round((triageProgress.current / triageProgress.total) * 100)}%`,
                  }}
                />
              </div>
              <span className="triage-progress-label">
                {triageProgress.current}/{triageProgress.total} — {triageProgress.message}
              </span>
            </div>
          )}

          {triageProgress.error && (
            <div className="triage-warning-banner">{triageProgress.error}</div>
          )}

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              className="triage-btn"
              onClick={handleRunTriage}
              disabled={isTriageRunning || !projectDir}
              type="button"
            >
              {isTriageRunning ? 'Running…' : 'Run Triage'}
            </button>
            {isTriageRunning && (
              <button
                className="triage-btn triage-btn--danger"
                onClick={handleCancelTriage}
                disabled={isCancelling}
                type="button"
              >
                {isCancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            {resultsList.length > 0 && !isTriageRunning && (
              <button
                className="triage-btn triage-btn--secondary"
                onClick={fetchTriageResults}
                type="button"
              >
                Reload Results
              </button>
            )}
          </div>
        </section>

        {/* Section 2: Results Summary */}
        {resultsList.length > 0 && (
          <section className="triage-section">
            <h2 className="triage-section-title">Results Summary</h2>
            <div className="triage-summary-stats">
              <div className="triage-stat triage-stat--match">
                <span className="triage-stat-value">{matchItems.length}</span>
                <span className="triage-stat-label">Match</span>
              </div>
              <div className="triage-stat triage-stat--borderline">
                <span className="triage-stat-value">{borderlineItems.length}</span>
                <span className="triage-stat-label">Borderline</span>
              </div>
              <div className="triage-stat triage-stat--no-match">
                <span className="triage-stat-value">{noMatchItems.length}</span>
                <span className="triage-stat-label">No Match</span>
              </div>
              <div className="triage-stat">
                <span className="triage-stat-value" style={{ color: '#d1d5db' }}>{totalItems}</span>
                <span className="triage-stat-label">Total</span>
              </div>
            </div>

            {matchItems.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <h3 style={{ color: '#22c55e', fontSize: '0.85rem', margin: '0 0 0.5rem 0' }}>
                  Matches
                </h3>
                <div className="triage-result-list">
                  {matchItems.map((r) => (
                    <div key={r.item_id} className="triage-result-item">
                      <img
                        src={`/api/v1/images/${r.item_id}/thumbnail`}
                        alt=""
                        className="triage-result-thumb"
                        loading="lazy"
                      />
                      <span className="triage-result-path" title={r.item_path}>
                        {r.item_path.split('/').pop() ?? r.item_path}
                      </span>
                      <span
                        className="triage-result-score"
                        style={{ backgroundColor: '#22c55e' }}
                      >
                        {r.best_score.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {borderlineItems.length > 0 && (
              <div>
                <h3 style={{ color: '#eab308', fontSize: '0.85rem', margin: '0 0 0.5rem 0' }}>
                  Borderline
                </h3>
                <div className="triage-result-list">
                  {borderlineItems.map((r) => (
                    <div key={r.item_id} className="triage-result-item">
                      <img
                        src={`/api/v1/images/${r.item_id}/thumbnail`}
                        alt=""
                        className="triage-result-thumb"
                        loading="lazy"
                      />
                      <span className="triage-result-path" title={r.item_path}>
                        {r.item_path.split('/').pop() ?? r.item_path}
                      </span>
                      <span
                        className="triage-result-score"
                        style={{ backgroundColor: '#eab308' }}
                      >
                        {r.best_score.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Section 3: Face Clustering */}
        <section className="triage-section">
          <h2 className="triage-section-title">Face Clustering</h2>

          {health && !health.insightface_available && (
            <div className="triage-info-banner">
              InsightFace not installed. Install with:{' '}
              <code>pip install insightface onnxruntime</code>
            </div>
          )}

          {isFaceRunning && faceProgress.total > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div className="triage-progress">
                <div
                  className="triage-progress-fill"
                  style={{
                    width: `${Math.round((faceProgress.current / faceProgress.total) * 100)}%`,
                  }}
                />
              </div>
              <span className="triage-progress-label">
                Computing face embeddings… {faceProgress.current}/{faceProgress.total} images
                {faceProgress.eta_seconds > 0 && ` (ETA: ${Math.round(faceProgress.eta_seconds)}s)`}
                {faceProgress.message ? ` — ${faceProgress.message}` : ''}
              </span>
            </div>
          )}

          {faceProgress.error && (
            <div className="triage-warning-banner">{faceProgress.error}</div>
          )}

          <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
            <button
              className="triage-btn"
              onClick={handleRunFaceEmbedding}
              disabled={isFaceRunning || !projectDir || (health ? !health.insightface_available : false)}
              type="button"
            >
              {isFaceRunning ? 'Computing…' : 'Compute Face Embeddings'}
            </button>
            {isFaceRunning && (
              <button
                className="triage-btn triage-btn--danger"
                onClick={handleCancelFace}
                disabled={isCancellingFace}
                type="button"
              >
                {isCancellingFace ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            {faceClusters.length > 0 && !isFaceRunning && (
              <button
                className="triage-btn triage-btn--secondary"
                onClick={fetchFaceClusters}
                type="button"
              >
                Reload Clusters
              </button>
            )}
          </div>

          {/* Suggested Subjects */}
          {faceClusters.length > 0 && (
            <div>
              <h3 style={{ color: '#f9fafb', fontSize: '0.9rem', margin: '0 0 0.75rem 0' }}>
                Suggested Subjects ({faceClusters.length} cluster{faceClusters.length !== 1 ? 's' : ''})
              </h3>
              <div className="face-clusters">
                {faceClusters.map((cluster) => (
                  <div key={cluster.cluster_id} className="face-cluster-card">
                    <div className="face-cluster-header">
                      <span style={{ color: '#9ca3af', fontSize: '0.8rem', flexShrink: 0 }}>
                        Cluster {cluster.cluster_id + 1}
                      </span>
                      <input
                        type="text"
                        className="face-cluster-name-input"
                        placeholder="Enter name (e.g. Person A)"
                        value={clusterNames[cluster.cluster_id] ?? ''}
                        onChange={(e) =>
                          setClusterNames((prev) => ({
                            ...prev,
                            [cluster.cluster_id]: e.target.value,
                          }))
                        }
                      />
                      <button
                        className="triage-btn triage-btn--confirm"
                        style={{ fontSize: '0.8rem', padding: '0.3rem 0.75rem', flexShrink: 0 }}
                        onClick={() => handleConfirmCluster(cluster.cluster_id)}
                        disabled={!(clusterNames[cluster.cluster_id] ?? '').trim()}
                        type="button"
                      >
                        Confirm
                      </button>
                    </div>
                    <div className="face-cluster-images">
                      {cluster.image_paths.map((imgPath, i) => {
                        const isPrimary = imgPath === cluster.primary_reference
                        return (
                          <div
                            key={i}
                            className={`face-cluster-img-wrap${isPrimary ? ' face-cluster-img-wrap--primary' : ''}`}
                            title={isPrimary ? 'Primary reference' : 'Click to set as primary'}
                            onClick={() => !isPrimary && handleSwapPrimary(cluster, imgPath)}
                          >
                            <img
                              src={`/api/v1/images/file?path=${encodeURIComponent(imgPath)}`}
                              alt={`Face ${i + 1}`}
                              loading="lazy"
                              onError={(e) => {
                                e.currentTarget.style.background = '#374151'
                                e.currentTarget.src = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%236b7280"><rect width="24" height="24" fill="%231f2937"/><path d="M12 4a4 4 0 100 8 4 4 0 000-8zm-6 14c0-3.31 4.03-5 6-5s6 1.69 6 5v1H6v-1z"/></svg>')
                              }}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!isFaceRunning && faceClusters.length === 0 && (
            <p style={{ color: '#6b7280', fontSize: '0.85rem', margin: 0 }}>
              Run face embedding to discover subject clusters in your dataset.
            </p>
          )}
        </section>
      </main>
    </div>
  )
}
