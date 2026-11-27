import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  Volume2,
  VolumeX,
  CheckCheck,
  ArrowRight,
  Bot,
  Megaphone,
  CheckCircle2,
  Zap,
  BellRing,
} from 'lucide-react'
import { notificationsApi } from '../services/api'
import {
  isNotifSoundEnabled,
  setNotifSoundEnabled,
  isNotifPushEnabled,
  setNotifPushEnabled,
  requestDesktopPushPermission,
  playNotificationChime,
  triggerDesktopPushNotification,
} from '../utils/notificationSound'

interface NotificationBellProps {
  compact?: boolean
}

export default function NotificationBell({ compact = false }: NotificationBellProps) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<any[]>([])
  const [unseenCount, setUnseenCount] = useState<number>(0)
  const [unreadCount, setUnreadCount] = useState<number>(0)
  const [soundOn, setSoundOn] = useState<boolean>(() => isNotifSoundEnabled())
  const [pushOn, setPushOn] = useState<boolean>(() => isNotifPushEnabled())
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const prevUnseenRef = useRef<number | null>(null)
  const seenToastIdsRef = useRef<Set<number>>(new Set())

  const fetchNotifications = async (notifyIfIncreased: boolean = true) => {
    try {
      const res = await notificationsApi.list({ limit: 20 })
      const list: any[] = res.data?.notifications || []
      const nextUnseen = Number(res.data?.unseen_count ?? 0)
      const nextUnread = Number(res.data?.unread_count ?? 0)

      if (
        notifyIfIncreased &&
        prevUnseenRef.current !== null &&
        nextUnseen > prevUnseenRef.current &&
        list.length > 0
      ) {
        const newest = list.find((n) => !n.is_seen && !seenToastIdsRef.current.has(n.id)) || list[0]
        if (newest && !seenToastIdsRef.current.has(newest.id)) {
          seenToastIdsRef.current.add(newest.id)
          triggerDesktopPushNotification({
            title: newest.title || 'StockAI Notification',
            body: newest.message || '',
            severity: newest.priority || 'INFO',
            tag: `notif-${newest.id}`,
            url: newest.metadata?.link || '/alerts?tab=INBOX',
          })
        }
      }

      prevUnseenRef.current = nextUnseen
      setItems(list)
      setUnseenCount(nextUnseen)
      setUnreadCount(nextUnread)
    } catch {
      // Ignore network hiccups while polling notifications
    }
  }

  useEffect(() => {
    fetchNotifications(false)

    const timer = window.setInterval(() => fetchNotifications(true), 25000)
    const onUpdate = () => fetchNotifications(false)
    const onPrefs = () => {
      setSoundOn(isNotifSoundEnabled())
      setPushOn(isNotifPushEnabled())
    }
    const onFocus = () => fetchNotifications(true)

    window.addEventListener('stockai:notifications-updated', onUpdate)
    window.addEventListener('stockai:notif-prefs-changed', onPrefs)
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('stockai:notifications-updated', onUpdate)
      window.removeEventListener('stockai:notif-prefs-changed', onPrefs)
      window.removeEventListener('focus', onFocus)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const handleOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  const handleToggleSound = () => {
    const next = !soundOn
    setNotifSoundEnabled(next)
    setSoundOn(next)
    if (next) playNotificationChime('INFO')
  }

  const handleTogglePush = async () => {
    if (pushOn) {
      setNotifPushEnabled(false)
      setPushOn(false)
      return
    }
    const granted = await requestDesktopPushPermission()
    setPushOn(granted)
    if (granted) {
      triggerDesktopPushNotification({
        title: '🔔 StockAI Desktop Alerts Enabled',
        body: 'You will now receive real-time alerts for System Auto-Sells and critical market notices.',
        severity: 'HIGH',
        tag: 'stockai-push-test',
      })
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllRead()
      setUnseenCount(0)
      setUnreadCount(0)
      prevUnseenRef.current = 0
      setItems((prev) => prev.map((it) => ({ ...it, is_seen: true, is_read: true })))
      window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
    } catch {
      // ignore
    }
  }

  const handleOpenInboxTab = () => {
    setOpen(false)
    navigate('/alerts?tab=INBOX')
  }

  const handleOpenNotificationItem = async (n: any) => {
    try {
      if (!n.is_read) {
        await notificationsApi.markRead(n.id)
      }
      window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
    } catch {
      // ignore
    }
    setOpen(false)
    navigate(n.metadata?.link || '/alerts?tab=INBOX')
  }

  const renderCategoryBadge = (cat: string) => {
    switch (cat) {
      case 'AUTO_SELL':
        return { label: 'Auto-Sold', bg: 'rgba(16, 185, 129, 0.16)', color: '#34d399', icon: <Bot size={11} /> }
      case 'ORDER_FILL':
        return { label: 'Order Filled', bg: 'rgba(59, 130, 246, 0.16)', color: '#60a5fa', icon: <CheckCircle2 size={11} /> }
      case 'SYSTEM_NOTICE':
        return { label: 'System', bg: 'rgba(168, 85, 247, 0.16)', color: '#c084fc', icon: <Megaphone size={11} /> }
      default:
        return { label: 'Alert', bg: 'rgba(245, 158, 11, 0.16)', color: '#fbbf24', icon: <Zap size={11} /> }
    }
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={`Notifications (${unseenCount} unseen)`}
        title={
          unseenCount > 0
            ? `${unseenCount} unseen notification${unseenCount > 1 ? 's' : ''} — click to preview or open Notifications tab`
            : 'Notifications & Auto-Sell Alerts'
        }
        style={{
          position: 'relative',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 5,
          padding: compact ? '6px 8px' : '6px 10px',
          borderRadius: '8px',
          border: `1px solid ${unseenCount > 0 ? 'rgba(239, 68, 68, 0.45)' : 'var(--color-border)'}`,
          background: open
            ? 'rgba(59, 130, 246, 0.16)'
            : unseenCount > 0
            ? 'rgba(239, 68, 68, 0.08)'
            : 'var(--color-bg-card)',
          color: unseenCount > 0 ? '#f87171' : 'var(--color-text-primary)',
          cursor: 'pointer',
          transition: 'all 0.15s ease',
        }}
      >
        <Bell size={compact ? 17 : 18} />
        {!compact && <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Inbox</span>}
        {unseenCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: -6,
              right: -6,
              minWidth: 18,
              height: 18,
              padding: '0 5px',
              borderRadius: 999,
              background: '#ef4444',
              color: '#ffffff',
              fontSize: 10,
              fontWeight: 800,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 0 2px var(--color-bg-secondary)',
              lineHeight: 1,
            }}
          >
            {unseenCount > 99 ? '99+' : unseenCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: 'fixed',
            top: compact ? 58 : 62,
            right: compact ? 8 : 20,
            width: 'min(410px, calc(100vw - 16px))',
            maxHeight: '78vh',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 12,
            boxShadow: '0 20px 45px rgba(0, 0, 0, 0.55)',
            zIndex: 10050,
            overflow: 'hidden',
          }}
        >
          {/* Popover Header */}
          <div
            style={{
              padding: '12px 14px',
              borderBottom: '1px solid var(--color-border)',
              background: 'var(--color-bg-secondary)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Bell size={15} style={{ color: 'var(--color-accent-blue)' }} />
                <span>Notifications</span>
                {unseenCount > 0 && (
                  <span style={{ background: '#ef4444', color: '#fff', fontSize: 10, padding: '1px 7px', borderRadius: 999, fontWeight: 800 }}>
                    {unseenCount} New
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Red marker stays until Notifications tab is opened
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                onClick={handleToggleSound}
                title={soundOn ? 'Sound Chime ON (click to mute)' : 'Sound Chime OFF (click to enable)'}
                style={{
                  background: soundOn ? 'rgba(59, 130, 246, 0.16)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${soundOn ? 'rgba(59,130,246,0.4)' : 'var(--color-border)'}`,
                  color: soundOn ? '#60a5fa' : 'var(--color-text-muted)',
                  borderRadius: 6,
                  padding: '4px 7px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                }}
              >
                {soundOn ? <Volume2 size={13} /> : <VolumeX size={13} />}
              </button>

              <button
                type="button"
                onClick={handleTogglePush}
                title={pushOn ? 'Desktop Push ON' : 'Enable Desktop Push Alerts'}
                style={{
                  background: pushOn ? 'rgba(16, 185, 129, 0.16)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${pushOn ? 'rgba(16,185,129,0.4)' : 'var(--color-border)'}`,
                  color: pushOn ? '#34d399' : 'var(--color-text-muted)',
                  borderRadius: 6,
                  padding: '4px 7px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                <BellRing size={13} />
                <span>{pushOn ? 'Push ON' : 'Push'}</span>
              </button>
            </div>
          </div>

          {/* Notification Items Preview List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {items.length === 0 ? (
              <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13 }}>
                No notifications yet. System auto-sells, order fills, and system notices will appear here.
              </div>
            ) : (
              items.slice(0, 12).map((n) => {
                const badge = renderCategoryBadge(n.category)
                const isUnread = !n.is_read
                return (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => handleOpenNotificationItem(n)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background: !n.is_seen
                        ? 'rgba(239, 68, 68, 0.06)'
                        : isUnread
                        ? 'rgba(59, 130, 246, 0.05)'
                        : 'transparent',
                      border: 'none',
                      borderBottom: '1px solid var(--color-border)',
                      borderLeft: !n.is_seen
                        ? '3px solid #ef4444'
                        : isUnread
                        ? '3px solid var(--color-accent-blue)'
                        : '3px solid transparent',
                      padding: '10px 14px',
                      cursor: 'pointer',
                      color: 'var(--color-text-primary)',
                      display: 'block',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: 4,
                          background: badge.bg,
                          color: badge.color,
                        }}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                      <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                        {n.created_at_ist || (n.created_at ? new Date(n.created_at).toLocaleString() : '')}
                      </span>
                    </div>
                    <div style={{ fontWeight: isUnread ? 700 : 600, fontSize: 13, marginBottom: 3 }}>
                      {n.title}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.35 }}>
                      {n.message}
                    </div>
                  </button>
                )
              })
            )}
          </div>

          {/* Popover Footer */}
          <div
            style={{
              padding: '10px 14px',
              borderTop: '1px solid var(--color-border)',
              background: 'var(--color-bg-secondary)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={unreadCount === 0 && unseenCount === 0}
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: '5px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
            >
              <CheckCheck size={14} /> Mark All Read
            </button>

            <button
              type="button"
              onClick={handleOpenInboxTab}
              className="btn btn-primary"
              style={{ fontSize: 12, padding: '6px 12px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
            >
              <span>Open Notifications Tab</span>
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
