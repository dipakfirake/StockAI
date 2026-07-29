/**
 * WebSocket client for real-time alert delivery.
 */

type AlertHandler = (alert: object) => void

class AlertWebSocket {
  private ws: WebSocket | null = null
  private handlers: AlertHandler[] = []
  private reconnectDelay = 3000
  private shouldReconnect = true

  connect(token: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/ws/alerts?token=${token}`

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('[WS] Connected to alert stream')
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
      console.log('[WS] Disconnected')
      if (this.shouldReconnect) {
        setTimeout(() => this.connect(token), this.reconnectDelay)
      }
    }

    this.ws.onerror = (err) => console.error('[WS] Error', err)
  }

  private ping() {
    setInterval(() => {
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
    this.ws?.close()
  }
}

export const alertWebSocket = new AlertWebSocket()
