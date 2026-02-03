import { Membrane, Observation } from '../dna';

export class WalletMembrane implements Membrane {
  /**
   * Validate wallet-related data or actions.
   */
  validate(data: unknown, schema?: unknown): Observation {
    switch (schema) {
      case 'bid':
        return this.validateBid(data);
      default:
        return { success: true };
    }
  }

  private validateBid(data: unknown): Observation {
    const { amount } = data as { amount: unknown };

    if (amount === undefined || amount === null) {
      return { success: false, error: 'Bid amount is required' };
    }

    const bidValue = typeof amount === 'string' ? parseFloat(amount) : amount;

    if (isNaN(bidValue as number)) {
      return { success: false, error: 'Invalid bid amount: not a number' };
    }

    if ((bidValue as number) <= 0) {
      return { success: false, error: 'Bid amount must be greater than zero' };
    }

    return { success: true, data: bidValue };
  }

  /**
   * Check if the Agent DID is valid.
   */
  isValidAgentDid(did: string): boolean {
    return did.startsWith('did:key:');
  }
}
