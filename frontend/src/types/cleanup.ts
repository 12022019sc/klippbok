export interface CleanupClassification {
  item_path: string
  item_id: string
  clip_score: number
  has_face: boolean
  confidence: number
  label: 'keep' | 'review' | 'remove'
}

export interface CleanupProgress {
  current: number
  total: number
  message: string
}

export interface CleanupStartRequest {
  mode: 'text' | 'reference'
  subject_description?: string
  reference_image_ids?: string[]
  clip_threshold?: number
}
