import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi, preferencesApi } from './services/api';

interface User {
  id: string;
  email: string;
  name: string;
  subscription_tier: 'FREE' | 'PRO';
  is_admin?: boolean;
  pro_status?: string;
  pro_requested_at?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  /** All user preferences loaded from the server after login */
  preferences: Record<string, any>;
  login: (token: string, userData?: User) => Promise<void> | void;
  logout: () => void;
  upgradeToPro: () => void;
  reloadUser: () => Promise<void>;
  /** Persist one or more preferences to the backend and update context */
  savePreferences: (prefs: Record<string, any>) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  preferences: {},
  login: () => {},
  logout: () => {},
  upgradeToPro: () => {},
  reloadUser: async () => {},
  savePreferences: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Optimistically hydrate user from local storage cache so navbar and components never flash logged-out state
  const [user, setUser] = useState<User | null>(() => {
    try {
      const cached = localStorage.getItem('auth_user_cache');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });

  // FIX 1: Only start in loading=true when there is NO cached user.
  // If a user was cached (most common case after Fyers token update), loading=false
  // immediately so the NavBar never flickers blank during the background authApi.me()
  // roundtrip that happens during/after the Fyers token update endpoint.
  const [loading, setLoading] = useState<boolean>(() => {
    try {
      return !localStorage.getItem('auth_user_cache');
    } catch {
      return true;
    }
  });
  const [preferences, setPreferences] = useState<Record<string, any>>({});

  const loadUser = async () => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setUser(null);
      localStorage.removeItem('auth_user_cache');
      setLoading(false);
      return;
    }
    try {
      const res = await authApi.me();
      const freshData: User = res.data;

      // FIX 2: Never overwrite a valid cached display name with an empty/null value
      // from the server. Admin accounts may have an empty User.name column in the DB,
      // causing GET /auth/me to return name: "" → NavBar shows nothing.
      // Merge strategy: prefer the fresh non-empty name; fall back to cached name; last resort empty string.
      const merged: User = {
        ...freshData,
        name: (freshData?.name ?? '').trim() || user?.name || '',
      };
      setUser(merged);
      try {
        localStorage.setItem('auth_user_cache', JSON.stringify(merged));
      } catch {
        // Ignore storage write issues
      }

      // After confirming the user is valid, load their server-side preferences.
      // This is done in a parallel-safe way — a failure here must never block the app.
      try {
        const prefRes = await preferencesApi.get();
        setPreferences(prefRes.data ?? {});
      } catch {
        // Preferences are optional — degrade gracefully to localStorage-only state
      }
    } catch (err: any) {
      console.warn('Backend user profile check notice:', err?.message || err);
      // ONLY wipe auth_token if the backend explicitly rejected it as 401 Unauthorized.
      // Retain token and cached user on network disconnects, timeouts, or temporary
      // 502/503 server restarts (e.g. during Fyers stream restart) so users are NEVER booted out.
      if (err?.response?.status === 401) {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user_cache');
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUser();
  }, []);

  // FIX 3: Listen for the auth_session_expired custom event dispatched by the Axios
  // response interceptor on a genuine 401. This replaces window.location.href='/login'
  // (which causes a hard page reload, wiping the SPA and making the NavBar appear ghost)
  // with a graceful in-memory state reset and React Router SPA navigation.
  useEffect(() => {
    const handleSessionExpired = () => {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user_cache');
      setUser(null);
      setPreferences({});
      // SPA navigation — no page reload, no bundle re-download, no name flash
      if (window.location.pathname !== '/login') {
        window.history.pushState({}, '', '/login');
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
    };
    window.addEventListener('auth_session_expired', handleSessionExpired);
    return () => window.removeEventListener('auth_session_expired', handleSessionExpired);
  }, []);

  const login = async (token: string, userData?: User) => {
    localStorage.setItem('auth_token', token);
    if (userData) {
      // Instant hydration: user profile is already in the login response payload
      setUser(userData);
      try {
        localStorage.setItem('auth_user_cache', JSON.stringify(userData));
      } catch {
        // Ignore storage write issues
      }
      setLoading(false);
      // Non-blocking background fetch for user preferences so login transitions immediately
      preferencesApi.get()
        .then(prefRes => setPreferences(prefRes.data ?? {}))
        .catch(() => {});
      return;
    }
    // Fallback if userData was not provided
    await loadUser();
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user_cache');
    setUser(null);
    setPreferences({});
    // Seamless SPA navigation to /login without forcing a heavy page reload
    if (window.location.pathname !== '/login') {
      window.history.pushState({}, '', '/login');
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
  };

  const upgradeToPro = () => {
    if (user) {
      setUser({ ...user, subscription_tier: 'PRO' });
    }
  };

  /**
   * Persist preferences to the backend and update local context immediately.
   * Uses an optimistic update: the context is updated first (zero-latency feel),
   * then the server write happens in the background.
   */
  const savePreferences = useCallback(async (prefs: Record<string, any>) => {
    // Optimistic update — UI responds instantly
    setPreferences(prev => ({ ...prev, ...prefs }));
    try {
      const res = await preferencesApi.set(prefs);
      // Sync with the authoritative response from server
      setPreferences(res.data ?? {});
    } catch {
      // Server write failed silently — localStorage still has the value so the
      // user won't lose state within this session
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, preferences, login, logout, upgradeToPro, reloadUser: loadUser, savePreferences }}>
      {children}
    </AuthContext.Provider>
  );
};
