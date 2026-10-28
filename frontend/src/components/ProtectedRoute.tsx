import { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const location = useLocation();

  // If loading and there is NO cached user, show a smooth dark-mode spinner
  if (loading && !localStorage.getItem('auth_user_cache')) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        gap: '16px',
        color: 'var(--color-text-secondary, #94a3b8)'
      }}>
        <div style={{
          width: '36px',
          height: '36px',
          border: '3px solid rgba(59, 130, 246, 0.2)',
          borderTop: '3px solid #3b82f6',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>Authenticating session...</span>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // If neither memory user nor localStorage auth token exists, redirect to login
  if (!user && !localStorage.getItem('auth_token')) {
    const returnUrl = location.pathname !== '/login' ? location.pathname : '/dashboard';
    return <Navigate to={`/login?redirect=${encodeURIComponent(returnUrl)}`} replace />;
  }

  return <>{children}</>;
}
