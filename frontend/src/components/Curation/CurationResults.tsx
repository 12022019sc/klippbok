import { useState, useEffect, useMemo, type MouseEvent } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useAppStore } from '../../stores/appStore'
import ScorePopover from './ScorePopover'
import type { CurationResult, ImageScore } from '../../types/curation'

interface Props {
  result: CurationResult
  onNewCuration: () => void
  onResultUpdate: (result: CurationResult) => void
}

export default function CurationResults({ result, onNewCuration, onResultUpdate }: Props) {
  const navigate = useNavigate()
  const selectByFilter = useAppStore((s) => s.selectByFilter)
  const selectionMode = useAppStore((s) => s.selectionMode)
  const toggleSelectionMode = useAppStore((s) => s.toggleSelectionMode)

  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set(result.pinned_ids))
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set(result.excluded_ids))
  const [popoverScore, setPopoverScore] = useState<ImageScore | null>(null)
  const [popoverPos, setPopoverPos] = useState({ x: 0, y: 0 })
  const [isRediversifying, setIsRediversifying] = useState(false)
  const [rejectedCollapsed, setRejectedCollapsed] = useState(false)
  const [gridFlash, setGridFlash] = useState(false)

  // Sync from result when it changes (e.g. after rediversify)
  useEffect(() => {
    setPinnedIds(new Set(result.pinned_ids))
    setExcludedIds(new Set(result.excluded_ids))
  }, [result.pinned_ids, result.excluded_ids])

  // Derive selected/rejected based on current pin/exclude state
  const { selectedScores, rejectedScores, effectiveSelectedIds } = useMemo(() => {
    const allIds = Object.keys(result.scores)
    // Start from original selected_ids, then apply pin/exclude modifications
    const baseSelected = new Set(result.selected_ids)

    // Pins add to selected, excludes remove from selected
    for (const id of pinnedIds) baseSelected.add(id)
    for (const id of excludedIds) baseSelected.delete(id)

    const selected: ImageScore[] = []
    const rejected: ImageScore[] = []
    const selIds: string[] = []

    for (const id of allIds) {
      const score = result.scores[id]
      if (baseSelected.has(id)) {
        selected.push(score)
        selIds.push(id)
      } else {
        rejected.push(score)
      }
    }

    // Sort by composite score descending
    selected.sort((a, b) => b.composite_score - a.composite_score)
    rejected.sort((a, b) => b.composite_score - a.composite_score)

    return { selectedScores: selected, rejectedScores: rejected, effectiveSelectedIds: selIds }
  }, [result.scores, result.selected_ids, pinnedIds, excludedIds])

  function handleSelectedClick(score: ImageScore) {
    const id = score.image_id
    if (pinnedIds.has(id)) {
      // Un-pin and exclude
      const nextPinned = new Set(pinnedIds)
      nextPinned.delete(id)
      setPinnedIds(nextPinned)
      const nextExcluded = new Set(excludedIds)
      nextExcluded.add(id)
      setExcludedIds(nextExcluded)
    } else {
      // Exclude (move to rejected)
      const nextExcluded = new Set(excludedIds)
      nextExcluded.add(id)
      setExcludedIds(nextExcluded)
    }
  }

  function handleRejectedClick(score: ImageScore) {
    const id = score.image_id
    // Pin (move to selected)
    const nextPinned = new Set(pinnedIds)
    nextPinned.add(id)
    setPinnedIds(nextPinned)
    const nextExcluded = new Set(excludedIds)
    nextExcluded.delete(id)
    setExcludedIds(nextExcluded)
  }

  function handleMouseEnter(score: ImageScore, e: MouseEvent) {
    setPopoverScore(score)
    setPopoverPos({ x: e.clientX, y: e.clientY })
  }

  function handleMouseLeave() {
    setPopoverScore(null)
  }

  async function handleRediversify() {
    setIsRediversifying(true)
    try {
      const res = await fetch('/api/v1/curation/rediversify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pinned_ids: [...pinnedIds],
          excluded_ids: [...excludedIds],
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Re-diversify failed', { description: (err as { detail: string }).detail })
        return
      }
      const updated = (await res.json()) as CurationResult
      const prevCount = result.selected_ids.length
      const newCount = updated.selected_ids.length
      const diff = newCount - prevCount
      const diffLabel = diff >= 0 ? `+${diff}` : `${diff}`
      toast.success(`Re-diversified (${diffLabel} images), ${newCount} now selected`)
      onResultUpdate(updated)
      // Flash the grid to signal refresh
      setGridFlash(true)
      setTimeout(() => setGridFlash(false), 400)
    } catch (err) {
      toast.error('Re-diversify failed', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsRediversifying(false)
    }
  }

  async function handleApply() {
    try {
      await fetch('/api/v1/curation/apply', { method: 'POST' })
    } catch {
      // best-effort
    }
    selectByFilter(effectiveSelectedIds)
    if (!selectionMode) toggleSelectionMode()
    toast.success(`Curated ${effectiveSelectedIds.length} images selected in gallery`)
    navigate('/')
  }

  async function handleProceedToCrop() {
    try {
      await fetch('/api/v1/curation/apply', { method: 'POST' })
    } catch {
      // best-effort
    }
    selectByFilter(effectiveSelectedIds)
    if (!selectionMode) toggleSelectionMode()
    toast.success(`Curated ${effectiveSelectedIds.length} images → proceeding to crop`)
    navigate('/crop')
  }

  return (
    <div className="curation-results">
      {/* Selected images */}
      <h3 style={{ margin: '0 0 0.5rem' }}>
        Selected ({selectedScores.length})
      </h3>
      <div className={`curation-selected-grid${gridFlash ? ' curation-grid-flash' : ''}`}>
        {selectedScores.map((score) => (
          <div
            key={score.image_id}
            className={`curation-card${pinnedIds.has(score.image_id) ? ' curation-pinned' : ''}`}
            onClick={() => handleSelectedClick(score)}
            onMouseEnter={(e) => handleMouseEnter(score, e)}
            onMouseLeave={handleMouseLeave}
          >
            <img
              src={`/api/v1/images/${score.image_id}/thumbnail`}
              alt={score.relative_path}
              loading="lazy"
            />
            <span className="curation-score-badge">
              {score.composite_score.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Rejected images */}
      <div className="curation-rejected-header" onClick={() => setRejectedCollapsed(!rejectedCollapsed)}>
        <span>Rejected ({rejectedScores.length})</span>
        <span>{rejectedCollapsed ? '\u25B6' : '\u25BC'}</span>
      </div>
      {!rejectedCollapsed && (
        <div className="curation-rejected-grid">
          {rejectedScores.map((score) => (
            <div
              key={score.image_id}
              className="curation-card"
              onClick={() => handleRejectedClick(score)}
              onMouseEnter={(e) => handleMouseEnter(score, e)}
              onMouseLeave={handleMouseLeave}
            >
              <img
                src={`/api/v1/images/${score.image_id}/thumbnail`}
                alt={score.relative_path}
                loading="lazy"
              />
              <span className="curation-score-badge">
                {score.composite_score.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Action bar */}
      <div className="curation-actions">
        <button
          className="import-button"
          onClick={handleRediversify}
          disabled={isRediversifying}
        >
          {isRediversifying ? 'Re-diversifying...' : 'Re-diversify'}
        </button>
        <button className="import-button" onClick={handleApply}>
          Apply to Gallery
        </button>
        <button className="import-button" onClick={handleProceedToCrop}>
          Proceed to Crop
        </button>
        <button
          className="import-button"
          onClick={onNewCuration}
          style={{ background: '#374151' }}
        >
          New Curation
        </button>
      </div>

      {/* Score popover */}
      {popoverScore && (
        <ScorePopover
          score={popoverScore}
          visible={true}
          position={popoverPos}
        />
      )}
    </div>
  )
}
