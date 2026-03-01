import { useQuery } from '@tanstack/react-query'
import type { GalleryResponse } from '../types/image'

async function fetchImages(): Promise<GalleryResponse> {
  const response = await fetch('/api/v1/images/')
  if (!response.ok) {
    throw new Error(`Failed to fetch images: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<GalleryResponse>
}

export function useImages() {
  const { data, isLoading, error, refetch } = useQuery<GalleryResponse, Error>({
    queryKey: ['images'],
    queryFn: fetchImages,
  })

  return { data, isLoading, error, refetch }
}
