export interface GalleryItem {
  id: string;
  relative_path: string;
  thumbnail_url: string;
  width: number;
  height: number;
  resolution_ok: boolean;
  quality_pass: boolean;
  bucket: string | null;
  is_near_duplicate: boolean;
  duplicate_group_id: string | null;
  caption: string | null;
  media_type: 'image' | 'video';
  full_url: string;
  video_url: string | null;
  duration?: number;
  fps?: number;
  codec?: string;
  triage_classification?: string;
  best_score?: number;
}

export interface GalleryResponse {
  total: number;
  images: GalleryItem[];
}
