import { useEffect, useRef, useState } from 'react'

export interface FrameCandidate {
  path: string
  score: number
  rank: number
}

export interface ExtractedFrame {
  video_path: string
  frame_path: string
  candidates?: FrameCandidate[]
}

export interface ProcessState {
  stage: string
  current: number
  total: number
  message: string
  error: string | null
  isComplete: boolean
  extractedFrames: ExtractedFrame[]
  processedVideoPaths: string[]
  skippedVideos: Array<{ path: string; reason: string }>
}

const INITIAL_STATE: ProcessState = {
  stage: '',
  current: 0,
  total: 0,
  message: '',
  error: null,
  isComplete: false,
  extractedFrames: [],
  processedVideoPaths: [],
  skippedVideos: [],
}

/**
 * useProcessEvents subscribes to the SSE progress stream for a video process operation.
 *
 * Creates an EventSource connection to /api/v1/video/process/{operationId}/events when
 * operationId is non-null. Uses named event listeners for "process_progress", "process_done",
 * "process_error".
 */
export function useProcessEvents(operationId: string | null): ProcessState {
  const [state, setState] = useState<ProcessState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!operationId) {
      setState(INITIAL_STATE)
      return
    }

    setState(INITIAL_STATE)

    const url = `/api/v1/video/process/${operationId}/events`
    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('process_progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as {
          stage?: string; current?: number; total?: number; message?: string
        }
        setState((prev) => ({
          ...prev,
          stage: data.stage ?? prev.stage,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? prev.message,
        }))
      } catch {
        // Ignore malformed events
      }
    })

    es.addEventListener('process_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as {
          current?: number; total?: number; message?: string
          extracted_frames?: ExtractedFrame[]
          processed_video_paths?: string[]
          skipped_videos?: Array<{ path: string; reason: string }>
        }
        setState((prev) => ({
          ...prev,
          current: data.current ?? prev.current,
          total: data.total ?? prev.total,
          message: data.message ?? 'Processing complete',
          isComplete: true,
          error: null,
          extractedFrames: data.extracted_frames ?? [],
          processedVideoPaths: data.processed_video_paths ?? [],
          skippedVideos: data.skipped_videos ?? [],
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          message: 'Processing complete',
          isComplete: true,
          error: null,
        }))
      }
      es.close()
      esRef.current = null
    })

    es.addEventListener('process_error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { error?: string; message?: string }
        setState((prev) => ({
          ...prev,
          error: data.error ?? data.message ?? 'Processing failed',
          isComplete: false,
        }))
      } catch {
        setState((prev) => ({
          ...prev,
          error: 'Processing failed',
          isComplete: false,
        }))
      }
      es.close()
      esRef.current = null
    })

    es.onerror = () => {
      es.close()
      esRef.current = null
      setState((prev) => ({
        ...prev,
        error: 'Process connection lost. The SSE connection was interrupted.',
        isComplete: false,
      }))
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [operationId])

  return state
}
