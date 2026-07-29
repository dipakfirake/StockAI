import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from './services/api';

interface User {
  id: string;
  email: string;
  name: string;
  subscription_tier: 'FREE' | 'PRO';
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (token: string) => void;
  logout: () => void;
  upgradeToPro: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
  upgradeToPro: () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = async () => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await authApi.me();
      setUser(res.data);
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
    window.location.href = '/login';
  };

  const upgradeToPro = () => {
    if (user) {
      setUser({ ...user, subscription_tier: 'PRO' });
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, upgradeToPro }}>
      {children}
    </AuthContext.Provider>
  );
};
