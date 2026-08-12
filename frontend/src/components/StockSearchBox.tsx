import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Loader2 } from 'lucide-react'
import { stocksApi } from '../services/api'

interface SearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}

interface Props {
  placeholder?: string
  width?: number | string
  onSelect?: (symbol: string) => void
  autoNavigate?: boolean
  className?: string
  value?: string
  onChange?: (val: string) => void
  clearOnSelect?: boolean
}

const FALLBACK_RESULTS: SearchResult[] = [
  { symbol: 'RELIANCE.NS', name: 'Reliance Industries', exchange: 'NSE', type: 'EQUITY' },
  { symbol: 'TCS.NS', name: 'Tata Consultancy Services', exchange: 'NSE', type: 'EQUITY' },
  { symbol: 'INFY.NS', name: 'Infosys', exchange: 'NSE', type: 'EQUITY' },
  { symbol: 'HDFCBANK.NS', name: 'HDFC Bank', exchange: 'NSE', type: 'EQUITY' },
  { symbol: 'ICICIBANK.NS', name: 'ICICI Bank', exchange: 'NSE', type: 'EQUITY' },
]

const normalizeOptionSymbol = (symbol: string) => {
  if (!symbol) return symbol
  if (symbol.includes('.') || symbol.startsWith('^')) return symbol
  return `${symbol}.NS`
}

const getFallbackResults = (query: string): SearchResult[] => {
  const normalizedQuery = query.trim().toUpperCase()
  if (!normalizedQuery || normalizedQuery.length < 2) return []

  return FALLBACK_RESULTS.filter((item) => {
    const fullSymbol = item.symbol.toUpperCase()
    const name = item.name.toUpperCase()
    return fullSymbol.includes(normalizedQuery) || name.includes(normalizedQuery)
  })
}

export default function StockSearchBox({ 
  placeholder = "Search symbol or company...", 
  width = 300,
  onSelect,
  autoNavigate = true,
  className = "",
  value,
  onChange,
  clearOnSelect = true
}: Props) {
  const [internalQuery, setInternalQuery] = useState('')
  const query = value !== undefined ? value : internalQuery

  const handleQueryChange = (val: string) => {
    setInternalQuery(val)
    if (onChange) onChange(val)
  }
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  
  const wrapperRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  useEffect(() => {
    const delayDebounceFn = setTimeout(async () => {
      if (query.trim().length >= 2) {
        setIsLoading(true)
        try {
          const res = await stocksApi.search(query)
          const apiResults = (res.data.results || []).map((item: SearchResult) => ({
            ...item,
            symbol: normalizeOptionSymbol(item.symbol),
          }))
          setResults(apiResults.length > 0 ? apiResults : getFallbackResults(query))
          setIsOpen(true)
        } catch (error) {
          console.error("Search failed:", error)
          setResults(getFallbackResults(query))
          setIsOpen(true)
        } finally {
          setIsLoading(false)
        }
      } else {
        setResults([])
        setIsOpen(false)
      }
    }, 300) // 300ms debounce

    return () => clearTimeout(delayDebounceFn)
  }, [query])

  const handleSelect = (symbol: string) => {
    setIsOpen(false)

    const normalizedSelection = normalizeOptionSymbol(symbol)
    const urlSymbol = normalizedSelection

    if (clearOnSelect) {
      handleQueryChange('')
    } else {
      handleQueryChange(urlSymbol)
    }

    if (onSelect) {
      onSelect(urlSymbol)
    }

    if (autoNavigate) {
      navigate(`/chart/${urlSymbol}`)
    }
  }

  return (
    <div
      ref={wrapperRef}
      role="combobox"
      aria-haspopup="listbox"
      aria-expanded={isOpen}
      aria-owns="stock-search-results"
      style={{ position: 'relative', width }}
      className={className}
    >
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <Search size={16} style={{ position: 'absolute', left: 12, color: 'var(--color-text-muted)' }} />
        <input
          type="text"
          className="input"
          placeholder={placeholder}
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          onFocus={() => { if (results.length > 0) setIsOpen(true) }}
          aria-autocomplete="list"
          aria-controls="stock-search-results"
          style={{ width: '100%', paddingLeft: 36, paddingRight: 36, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: '6px' }}
        />
        {isLoading && (
          <Loader2 size={16} className="spinner" style={{ position: 'absolute', right: 12, color: 'var(--color-text-muted)' }} />
        )}
      </div>

      {isOpen && results.length > 0 && (
        <div
          role="listbox"
          id="stock-search-results"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            background: 'var(--color-bg-primary)',
            border: '1px solid var(--color-border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            zIndex: 1000,
            maxHeight: 300,
            overflowY: 'auto'
          }}
        >
          {results.map((r, i) => {
            const optionSymbol = normalizeOptionSymbol(r.symbol)
            return (
            <div 
              key={`${optionSymbol}-${i}`}
              data-testid={`stock-search-option-${optionSymbol}`}
              role="option"
              aria-label={`${r.name} (${optionSymbol})`}
              onClick={() => handleSelect(optionSymbol)}
              style={{
                padding: '10px 12px',
                cursor: 'pointer',
                borderBottom: '1px solid var(--color-border)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-bg-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <div>
                <div style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{r.name}</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>{optionSymbol}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span className="badge badge-neutral" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }}>{r.exchange || 'NSE'}</span>
                {r.type && <span className="badge badge-neutral" style={{ fontSize: 10, padding: '2px 6px' }}>{r.type}</span>}
              </div>
            </div>
            )
          })}
        </div>
      )}
      
      {isOpen && query.length >= 2 && results.length === 0 && !isLoading && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          marginTop: 4,
          background: 'var(--color-bg-primary)',
          border: '1px solid var(--color-border)',
          borderRadius: 6,
          padding: '12px',
          textAlign: 'center',
          color: 'var(--color-text-muted)',
          zIndex: 1000,
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        }}>
          No stocks found for "{query}"
        </div>
      )}
    </div>
  )
}
