import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useImages } from '../hooks/useImages'
import { useCaptionEvents } from '../hooks/useCaptionEvents'
import ProviderConfigSection from '../components/Caption/ProviderConfigSection'
import ThumbnailStrip from '../components/Caption/ThumbnailStrip'
import BatchTagBar from '../components/Caption/BatchTagBar'
import type { GalleryItem } from '../types/image'

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

const DEFAULT_CONFIG: CaptionProviderConfig = {
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

async function fetchConfig(): Promise<CaptionProviderConfig> {
  const res = await fetch('/api/v1/captions/config')
  if (!res.ok) throw new Error('Failed to fetch caption config')
  return res.json() as Promise<CaptionProviderConfig>
}

async function fetchSettings(): Promise<{ anchor_word?: string }> {
  const res = await fetch('/api/v1/settings/')
  if (!res.ok) throw new Error('Failed to fetch settings')
  return res.json() as Promise<{ anchor_word?: string }>
}

export default function CaptionPage() {
  const queryClient = useQueryClient()
  const { data: imagesData, isLoading: imagesLoading } = useImages()
  const images: GalleryItem[] = imagesData?.images ?? []

  const { data: config = DEFAULT_CONFIG } = useQuery<CaptionProviderConfig>({
    queryKey: ['caption-config'],
    queryFn: fetchConfig,
  })

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const triggerWord = settings?.anchor_word ?? ''

  const [selectedImageId, setSelectedImageId] = useState<string | null>(null)
  const [captionOperationId, setCaptionOperationId] = useState<string | null>(null)
  const [editingCaption, setEditingCaption] = useState<string>('')
  const [isSavingCaption, setIsSavingCaption] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [overwriteExisting, setOverwriteExisting] = useState(false)

  const captionProgress = useCaptionEvents(captionOperationId)

  const selectedImage = images.find((img) => img.id === selectedImageId) ?? null

  // Sync editing caption when selected image changes
  useEffect(() => {
    if (selectedImage) {
      setEditingCaption(selectedImage.caption ?? '')
    }
  }, [selectedImageId, selectedImage])

  // Handle caption progress
  useEffect(() => {
    if (!captionOperationId) return

    if (captionProgress.isComplete) {
      // Show warning if some images failed, success if all passed
      const hasErrors = captionProgress.errorCount > 0
      const toastFn = hasErrors ? toast.warning : toast.success
      let description = captionProgress.message
      if (hasErrors && captionProgress.firstError) {
        // Extract the error reason from "Error captioning foo.jpg: <reason>"
        const match = captionProgress.firstError.match(/Error captioning [^:]+: (.+)/)
        const reason = match ? match[1] : captionProgress.firstError
        description += `\n${reason}`
      }
      toastFn(hasErrors ? 'Captioning finished with errors' : 'Captions generated', {
        id: 'caption-progress',
        description,
        duration: hasErrors ? 8000 : 4000,
      })
      setCaptionOperationId(null)
      void queryClient.invalidateQueries({ queryKey: ['images'] })
    } else if (captionProgress.error) {
      toast.error('Caption generation failed', {
        id: 'caption-progress',
        description: captionProgress.error,
      })
      setCaptionOperationId(null)
    } else if (captionProgress.total > 0) {
      const pct = Math.round((captionProgress.current / captionProgress.total) * 100)
      toast.loading(`Generating captions... ${captionProgress.current}/${captionProgress.total} (${pct}%)`, {
        id: 'caption-progress',
      })
    }
  }, [captionProgress, captionOperationId, queryClient])

  async function handleGenerateCaptions() {
    if (isGenerating || captionOperationId) return
    setIsGenerating(true)
    try {
      const res = await fetch('/api/v1/captions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          style: 'auto',
          provider_preset: config.provider,
          overwrite: overwriteExisting,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to start captioning', { description: (err as { detail: string }).detail })
        return
      }
      const data = await res.json() as { operation_id: string }
      setCaptionOperationId(data.operation_id)
      toast.loading('Starting caption generation...', { id: 'caption-progress' })
    } catch (err) {
      toast.error('Failed to start captioning', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsGenerating(false)
    }
  }

  async function handleSaveCaption() {
    if (!selectedImageId) return
    setIsSavingCaption(true)
    try {
      const res = await fetch(`/api/v1/captions/${selectedImageId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caption: editingCaption }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to save caption', { description: (err as { detail: string }).detail })
        return
      }
      toast.success('Caption saved')
      void queryClient.invalidateQueries({ queryKey: ['images'] })
    } catch (err) {
      toast.error('Failed to save caption', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsSavingCaption(false)
    }
  }

  function handleConfigSave(savedConfig: CaptionProviderConfig) {
    queryClient.setQueryData(['caption-config'], savedConfig)
    toast.success('Provider config saved')
  }

  function handleTriggerWordSave(word: string) {
    queryClient.setQueryData(['settings'], (old: { anchor_word?: string } | undefined) => ({
      ...old,
      anchor_word: word,
    }))
  }

  const isCaptioning = captionOperationId !== null && !captionProgress.isComplete && !captionProgress.error

  return (
    <div className="caption-page">
      {/* Provider config */}
      <ProviderConfigSection
        config={config}
        onSave={handleConfigSave}
        triggerWord={triggerWord}
        onTriggerWordSave={handleTriggerWordSave}
      />

      {/* Batch tag operations */}
      <BatchTagBar triggerWord={triggerWord} />

      {/* Thumbnail strip */}
      {imagesLoading ? (
        <div className="caption-loading">Loading images...</div>
      ) : (
        <ThumbnailStrip
          images={images}
          selectedId={selectedImageId}
          onSelect={setSelectedImageId}
        />
      )}

      {/* Generate Captions button */}
      <div className="caption-generate-row">
        <button
          className="caption-generate-btn"
          onClick={() => void handleGenerateCaptions()}
          disabled={isGenerating || isCaptioning}
        >
          {isCaptioning
            ? `Generating... ${captionProgress.current}/${captionProgress.total}`
            : isGenerating
              ? 'Starting...'
              : 'Generate Captions'}
        </button>
        <label className="caption-overwrite-label">
          <input
            type="checkbox"
            checked={overwriteExisting}
            onChange={(e) => setOverwriteExisting(e.target.checked)}
            disabled={isGenerating || isCaptioning}
          />
          Overwrite existing
        </label>
        {isCaptioning && captionProgress.total > 0 && (
          <div className="caption-progress-bar-track">
            <div
              className="caption-progress-bar-fill"
              style={{
                width: `${Math.round((captionProgress.current / captionProgress.total) * 100)}%`,
              }}
            />
          </div>
        )}
      </div>

      {/* Workspace: image preview + caption editor */}
      {selectedImage ? (
        <div className="caption-workspace">
          <div className="caption-preview">
            <img
              src={selectedImage.full_url}
              alt={selectedImage.relative_path}
              className="caption-preview-img"
            />
            <p className="caption-preview-filename">
              {selectedImage.relative_path.split('/').pop()}
            </p>
          </div>
          <div className="caption-editor">
            <textarea
              className="caption-textarea"
              value={editingCaption}
              onChange={(e) => setEditingCaption(e.target.value)}
              placeholder="Caption will appear here after generation. Click to edit."
            />
            <div className="caption-editor-actions">
              <button
                className="caption-save-btn"
                onClick={() => void handleSaveCaption()}
                disabled={isSavingCaption}
              >
                {isSavingCaption ? 'Saving...' : 'Save Caption'}
              </button>
              <button
                className="caption-reset-btn"
                onClick={() => setEditingCaption(selectedImage.caption ?? '')}
                disabled={isSavingCaption}
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="caption-workspace-empty">
          <p>Click a thumbnail above to view and edit its caption.</p>
        </div>
      )}
    </div>
  )
}
