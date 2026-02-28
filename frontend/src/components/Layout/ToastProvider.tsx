import { Toaster } from 'sonner'

/**
 * ToastProvider mounts the Sonner Toaster at the app root.
 * Renders in the bottom-right corner with dark theme and rich colors.
 */
export default function ToastProvider() {
  return <Toaster position="bottom-right" theme="dark" richColors />
}
