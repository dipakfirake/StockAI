import React, { useEffect, useState, useRef } from 'react'
import { marketApi } from '../services/api'
import { isWebSocketSupportedOnHost } from '../services/websocket'
import { NavLink } from 'react-router-dom'
import { formatNumber2Dec } from '../utils/formatters'

interface IndexData {
  name: string
  symbol: string
  price: number
  change: number
  change_percent?: number
  change_pct?: number
}

export const cleanSymbol = (sym: string | null | undefined): string => {
  if (!sym) return ''
  return String(sym)
    .replace(/^NSE:|^BSE:/, '')
    .replace(/-INDEX$|-EQ$/, '')
    .replace(/\.NS$|\.BO$/, '')
    .replace(/^\^/, '')
    .replace(/[\s\-_]+/g, '')
    .toUpperCase()
}

export const isNifty50 = (symOrName: string | null | undefined): boolean => {
  const s = cleanSymbol(symOrName)
  return s === 'NSEI' || s === 'NIFTY50' || s === 'NIFTY' || s === 'CNXNIFTY'
}

export const isBankNifty = (symOrName: string | null | undefined): boolean => {
  const s = cleanSymbol(symOrName)
  return s === 'NSEBANK' || s === 'BANKNIFTY' || s === 'NIFTYBANK'
}

export const isIndexMatch = (
  idxSymbol: string | null | undefined,
  idxName: string | null | undefined,
  targetSymbol: string | null | undefined
): boolean => {
  const targetClean = cleanSymbol(targetSymbol)
  if (!targetClean) return false

  if (isNifty50(targetClean) && (isNifty50(idxSymbol) || isNifty50(idxName))) {
    return true
  }
  if (isBankNifty(targetClean) && (isBankNifty(idxSymbol) || isBankNifty(idxName))) {
    return true
  }

  const sSym = cleanSymbol(idxSymbol)
  const sName = cleanSymbol(idxName)
  return sSym === targetClean || sName === targetClean
}

