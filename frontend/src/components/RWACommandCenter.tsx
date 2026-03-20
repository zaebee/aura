import { useRef, useState, useCallback, useEffect } from 'react'

type Phase =
  | 'idle'
  | 'scanning'
  | 'scanned'
  | 'compliance_0'
  | 'compliance_1'
  | 'compliance_2'
  | 'ready'
  | 'minting'
  | 'minted'

type ComplianceState = 'pending' | 'active' | 'verified'

interface TerminalLine {
  prefix: string
  text: string
  color: string
}

const COMPLIANCE_LABELS = ['KYC', 'AML Risk', 'Travel Rule']
const COMPLIANCE_BADGES = ['VERIFIED', 'LOW', 'COMPLIANT']

function prefixColor(prefix: string): string {
  if (prefix === 'Aggregator') return '#00f0ff'
  if (prefix === 'Transformer') return '#ffd700'
  if (prefix === 'Membrane') return '#ff00aa'
  return '#9ca3af'
}

export default function RWACommandCenter() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [assetFile, setAssetFile] = useState<File | null>(null)
  const [assetPreview, setAssetPreview] = useState<string | null>(null)
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([
    { prefix: 'System', text: 'Aura Sovereign Vault online. Awaiting RWA asset signal.', color: '#9ca3af' },
  ])
  const [complianceStatus, setComplianceStatus] = useState<ComplianceState[]>([
    'pending', 'pending', 'pending',
  ])
  const [isDragOver, setIsDragOver] = useState(false)

  const terminalRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const pushLine = useCallback((prefix: string, text: string) => {
    setTerminalLines(prev => [...prev, { prefix, text, color: prefixColor(prefix) }])
  }, [])

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [terminalLines])

  const handleAsset = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) return
    const url = URL.createObjectURL(file)
    setAssetFile(file)
    setAssetPreview(url)
    setPhase('scanning')
    setComplianceStatus(['pending', 'pending', 'pending'])
    pushLine('System', 'RWA asset signal detected. Initiating appraisal protocol.')
    pushLine('Aggregator', 'Visual hash received. Routing to Gemma 3 cortex.')

    setTimeout(() => {
      setPhase('scanned')
      pushLine('Transformer', 'Appraising asset... estimated LTV 60%. Confidence 94.2%.')

      // Compliance sequence
      setTimeout(() => {
        setPhase('compliance_0')
        setComplianceStatus(['active', 'pending', 'pending'])
        pushLine('Membrane', 'Initiating KYC verification stream...')

        setTimeout(() => {
          setComplianceStatus(['verified', 'active', 'pending'])
          setPhase('compliance_1')
          pushLine('Membrane', 'KYC: VERIFIED. Identity score 99/100.')

          setTimeout(() => {
            setComplianceStatus(['verified', 'verified', 'active'])
            setPhase('compliance_2')
            pushLine('Membrane', 'AML Risk: LOW. No adverse media matches.')

            setTimeout(() => {
              setComplianceStatus(['verified', 'verified', 'verified'])
              setPhase('ready')
              pushLine('Membrane', 'Travel Rule: COMPLIANT. FATF threshold clear.')
              pushLine('System', 'All compliance gates passed. Vault ready for issuance.')
            }, 1500)
          }, 1500)
        }, 1500)
      }, 0)
    }, 3000)
  }, [pushLine])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleAsset(file)
  }, [handleAsset])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleAsset(file)
  }, [handleAsset])

  const handleMint = useCallback(() => {
    if (phase !== 'ready') return
    setPhase('minting')
    pushLine('Membrane', 'EIP-712 Signature generated. X-Aura-Sig: valid.')
    setTimeout(() => {
      setPhase('minted')
      const code = `AURA-${Math.random().toString(36).slice(2, 6).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`
      pushLine('Connector', `Stablecoin loan minted. Reservation code: ${code}.`)
    }, 1500)
  }, [phase, pushLine])

  const isScanning = phase === 'scanning'
  const isMinted = phase === 'minted'
  const showMint = phase === 'ready' || phase === 'minting' || phase === 'minted'

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: '#0a0a0f', fontFamily: "'Fira Code', monospace" }}
    >
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-4 border-b"
        style={{ borderColor: 'rgba(0,240,255,0.25)', backgroundColor: '#0d0d14' }}
      >
        <div className="flex items-center gap-4">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: '#00f0ff', boxShadow: '0 0 8px #00f0ff' }}
          />
          <h1
            className="text-xl font-semibold tracking-widest uppercase"
            style={{ color: '#00f0ff', textShadow: '0 0 12px rgba(0,240,255,0.6)' }}
          >
            AURA SOVEREIGN VAULT
          </h1>
          <span
            className="text-xs px-2 py-0.5 rounded border tracking-widest"
            style={{ color: '#ffd700', borderColor: 'rgba(255,215,0,0.4)', backgroundColor: 'rgba(255,215,0,0.08)' }}
          >
            RWA COMMAND CENTER v2.6
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: '#9ca3af' }}>
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: '#00ff64', boxShadow: '0 0 6px #00ff64' }}
          />
          <span>AGENT: aura-nucleus-01</span>
        </div>
      </header>

      {/* Main grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-px" style={{ backgroundColor: 'rgba(0,240,255,0.1)' }}>

        {/* Organelle 1 — RWA Scanner */}
        <section className="p-5 flex flex-col gap-4" style={{ backgroundColor: '#0a0a0f' }}>
          <SectionHeader label="01" title="RWA SCANNER" subtitle="Visual Cortex · Gemma 3" />

          {/* Drop zone */}
          <div
            className="relative flex-1 min-h-64 rounded-lg flex items-center justify-center cursor-pointer overflow-hidden"
            style={{
              border: `2px dashed ${isDragOver ? '#ffd700' : '#00f0ff'}`,
              backgroundColor: '#0d0d14',
              transition: 'border-color 0.2s',
            }}
            onDragOver={e => { e.preventDefault(); setIsDragOver(true) }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !assetFile && fileInputRef.current?.click()}
          >
            {/* Pulse glow on idle */}
            {phase === 'idle' && (
              <div
                className="absolute inset-0 rounded-lg animate-pulse-glow"
                style={{ pointerEvents: 'none' }}
              />
            )}

            {/* Asset preview */}
            {assetPreview && (
              <img
                src={assetPreview}
                alt="RWA asset"
                className="absolute inset-0 w-full h-full object-cover"
                style={{
                  filter: isScanning ? 'blur(2px) brightness(0.5)' : isMinted ? 'brightness(0.4)' : 'brightness(0.7)',
                  transition: 'filter 0.5s',
                }}
              />
            )}

            {/* Scanline overlay */}
            {isScanning && (
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background: 'linear-gradient(180deg, transparent 0%, rgba(0,240,255,0.15) 48%, rgba(0,240,255,0.3) 50%, rgba(0,240,255,0.15) 52%, transparent 100%)',
                  backgroundSize: '100% 200%',
                  animation: 'scanline 2s linear infinite',
                }}
              />
            )}

            {/* Idle state */}
            {phase === 'idle' && (
              <div className="relative z-10 text-center px-6">
                <div className="text-4xl mb-3" style={{ color: 'rgba(0,240,255,0.4)' }}>⬡</div>
                <p className="text-sm tracking-wider uppercase" style={{ color: 'rgba(0,240,255,0.7)' }}>
                  DROP ASSET IMAGE
                </p>
                <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  PNG · JPG · WEBP — click or drag
                </p>
              </div>
            )}

            {/* Scanning overlay */}
            {isScanning && (
              <div className="relative z-10 text-center">
                <p
                  className="text-sm tracking-widest uppercase"
                  style={{ color: '#00f0ff', textShadow: '0 0 10px #00f0ff' }}
                >
                  VISUAL CORTEX (Gemma 3) ANALYZING
                  <BlinkingDots />
                </p>
                <div
                  className="mt-3 text-xs"
                  style={{ color: 'rgba(0,240,255,0.6)' }}
                >
                  {assetFile?.name}
                </div>
              </div>
            )}

            {/* Scanned / Ready state */}
            {(phase === 'scanned' || phase.startsWith('compliance') || phase === 'ready') && assetPreview && (
              <div className="relative z-10 flex flex-col items-center gap-2">
                <StatusBadge color="#ffd700" label="ASSET VERIFIED" />
                <span className="text-xs" style={{ color: 'rgba(255,215,0,0.7)' }}>LTV 60% · Confidence 94.2%</span>
              </div>
            )}

            {/* Minting */}
            {phase === 'minting' && (
              <div className="absolute inset-0 flex items-center justify-center z-20" style={{ backgroundColor: 'rgba(10,10,15,0.7)' }}>
                <p className="text-sm tracking-widest" style={{ color: '#ffd700', textShadow: '0 0 12px #ffd700' }}>
                  SIGNING EIP-712<BlinkingDots />
                </p>
              </div>
            )}

            {/* Minted */}
            {isMinted && (
              <div
                className="absolute inset-0 flex flex-col items-center justify-center z-20"
                style={{ backgroundColor: 'rgba(0,10,5,0.85)' }}
              >
                <div
                  className="text-5xl mb-2"
                  style={{ color: '#00ff64', textShadow: '0 0 20px #00ff64' }}
                >
                  ✓
                </div>
                <p
                  className="text-sm tracking-widest uppercase"
                  style={{ color: '#00ff64', textShadow: '0 0 10px #00ff64' }}
                >
                  LOAN MINTED
                </p>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
        </section>

        {/* Organelle 2 — Compliance Matrix */}
        <section className="p-5 flex flex-col gap-4" style={{ backgroundColor: '#0a0a0f' }}>
          <SectionHeader label="02" title="COMPLIANCE MATRIX" subtitle="Membrane · ERC-8004 Guards" />

          <div className="flex flex-col gap-3">
            {COMPLIANCE_LABELS.map((label, i) => (
              <ComplianceRow
                key={label}
                label={label}
                badge={COMPLIANCE_BADGES[i]}
                status={complianceStatus[i]}
              />
            ))}
          </div>

          {/* Vault info */}
          <div
            className="mt-auto rounded-lg p-4 text-xs space-y-2"
            style={{ backgroundColor: '#0d0d14', border: '1px solid rgba(0,240,255,0.12)' }}
          >
            <div className="flex justify-between">
              <span style={{ color: '#9ca3af' }}>VAULT TYPE</span>
              <span style={{ color: '#00f0ff' }}>RWA-BACKED STABLECOIN</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: '#9ca3af' }}>PROTOCOL</span>
              <span style={{ color: '#ffd700' }}>x402 / ERC-8004</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: '#9ca3af' }}>CHAIN</span>
              <span style={{ color: '#ff00aa' }}>ASI Alliance Testnet</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: '#9ca3af' }}>AGENT FRAMEWORK</span>
              <span style={{ color: '#00f0ff' }}>uAgents 3.x · ATCG-M</span>
            </div>
          </div>
        </section>
      </div>

      {/* Organelle 3 — NATS Bloodstream Terminal */}
      <section
        className="border-t"
        style={{ borderColor: 'rgba(0,240,255,0.15)', backgroundColor: '#0d0d14' }}
      >
        <div className="flex items-center gap-3 px-5 py-2 border-b" style={{ borderColor: 'rgba(0,240,255,0.1)' }}>
          <SectionHeader label="03" title="NATS BLOODSTREAM TERMINAL" subtitle="Live agent signal stream" inline />
        </div>
        <div
          ref={terminalRef}
          className="px-5 py-3 overflow-y-auto text-xs leading-relaxed"
          style={{ height: '160px', fontFamily: "'Fira Code', monospace" }}
        >
          {terminalLines.map((line, i) => (
            <div key={i} className="flex gap-2">
              <span style={{ color: 'rgba(255,255,255,0.25)' }}>{'>'}</span>
              <span style={{ color: line.color }}>
                [{line.prefix}]
              </span>
              <span style={{ color: 'rgba(255,255,255,0.75)' }}>{line.text}</span>
              {i === terminalLines.length - 1 && (
                <span
                  className="animate-blink-cursor"
                  style={{ color: '#00f0ff', marginLeft: '2px' }}
                >
                  ▌
                </span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Organelle 4 — Settlement Action */}
      <section
        className="border-t p-5"
        style={{
          borderColor: 'rgba(0,240,255,0.15)',
          backgroundColor: '#0a0a0f',
          opacity: showMint ? 1 : 0,
          pointerEvents: showMint ? 'auto' : 'none',
          transition: 'opacity 0.5s ease-in-out',
        }}
      >
        <button
          onClick={handleMint}
          disabled={phase !== 'ready'}
          className="w-full py-4 text-sm font-semibold tracking-widest uppercase rounded-lg"
          style={{
            fontFamily: "'Fira Code', monospace",
            background: phase === 'minted'
              ? 'linear-gradient(90deg, #00ff64, #00f0ff)'
              : 'linear-gradient(90deg, #ffd700, #00f0ff)',
            color: '#0a0a0f',
            cursor: phase === 'ready' ? 'pointer' : 'default',
            animation: phase === 'ready' ? 'mint-pulse 1.5s ease-in-out infinite' : 'none',
            transition: 'background 0.5s',
          }}
        >
          {phase === 'minting'
            ? '[ SIGNING... ]'
            : phase === 'minted'
            ? '[ LOAN MINTED — RESERVATION ACTIVE ]'
            : '[ MINT STABLECOIN LOAN ]'}
        </button>
      </section>
    </div>
  )
}

function SectionHeader({
  label,
  title,
  subtitle,
  inline = false,
}: {
  label: string
  title: string
  subtitle: string
  inline?: boolean
}) {
  return (
    <div className={`flex ${inline ? 'items-center gap-3' : 'items-start gap-3'}`}>
      <span
        className="text-xs font-bold px-1.5 py-0.5 rounded"
        style={{ color: '#0a0a0f', backgroundColor: '#00f0ff', fontFamily: "'Fira Code', monospace" }}
      >
        {label}
      </span>
      <div>
        <p
          className="text-xs font-semibold tracking-widest uppercase"
          style={{ color: '#00f0ff' }}
        >
          {title}
        </p>
        {!inline && (
          <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
            {subtitle}
          </p>
        )}
      </div>
    </div>
  )
}

function ComplianceRow({
  label,
  badge,
  status,
}: {
  label: string
  badge: string
  status: ComplianceState
}) {
  const isVerified = status === 'verified'
  const isActive = status === 'active'

  return (
    <div
      className="flex items-center justify-between px-4 py-3 rounded-lg"
      style={{
        backgroundColor: '#0d0d14',
        border: `1px solid ${isVerified ? 'rgba(0,255,100,0.3)' : isActive ? 'rgba(0,240,255,0.3)' : 'rgba(255,255,255,0.06)'}`,
        transition: 'border-color 0.4s',
      }}
    >
      <div className="flex items-center gap-3">
        {/* LED */}
        <div
          className="w-3 h-3 rounded-full flex-shrink-0"
          style={{
            backgroundColor: isVerified ? '#00ff64' : isActive ? '#00f0ff' : '#2d2d3a',
            boxShadow: isVerified
              ? '0 0 8px 2px rgba(0,255,100,0.8)'
              : isActive
              ? '0 0 8px 2px rgba(0,240,255,0.8)'
              : 'none',
            animation: isVerified ? 'led-on 0.4s ease-out forwards' : 'none',
            transition: 'background-color 0.3s, box-shadow 0.3s',
          }}
        />
        <span
          className="text-xs tracking-wider uppercase"
          style={{ color: isVerified ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.35)' }}
        >
          {label}
        </span>
      </div>

      <span
        className="text-xs px-2 py-0.5 rounded tracking-widest"
        style={{
          color: isVerified ? '#00ff64' : isActive ? '#00f0ff' : '#2d2d3a',
          backgroundColor: isVerified
            ? 'rgba(0,255,100,0.1)'
            : isActive
            ? 'rgba(0,240,255,0.1)'
            : 'rgba(255,255,255,0.04)',
          border: `1px solid ${isVerified ? 'rgba(0,255,100,0.3)' : isActive ? 'rgba(0,240,255,0.3)' : 'rgba(255,255,255,0.08)'}`,
          transition: 'all 0.3s',
          fontFamily: "'Fira Code', monospace",
        }}
      >
        {isActive ? 'CHECKING...' : isVerified ? badge : '------'}
      </span>
    </div>
  )
}

function StatusBadge({ color, label }: { color: string; label: string }) {
  return (
    <span
      className="text-xs px-3 py-1 rounded tracking-widest uppercase"
      style={{
        color,
        border: `1px solid ${color}`,
        backgroundColor: `${color}18`,
        textShadow: `0 0 8px ${color}`,
        fontFamily: "'Fira Code', monospace",
      }}
    >
      {label}
    </span>
  )
}

function BlinkingDots() {
  const [dots, setDots] = useState('.')
  useEffect(() => {
    const id = setInterval(() => {
      setDots(d => (d.length >= 3 ? '.' : d + '.'))
    }, 400)
    return () => clearInterval(id)
  }, [])
  return <span>{dots}</span>
}
