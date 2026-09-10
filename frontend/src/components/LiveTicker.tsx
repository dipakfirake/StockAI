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
    // We fetch once to get the initial names/symbols, then let WebSocket update prices.

    const token = localStorage.getItem('auth_token')
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let ws: WebSocket | null = null

    try {
      ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

      ws.onopen = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol: '^NSEI' }))
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol: '^NSEBANK' }))
        }
      }

      ws.onerror = () => {}

      ws.onclose = () => {
        setTimeout(() => {
          // Re-trigger the effect by forcing a small state update if we wanted, 
          // or just re-establish the ws here. But since we are in useEffect, 
          // the easiest way to reconnect without dependency loops is to just reload or re-call connect.
          // Since this is a simple ticker, let's just let the user refresh if it completely dies, 
          // or we can implement a basic reconnect inside the closure.
        }, 3000)
      }


      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'market_update' && data.price > 0) {
            const cleanSym = (data.symbol || '').replace(/\.NS$/, '').replace(/\.BO$/, '').toUpperCase()
            
            if (cleanSym === '^NSEI' || cleanSym === 'NSEI' || cleanSym === 'NIFTY50') {
              setNifty(prev => prev ? {
                ...prev,
                price: Number(data.price),
                change: data.change !== undefined ? data.change : prev.change,
                change_pct: data.change_pct !== undefined ? data.change_pct : prev.change_pct,
                change_percent: data.change_pct !== undefined ? data.change_pct : prev.change_percent
              } : null)
            } else if (cleanSym === '^NSEBANK' || cleanSym === 'NSEBANK' || cleanSym === 'BANKNIFTY') {
              setBankNifty(prev => prev ? {
                ...prev,
                price: Number(data.price),
                change: data.change !== undefined ? data.change : prev.change,
                change_pct: data.change_pct !== undefined ? data.change_pct : prev.change_pct,
                change_percent: data.change_pct !== undefined ? data.change_pct : prev.change_percent
              } : null)
            }
          }
        } catch (err) {
          console.error('WebSocket LiveTicker error:', err)
        }
      }
    } catch (e) {
      console.warn('WebSocket LiveTicker init skipped:', e)
    }

    return () => {
      if (ws) {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        } else if (ws.readyState === WebSocket.CONNECTING) {
          ws.onopen = () => {
            try { ws?.close() } catch (_) {}
          }
        }
      }
    }
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
