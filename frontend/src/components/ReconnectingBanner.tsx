import React, { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';

export const ReconnectingBanner: React.FC = () => {
  const [reconnecting, setReconnecting] = useState(false);
  const [attempt, setAttempt] = useState(1);

  useEffect(() => {
    let hideTimer: any = null;

    const handleConnectionState = (e: any) => {
      const state = e.detail?.state;
      if (state === 'reconnecting') {
        if (hideTimer) clearTimeout(hideTimer);
        setAttempt(e.detail?.attempt || 1);
        setReconnecting(true);
      } else if (state === 'connected') {
        // Small delay to prevent flashing
        hideTimer = setTimeout(() => {
          setReconnecting(false);
        }, 600);
      }
    };

    window.addEventListener('api_connection_state', handleConnectionState);
    return () => {
      window.removeEventListener('api_connection_state', handleConnectionState);
      if (hideTimer) clearTimeout(hideTimer);
    };
  }, []);

  if (!reconnecting) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 14,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        background: 'rgba(15, 23, 42, 0.92)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(59, 130, 246, 0.4)',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
        padding: '6px 16px',
        borderRadius: '9999px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        color: '#60a5fa',
        fontSize: '12.5px',
        fontWeight: 600,
        pointerEvents: 'none',
        animation: 'fadeIn 0.2s ease-in-out',
      }}
    >
      <RefreshCw size={13} style={{ animation: 'spin 1.2s linear infinite' }} />
      <span>Reconnecting to live server (attempt {attempt}/3)...</span>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translate(-50%, -8px); }
          to { opacity: 1; transform: translate(-50%, 0); }
        }
      `}</style>
    </div>
  );
};
