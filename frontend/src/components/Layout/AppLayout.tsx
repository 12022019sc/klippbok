import { useEffect, useRef } from 'react'
import { Outlet } from 'react-router'
import { toast } from 'sonner'
import NavBar from './NavBar'
import { useAppStore } from '../../stores/appStore'

/**
 * AppLayout wraps all pages with the NavBar and a persistent import progress
 * toast that remains visible while navigating between pages.
 *
 * The toast.loading() call uses a stable ID ("import-progress") so updates
 * replace the same toast instead of stacking new ones.
 */
export default function AppLayout() {
  const importOperationId = useAppStore((s) => s.importOperationId)
  const importProgress = useAppStore((s) => s.importProgress)
  const toastIdRef = useRef<string | number | null>(null)

  useEffect(() => {
    if (importOperationId) {
      const message = importProgress?.message ?? 'Import in progress...'
      const description =
        importProgress && importProgress.total > 0
          ? `${importProgress.current} / ${importProgress.total} images`
          : undefined

      if (toastIdRef.current === null) {
        // Create a new persistent loading toast
        toastIdRef.current = toast.loading(message, {
          id: 'import-progress',
          description,
        })
      } else {
        // Update the existing toast in place
        toast.loading(message, {
          id: 'import-progress',
          description,
        })
      }
    } else {
      // Import finished or was cleared -- dismiss the persistent toast
      if (toastIdRef.current !== null) {
        toast.dismiss('import-progress')
        toastIdRef.current = null
      }
    }
  }, [importOperationId, importProgress])

  return (
    <>
      <NavBar />
      <div className="page-container">
        <Outlet />
      </div>
    </>
  )
}
