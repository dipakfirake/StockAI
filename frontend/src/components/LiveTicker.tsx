import React, { useEffect, useState } from 'react'
import { marketApi } from '../services/api'
import { NavLink } from 'react-router-dom'

interface IndexData {
  name: string
  symbol: string
  price: number
  change: number
  change_percent?: number
  change_pct?: number
}

export default function LiveTicker() {
  const [nifty, setNifty] = useState<IndexData | null>(null)
  const [bankNifty, setBankNifty] = useState<IndexData | null>(null)

  useEffect(() => {
    async function fetchIndices() {
      try {
        const res = await marketApi.getIndices()
        if (res.data) {
          const data = res.data.indices || res.data
          const indices = Array.isArray(data) ? data : Object.values(data)
          
          const n50 = indices.find((idx: any) => idx.name === 'Nifty 50')
          if (n50) setNifty(n50)
            
          const bnf = indices.find((idx: any) => idx.name === 'Nifty Bank')
          if (bnf) setBankNifty(bnf)
        }
      } catch (e: any) {
        if (e.name !== 'CanceledError' && e.message !== 'Request aborted' && e.code !== 'ERR_CANCELED') {
          console.error('Error fetching indices:', e)
        }
      }
    }

    fetchIndices()
    const interval = setInterval(fetchIndices, 30000)
    return () => clearInterval(interval)
  }, [])

  const renderTicker = (data: IndexData | null, fallbackName: string, link: string) => {
    if (!data || data.price == null) {
      return (
        <NavLink to={link} style={{ textDecoration: 'none', padding: '2px 8px', fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center' }}>
          {fallbackName}
        </NavLink>
      )
    }
    const change = data.change ?? 0
    const changePercent = data.change_percent ?? data.change_pct ?? 0
    const isPositive = change >= 0
    const color = isPositive ? 'var(--color-buy)' : 'var(--color-sell)'
    const arrow = isPositive ? '▲' : '▼'

    return (
      <NavLink to={link} style={{ 
        textDecoration: 'none', 
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: '0px',
        lineHeight: 1.2
      }}>
        <span style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 700, letterSpacing: '0.5px' }}>{data.name.toUpperCase()}</span>
        <span className="mono" style={{ color: color, fontSize: '0.85rem', fontWeight: 600 }}>{data.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
        <span className="mono" style={{ color: color, fontSize: '0.7rem' }}>
          {change > 0 ? '+' : ''}{change.toFixed(2)} ({changePercent.toFixed(2)}%)
        </span>
      </NavLink>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 24, marginRight: 'auto', alignItems: 'center' }} className="hide-on-mobile">
      {renderTicker(nifty, 'NIFTY 50', '/chart/^NSEI')}
      {renderTicker(bankNifty, 'NIFTY BANK', '/chart/^NSEBANK')}
    </div>
  )
}
