import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { User, getCurrentUser, logout as apiLogout } from '../api/client';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  needsSetup: boolean;
  passwordChangeRequired: boolean;
  login: (user: User) => void;
  logout: () => Promise<void>;
  clearPasswordChangeRequired: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [passwordChangeRequired, setPasswordChangeRequired] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const currentUser = await getCurrentUser();
      if (currentUser) {
        setUser(currentUser);
        setNeedsSetup(false);
        setPasswordChangeRequired(currentUser.password_change_required ?? false);
      } else {
        // Check if setup is needed by trying to access the setup endpoint
        const response = await fetch(
          `${import.meta.env.VITE_API_URL || ''}/api/auth/setup`,
          { method: 'GET' }
        );
        // If GET returns 200 with needs_setup, then setup is required
        if (response.ok) {
          const data = await response.json();
          setNeedsSetup(data.needs_setup === true);
        } else {
          setNeedsSetup(false);
        }
      }
    } catch (err) {
      console.error('Auth check failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const login = useCallback((user: User) => {
    setUser(user);
    setNeedsSetup(false);
    setPasswordChangeRequired(user.password_change_required ?? false);
  }, []);

  const clearPasswordChangeRequired = useCallback(() => {
    setPasswordChangeRequired(false);
    if (user) {
      setUser({ ...user, password_change_required: false });
    }
  }, [user]);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, needsSetup, passwordChangeRequired, login, logout, clearPasswordChangeRequired }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
