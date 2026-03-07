import { useLocation } from 'react-router'
import QuickProcess from '../components/Video/QuickProcess'
import AdvancedPanel from '../components/Video/AdvancedPanel'

/**
 * VideoPage provides the Quick Process pipeline as the default view,
 * with the existing Advanced Ingest/Scan/Extract tabs in a collapsible panel below.
 *
 * Navigation state from Gallery pre-populates queued video paths.
 */
export default function VideoPage() {
  const location = useLocation()
  const navState = location.state as { videoPaths?: string[] } | null
  const queuedPaths = navState?.videoPaths ?? null

  return (
    <div className="video-page">
      <h1 className="page-title">Video Pipeline</h1>
      <p className="page-subtitle">
        Process videos to extract reference frames for your training dataset.
      </p>

      <QuickProcess queuedPaths={queuedPaths} />

      <AdvancedPanel />
    </div>
  )
}
