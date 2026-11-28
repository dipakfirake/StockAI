/**
 * WebSocket client for real-time alert and market delivery using short-lived 45s tickets
 * so persistent JWTs never sit in localStorage or appear in WebSocket URLs.
 */
import { authApi } from './api'

export const isWebSocketSupportedOnHost = (): boolean => {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    // Vercel serverless edge rewrites do not support persistent WebSockets
    if (host.endsWith('vercel.app')) return false
  }
  return true
}

let _pendingTicketPromise: Promise<string | null> | null = null

export async function fetchWsTicketUrl(): Promise<string | null> {
  if (typeof window === 'undefined' || !isWebSocketSupportedOnHost()) return null
  if (!_pendingTicketPromise) {
    _pendingTicketPromise = authApi
      .getWsTicket()
      .then((res) => res.data?.ws_ticket || null)
      .catch(() => null)
      .finally(() => {
        setTimeout(() => {
          _pendingTicketPromise = null
        }, 1500)
      })
  }
  const ticket = await _pendingTicketPromise
  if (!ticket) return null
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/?ticket=${encodeURIComponent(ticket)}`
}

type AlertHandler = (alert: object) => void

class AlertWebSocket {
  private ws: WebSocket | null = null
  private handlers: AlertHandler[] = []
  private reconnectDelay = 5000
  private shouldReconnect = true
  private pingTimer: number | null = null
  private failedAttempts = 0
  private maxAttempts = 2

  async connect(_unusedToken?: string) {
    // If host doesn't support persistent WebSockets or failed attempts exceeded, gracefully return
    if (!isWebSocketSupportedOnHost() || this.failedAttempts >= this.maxAttempts) {
      return
    }

    const url = await fetchWsTicketUrl()
    if (!url) return

    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.failedAttempts = 0
        this.ping()
      }

      this.ws.onmessage = (event) => {
        if (event.data === 'pong') return
        try {
          const payload = JSON.parse(event.data)
          this.handlers.forEach((handler) => handler(payload))
        } catch {
          // ignore malformed messages
        }
      }

      this.ws.onclose = () => {
        this.failedAttempts++
        if (this.shouldReconnect && this.failedAttempts < this.maxAttempts) {
          setTimeout(() => this.connect(), this.reconnectDelay)
        }
      }

      this.ws.onerror = () => {
        this.failedAttempts++
      }
    } catch {
      this.failedAttempts++
    }
  }

  private ping() {
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer)
    this.pingTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping')
      }
    }, 30000)
  }

  onAlert(handler: AlertHandler) {
    this.handlers.push(handler)
  }

  disconnect() {
    this.shouldReconnect = false
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer)
    this.pingTimer = null
    this.ws?.close()
  }
}

export const alertWebSocket = new AlertWebSocket()
