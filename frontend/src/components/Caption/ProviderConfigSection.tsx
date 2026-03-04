import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

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

interface Props {
  config: CaptionProviderConfig
  onSave: (config: CaptionProviderConfig) => void
  triggerWord: string
  onTriggerWordSave: (word: string) => void
}

async function fetchModels(provider: string, baseUrl: string): Promise<string[]> {
  const params = new URLSearchParams({ provider })
  if (provider === 'lm_studio' && baseUrl) {
    params.set('base_url', baseUrl)
  }
  const res = await fetch(`/api/v1/captions/models?${params.toString()}`)
  if (!res.ok) return []
  return res.json() as Promise<string[]>
}

const GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
const PROVIDER_LABELS: Record<string, string> = {
  lm_studio: 'LM Studio',
  nanogpt: 'NanoGPT',
  gemini: 'Gemini',
  joycaption: 'JoyCaption',
}

export default function ProviderConfigSection({ config, onSave, triggerWord, onTriggerWordSave }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isAdvanced, setIsAdvanced] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [local, setLocal] = useState<CaptionProviderConfig>({ ...config })
  const [localTriggerWord, setLocalTriggerWord] = useState(triggerWord)
  const [isSaving, setIsSaving] = useState(false)

  const queryClient = useQueryClient()

  const modelsEnabled = local.provider === 'lm_studio' || local.provider === 'nanogpt'
  const { data: modelList = [] } = useQuery<string[]>({
    queryKey: ['caption-models', local.provider, local.lm_studio_base_url],
    queryFn: () => fetchModels(local.provider, local.lm_studio_base_url),
    enabled: modelsEnabled,
    staleTime: 30_000,
  })

  function getProviderSummary(): string {
    const label = PROVIDER_LABELS[local.provider] ?? local.provider
    const model = local.provider === 'lm_studio'
      ? local.lm_studio_model || 'no model'
      : local.provider === 'nanogpt'
        ? local.nanogpt_model || 'no model'
        : local.provider === 'gemini'
          ? local.gemini_model
          : 'subprocess'
    return `${label} — ${model}`
  }

  async function handleSave() {
    setIsSaving(true)
    try {
      // Save global provider config
      const res = await fetch('/api/v1/captions/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(local),
      })
      if (!res.ok) throw new Error('Failed to save config')
      const saved = await res.json() as CaptionProviderConfig
      onSave(saved)

      // Save trigger word to settings (anchor_word field)
      if (localTriggerWord !== triggerWord) {
        await fetch('/api/v1/settings/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ anchor_word: localTriggerWord }),
        })
        onTriggerWordSave(localTriggerWord)
      }

      void queryClient.invalidateQueries({ queryKey: ['caption-config'] })
      setIsExpanded(false)
    } catch {
      // Keep expanded on error
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="provider-config">
      <div
        className="provider-config-header"
        onClick={() => setIsExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setIsExpanded((v) => !v)}
      >
        <span className="provider-config-summary">{getProviderSummary()}</span>
        <span className="provider-config-toggle">{isExpanded ? '▲' : '▼'}</span>
      </div>

      {isExpanded && (
        <div className="provider-config-body">
          {/* Provider dropdown */}
          <div className="provider-config-field">
            <label className="provider-config-label">Provider</label>
            <select
              className="provider-config-select"
              value={local.provider}
              onChange={(e) => setLocal({ ...local, provider: e.target.value })}
            >
              <option value="lm_studio">LM Studio</option>
              <option value="nanogpt">NanoGPT</option>
              <option value="gemini">Gemini</option>
              <option value="joycaption">JoyCaption</option>
            </select>
          </div>

          {/* LM Studio base URL */}
          {local.provider === 'lm_studio' && (
            <div className="provider-config-field">
              <label className="provider-config-label">Base URL</label>
              <input
                type="text"
                className="provider-config-input"
                value={local.lm_studio_base_url}
                onChange={(e) => setLocal({ ...local, lm_studio_base_url: e.target.value })}
                placeholder="http://localhost:1234/v1"
              />
            </div>
          )}

          {/* Model picker */}
          {(local.provider === 'lm_studio' || local.provider === 'nanogpt') && (
            <div className="provider-config-field">
              <label className="provider-config-label">Model</label>
              {local.provider === 'lm_studio' && modelList.length === 0 ? (
                <div>
                  <p className="provider-config-hint">No model loaded in LM Studio</p>
                  <input
                    type="text"
                    className="provider-config-input"
                    value={local.lm_studio_model}
                    onChange={(e) => setLocal({ ...local, lm_studio_model: e.target.value })}
                    placeholder="Enter model name manually"
                  />
                </div>
              ) : local.provider === 'lm_studio' ? (
                <select
                  className="provider-config-select"
                  value={local.lm_studio_model}
                  onChange={(e) => setLocal({ ...local, lm_studio_model: e.target.value })}
                >
                  <option value="">-- select model --</option>
                  {modelList.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <select
                  className="provider-config-select"
                  value={local.nanogpt_model}
                  onChange={(e) => setLocal({ ...local, nanogpt_model: e.target.value })}
                >
                  <option value="">-- select model --</option>
                  {modelList.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Gemini model (static list) */}
          {local.provider === 'gemini' && (
            <div className="provider-config-field">
              <label className="provider-config-label">Model</label>
              <select
                className="provider-config-select"
                value={local.gemini_model}
                onChange={(e) => setLocal({ ...local, gemini_model: e.target.value })}
              >
                {GEMINI_MODELS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}

          {/* API key (nanogpt + gemini only) */}
          {(local.provider === 'nanogpt' || local.provider === 'gemini') && (
            <div className="provider-config-field">
              <label className="provider-config-label">API Key</label>
              <div className="provider-config-key-row">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  className="provider-config-input provider-config-input--key"
                  value={local.provider === 'nanogpt' ? local.nanogpt_api_key : local.gemini_api_key}
                  onChange={(e) => {
                    if (local.provider === 'nanogpt') {
                      setLocal({ ...local, nanogpt_api_key: e.target.value })
                    } else {
                      setLocal({ ...local, gemini_api_key: e.target.value })
                    }
                  }}
                  placeholder="sk-..."
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="provider-config-btn provider-config-btn--icon"
                  onClick={() => setShowApiKey((v) => !v)}
                  title={showApiKey ? 'Hide key' : 'Show key'}
                >
                  {showApiKey ? '🙈' : '👁'}
                </button>
              </div>
            </div>
          )}

          {/* JoyCaption path */}
          {local.provider === 'joycaption' && (
            <div className="provider-config-field">
              <label className="provider-config-label">JoyCaption Path</label>
              <input
                type="text"
                className="provider-config-input"
                value={local.joycaption_path}
                onChange={(e) => setLocal({ ...local, joycaption_path: e.target.value })}
                placeholder="/path/to/JoyCaption"
              />
            </div>
          )}

          {/* Trigger word (always visible) */}
          <div className="provider-config-field">
            <label className="provider-config-label">Trigger Word</label>
            <input
              type="text"
              className="provider-config-input"
              value={localTriggerWord}
              onChange={(e) => setLocalTriggerWord(e.target.value)}
              placeholder="e.g. ohwx person"
            />
            <span className="provider-config-hint">Saved per-project (anchor_word in manifest)</span>
          </div>

          {/* Advanced toggle */}
          <div className="provider-config-field">
            <button
              type="button"
              className="provider-config-btn provider-config-btn--link"
              onClick={() => setIsAdvanced((v) => !v)}
            >
              Advanced {isAdvanced ? '▲' : '▼'}
            </button>
          </div>

          {isAdvanced && (
            <div className="provider-config-field">
              <label className="provider-config-label">Custom Prompt</label>
              <textarea
                className="provider-config-textarea"
                value={local.custom_prompt ?? ''}
                onChange={(e) => setLocal({ ...local, custom_prompt: e.target.value || null })}
                rows={4}
                placeholder="Leave blank to use the default prompt for this provider..."
              />
            </div>
          )}

          {/* Save button */}
          <div className="provider-config-actions">
            <button
              type="button"
              className="provider-config-btn provider-config-btn--save"
              onClick={() => void handleSave()}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
            <button
              type="button"
              className="provider-config-btn provider-config-btn--cancel"
              onClick={() => {
                setLocal({ ...config })
                setLocalTriggerWord(triggerWord)
                setIsExpanded(false)
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
