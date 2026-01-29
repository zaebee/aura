'use client'

import { useState, useEffect } from 'react'
import { BrowserAgentWallet } from '@/lib/agent-wallet'
import { Search, MessageCircle, Wallet } from 'lucide-react'
import { SearchResultItem, SearchResponse, NegotiateResponse, JitUiRequest } from '@/lib/aura/negotiation/v1/negotiation_pb'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { JITRenderer } from '@/components/JITRenderer'

// Using proto-generated SearchResultItem type

interface NegotiationEntry {
  type: 'bid' | 'counter' | 'accept' | 'reject' | 'jit_approved' | 'jit_rejected';
  amount?: number;
  message?: string;
  reason?: string;
  reservationCode?: string;
  template?: string;
  timestamp: string;
}

export default function AgentConsole() {
  const [wallet, setWallet] = useState<BrowserAgentWallet | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([])
  const [selectedItem, setSelectedItem] = useState<SearchResultItem | null>(null)
  const [bidAmount, setBidAmount] = useState('')
  const [negotiationHistory, setNegotiationHistory] = useState<NegotiationEntry[]>([])
  const [jitManifest, setJitManifest] = useState<JitUiRequest | null>(null)
  const [currentStatus, setCurrentStatus] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Initialize wallet on component mount
  useEffect(() => {
    const walletInstance = new BrowserAgentWallet()
    setWallet(walletInstance)
  }, [])

  const handleSearch = async () => {
    if (!wallet || !searchQuery.trim()) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      const results: SearchResponse = await wallet.search(searchQuery, 5)
      setSearchResults(results.results)
      setSelectedItem(null)
      setNegotiationHistory([])
      setCurrentStatus(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      console.error('Search error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSelectItem = (item: SearchResultItem) => {
    setSelectedItem(item)
    setBidAmount(item.basePrice ? (item.basePrice * 0.8).toFixed(2) : '')
    setNegotiationHistory([])
    setCurrentStatus(null)
  }

  const handleNegotiate = async () => {
    if (!wallet || !selectedItem || !bidAmount) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      const bidValue = parseFloat(bidAmount)
      if (isNaN(bidValue) || bidValue <= 0) {
        setError('Please enter a valid bid amount')
        return
      }

      const result: NegotiateResponse = await wallet.negotiate(selectedItem.itemId, bidValue)
      
      // Add to negotiation history
      setNegotiationHistory(prev => [...prev, {
        type: 'bid',
        amount: bidValue,
        timestamp: new Date().toISOString()
      }])

      // Handle different response types using proto discriminated union
      if (result.result.case === 'accepted') {
        const accepted = result.result.value
        setCurrentStatus('accepted')

        // Handle oneof reveal_method (reservationCode or cryptoPayment)
        const reservationCode = accepted.revealMethod?.case === 'reservationCode'
          ? accepted.revealMethod.value
          : undefined

        setNegotiationHistory(prev => [...prev, {
          type: 'accept',
          amount: accepted.finalPrice,
          reservationCode: reservationCode,
          timestamp: new Date().toISOString()
        }])
      } else if (result.result.case === 'countered') {
        const countered = result.result.value
        setCurrentStatus('countered')
        setNegotiationHistory(prev => [...prev, {
          type: 'counter',
          amount: countered.proposedPrice,
          message: countered.humanMessage,
          timestamp: new Date().toISOString()
        }])
      } else if (result.result.case === 'uiRequired') {
        const uiRequest = result.result.value
        setCurrentStatus('ui_required')
        setJitManifest(uiRequest)
      } else if (result.result.case === 'rejected') {
        const rejected = result.result.value
        setCurrentStatus('rejected')
        setNegotiationHistory(prev => [...prev, {
          type: 'reject',
          reason: rejected.reasonCode,
          timestamp: new Date().toISOString()
        }])
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Negotiation failed')
      console.error('Negotiation error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleJITResponse = async (approved: boolean) => {
    if (!jitManifest || !wallet) return
    
    setIsLoading(true)
    setError(null)

    try {
      // For now, we'll just close the JIT dialog
      // In a real implementation, this would send an approval/rejection to the backend
      setJitManifest(null)
      setNegotiationHistory(prev => [...prev, {
        type: approved ? 'jit_approved' : 'jit_rejected',
        template: jitManifest.templateId,
        timestamp: new Date().toISOString()
      }])
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'JIT action failed')
      console.error('JIT error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-4">
      <header className="flex justify-between items-center py-6 border-b border-gray-700 animate-fade-in">
        <h1 className="h1 bg-cyberpunk-gradient bg-clip-text text-transparent">Aura Agent Console</h1>
        {wallet && (
          <div className="flex items-center space-x-3 bg-gray-800 px-4 py-2 rounded-lg border border-gray-700">
            <Wallet className="text-cyberpunk-purple" size={18} />
            <span className="body-text-sm">Agent: {wallet.getAgentId()}</span>
          </div>
        )}
      </header>

      {/* Search Section */}
      <Card className="bg-card-bg border border-gray-700 rounded-lg shadow-card animate-fade-in">
        <CardHeader>
          <CardTitle className="text-cyberpunk-blue h4">Search Inventory</CardTitle>
          <CardDescription className="caption-text">Find items to negotiate</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex space-x-2">
            <Input
              type="text"
              placeholder="Search for items..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              className="bg-gray-800 border border-gray-600 text-white rounded-md py-2 px-3 focus:outline-none focus:border-cyberpunk-blue focus:ring-1 focus:ring-cyberpunk-blue flex-1"
            />
            <Button
              onClick={handleSearch}
              disabled={isLoading || !searchQuery.trim()}
              className="bg-cyberpunk-blue hover:bg-cyberpunk-blue/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200"
            >
              <Search className="mr-2" size={16} />
              {isLoading ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert className="bg-error/20 border-error animate-fade-in">
          <AlertTitle className="text-error h4">Error</AlertTitle>
          <AlertDescription className="body-text">{error}</AlertDescription>
        </Alert>
      )}

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-fade-in">
          {searchResults.map((item) => (
            <Card
              key={item.itemId}
              className={`bg-card-bg border rounded-lg shadow-card cursor-pointer hover:border-cyberpunk-blue transition-all duration-200 ${selectedItem?.itemId === item.itemId ? 'border-cyberpunk-blue' : 'border-gray-700'}`}
              onClick={() => handleSelectItem(item)}
            >
              <CardHeader>
                <CardTitle className="text-cyberpunk-blue text-sm truncate">{item.name}</CardTitle>
                <CardDescription className="caption-text text-xs">ID: {item.itemId}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="body-text-sm">Base Price:</span>
                    <Badge variant="secondary" className="bg-gray-700 caption-text">
                      ${item.basePrice?.toFixed(2) || 'N/A'}
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="body-text-sm">Relevance:</span>
                    <Badge variant={item.similarityScore > 0.8 ? 'default' : 'secondary'} className="caption-text">
                      {(item.similarityScore * 100).toFixed(1)}%
                    </Badge>
                  </div>
                </div>
                <p className="caption-text mt-2 truncate">{item.descriptionSnippet}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Negotiation Section */}
      {selectedItem && (
        <Card className="bg-card-bg border border-gray-700 rounded-lg shadow-card animate-fade-in">
          <CardHeader>
            <CardTitle className="text-cyberpunk-purple h4">Negotiation</CardTitle>
            <CardDescription className="caption-text">Bid on {selectedItem.name}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex space-x-2">
                <Input
                  type="number"
                  placeholder="Enter bid amount"
                  value={bidAmount}
                  onChange={(e) => setBidAmount(e.target.value)}
                  className="bg-gray-800 border border-gray-600 text-white rounded-md py-2 px-3 focus:outline-none focus:border-cyberpunk-blue focus:ring-1 focus:ring-cyberpunk-blue flex-1"
                  min="0"
                  step="0.01"
                />
                <Button
                  onClick={handleNegotiate}
                  disabled={isLoading || !bidAmount}
                  className="bg-cyberpunk-purple hover:bg-cyberpunk-purple/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200"
                >
                  <MessageCircle className="mr-2" size={16} />
                  {isLoading ? 'Negotiating...' : 'Submit Bid'}
                </Button>
              </div>

              {/* Negotiation History */}
              {negotiationHistory.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-gray-300">Negotiation History</h3>
                  <ScrollArea className="h-64 border border-gray-700 rounded-md p-3">
                    <div className="space-y-3">
                      {negotiationHistory.map((entry, index) => (
                        <div key={`${entry.type}-${entry.timestamp}-${index}`} className={`flex ${entry.type === 'bid' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`max-w-xs p-3 rounded-lg ${entry.type === 'bid' ? 'bg-cyberpunk-blue/20 border border-cyberpunk-blue' : entry.type === 'accept' ? 'bg-green-900/50 border border-green-700' : entry.type === 'counter' ? 'bg-yellow-900/50 border border-yellow-700' : 'bg-red-900/50 border border-red-700'}`}>
                            {entry.type === 'bid' && (
                              <div>
                                <p className="text-sm font-medium">Your Bid: ${entry.amount}</p>
                                <p className="text-xs text-gray-400">{new Date(entry.timestamp).toLocaleTimeString()}</p>
                              </div>
                            )}
                            {entry.type === 'counter' && (
                              <div>
                                <p className="text-sm font-medium">Counter Offer: ${entry.amount}</p>
                                <p className="text-xs text-gray-400">{entry.message}</p>
                                <p className="text-xs text-gray-400">{new Date(entry.timestamp).toLocaleTimeString()}</p>
                              </div>
                            )}
                            {entry.type === 'accept' && (
                              <div>
                                <p className="text-sm font-medium text-green-400">✅ Deal Accepted!</p>
                                <p className="text-sm">Final Price: ${entry.amount}</p>
                                <p className="text-xs text-gray-400">Reservation: {entry.reservationCode}</p>
                                <p className="text-xs text-gray-400">{new Date(entry.timestamp).toLocaleTimeString()}</p>
                              </div>
                            )}
                            {entry.type === 'reject' && (
                              <div>
                                <p className="text-sm font-medium text-red-400">❌ Offer Rejected</p>
                                <p className="text-xs text-gray-400">Reason: {entry.reason}</p>
                                <p className="text-xs text-gray-400">{new Date(entry.timestamp).toLocaleTimeString()}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* JIT Renderer */}
      {jitManifest && (
        <JITRenderer 
          manifest={jitManifest} 
          onApprove={() => handleJITResponse(true)} 
          onReject={() => handleJITResponse(false)} 
        />
      )}
    </div>
  )
}