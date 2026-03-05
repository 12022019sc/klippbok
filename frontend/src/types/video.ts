export interface IngestConfig {
  video_path?: string
  directory_path?: string
  fps: number        // default 16
  resolution: number // default 720
  threshold: number  // default 27.0
  max_frames?: number
}

export interface IngestProgress {
  stage: string
  current: number
  total: number
  message: string
}

export interface ExtractProgress {
  current: number
  total: number
  message: string
}

export interface ScanResultItem {
  filename: string
  width: number
  height: number
  fps: number
  duration: number
  codec: string
  frame_count: number
  issues: string[]
}

export interface ScanResult {
  clips: ScanResultItem[]
  total: number
}

export interface VideoClip {
  id: string
  relative_path: string
  thumbnail_url: string
  duration: number
  fps: number
  width: number
  height: number
  frame_count: number
}
