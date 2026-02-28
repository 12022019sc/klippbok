import { create } from 'zustand'

interface ImportProgress {
  current: number
  total: number
  message: string
}

interface AppState {
  importOperationId: string | null
  importProgress: ImportProgress | null
  setImportOperationId: (id: string | null) => void
  setImportProgress: (progress: ImportProgress | null) => void
  clearImport: () => void
}

export const useAppStore = create<AppState>((set) => ({
  importOperationId: null,
  importProgress: null,
  setImportOperationId: (id) => set({ importOperationId: id }),
  setImportProgress: (progress) => set({ importProgress: progress }),
  clearImport: () => set({ importOperationId: null, importProgress: null }),
}))
