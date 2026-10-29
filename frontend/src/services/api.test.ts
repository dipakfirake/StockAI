import { describe, it, expect, vi, beforeEach } from 'vitest'
import { marketApi, _resetIndicesCache } from './api'
import { cleanSymbol, isNifty50, isBankNifty, isIndexMatch } from '../components/LiveTicker'
import axios from 'axios'

vi.mock('axios', () => {
  const mockAxiosInstance: any = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }
  return {
    default: {
      create: () => mockAxiosInstance,
    },
  }
})

describe('marketApi.getIndices single-request coalescing and cloning architecture', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetIndicesCache()
  })

  it('coalesces concurrent requests and returns cloned responses without duplicate network requests', async () => {
    const mockIndicesData = {
      indices: [
        { name: 'Nifty 50', symbol: '^NSEI', price: 24500.5, change: 120.5, change_pct: 0.49 },
        { name: 'Nifty Bank', symbol: '^NSEBANK', price: 51200.0, change: -80.0, change_pct: -0.16 },
      ],
    }

    const apiInstance = (axios.create() as any)
    let resolveNetworkCall: (val: any) => void
    const networkPromise = new Promise((resolve) => {
      resolveNetworkCall = resolve
    })

    apiInstance.get.mockImplementation((url: string) => {
      if (url === '/market/indices') {
        return networkPromise
      }
      return Promise.resolve({ data: {} })
    })

    // Initiate two simultaneous calls across distinct components (e.g. LiveTicker and Dashboard)
    const call1 = marketApi.getIndices()
    const call2 = marketApi.getIndices()

    // Resolve the single network call
    resolveNetworkCall!({ data: mockIndicesData })

    const [res1, res2] = await Promise.all([call1, call2])

    // Verify only a single network request was executed
    expect(apiInstance.get).toHaveBeenCalledTimes(1)
    expect(apiInstance.get).toHaveBeenCalledWith('/market/indices')

    // Verify deep equality of data
    expect(res1.data.indices[0].price).toBe(24500.5)
    expect(res2.data.indices[0].price).toBe(24500.5)

    // Verify reference isolation (cloning strategy): mutating res1 does not affect res2
    res1.data.indices[0].price = 99999
    expect(res2.data.indices[0].price).toBe(24500.5)
    expect(res1).not.toBe(res2)
  })

  it('safely handles Axios responses containing circular references without throwing serialization errors', async () => {
    const mockIndicesData = {
      indices: [
        { name: 'Nifty 50', symbol: '^NSEI', price: 24550.0, change: 170.0, change_pct: 0.70 },
      ],
    }

    const circularResponse: any = {
      status: 200,
      statusText: 'OK',
      headers: {},
      data: mockIndicesData,
    }
    // Simulate real Axios circular reference between request and response/config
    circularResponse.request = circularResponse
    circularResponse.config = { env: circularResponse }

    const apiInstance = (axios.create() as any)
    apiInstance.get.mockResolvedValueOnce(circularResponse)

    // Must not throw "TypeError: Converting circular structure to JSON"
    const result = await marketApi.getIndices()
    expect(result.data.indices[0].price).toBe(24550.0)
    expect(result.status).toBe(200)

    // Mutating returned clone must not affect source data
    result.data.indices[0].price = 0
    expect(mockIndicesData.indices[0].price).toBe(24550.0)
  })

  it('serves subsequent calls within TTL from cache without redundant network calls', async () => {
    const mockIndicesData = {
      indices: [
        { name: 'Nifty 50', symbol: '^NSEI', price: 24600.0, change: 220.0, change_pct: 0.90 },
      ],
    }

    const apiInstance = (axios.create() as any)
    apiInstance.get.mockResolvedValueOnce({ data: mockIndicesData })

    const res1 = await marketApi.getIndices()
    const res2 = await marketApi.getIndices()

    expect(apiInstance.get).toHaveBeenCalledTimes(1)
    expect(res1.data.indices[0].price).toBe(24600.0)
    expect(res2.data.indices[0].price).toBe(24600.0)
    expect(res1).not.toBe(res2) // Isolated clones
  })

  it('recovers cleanly on network failure and allows subsequent retries', async () => {
    const apiInstance = (axios.create() as any)
    apiInstance.get.mockRejectedValueOnce(new Error('Network Timeout'))

    await expect(marketApi.getIndices()).rejects.toThrow('Network Timeout')

    // Subsequent call should initiate a fresh network request
    const retryData = {
      indices: [{ name: 'Nifty 50', symbol: '^NSEI', price: 24650.0, change: 270.0, change_pct: 1.11 }],
    }
    apiInstance.get.mockResolvedValueOnce({ data: retryData })

    const res = await marketApi.getIndices()
    expect(res.data.indices[0].price).toBe(24650.0)
  })

  it('bypasses client cache and triggers fresh network request when forceRefresh is true', async () => {
    const initialData = {
      indices: [{ name: 'Nifty 50', symbol: '^NSEI', price: 24700.0, change: 320.0, change_pct: 1.31 }],
    }
    const freshData = {
      indices: [{ name: 'Nifty 50', symbol: '^NSEI', price: 24750.0, change: 370.0, change_pct: 1.51 }],
    }

    const apiInstance = (axios.create() as any)
    apiInstance.get.mockResolvedValueOnce({ data: initialData })

    const res1 = await marketApi.getIndices()
    expect(res1.data.indices[0].price).toBe(24700.0)
    expect(apiInstance.get).toHaveBeenCalledTimes(1)

    // With forceRefresh=true, must trigger a 2nd network request even within TTL
    apiInstance.get.mockResolvedValueOnce({ data: freshData })
    const res2 = await marketApi.getIndices(true)
    expect(apiInstance.get).toHaveBeenCalledTimes(2)
    expect(res2.data.indices[0].price).toBe(24750.0)
  })

  it('preserves array data structure during cloneIndicesResponse catch fallback when circular references exist', async () => {
    // Some mock data setups return an array directly as res.data
    const mockArrayData: any[] = [
      { name: 'Nifty 50', symbol: '^NSEI', price: 24800.0, change: 400.0 },
      { name: 'Nifty Bank', symbol: '^NSEBANK', price: 51500.0, change: 100.0 },
    ]
    // Introduce circular reference inside array items to trigger JSON.stringify catch block
    mockArrayData[0].self = mockArrayData[0]

    const apiInstance = (axios.create() as any)
    apiInstance.get.mockResolvedValueOnce({ data: mockArrayData })

    const result = await marketApi.getIndices()
    // Must preserve Array type and not convert to an object with numeric keys
    expect(Array.isArray(result.data)).toBe(true)
    expect(result.data.length).toBe(2)
    expect(result.data[0].price).toBe(24800.0)
    expect(result.data[1].price).toBe(51500.0)
  })
})