export default function LiveTicker() {
  const [nifty, setNifty] = useState<IndexData | null>(null)
  const [bankNifty, setBankNifty] = useState<IndexData | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)

  useEffect(() => {
    let isMounted = true
    let ws: WebSocket | null = null

    // Fetch initial baseline index data via single consolidated request
    async function fetchIndices() {
      if (!isMounted) return
      try {
        const res = await marketApi.getIndices()
        if (!isMounted || !res || !res.data) return
        const data = res.data.indices || res.data
        const indices = Array.isArray(data) ? data : Object.values(data)

        const n50 = indices.find((idx: any) => isNifty50(idx?.symbol) || isNifty50(idx?.name))
        const n50Price = Number(n50?.price)
        if (n50 && Number.isFinite(n50Price) && n50Price > 0) {
          setNifty(prev => {
            const rawChange = Number(n50.change)
            const newChange = Number.isFinite(rawChange) ? rawChange : (prev?.change ?? 0)
            const rawPct = Number(n50.change_pct ?? n50.change_percent)
            const newPct = Number.isFinite(rawPct) ? rawPct : (prev?.change_pct ?? prev?.change_percent ?? 0)
            if (prev && prev.price === n50Price && prev.change === newChange && (prev.change_pct === newPct || prev.change_percent === newPct)) {
              return prev // Price unchanged: preserve reference and prevent re-render
            }
            return {
              name: n50.name || 'Nifty 50',
              symbol: '^NSEI',
              price: n50Price,
              change: newChange,
              change_pct: newPct,
              change_percent: newPct,
            }
          })
        }

        const bnf = indices.find((idx: any) => isBankNifty(idx?.symbol) || isBankNifty(idx?.name))
        const bnfPrice = Number(bnf?.price)
        if (bnf && Number.isFinite(bnfPrice) && bnfPrice > 0) {
          setBankNifty(prev => {
            const rawChange = Number(bnf.change)
            const newChange = Number.isFinite(rawChange) ? rawChange : (prev?.change ?? 0)
            const rawPct = Number(bnf.change_pct ?? bnf.change_percent)
            const newPct = Number.isFinite(rawPct) ? rawPct : (prev?.change_pct ?? prev?.change_percent ?? 0)
            if (prev && prev.price === bnfPrice && prev.change === newChange && (prev.change_pct === newPct || prev.change_percent === newPct)) {
              return prev // Price unchanged: preserve reference and prevent re-render
            }
            return {
              name: bnf.name || 'Nifty Bank',
              symbol: '^NSEBANK',
              price: bnfPrice,
              change: newChange,
              change_pct: newPct,
              change_percent: newPct,
            }
          })
        }
      } catch (e: any) {
        if (e.name !== 'CanceledError' && e.message !== 'Request aborted' && e.code !== 'ERR_CANCELED') {
          console.error('Error fetching indices:', e)
        }
      }
    }

    // 1. Initial single consolidated request to seed ticker values
    fetchIndices()

    const supportsWs = isWebSocketSupportedOnHost()

    const startFallbackPolling = () => {
      if (!isMounted) return
      if (pollTimerRef.current === null) {
        // Fallback polling only when WebSocket is unavailable (30s interval, not per-second)
        pollTimerRef.current = window.setInterval(fetchIndices, 30000)
      }
    }

    const stopFallbackPolling = () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }

    const scheduleReconnect = () => {
      const token = localStorage.getItem('auth_token')
      if (!isMounted || !token || !supportsWs) return
      if (reconnectTimerRef.current !== null) return
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null
        if (isMounted) {
          connectWebSocket()
        }
      }, 5000)
    }

    const connectWebSocket = () => {
      const token = localStorage.getItem('auth_token')
      if (!isMounted || !token || !supportsWs) {
        startFallbackPolling()
        return
      }

      // Ensure any existing socket is completely dismantled before opening a new one
      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        try { ws.close() } catch (_) {}
        ws = null
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      try {
        ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

        ws.onopen = () => {
          if (!isMounted) return
          // Push-driven price updates active; stop fallback polling
          stopFallbackPolling()
          if (reconnectTimerRef.current !== null) {
            window.clearTimeout(reconnectTimerRef.current)
            reconnectTimerRef.current = null
          }
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol: '^NSEI' }))
            ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol: '^NSEBANK' }))
          }
        }

        ws.onerror = () => {
          if (!isMounted) return
          startFallbackPolling()
          // Do not schedule reconnect here; W3C WebSocket standard mandates onclose fires next.
        }

        ws.onclose = (event: CloseEvent) => {
          if (!isMounted) return
          startFallbackPolling()
          // Clear any pending reconnect timer and halt reconnect loop on auth failure
          if (event.code === 1008 || event.code === 4401 || event.code === 4003) {
            if (reconnectTimerRef.current !== null) {
              window.clearTimeout(reconnectTimerRef.current)
              reconnectTimerRef.current = null
            }
            console.warn('WebSocket authentication rejected (code ' + event.code + '). Halting reconnect loop.')
            return
          }
          scheduleReconnect()
        }

        ws.onmessage = (event) => {
          if (!isMounted) return
          try {
            const data = JSON.parse(event.data)
            const newPrice = Number(data.price)
            if (data.type === 'market_update' && Number.isFinite(newPrice) && newPrice > 0) {
              const symRaw = data.symbol || ''

              if (isNifty50(symRaw)) {
                setNifty(prev => {
                  const rawChange = Number(data.change)
                  const newChange = Number.isFinite(rawChange) ? rawChange : (prev?.change ?? 0)
                  const rawPct = Number(data.change_pct !== undefined ? data.change_pct : data.change_percent)
                  const newPct = Number.isFinite(rawPct) ? rawPct : (prev?.change_pct ?? prev?.change_percent ?? 0)
                  // Strictly price-change-driven: do not update if price and change remain identical
                  if (prev && prev.price === newPrice && prev.change === newChange && (prev.change_pct === newPct || prev.change_percent === newPct)) {
                    return prev
                  }
                  return {
                    name: prev?.name || 'Nifty 50',
                    symbol: '^NSEI',
                    price: newPrice,
                    change: newChange,
                    change_pct: newPct,
                    change_percent: newPct,
                  }
                })
              } else if (isBankNifty(symRaw)) {
                setBankNifty(prev => {
                  const rawChange = Number(data.change)
                  const newChange = Number.isFinite(rawChange) ? rawChange : (prev?.change ?? 0)
                  const rawPct = Number(data.change_pct !== undefined ? data.change_pct : data.change_percent)
                  const newPct = Number.isFinite(rawPct) ? rawPct : (prev?.change_pct ?? prev?.change_percent ?? 0)
                  // Strictly price-change-driven: do not update if price and change remain identical
                  if (prev && prev.price === newPrice && prev.change === newChange && (prev.change_pct === newPct || prev.change_percent === newPct)) {
                    return prev
                  }
                  return {
                    name: prev?.name || 'Nifty Bank',
                    symbol: '^NSEBANK',
                    price: newPrice,
                    change: newChange,
                    change_pct: newPct,
                    change_percent: newPct,
                  }
                })
              }
            }
          } catch (err) {
            console.error('WebSocket LiveTicker error:', err)
          }
        }
      } catch (e) {
        console.warn('WebSocket LiveTicker init skipped:', e)
        startFallbackPolling()
        scheduleReconnect()
      }
    }

    connectWebSocket()

    return () => {
      isMounted = false
      stopFallbackPolling()
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        try {
          if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
            ws.close()
          }
        } catch (_) {}
      }
    }
  }, [])

  // Symbol is passed via navigation STATE, not in the URL path
  const renderTicker = (data: IndexData | null, fallbackName: string, symbol: string) => {
    const linkProps = { to: '/chart', state: { symbol } }
    if (!data || data.price == null) {
      return (
        <NavLink {...linkProps} style={{ textDecoration: 'none', padding: '2px 8px', fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center' }}>
          {fallbackName}
        </NavLink>
      )
    }
    const change = Number(data.change ?? 0)
    const changePercent = Number(data.change_percent ?? data.change_pct ?? 0)
    const isPositive = change >= 0
    const color = isPositive ? 'var(--color-buy)' : 'var(--color-sell)'
    const arrow = isPositive ? '▲' : '▼'

    return (
      <NavLink {...linkProps} style={{ 
        textDecoration: 'none', 
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: '0px',
        lineHeight: 1.2
      }}>
        <span style={{ fontSize: '0.65rem', color: 'var(--color-text-muted)', fontWeight: 700, letterSpacing: '0.5px' }}>{data.name.toUpperCase()}</span>
        <span className="mono" style={{ color: color, fontSize: '0.85rem', fontWeight: 600 }}>{formatNumber2Dec(data.price)}</span>
        <span className="mono" style={{ color: color, fontSize: '0.7rem' }}>
          {arrow} {change > 0 ? '+' : ''}{change.toFixed(2)} ({changePercent.toFixed(2)}%)
        </span>
      </NavLink>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 24, marginRight: 'auto', alignItems: 'center' }} className="hide-on-mobile">
      {renderTicker(nifty, 'NIFTY 50', '^NSEI')}
      {renderTicker(bankNifty, 'NIFTY BANK', '^NSEBANK')}
    </div>
  )
}
