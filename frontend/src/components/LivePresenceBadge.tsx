import React from 'react'
import { usePresenceContext } from '../PresenceContext'

interface LivePresenceBadgeProps {
  compact?: boolean
  className?: string
  style?: React.CSSProperties
}

export default function LivePresenceBadge({ compact = false, className = '', style }: LivePresenceBadgeProps) {
  const { liveCount } = usePresenceContext()

  return (
    <div
      className={`live-presence-badge ${className}`}
      title={`${liveCount} active user${liveCount === 1 ? '' : 's'} live on StockAI`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: compact ? '4px' : '6px',
        padding: compact ? '2px 7px' : '3px 10px',
        borderRadius: '20px',
        background: 'rgba(34, 197, 94, 0.1)',
        border: '1px solid rgba(34, 197, 94, 0.25)',
        color: '#22c55e',
        fontSize: compact ? '0.72rem' : '0.78rem',
        fontWeight: 650,
        userSelect: 'none',
        flexShrink: 0,
        transition: 'all 0.2s ease',
        cursor: 'default',
        ...style,
      }}
    >
      <span
        style={{
          position: 'relative',
          display: 'flex',
          height: compact ? '6px' : '7px',
          width: compact ? '6px' : '7px',
        }}
      >
        <span
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            backgroundColor: '#22c55e',
            opacity: 0.75,
            animation: 'presence-ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite',
          }}
        />
        <span
          style={{
            position: 'relative',
            display: 'inline-flex',
            borderRadius: '50%',
            height: '100%',
            width: '100%',
            backgroundColor: '#22c55e',
            boxShadow: '0 0 6px rgba(34, 197, 94, 0.7)',
          }}
        />
      </span>
      <span>
        {liveCount} {compact ? 'Live' : 'Live'}
      </span>
      <style>{`
        @keyframes presence-ping {
          75%, 100% {
            transform: scale(2.2);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  )
}
