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
}

export default function StockSearchBox({ 
  placeholder = "Search stocks, indices...", 
  width = 300,
  onSelect,
  autoNavigate = true,
  className = ""
}: Props) {
  const [query, setQuery] = useState('')
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
          setResults(res.data.results || [])
          setIsOpen(true)
        } catch (error) {
          console.error("Search failed:", error)
          setResults([])
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
    setQuery('')
    
    // Add .NS if it's a standard symbol without exchange, though the backend returns it without .NS for presentation.
    const urlSymbol = symbol.includes('.') || symbol.startsWith('^') ? symbol : `${symbol}.NS`

    if (onSelect) {
      onSelect(urlSymbol)
    }
    
    if (autoNavigate) {
      navigate(`/chart/${urlSymbol}`)
    }
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', width }} className={className}>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <Search size={16} style={{ position: 'absolute', left: 12, color: 'var(--color-text-muted)' }} />
        <input
          type="text"
          className="input"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => { if (results.length > 0) setIsOpen(true) }}
          style={{ width: '100%', paddingLeft: 36, paddingRight: 36, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: '6px' }}
        />
        {isLoading && (
          <Loader2 size={16} className="spinner" style={{ position: 'absolute', right: 12, color: 'var(--color-text-muted)' }} />
        )}
      </div>

      {isOpen && results.length > 0 && (
        <div style={{
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
        }}>
          {results.map((r, i) => (
            <div 
              key={`${r.symbol}-${i}`}
              onClick={() => handleSelect(r.symbol)}
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
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>{r.symbol}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span className="badge badge-neutral" style={{ fontSize: 10, padding: '2px 6px', marginRight: 4 }}>{r.exchange || 'NSE'}</span>
                {r.type && <span className="badge badge-neutral" style={{ fontSize: 10, padding: '2px 6px' }}>{r.type}</span>}
              </div>
            </div>
          ))}
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
