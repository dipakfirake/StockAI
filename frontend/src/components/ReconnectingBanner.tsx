import React, { useState, useEffect } from 'react';
import { RefreshCw, WifiOff } from 'lucide-react';

export const ReconnectingBanner: React.FC = () => {
  const [reconnecting, setReconnecting] = useState(false);
  const [attempt, setAttempt] = useState(1);
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' ? !navigator.onLine : false);

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

    const handleOnline = () => {
      setIsOffline(false);
      window.dispatchEvent(new CustomEvent('api_connection_state', { detail: { state: 'connected' } }));
    };

    const handleOffline = () => {
      setIsOffline(true);
    };

    window.addEventListener('api_connection_state', handleConnectionState);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('api_connection_state', handleConnectionState);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (hideTimer) clearTimeout(hideTimer);
    };
  }, []);

  if (!reconnecting && !isOffline) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 14,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        background: isOffline ? 'rgba(30, 20, 10, 0.95)' : 'rgba(15, 23, 42, 0.92)',
        backdropFilter: 'blur(12px)',
        border: isOffline ? '1px solid rgba(245, 158, 11, 0.5)' : '1px solid rgba(59, 130, 246, 0.4)',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
        padding: '6px 16px',
        borderRadius: '9999px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        color: isOffline ? '#f59e0b' : '#60a5fa',
        fontSize: '12.5px',
        fontWeight: 600,
        pointerEvents: 'none',
        animation: 'fadeIn 0.2s ease-in-out',
      }}
    >
      {isOffline ? (
        <>
          <WifiOff size={14} />
          <span>Internet disconnected. Reconnecting automatically when online...</span>
        </>
      ) : (
        <>
          <RefreshCw size={13} style={{ animation: 'spin 1.2s linear infinite' }} />
          <span>Reconnecting to live server (attempt {attempt}/3)...</span>
        </>
      )}
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
