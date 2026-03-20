import { AgentWallet } from '../hive/connector/wallet'

export interface VisionResult {
  source: 'vision-cortex'
  make: string
  model: string
  year: number
  color: string
  estimated_price: number
  confidence_score: number
  id?: string
  name?: string
}

export interface NegotiateResult {
  session_token: string
  status: 'accepted' | 'countered' | 'rejected' | 'uiRequired'
  valid_until: number
  data?: {
    final_price?: number
    reservation_code?: string
    payment_instructions?: { deal_id: string; [k: string]: unknown }
    proposed_price?: number
    message?: string
  }
  action_required?: { template: string; context: Record<string, string> }
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

let _wallet: AgentWallet | null = null
function getWallet(): AgentWallet {
  if (!_wallet) _wallet = new AgentWallet()
  return _wallet
}

const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

function mockVision(): VisionResult {
  return {
    source: 'vision-cortex',
    make: 'Rolex',
    model: 'Submariner',
    year: 2021,
    color: 'Black',
    estimated_price: 9500,
    confidence_score: 0.942,
  }
}

function mockNegotiate(): NegotiateResult {
  return {
    session_token: 'mock',
    status: 'accepted',
    valid_until: Math.floor(Date.now() / 1000) + 3600,
    data: { reservation_code: 'MOCK-0001' },
  }
}

export async function analyzeVision(file: File, signal?: AbortSignal): Promise<VisionResult> {
  if (import.meta.env.VITE_MOCK_RWA === 'true') {
    await delay(2500)
    return mockVision()
  }

  const wallet = getWallet()

  const formData = new FormData()
  formData.append('files', file)

  // Serialize multipart to get exact bytes + boundary
  const tempReq = new Request('http://x', { method: 'POST', body: formData })
  const ct = tempReq.headers.get('Content-Type')!
  const blob = await tempReq.blob()

  const hashBuffer = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  const bodyHash = Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')

  const authHeaders = await wallet.signRawHash('POST', '/vision/analyze', bodyHash)

  const resp = await fetch(`${wallet.getGatewayUrl()}/vision/analyze`, {
    method: 'POST',
    headers: { ...authHeaders, 'Content-Type': ct },
    body: blob,
    signal,
  })

  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const json = await resp.json()
      if (json.detail) detail = json.detail
    } catch {}
    throw new ApiError(resp.status, detail)
  }

  return (await resp.json()) as VisionResult
}

export async function negotiateItem(
  itemId: string,
  bidAmount: number,
  _signal?: AbortSignal
): Promise<NegotiateResult> {
  if (import.meta.env.VITE_MOCK_RWA === 'true') {
    await delay(1000)
    return mockNegotiate()
  }

  const wallet = getWallet()
  const body = {
    request_id: `req_${Date.now()}`,
    item_id: itemId,
    bid_amount: bidAmount,
    currency_code: 'USD',
    agent_did: wallet.getAgentId(),
  }

  let resp: Response
  try {
    resp = await wallet.fetchWithAuth('/negotiate', 'POST', body)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new ApiError(0, msg)
  }

  // fetchWithAuth throws on !ok, but re-wrap with ApiError for callers
  return (await resp.json()) as NegotiateResult
}
