import nacl from 'tweetnacl'
import { encode as encodeBase64 } from 'js-base64'
import { fromJson } from "@bufbuild/protobuf";
import { SearchResponseSchema, SearchResultItem, SearchResponse, NegotiateRequest, NegotiateResponse, NegotiateResponseSchema } from './aura/negotiation/v1/negotiation_pb'

export class BrowserAgentWallet {
  private keyPair: nacl.SignKeyPair
  private agentId: string
  private readonly GATEWAY_URL: string = 'http://localhost:8000/v1'

  constructor() {
    // Generate Ed25519 key pair
    this.keyPair = nacl.sign.keyPair()
    // Create agent ID from public key
    this.agentId = `did:web:agent-${Buffer.from(this.keyPair.publicKey).toString('hex').substring(0, 8)}`
  }

  /**
   * Get the agent's decentralized identifier
   */
  getAgentId(): string {
    return this.agentId
  }

  /**
   * Get the public key for verification
   */
  getPublicKey(): Uint8Array {
    return this.keyPair.publicKey
  }

  /**
   * Hash the request body to create a consistent signature
   */
  private hashBody(body: unknown): string {
    if (!body) return ''
    
    // Sort keys for consistent hashing
    const sortedBody = typeof body === 'object' && body !== null
      ? Object.keys(body as object).sort().reduce((acc, key) => {
          acc[key] = (body as Record<string, unknown>)[key]
          return acc
        }, {} as Record<string, unknown>)
      : body
    
    return encodeBase64(JSON.stringify(sortedBody))
  }

  /**
   * Sign a request with Ed25519 and return authentication headers
   */
  signRequest(method: string, path: string, body: unknown = null): Record<string, string> {
    const timestamp = Date.now().toString()
    const bodyHash = this.hashBody(body)
    
    // Create canonical request format
    const canonicalRequest = `${method.toUpperCase()}:${path}:${timestamp}:${bodyHash}`
    
    // Sign with Ed25519
    const signature = nacl.sign.detached(
      new TextEncoder().encode(canonicalRequest),
      this.keyPair.secretKey
    )

    return {
      'X-Agent-ID': this.agentId,
      'X-Timestamp': timestamp,
      'X-Signature': Buffer.from(signature).toString('base64')
    }
  }

  /**
   * Make an authenticated API request
   */
  async fetchWithAuth(path: string, method: string = 'GET', body: unknown = null): Promise<Response> {
    const headers = this.signRequest(method, path, body)
    
    const response = await fetch(`${this.GATEWAY_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers
      },
      body: body ? JSON.stringify(body) : undefined
    })

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`)
    }

    return response
  }

  /**
   * Search for items using the API
   */
  async search(query: string, limit: number = 3): Promise<SearchResponse> {
    const response = await this.fetchWithAuth('/search', 'POST', {
      query,
      limit
    })
    const json = await response.json()
    return fromJson(SearchResponseSchema, json)
  }

  /**
   * Submit a negotiation request
   */
  async negotiate(itemId: string, bidAmount: number, currency: string = 'USD'): Promise<NegotiateResponse> {
    const response = await this.fetchWithAuth('/negotiate', 'POST', {
      request_id: `req_${Date.now()}`,
      item_id: itemId,
      bid_amount: bidAmount,
      currency_code: currency,
      agent_did: this.agentId,
      // agent: {
      //   did: this.agentId,
      //   reputation_score: 0.8 // Default reputation score
      // }
    })
    const json = await response.json()
    return fromJson(NegotiateResponseSchema, json)
  }
}
