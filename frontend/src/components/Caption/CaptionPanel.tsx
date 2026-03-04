import { useState } from 'react'
import { toast } from 'sonner'

interface CaptionPanelProps {
  imageId: string
  initialCaption: string | null
  onSaved: (caption: string) => void
}

/**
 * CaptionPanel renders an inline caption editor in the lightbox footer.
 *
 * Read-only by default — shows caption text or a placeholder.
 * Click "Edit" to enter edit mode with a textarea and Save/Cancel controls.
 * Saving calls PATCH /api/v1/captions/{imageId} and invokes the onSaved callback.
 */
export default function CaptionPanel({ imageId, initialCaption, onSaved }: CaptionPanelProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedCaption, setEditedCaption] = useState(initialCaption ?? '')
  const [savedCaption, setSavedCaption] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  // Use savedCaption if we've saved locally, otherwise fall back to prop
  const displayCaption = savedCaption ?? initialCaption

  function handleEdit() {
    setEditedCaption(displayCaption ?? '')
    setIsEditing(true)
  }

  function handleCancel() {
    setEditedCaption(displayCaption ?? '')
    setIsEditing(false)
  }

  async function handleSave() {
    if (isSaving) return
    setIsSaving(true)
    try {
      const res = await fetch(`/api/v1/captions/${imageId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caption: editedCaption }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        toast.error('Failed to save caption', { description: err.detail })
        return
      }
      setSavedCaption(editedCaption)
      onSaved(editedCaption)
      setIsEditing(false)
      toast.success('Caption saved')
    } catch (err) {
      toast.error('Failed to save caption', {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setIsSaving(false)
    }
  }

  if (isEditing) {
    return (
      <div className="caption-panel caption-panel--editing">
        <textarea
          className="caption-panel-textarea"
          value={editedCaption}
          onChange={(e) => setEditedCaption(e.target.value)}
          rows={3}
          autoFocus
          placeholder="Enter caption..."
        />
        <div className="caption-panel-actions">
          <button
            className="caption-panel-btn caption-panel-btn--save"
            onClick={() => void handleSave()}
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          <button
            className="caption-panel-btn caption-panel-btn--cancel"
            onClick={handleCancel}
            disabled={isSaving}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="caption-panel caption-panel--readonly">
      <span className="caption-panel-text">
        {displayCaption ?? <span className="caption-panel-placeholder">No caption</span>}
      </span>
      <button className="caption-panel-btn caption-panel-btn--edit" onClick={handleEdit}>
        Edit
      </button>
    </div>
  )
}
