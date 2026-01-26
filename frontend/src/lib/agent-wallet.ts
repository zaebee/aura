import nacl from 'tweetnacl'
import { fromJson } from "@bufbuild/protobuf";
import { SearchResponseSchema, SearchResultItem, SearchResponse, NegotiateRequest, NegotiateResponse, NegotiateResponseSchema } from './aura/negotiation/v1/negotiation_pb'

export class BrowserAgentWallet {
  private keyPair: nacl.SignKeyPair
  private agentId: string
  private readonly GATEWAY_URL: string = 'http://localhost:8000/v1'

  constructor() {
    // Generate Ed25519 key pair
    this.keyPair = nacl.sign.keyPair()
    // Create agent ID from public key (did:key format with full hex)
    this.agentId = `did:key:${Array.from(this.keyPair.publicKey).map(b => b.toString(16).padStart(2, '0')).join('')}`
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
   * Returns SHA-256 hash as hex string to match backend format
   */
  private async hashBody(body: unknown): Promise<string> {
    // Recursively sort object keys to ensure a canonical JSON representation
    // that matches the backend's implementation.
    const deepSort = (obj: any): any => {
      if (Array.isArray(obj)) {
        return obj.map(v => deepSort(v));
      }
      if (obj !== null && typeof obj === 'object') {
        return Object.keys(obj).sort().reduce((result, key) => {
          result[key] = deepSort(obj[key]);
          return result;
        }, {} as Record<string, any>);
      }
      return obj;
    };

    // Prepare data for hashing: empty array for no body, or encoded canonical JSON
    const dataToHash = !body
      ? new Uint8Array(0)
      : new TextEncoder().encode(JSON.stringify(deepSort(body)));

    // Calculate SHA-256 hash
    const hashBuffer = await crypto.subtle.digest('SHA-256', dataToHash);

    // Convert to hex string (matches Python hashlib.sha256().hexdigest())
    return Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('')
  }

  /**
   * Sign a request with Ed25519 and return authentication headers
   * Format matches backend: METHOD + PATH + TIMESTAMP + BODY_HASH (no separators)
   */
  async signRequest(method: string, path: string, body: unknown = null): Promise<Record<string, string>> {
    // 1. Timestamp in SECONDS (not milliseconds)
    const timestamp = Math.floor(Date.now() / 1000).toString()

    // 2. Hash body as HEX
    const bodyHash = await this.hashBody(body)

    // 3. Create canonical request: METHOD + PATH + TIMESTAMP + BODY_HASH
    // Direct concatenation, no separators
    // Uppercase method for HTTP standard compliance (backend receives uppercase)
    const canonicalRequest = `${method.toUpperCase()}${path}${timestamp}${bodyHash}`

    // 4. Sign with Ed25519
    const signature = nacl.sign.detached(
      new TextEncoder().encode(canonicalRequest),
      this.keyPair.secretKey
    )

    // 5. Return headers with HEX-encoded signature (not base64)
    return {
      'X-Agent-ID': this.agentId,
      'X-Timestamp': timestamp,
      'X-Signature': Array.from(signature).map(b => b.toString(16).padStart(2, '0')).join('')
    }
  }

  /**
   * Make an authenticated API request
   */
  async fetchWithAuth(path: string, method: string = 'GET', body: unknown = null): Promise<Response> {
    // signRequest is now async, so await it
    const headers = await this.signRequest(method, path, body)

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
