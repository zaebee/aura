import AgentConsole from './components/AgentConsole'
import MetabolismGraph from './components/MetabolismGraph'

function App() {
  return (
    <main className="min-h-screen p-4 bg-[#0a0a0a] space-y-6">
      <div className="max-w-7xl mx-auto">
        <MetabolismGraph />
      </div>
      <AgentConsole />
    </main>
  )
}

export default App
