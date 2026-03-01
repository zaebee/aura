const EVM_ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/

export function validateEVMAddress(address: string): { valid: boolean; error?: string } {
  if (!address) return { valid: false, error: 'Wallet address is required' }
  if (!EVM_ADDRESS_RE.test(address)) return { valid: false, error: 'Invalid EVM address format (must be 0x + 40 hex chars)' }
  return { valid: true }
}
