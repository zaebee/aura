import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AgentConsole from './components/AgentConsole'
import CourierPage from './pages/CourierPage'

function App() {
  return (
    <BrowserRouter>
      <main className="min-h-screen bg-[#0a0a0a]">
        <Routes>
          <Route path="/courier/:jobId" element={<CourierPage />} />
          <Route path="*" element={<div className="p-4"><AgentConsole /></div>} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