describe('LiveTicker symbol normalization and matching across Indian broker feeds', () => {
  it('correctly normalizes symbols with broker prefixes, index tags, and spaces', () => {
    expect(cleanSymbol('^NSEI')).toBe('NSEI')
    expect(cleanSymbol('NSE:NIFTY50-INDEX')).toBe('NIFTY50')
    expect(cleanSymbol('Nifty 50')).toBe('NIFTY50')
    expect(cleanSymbol('NIFTY-50')).toBe('NIFTY50')
    expect(cleanSymbol('NIFTY_50')).toBe('NIFTY50')
    expect(cleanSymbol('^NSEBANK')).toBe('NSEBANK')
    expect(cleanSymbol('NSE:NIFTYBANK-INDEX')).toBe('NIFTYBANK')
    expect(cleanSymbol('NSE:BANKNIFTY-INDEX')).toBe('BANKNIFTY')
    expect(cleanSymbol('Bank Nifty')).toBe('BANKNIFTY')
    expect(cleanSymbol('BANK-NIFTY')).toBe('BANKNIFTY')
    expect(cleanSymbol('Nifty Bank')).toBe('NIFTYBANK')
    expect(cleanSymbol('NIFTY-BANK')).toBe('NIFTYBANK')
    expect(cleanSymbol('RELIANCE.NS')).toBe('RELIANCE')
    expect(cleanSymbol('BSE:SENSEX-INDEX')).toBe('SENSEX')
    expect(cleanSymbol('NSE:NIFTYIT-INDEX')).toBe('NIFTYIT')
    expect(cleanSymbol(null)).toBe('')
    expect(cleanSymbol(undefined)).toBe('')
    expect(cleanSymbol(500325 as any)).toBe('500325')
  })

  it('identifies all variations of Nifty 50 across index feeds', () => {
    expect(isNifty50('^NSEI')).toBe(true)
    expect(isNifty50('NSEI')).toBe(true)
    expect(isNifty50('NIFTY 50')).toBe(true)
    expect(isNifty50('Nifty 50')).toBe(true)
    expect(isNifty50('NIFTY50')).toBe(true)
    expect(isNifty50('NIFTY')).toBe(true)
    expect(isNifty50('NIFTY-50')).toBe(true)
    expect(isNifty50('NIFTY_50')).toBe(true)
    expect(isNifty50('CNXNIFTY')).toBe(true)
    expect(isNifty50('NSE:NIFTY50-INDEX')).toBe(true)

    // Non-Nifty symbols
    expect(isNifty50('^NSEBANK')).toBe(false)
    expect(isNifty50('RELIANCE.NS')).toBe(false)
    expect(isNifty50(null)).toBe(false)
    expect(isNifty50(undefined)).toBe(false)
  })

  it('identifies all variations of Nifty Bank across index feeds', () => {
    expect(isBankNifty('^NSEBANK')).toBe(true)
    expect(isBankNifty('NSEBANK')).toBe(true)
    expect(isBankNifty('BANKNIFTY')).toBe(true)
    expect(isBankNifty('Bank Nifty')).toBe(true)
    expect(isBankNifty('BANK-NIFTY')).toBe(true)
    expect(isBankNifty('Nifty Bank')).toBe(true)
    expect(isBankNifty('NIFTY-BANK')).toBe(true)
    expect(isBankNifty('NIFTYBANK')).toBe(true)
    expect(isBankNifty('NSE:NIFTYBANK-INDEX')).toBe(true)
    expect(isBankNifty('NSE:BANKNIFTY-INDEX')).toBe(true)

    // Non-Bank symbols
    expect(isBankNifty('^NSEI')).toBe(false)
    expect(isBankNifty('HDFCBANK.NS')).toBe(false)
    expect(isBankNifty(null)).toBe(false)
    expect(isBankNifty(undefined)).toBe(false)
  })

  it('accurately matches target feed symbols to index state definitions in Dashboard and LiveTicker', () => {
    // Bank Nifty matches across broker representations
    expect(isIndexMatch('^NSEBANK', 'Nifty Bank', 'BANKNIFTY')).toBe(true)
    expect(isIndexMatch('^NSEBANK', 'Nifty Bank', 'NSE:BANKNIFTY-INDEX')).toBe(true)
    expect(isIndexMatch('^NSEBANK', 'Nifty Bank', 'NSE:NIFTYBANK-INDEX')).toBe(true)
    expect(isIndexMatch('^NSEBANK', 'Bank Nifty', 'BANK-NIFTY')).toBe(true)
    expect(isIndexMatch('^NSEBANK', 'Nifty Bank', '^NSEBANK')).toBe(true)

    // Nifty 50 matches across broker representations
    expect(isIndexMatch('^NSEI', 'Nifty 50', 'NSE:NIFTY50-INDEX')).toBe(true)
    expect(isIndexMatch('^NSEI', 'Nifty 50', 'NIFTY')).toBe(true)
    expect(isIndexMatch('^NSEI', 'Nifty 50', 'NIFTY-50')).toBe(true)
    expect(isIndexMatch('^NSEI', 'Nifty 50', 'NIFTY_50')).toBe(true)
    expect(isIndexMatch('^NSEI', 'Nifty 50', 'CNXNIFTY')).toBe(true)
    expect(isIndexMatch('^NSEI', 'Nifty 50', '^NSEI')).toBe(true)

    // Sensex & Sector indices
    expect(isIndexMatch('^BSESN', 'Sensex', 'BSE:SENSEX-INDEX')).toBe(true)
    expect(isIndexMatch('^BSESN', 'Sensex', '^BSESN')).toBe(true)
    expect(isIndexMatch('^CNXIT', 'Nifty IT', 'NSE:NIFTYIT-INDEX')).toBe(true)
    expect(isIndexMatch('^CNXIT', 'Nifty IT', '^CNXIT')).toBe(true)
    expect(isIndexMatch('^INDIAVIX', 'India VIX', 'NSE:INDIAVIX-INDEX')).toBe(true)

    // Negative / disjoint matches
    expect(isIndexMatch('^NSEI', 'Nifty 50', '^NSEBANK')).toBe(false)
    expect(isIndexMatch('^NSEBANK', 'Nifty Bank', 'RELIANCE.NS')).toBe(false)
    expect(isIndexMatch(null, null, 'BANKNIFTY')).toBe(false)
    expect(isIndexMatch('^NSEI', 'Nifty 50', null)).toBe(false)
    expect(isIndexMatch(undefined, undefined, undefined)).toBe(false)
  })
})
