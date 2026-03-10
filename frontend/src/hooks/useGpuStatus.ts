import { useQuery } from '@tanstack/react-query'

interface TrainStatusResponse {
  onetrainer_detected: boolean
  onetrainer_path: string | null
  training_active: boolean
  gpu_vram_used_mb: number | null
  gpu_busy: boolean
}

interface GpuStatus {
  gpuBusy: boolean
  trainingActive: boolean
  vramUsedMb: number | null
}

/**
 * Shared hook for polling GPU busy status via TanStack Query.
 *
 * Polls GET /api/v1/export/train/status every 30 seconds.
 * Returns gpuBusy, trainingActive, and vramUsedMb.
 *
 * Used by CleanupPage, CuratePage, TriagePage, and TrainingPanel to
 * disable GPU-intensive actions during active training.
 */
export function useGpuStatus(): GpuStatus {
  const { data } = useQuery<TrainStatusResponse>({
    queryKey: ['train-status'],
    queryFn: async () => {
      const res = await fetch('/api/v1/export/train/status')
      if (!res.ok) throw new Error('Failed to fetch train status')
      return res.json() as Promise<TrainStatusResponse>
    },
    refetchInterval: 30000,
    staleTime: 25000,
  })

  return {
    gpuBusy: data?.gpu_busy ?? false,
    trainingActive: data?.training_active ?? false,
    vramUsedMb: data?.gpu_vram_used_mb ?? null,
  }
}
