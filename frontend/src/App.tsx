import { BrowserRouter, Routes, Route } from 'react-router-dom'
import CourierPage from './pages/CourierPage'
import RWACommandCenter from './components/RWACommandCenter'

function App() {
  return (
    <BrowserRouter>
      <main className="min-h-screen bg-[#0a0a0f]">
        <Routes>
          <Route path="/courier/:jobId" element={<CourierPage />} />
          <Route path="*" element={<RWACommandCenter />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
