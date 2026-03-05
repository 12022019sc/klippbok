import { useQuery } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import type { GalleryItem, GalleryResponse } from '../types/image'

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

export function useImages() {
  const galleryFilter = useAppStore((s) => s.galleryFilter)

  const { data, isLoading, error, refetch } = useQuery<GalleryResponse, Error>({
    queryKey: ['images'],
    queryFn: fetchImages,
  })

  // Apply client-side gallery filter based on media type
  const filteredData: GalleryResponse | undefined = data
    ? {
        total: data.total,
        images: applyFilter(data.images, galleryFilter),
      }
    : undefined

  return { data: filteredData, isLoading, error, refetch }
}
