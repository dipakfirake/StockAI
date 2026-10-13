/**
 * WebSocket client for real-time alert delivery with graceful HTTP fallback.
 */

export const isWebSocketSupportedOnHost = (): boolean => {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    // Vercel serverless edge rewrites do not support persistent WebSockets
    if (host.endsWith('vercel.app')) return false
  }
  return true
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

  connect(token: string) {
    if (!token) return

    // If host doesn't support persistent WebSockets or failed attempts exceeded, gracefully return
    if (!isWebSocketSupportedOnHost() || this.failedAttempts >= this.maxAttempts) {
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/ws?token=${encodeURIComponent(token)}`

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
          setTimeout(() => this.connect(token), this.reconnectDelay)
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
