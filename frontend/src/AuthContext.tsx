import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi, preferencesApi } from './services/api';

interface User {
  id: string;
  email: string;
  name: string;
  subscription_tier: 'FREE' | 'PRO';
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  /** All user preferences loaded from the server after login */
  preferences: Record<string, any>;
  login: (token: string) => void;
  logout: () => void;
  upgradeToPro: () => void;
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
  savePreferences: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [preferences, setPreferences] = useState<Record<string, any>>({});

  const loadUser = async () => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await authApi.me();
      setUser(res.data);

      // After confirming the user is valid, load their server-side preferences.
      // This is done in parallel-safe way — a failure here must never block the app.
      try {
        const prefRes = await preferencesApi.get();
        setPreferences(prefRes.data ?? {});
      } catch {
        // Preferences are optional — degrade gracefully to localStorage-only state
      }
    } catch (err) {
      console.error('Failed to load user', err);
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUser();
  }, []);

  const login = async (token: string) => {
    localStorage.setItem('auth_token', token);
    await loadUser();
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    setPreferences({});
    window.location.href = '/login';
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
    <AuthContext.Provider value={{ user, loading, preferences, login, logout, upgradeToPro, savePreferences }}>
      {children}
    </AuthContext.Provider>
  );
};
