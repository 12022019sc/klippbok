import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { useCurationEvents } from '../hooks/useCurationEvents'
import CurationConfig from '../components/Curation/CurationConfig'
import CurationProgress from '../components/Curation/CurationProgress'
import CurationResults from '../components/Curation/CurationResults'
import PipelineSummary from '../components/Curation/PipelineSummary'
import type { CurationConfig as CurationConfigType, CurationResult, CurationProgress as CurationProgressType } from '../types/curation'

type PageState = 'config' | 'progress' | 'results'

export default function CuratePage() {
  const [pageState, setPageState] = useState<PageState>('config')
  const [operationId, setOperationId] = useState<string | null>(null)
  const [result, setResult] = useState<CurationResult | null>(null)
  const [progress, setProgress] = useState<CurationProgressType | null>(null)

  const events = useCurationEvents(operationId)

  // Check for existing results on mount
  useEffect(() => {
    fetch('/api/v1/curation/results')
      .then((res) => {
        if (res.ok) return res.json()
        return null
      })
      .then((data: CurationResult | null) => {
        if (data && data.selected_ids && data.selected_ids.length > 0) {
          setResult(data)
          setPageState('results')
        }
      })
      .catch(() => {
        // No existing results, stay in config
      })
  }, [])

  // Handle SSE events
  useEffect(() => {
    if (events.isComplete && events.result) {
      setResult(events.result)
      setOperationId(null)
      setPageState('results')
    }
  }, [events.isComplete, events.result])

  useEffect(() => {
    if (events.stage || events.current > 0) {
      setProgress({ stage: events.stage, current: events.current, total: events.total })
    }
  }, [events.stage, events.current, events.total])

  useEffect(() => {
    if (events.error) {
      toast.error('Curation failed', { description: events.error })
      setOperationId(null)
      setPageState('config')
    }
  }, [events.error])

  async function handleStart(config: CurationConfigType) {
    try {
      const res = await fetch('/api/v1/curation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start curation', { description: (err as { detail: string }).detail })
        return
      }
      const data = (await res.json()) as { operation_id: string }
      setOperationId(data.operation_id)
      setProgress(null)
      setPageState('progress')
    } catch (err) {
      toast.error('Failed to start curation', {
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  async function handleCancel() {
    if (!operationId) return
    try {
      await fetch(`/api/v1/curation/${operationId}/cancel`, { method: 'POST' })
    } catch {
      // best-effort cancel
    }
    setOperationId(null)
    setPageState('config')
  }

  function handleNewCuration() {
    setResult(null)
    setProgress(null)
    setPageState('config')
  }

  if (pageState === 'progress') {
    return (
      <div style={{ padding: '2rem', maxWidth: 600 }}>
        <h1 className="page-title">Dataset Curation</h1>
        <p className="page-subtitle">Running curation pipeline...</p>
        <CurationProgress progress={progress} onCancel={handleCancel} />
      </div>
    )
  }

  if (pageState === 'results' && result) {
    return (
      <div style={{ padding: '2rem' }}>
        <h1 className="page-title">Dataset Curation</h1>
        <p className="page-subtitle">
          {`${result.selected_ids.length} images selected from ${result.summary.total_scanned} scanned`}
        </p>
        <PipelineSummary summary={result.summary} />
        <CurationResults
          result={result}
          onNewCuration={handleNewCuration}
          onResultUpdate={(updated) => setResult(updated)}
        />
      </div>
    )
  }

  // Config state
  return (
    <div style={{ padding: '2rem', maxWidth: 700 }}>
      <h1 className="page-title">Dataset Curation</h1>
      <p className="page-subtitle">Automatically select the best images for LoRA training.</p>
      <CurationConfig onStart={handleStart} />
    </div>
  )
}
