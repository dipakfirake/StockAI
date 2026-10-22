import { useState, useEffect, useRef, useCallback } from 'react'

/**
 * Hook to track live active presence on the platform.
 * Synchronizes presence with backend Redis sliding-window ZSET.
 * Automatically signals "leave" immediately when:
 * 1. User switches tabs (document.visibilityState === 'hidden')
 * 2. Mobile browser is moved to "Recent Apps" / App Switcher
 * 3. Browser tab or window is closed (pagehide / beforeunload)
 * Automatically signals "heartbeat" immediately when user returns/focuses.
 */
export function usePresence() {
  const [liveCount, setLiveCount] = useState<number>(1)
  const sessionIdRef = useRef<string>('')

  // Initialize or retrieve persistent session ID per tab
  if (!sessionIdRef.current) {
    try {
      let stored = sessionStorage.getItem('stockai_presence_session_id')
      if (!stored) {
        stored = `sess_${Math.random().toString(36).substring(2, 10)}_${Date.now().toString(36)}`
        sessionStorage.setItem('stockai_presence_session_id', stored)
      }
      sessionIdRef.current = stored
    } catch {
      sessionIdRef.current = `sess_${Math.random().toString(36).substring(2, 10)}_${Date.now().toString(36)}`
    }
  }

  const sendHeartbeat = useCallback(async () => {
    const sessionId = sessionIdRef.current
    if (!sessionId || document.visibilityState === 'hidden') return

    try {
      const res = await fetch('/api/presence/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      })
      if (res.ok) {
        const data = await res.json()
        if (typeof data.count === 'number' && data.count > 0) {
          setLiveCount(data.count)
        }
      }
    } catch (err) {
      // Non-blocking background heartbeat
    }
  }, [])

  const sendLeaveBeacon = useCallback(() => {
    const sessionId = sessionIdRef.current
    if (!sessionId) return

    const url = '/api/presence/leave'
    const payload = JSON.stringify({ session_id: sessionId })

    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' })
        navigator.sendBeacon(url, blob)
      } else {
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true,
        }).catch(() => {})
      }
    } catch {
      // Fallback silent catch for browser unload safety
    }
  }, [])

  useEffect(() => {
    // 1. Initial heartbeat on mount if visible
    if (document.visibilityState === 'visible') {
      sendHeartbeat()
    }

    // 2. Mobile App Switcher & Tab Switch detection via Page Visibility API
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        // User switched tab or moved mobile browser into Recent Apps overview
        sendLeaveBeacon()
      } else if (document.visibilityState === 'visible') {
        // User switched back or reopened app from Recent Apps
        sendHeartbeat()
      }
    }

    // 3. Tab close, reload, or page navigation events
    const handlePageHide = () => {
      sendLeaveBeacon()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('pagehide', handlePageHide)
    window.addEventListener('beforeunload', handlePageHide)

    // 4. Periodic keep-alive heartbeat every 10 seconds while tab remains active & visible
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        sendHeartbeat()
      }
    }, 10000)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('pagehide', handlePageHide)
      window.removeEventListener('beforeunload', handlePageHide)
      clearInterval(interval)
      sendLeaveBeacon()
    }
  }, [sendHeartbeat, sendLeaveBeacon])

  return { liveCount }
}
