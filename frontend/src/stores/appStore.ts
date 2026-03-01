import { create } from 'zustand'

interface ImportProgress {
  current: number
  total: number
  message: string
}

interface AppState {
  projectDir: string | null
  importOperationId: string | null
  importProgress: ImportProgress | null
  setProjectDir: (dir: string | null) => void
  setImportOperationId: (id: string | null) => void
  setImportProgress: (progress: ImportProgress | null) => void
  clearImport: () => void
}

export const useAppStore = create<AppState>((set) => ({
  projectDir: null,
  importOperationId: null,
  importProgress: null,
  setProjectDir: (dir) => set({ projectDir: dir }),
  setImportOperationId: (id) => set({ importOperationId: id }),
  setImportProgress: (progress) => set({ importProgress: progress }),
  clearImport: () => set({ importOperationId: null, importProgress: null }),
}))
