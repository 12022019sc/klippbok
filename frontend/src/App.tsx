import { BrowserRouter, Routes, Route } from 'react-router'
import AppLayout from './components/Layout/AppLayout'
import GalleryPage from './pages/GalleryPage'
import ImportPage from './pages/ImportPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<GalleryPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
