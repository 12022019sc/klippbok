import { create } from 'zustand'
import type { CropState } from '../types/crop'
import type { TriageScore } from '../types/triage'

interface ImportProgress {
  current: number
  total: number
  message: string
}

interface AppState {
  // --- existing fields ---
  projectDir: string | null
  importOperationId: string | null
  importProgress: ImportProgress | null
  setProjectDir: (dir: string | null) => void
  setImportOperationId: (id: string | null) => void
  setImportProgress: (progress: ImportProgress | null) => void
  clearImport: () => void

  // --- selection mode ---
  selectionMode: boolean
  selectedImageIds: Set<string>
  toggleSelectionMode: () => void
  toggleImageSelection: (id: string) => void
  selectAll: (ids: string[]) => void
  deselectAll: () => void
  selectByFilter: (ids: string[]) => void

  // --- crop state ---
  cropStates: Map<string, CropState>
  setCropState: (id: string, state: CropState) => void
  removeCropState: (id: string) => void
  clearCropStates: () => void

  // --- gallery filter ---
  galleryFilter: 'all' | 'images' | 'videos'
  setGalleryFilter: (filter: 'all' | 'images' | 'videos') => void

  // --- triage results ---
  triageResults: Record<string, TriageScore>
  triageThreshold: number
  setTriageResults: (results: Record<string, TriageScore>) => void
  setTriageThreshold: (t: number) => void
  clearTriageResults: () => void
}

export const useAppStore = create<AppState>((set) => ({
  // --- existing state ---
  projectDir: null,
  importOperationId: null,
  importProgress: null,
  setProjectDir: (dir) => set({ projectDir: dir }),
  setImportOperationId: (id) => set({ importOperationId: id }),
  setImportProgress: (progress) => set({ importProgress: progress }),
  clearImport: () => set({ importOperationId: null, importProgress: null }),

  // --- selection mode state ---
  selectionMode: false,
  selectedImageIds: new Set<string>(),

  toggleSelectionMode: () =>
    set((state) => ({
      selectionMode: !state.selectionMode,
      // clear selection when exiting selection mode
      selectedImageIds: state.selectionMode ? new Set<string>() : state.selectedImageIds,
    })),

  toggleImageSelection: (id) =>
    set((state) => {
      const next = new Set(state.selectedImageIds)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return { selectedImageIds: next }
    }),

  selectAll: (ids) =>
    set({ selectedImageIds: new Set(ids) }),

  deselectAll: () =>
    set({ selectedImageIds: new Set<string>() }),

  selectByFilter: (ids) =>
    set({ selectedImageIds: new Set(ids) }),

  // --- crop state ---
  cropStates: new Map<string, CropState>(),

  setCropState: (id, state) =>
    set((prev) => ({
      cropStates: new Map([...prev.cropStates, [id, state]]),
    })),

  removeCropState: (id) =>
    set((prev) => {
      const next = new Map(prev.cropStates)
      next.delete(id)
      return { cropStates: next }
    }),

  clearCropStates: () =>
    set({ cropStates: new Map<string, CropState>() }),

  // --- gallery filter state ---
  galleryFilter: 'all',
  setGalleryFilter: (filter) => set({ galleryFilter: filter }),

  // --- triage results state ---
  triageResults: {},
  triageThreshold: 0.70,
  setTriageResults: (results) => set({ triageResults: results }),
  setTriageThreshold: (t) => set({ triageThreshold: t }),
  clearTriageResults: () => set({ triageResults: {} }),
}))
