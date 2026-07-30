import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeToggle } from './components/ThemeToggle'
import { useTheme } from './hooks/useTheme'
import { DatasetList } from './pages/DatasetList'
import { Report } from './pages/Report'

function App() {
  const { theme, toggle } = useTheme()

  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <div className="fixed top-4 right-4 z-50">
          <ThemeToggle theme={theme} onToggle={toggle} />
        </div>
        <Routes>
          <Route path="/" element={<DatasetList />} />
          <Route path="/report/:runId" element={<Report />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App
