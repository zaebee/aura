/**
 * DNA of the Hive - Frontend Protocols
 * Mirroring packages/aura-core/src/aura_core/dna.py
 */

export interface Observation {
  success: boolean;
  data?: unknown;
  error?: string | null;
  event_type?: string;
  metadata?: Record<string, unknown>;
}

/**
 * A - Aggregator: Extracts signals into context.
 * In the frontend, this handles fetching Hive State and Search results.
 */
export interface Aggregator {
  perceive(signal: unknown, state_data?: Record<string, unknown>): Promise<unknown>;
}

/**
 * T - Transformer: The JIT UI engine.
 * Takes a JitUiRequest and returns a set of React components (or a rendering manifest).
 */
export interface Transformer {
  think(context: unknown): Promise<unknown>;
}

/**
 * C - Connector: Executes actions.
 * In the frontend, this is the Agent Wallet and API calling logic.
 */
export interface Connector {
  act(action: string, params: unknown): Promise<Observation>;
}

/**
 * M - Membrane: Input validation and schema checking.
 */
export interface Membrane {
  validate(data: unknown, schema?: unknown): Observation;
}
