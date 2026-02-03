import { Aggregator } from '../dna';
import { AgentWallet } from '../connector/wallet';

export class SearchAggregator implements Aggregator {
  constructor(private wallet: AgentWallet) {}

  /**
   * Perceive the state based on a search query (signal).
   */
  async perceive(signal: unknown): Promise<unknown> {
    const s = signal as { query: string; limit?: number };
    const observation = await this.wallet.act('search', {
      query: s.query,
      limit: s.limit || 5
    });

    if (!observation.success) {
      throw new Error(observation.error || 'Failed to fetch search results');
    }

    return observation.data;
  }

  /**
   * Fetch general Hive State (could be extended)
   */
  async fetchHiveState(): Promise<unknown> {
    // Currently just a placeholder, but could fetch system health etc.
    return {
      timestamp: new Date().toISOString(),
      status: 'active'
    };
  }
}
