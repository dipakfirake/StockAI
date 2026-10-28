import { useState, useEffect, useRef, useCallback } from 'react'
import { presenceApi } from '../services/api'

export interface LiveUserSession {
  session_id: string
  user_id?: string | null
  user_name: string
  user_email?: string | null
  role: 'ADMIN' | 'PRO' | 'FREE' | 'GUEST'
  path: string
  device: string
  last_seen_seconds_ago: number
}

/**
 * Ultra-efficient hook to track real-time live users online.
 * Synchronizes with backend Redis in-memory storage (0 database queries).
 * Heartbeat every 4 seconds when active; instant leave on mobile recents / tab switch.
 */
export function usePresence(user: any) {
  const [liveCount, setLiveCount] = useState<number>(1)
  const [liveUsers, setLiveUsers] = useState<LiveUserSession[]>([])
  const [loadingUsers, setLoadingUsers] = useState<boolean>(false)
  const sessionIdRef = useRef<string>('')

  // Persistent unique session ID per tab
  if (!sessionIdRef.current) {
    try {
      let stored = sessionStorage.getItem('stockai_presence_session_id')
      if (!stored) {
        stored = `sess_${Math.random().toString(36).substring(2, 9)}_${Date.now().toString(36)}`
        sessionStorage.setItem('stockai_presence_session_id', stored)
      }
      sessionIdRef.current = stored
    } catch {
      sessionIdRef.current = `sess_${Math.random().toString(36).substring(2, 9)}_${Date.now().toString(36)}`
    }
  }

  const sendHeartbeat = useCallback(async () => {
    const sessionId = sessionIdRef.current
    if (!sessionId || document.visibilityState === 'hidden') return

    const isAdmin = Boolean(user?.is_admin)
    const role: 'ADMIN' | 'PRO' | 'FREE' | 'GUEST' = isAdmin
      ? 'ADMIN'
      : user?.subscription_tier === 'PRO'
      ? 'PRO'
      : user
      ? 'FREE'
      : 'GUEST'

    const isMobile = /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
    const payload = {
      session_id: sessionId,
      user_id: user?.id || null,
      user_name: user?.name || `Guest #${sessionId.slice(-4)}`,
      user_email: user?.email || null,
      role,
      path: window.location.pathname || '/',
      device: isMobile ? 'Mobile' : 'Desktop',
    }

    try {
      const res = await fetch('/api/presence/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        if (typeof data.count === 'number' && data.count > 0) {
          setLiveCount(data.count)
        }
      }
    } catch {
      // Non-blocking in-memory heartbeat
    }
  }, [user])

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
      // Browser unload silent safety
    }
  }, [])

  // Admin function to fetch list of live active users from Redis (0 DB queries)
  const fetchLiveUsers = useCallback(async () => {
    setLoadingUsers(true)
    try {
      const res = await presenceApi.getUsers()
      if (res.data) {
        if (Array.isArray(res.data.users)) {
          setLiveUsers(res.data.users)
        }
        if (typeof res.data.count === 'number') {
          setLiveCount(res.data.count)
        }
      }
    } catch (err) {
      console.debug('Failed to fetch live users list:', err)
    } finally {
      setLoadingUsers(false)
    }
  }, [])

  useEffect(() => {
    // 1. Initial heartbeat
    if (document.visibilityState === 'visible') {
      sendHeartbeat()
    }

    // 2. Mobile App Switcher & Tab Switch detection via Page Visibility API
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        sendLeaveBeacon()
      } else if (document.visibilityState === 'visible') {
        sendHeartbeat()
      }
    }

    // 3. Tab close & reload listeners
    const handlePageHide = () => {
      sendLeaveBeacon()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('pagehide', handlePageHide)
    window.addEventListener('beforeunload', handlePageHide)

    // 4. Ultra-lightweight 25-second heartbeat cadence while visible (prevents app slowdown)
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        sendHeartbeat()
      }
    }, 25000)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('pagehide', handlePageHide)
      window.removeEventListener('beforeunload', handlePageHide)
      clearInterval(interval)
      sendLeaveBeacon()
    }
  }, [sendHeartbeat, sendLeaveBeacon])

  return { liveCount, liveUsers, fetchLiveUsers, loadingUsers }
}
