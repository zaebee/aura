import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { validateEVMAddress } from '../hive/membrane/courier'
import { submitCourierProof } from '../hive/connector/courier'
import type { CourierResponse } from '../hive/connector/courier'

type PageState = 'idle' | 'scanning' | 'success' | 'error'

export default function CourierPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [imageB64, setImageB64] = useState<string | null>(null)
  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [wallet, setWallet] = useState('')
  const [walletTouched, setWalletTouched] = useState(false)
  const [pageState, setPageState] = useState<PageState>('idle')
  const [result, setResult] = useState<CourierResponse | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Derived — no separate state needed; computed each render
  const walletValidation = wallet ? validateEVMAddress(wallet) : null
  const walletError = walletTouched && walletValidation && !walletValidation.valid
    ? (walletValidation.error ?? null)
    : null
  const walletValid = walletValidation?.valid ?? false

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.readAsDataURL(file)
    reader.onload = () => {
      const dataUrl = reader.result as string
      setImageSrc(dataUrl)
      setImageB64(dataUrl.split(',')[1])
    }
  }

  async function handlePaste() {
    try {
      const text = await navigator.clipboard.readText()
      setWallet(text)
      setWalletTouched(true)
    } catch {
      // Clipboard denied — treat as touched with empty wallet so error shows on next interaction
      setWalletTouched(true)
    }
  }

  const canSubmit = !!imageB64 && walletValid && pageState === 'idle'
  const canSubmit = !!imageB64 && walletValid && pageState === 'idle'

  async function handleSubmit() {
    if (!canSubmit || !imageB64) return
    setPageState('scanning')
    setSubmitError(null)
    try {
      const response = await submitCourierProof({
        image: imageB64,
        wallet_address: wallet,
        job_id: jobId ?? '',
        timestamp: new Date().toISOString(),
      })
      setResult(response)
      setPageState(response.status === 'verified' ? 'success' : 'error')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Unknown error')
      setPageState('error')
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white flex flex-col items-center px-4 py-8">
      <style>{`
        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 8px #00f5ff44, 0 0 24px #00f5ff22; border-color: #00f5ff66; }
          50% { box-shadow: 0 0 24px #00f5ffaa, 0 0 48px #00f5ff55; border-color: #00f5ff; }
        }
        .scanning-pulse { animation: pulse-glow 1.2s ease-in-out infinite; }
      `}</style>

      <div className="w-full max-w-md flex flex-col gap-6">
        {/* Header */}
        <header className="flex flex-col gap-2">
          <h1 className="text-xl font-bold tracking-widest text-[#00f5ff] uppercase">
            Aura Hive Dispatch
          </h1>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 uppercase tracking-wider">Job</span>
            <span className="bg-[#1a1a2e] border border-[#00f5ff33] text-[#00f5ff] text-xs font-mono px-3 py-1 rounded-full">
              {jobId ?? '—'}
            </span>
          </div>
        </header>

        {/* Photo Capture */}
        <section className="flex flex-col gap-3">
          <label className="text-xs uppercase tracking-widest text-gray-400">
            Proof of Delivery
          </label>

          <input
            id="photo-capture"
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={handleFileChange}
          />

          <label
            htmlFor="photo-capture"
            className={`
              flex items-center justify-center gap-3
              min-h-[72px] w-full rounded-xl border-2 cursor-pointer
              font-semibold text-base transition-all select-none
              ${imageB64
                ? 'border-[#00f5ff] bg-[#00f5ff11] text-[#00f5ff]'
                : 'border-[#333] bg-[#111] text-gray-300 hover:border-[#00f5ff66] hover:text-white'}
            `}
          >
            {imageB64 ? '✓ Photo Ready' : '📷 Capture Proof'}
          </label>

          {imageSrc && (
            <img
              src={imageSrc}
              alt="Delivery proof preview"
              className="w-full max-h-52 object-cover rounded-xl border border-[#00f5ff33]"
            />
          )}
        </section>

        {/* Wallet Input */}
        <section className="flex flex-col gap-3">
          <label className="text-xs uppercase tracking-widest text-gray-400">
            Wallet Address
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={wallet}
              onChange={e => { setWallet(e.target.value); setWalletTouched(true) }}
              placeholder="0x..."
              className={`
                flex-1 bg-[#111] border rounded-xl px-4 py-4 font-mono text-sm outline-none
                transition-colors min-h-[56px]
                ${walletError ? 'border-red-500 text-red-300' : 'border-[#333] text-white focus:border-[#00f5ff]'}
              `}
            />
            <button
              type="button"
              onClick={handlePaste}
              className="bg-[#1a1a2e] border border-[#333] text-gray-300 rounded-xl px-4 text-sm
                         hover:border-[#00f5ff66] hover:text-[#00f5ff] transition-colors min-h-[56px]"
            >
              Paste
            </button>
          </div>
          {walletError && (
            <p className="text-red-400 text-xs mt-1">{walletError}</p>
          )}
        </section>

        {/* Submit */}
        {pageState === 'idle' && (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`
              min-h-[72px] w-full rounded-xl font-bold text-base tracking-wider uppercase
              transition-all border-2
              ${canSubmit
                ? 'bg-[#00f5ff] text-[#0a0a0a] border-[#00f5ff] hover:bg-[#00d4e0] active:scale-95'
                : 'bg-transparent text-gray-600 border-[#222] cursor-not-allowed'}
            `}
          >
            Submit Proof
          </button>
        )}

        {/* Scanning Overlay */}
        {pageState === 'scanning' && (
          <div className="flex flex-col items-center gap-4 py-6">
            <div className="scanning-pulse w-16 h-16 rounded-full border-2 border-[#00f5ff66] flex items-center justify-center">
              <div className="w-8 h-8 rounded-full bg-[#00f5ff22]" />
            </div>
            <p className="text-[#00f5ff] font-mono text-sm tracking-widest uppercase">
              Scanning...
            </p>
          </div>
        )}

        {/* Result Panel */}
        {pageState === 'success' && result && (
          <div className="rounded-xl border border-[#00f5ff] bg-[#00f5ff0a] px-6 py-6 flex flex-col gap-3">
            <p className="text-[#00f5ff] font-bold text-lg">Verified ✓</p>
            {result.tx && (
              <div className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-widest text-gray-500">Transaction</span>
                <span className="font-mono text-xs text-gray-300 break-all">{result.tx}</span>
              </div>
            )}
            {result.message && (
              <p className="text-sm text-gray-400">{result.message}</p>
            )}
          </div>
        )}

        {pageState === 'error' && (
          <div className="rounded-xl border border-red-800 bg-red-950/30 px-6 py-6 flex flex-col gap-3">
            <p className="text-red-400 font-bold text-lg">Rejected</p>
            <p className="text-sm text-gray-400">
              {submitError ?? result?.message ?? 'Proof could not be verified. Please try again.'}
            </p>
            <button
              type="button"
              onClick={() => { setPageState('idle'); setResult(null); setSubmitError(null) }}
              className="mt-2 min-h-[56px] w-full rounded-xl border border-[#333] text-gray-300
                         hover:border-[#00f5ff66] hover:text-[#00f5ff] transition-colors text-sm font-semibold"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
