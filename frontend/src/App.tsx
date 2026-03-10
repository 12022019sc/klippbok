import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router'
import { useAppStore } from './stores/appStore'
import AppLayout from './components/Layout/AppLayout'
import GalleryPage from './pages/GalleryPage'
import ImportPage from './pages/ImportPage'
import SettingsPage from './pages/SettingsPage'
import CropPage from './pages/CropPage'
import ProcessPage from './pages/ProcessPage'
import CaptionPage from './pages/CaptionPage'
import VideoPage from './pages/VideoPage'
import CleanupPage from './pages/CleanupPage'
import CuratePage from './pages/CuratePage'
import ExportPage from './pages/ExportPage'
import TriagePage from './pages/TriagePage'
import ProjectPickerPage from './pages/ProjectPickerPage'

export default function App() {
  const projectDir = useAppStore((s) => s.projectDir)
  const setProjectDir = useAppStore((s) => s.setProjectDir)

  // On mount, check if a project is already active (e.g. via --project-dir CLI arg)
  useEffect(() => {
    fetch('/api/v1/settings/')
      .then((res) => res.json())
      .then((data) => {
        if (data.project_dir) {
          setProjectDir(data.project_dir)
        }
      })
      .catch(() => {
        // Server not ready yet, will retry on user action
      })
  }, [setProjectDir])

  // No project selected — show the picker (no nav bar, no routing)
  if (!projectDir) {
    return <ProjectPickerPage />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<GalleryPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/cleanup" element={<CleanupPage />} />
          <Route path="/curate" element={<CuratePage />} />
          <Route path="/crop" element={<CropPage />} />
          <Route path="/process" element={<ProcessPage />} />
          <Route path="/caption" element={<CaptionPage />} />
          <Route path="/video" element={<VideoPage />} />
          <Route path="/triage" element={<TriagePage />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
