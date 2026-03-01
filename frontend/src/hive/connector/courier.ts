const API_BASE = import.meta.env.VITE_API_GATEWAY_URL || '/api/v1'
const MOCK_MODE = import.meta.env.VITE_MOCK_COURIER === 'true'

export interface CourierPayload {
  image: string          // base64
  wallet_address: string
  job_id: string
  timestamp: string      // ISO 8601
}

export interface CourierResponse {
  status: 'verified' | 'rejected'
  tx?: string
  message?: string
}

export async function submitCourierProof(payload: CourierPayload): Promise<CourierResponse> {
  if (MOCK_MODE) {
    await new Promise(r => setTimeout(r, 2000))
    return { status: 'verified', tx: '0x123abc...' }
  }
  const res = await fetch(`${API_BASE}/courier/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`)
  return res.json()
}
