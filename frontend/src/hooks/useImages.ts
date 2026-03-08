import { useQuery } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import type { GalleryItem, GalleryResponse, GallerySortKey, GallerySortDir } from '../types/image'

async function fetchImages(): Promise<GalleryResponse> {
  const response = await fetch('/api/v1/images/')
  if (!response.ok) {
    throw new Error(`Failed to fetch images: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<GalleryResponse>
}

function applyFilter(items: GalleryItem[], filter: 'all' | 'images' | 'videos'): GalleryItem[] {
  if (filter === 'images') return items.filter((item) => item.media_type === 'image')
  if (filter === 'videos') return items.filter((item) => item.media_type === 'video')
  return items
}

function applySort(items: GalleryItem[], key: GallerySortKey, dir: GallerySortDir): GalleryItem[] {
  const sorted = [...items]
  const mul = dir === 'asc' ? 1 : -1

  sorted.sort((a, b) => {
    switch (key) {
      case 'name':
        return mul * a.relative_path.localeCompare(b.relative_path)
      case 'quality':
        // Sort by blur_score: higher = sharper. Nulls go last.
        return mul * compareNullable(a.blur_score, b.blur_score)
      case 'size':
        return mul * compareNullable(a.file_size, b.file_size)
      case 'dimensions':
        return mul * ((a.width * a.height) - (b.width * b.height))
      case 'type':
        return mul * (a.format ?? '').localeCompare(b.format ?? '')
      case 'date':
        return mul * (a.created_at ?? '').localeCompare(b.created_at ?? '')
      default:
        return 0
    }
  })

  return sorted
}

function compareNullable(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  return a - b
}

export function useImages() {
  const galleryFilter = useAppStore((s) => s.galleryFilter)
  const gallerySortKey = useAppStore((s) => s.gallerySortKey)
  const gallerySortDir = useAppStore((s) => s.gallerySortDir)

  const { data, isLoading, error, refetch } = useQuery<GalleryResponse, Error>({
    queryKey: ['images'],
    queryFn: fetchImages,
  })

  // Apply client-side gallery filter and sort
  const filteredData: GalleryResponse | undefined = data
    ? {
        total: data.total,
        images: applySort(
          applyFilter(data.images, galleryFilter),
          gallerySortKey,
          gallerySortDir,
        ),
      }
    : undefined

  return { data: filteredData, rawData: data, isLoading, error, refetch }
}
