export type CurationMode = 'character' | 'style'

export interface SignalScores {
  face_confidence: number
  face_area_ratio: number
  identity_similarity: number
  quality_score: number
  aesthetic_score: number
  sharpness_whole: number
  sharpness_face: number
  occlusion_score: number
  pose_vector: number[]
  is_duplicate: boolean
}

export interface ImageScore {
  image_id: string
  relative_path: string
  signals: SignalScores
  composite_score: number
  mode: CurationMode
}

export interface CurationConfig {
  mode: CurationMode
  target_count: number
  quality_floor_pct: number
  face_confidence_threshold: number
  pose_angle_limit: number
  identity_threshold: number
  reference_image_id: string | null
  model_profile: string | null
}

export interface DiversityMetrics {
  pose_variety: number
  unique_backgrounds: number
  expression_spread: number
}

export interface PipelineSummary {
  total_scanned: number
  passed_quality: number
  selected: number
  diversity_metrics: DiversityMetrics | null
}

export interface CurationResult {
  config: CurationConfig
  scores: Record<string, ImageScore>
  selected_ids: string[]
  pinned_ids: string[]
  excluded_ids: string[]
  summary: PipelineSummary
  timestamp: string
}

// Model profile target count defaults (locked decisions from context doc)
export const MODEL_TARGET_DEFAULTS: Record<string, number> = {
  sd15: 40,
  sdxl: 80,
  flux: 100,
  pony: 70,
  custom: 60,
}

export interface CurationProgress {
  stage: string
  current: number
  total: number
}
