import nacl from 'tweetnacl'
import { fromJson } from "@bufbuild/protobuf";
import {
  SearchResponseSchema,
  SearchResponse,
  NegotiateResponse,
  NegotiateResponseSchema
} from '../../lib/aura/negotiation/v1/negotiation_pb'
import { Connector, Observation } from '../dna';

export class AgentWallet implements Connector {
  private keyPair: nacl.SignKeyPair
  private agentId: string
  private readonly GATEWAY_URL: string

  constructor(gatewayUrl?: string) {
    this.GATEWAY_URL = gatewayUrl ||
      (import.meta.env.VITE_API_GATEWAY_URL) ||
      'http://localhost:8000/v1'

    this.keyPair = nacl.sign.keyPair()
    this.agentId = `did:key:${Array.from(this.keyPair.publicKey).map(b => b.toString(16).padStart(2, '0')).join('')}`
  }

  getAgentId(): string {
    return this.agentId
  }

  async act(action: string, params: unknown): Promise<Observation> {
    try {
      switch (action) {
        case 'search': {
          if (!params || typeof params !== 'object' || !('query' in params)) {
            return { success: false, error: 'Invalid params for search: missing query' };
          }
          const p = params as { query: string; limit?: number };
          const searchResult = await this.search(p.query, p.limit);
          return { success: true, data: searchResult };
        }
        case 'negotiate': {
          if (!params || typeof params !== 'object' || !('itemId' in params) || !('bidAmount' in params)) {
            return { success: false, error: 'Invalid params for negotiate: missing itemId or bidAmount' };
          }
          const p = params as { itemId: string; bidAmount: number; currency?: string };
          const negotiateResult = await this.negotiate(p.itemId, p.bidAmount, p.currency);
          return { success: true, data: negotiateResult };
        }
        default:
          return { success: false, error: `Unknown action: ${action}` };
      }
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  private async hashBody(body: unknown): Promise<string> {
    const deepSort = (obj: unknown): unknown => {
      if (Array.isArray(obj)) {
        return obj.map(v => deepSort(v));
      }
      if (obj !== null && typeof obj === 'object') {
        return Object.keys(obj).sort().reduce((result, key) => {
          (result as Record<string, unknown>)[key] = deepSort((obj as Record<string, unknown>)[key]);
          return result;
        }, {} as Record<string, unknown>);
      }
      return obj;
    };

    const dataToHash = !body
      ? new Uint8Array(0)
      : new TextEncoder().encode(JSON.stringify(deepSort(body)));

    const hashBuffer = await crypto.subtle.digest('SHA-256', dataToHash);

    return Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('')
  }

  async signRequest(method: string, path: string, body: unknown = null): Promise<Record<string, string>> {
    const timestamp = Math.floor(Date.now() / 1000).toString()
    const bodyHash = await this.hashBody(body)
    const canonicalRequest = `${method.toUpperCase()}${path}${timestamp}${bodyHash}`

    const signature = nacl.sign.detached(
      new TextEncoder().encode(canonicalRequest),
      this.keyPair.secretKey
    )

    return {
      'X-Agent-ID': this.agentId,
      'X-Timestamp': timestamp,
      'X-Signature': Array.from(signature).map(b => b.toString(16).padStart(2, '0')).join('')
    }
  }

  async fetchWithAuth(path: string, method: string = 'GET', body: unknown = null): Promise<Response> {
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

  private async search(query: string, limit: number = 3): Promise<SearchResponse> {
    const response = await this.fetchWithAuth('/search', 'POST', {
      query,
      limit
    })
    const json = await response.json()
    return fromJson(SearchResponseSchema, json)
  }

  private async negotiate(itemId: string, bidAmount: number, currency: string = 'USD'): Promise<NegotiateResponse> {
    const response = await this.fetchWithAuth('/negotiate', 'POST', {
      request_id: `req_${Date.now()}`,
      item_id: itemId,
      bid_amount: bidAmount,
      currency_code: currency,
      agent_did: this.agentId,
    })
    const json = await response.json()
    return fromJson(NegotiateResponseSchema, json)
  }
}
