import { useState } from 'react'
import { toast } from 'sonner'

interface Props {
  triggerWord: string
  imageIds?: string[]
}

async function batchOp(action: string, body: Record<string, unknown>): Promise<void> {
  const res = await fetch('/api/v1/captions/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...body }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error((err as { detail: string }).detail ?? 'Batch operation failed')
  }
}

export default function BatchTagBar({ triggerWord, imageIds }: Props) {
  const [addTag, setAddTag] = useState('')
  const [removeTag, setRemoveTag] = useState('')
  const [replaceFrom, setReplaceFrom] = useState('')
  const [replaceTo, setReplaceTo] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const scope = imageIds && imageIds.length > 0 ? { image_ids: imageIds } : {}

  async function handleAdd() {
    if (!addTag.trim()) return
    setIsLoading(true)
    try {
      await batchOp('add_tag', { tag: addTag.trim(), ...scope })
      toast.success(`Tag "${addTag.trim()}" added`)
      setAddTag('')
    } catch (err) {
      toast.error('Failed to add tag', { description: err instanceof Error ? err.message : String(err) })
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRemove() {
    if (!removeTag.trim()) return
    setIsLoading(true)
    try {
      await batchOp('remove_tag', { tag: removeTag.trim(), ...scope })
      toast.success(`Tag "${removeTag.trim()}" removed`)
      setRemoveTag('')
    } catch (err) {
      toast.error('Failed to remove tag', { description: err instanceof Error ? err.message : String(err) })
    } finally {
      setIsLoading(false)
    }
  }

  async function handleReplace() {
    if (!replaceFrom.trim()) return
    setIsLoading(true)
    try {
      await batchOp('replace_tag', { old_tag: replaceFrom.trim(), new_tag: replaceTo.trim(), ...scope })
      toast.success(`Replaced "${replaceFrom.trim()}" with "${replaceTo.trim()}"`)
      setReplaceFrom('')
      setReplaceTo('')
    } catch (err) {
      toast.error('Failed to replace tag', { description: err instanceof Error ? err.message : String(err) })
    } finally {
      setIsLoading(false)
    }
  }

  async function handlePrepend() {
    if (!triggerWord.trim()) {
      toast.warning('No trigger word set — configure it in Provider Settings')
      return
    }
    setIsLoading(true)
    try {
      await batchOp('prepend_trigger', { trigger_word: triggerWord, ...scope })
      toast.success(`Prepended trigger word "${triggerWord}"`)
    } catch (err) {
      toast.error('Failed to prepend trigger', { description: err instanceof Error ? err.message : String(err) })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="batch-tag-bar">
      {/* Add Tag */}
      <div className="batch-tag-group">
        <input
          type="text"
          className="batch-tag-input"
          placeholder="Tag to add..."
          value={addTag}
          onChange={(e) => setAddTag(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void handleAdd()}
          disabled={isLoading}
        />
        <button
          className="batch-tag-btn batch-tag-btn--add"
          onClick={() => void handleAdd()}
          disabled={isLoading || !addTag.trim()}
        >
          Add
        </button>
      </div>

      {/* Remove Tag */}
      <div className="batch-tag-group">
        <input
          type="text"
          className="batch-tag-input"
          placeholder="Tag to remove..."
          value={removeTag}
          onChange={(e) => setRemoveTag(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void handleRemove()}
          disabled={isLoading}
        />
        <button
          className="batch-tag-btn batch-tag-btn--remove"
          onClick={() => void handleRemove()}
          disabled={isLoading || !removeTag.trim()}
        >
          Remove
        </button>
      </div>

      {/* Replace Tag */}
      <div className="batch-tag-group">
        <input
          type="text"
          className="batch-tag-input"
          placeholder="Replace..."
          value={replaceFrom}
          onChange={(e) => setReplaceFrom(e.target.value)}
          disabled={isLoading}
        />
        <span className="batch-tag-arrow">→</span>
        <input
          type="text"
          className="batch-tag-input"
          placeholder="With..."
          value={replaceTo}
          onChange={(e) => setReplaceTo(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void handleReplace()}
          disabled={isLoading}
        />
        <button
          className="batch-tag-btn batch-tag-btn--replace"
          onClick={() => void handleReplace()}
          disabled={isLoading || !replaceFrom.trim()}
        >
          Replace
        </button>
      </div>

      {/* Prepend Trigger */}
      <div className="batch-tag-group">
        <button
          className="batch-tag-btn batch-tag-btn--prepend"
          onClick={() => void handlePrepend()}
          disabled={isLoading}
          title={triggerWord ? `Prepend "${triggerWord}" to all captions` : 'Set trigger word in Provider Settings first'}
        >
          Prepend Trigger{triggerWord ? `: "${triggerWord}"` : ''}
        </button>
      </div>
    </div>
  )
}
