export interface TriageScore {
  item_id: string
  best_score: number
  classification: 'match' | 'borderline' | 'no_match'
  matches: { concept_name: string; score: number }[]
}

export interface ConceptRef {
  name: string
  concept_type: string
  image_path: string
  folder_name: string
}

export interface FaceCluster {
  cluster_id: number
  image_paths: string[]
  suggested_name: string | null
  primary_reference: string | null
}

export interface TriageProgress {
  current: number
  total: number
  message: string
}

export interface FaceProgress {
  current: number
  total: number
  eta_seconds: number
  message: string
}
