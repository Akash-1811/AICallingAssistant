import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, Outlet } from "react-router-dom";

export type AuthUser = {
  id: string;
  email: string;
  display_name: string | null;
};

type AuthResponse = { access_token: string; user: AuthUser };

const TOKEN_KEY = "auth_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function authRequest(path: string, body: Record<string, unknown>): Promise<AuthResponse> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || "Request failed");
  return data as AuthResponse;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const saveSession = useCallback((nextToken: string, nextUser: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  useEffect(() => {
    const saved = getStoredToken();
    if (!saved) {
      setLoading(false);
      return;
    }
    void fetch("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${saved}`, Accept: "application/json" },
    })
      .then((res) => (res.ok ? (res.json() as Promise<AuthUser>) : null))
      .then((me) => {
        if (me) saveSession(saved, me);
        else clearStoredToken();
      })
      .finally(() => setLoading(false));
  }, [saveSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await authRequest("/api/v1/auth/login", { email, password });
      saveSession(data.access_token, data.user);
    },
    [saveSession]
  );

  const signup = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const body: Record<string, unknown> = { email, password };
      if (displayName?.trim()) body.display_name = displayName.trim();
      const data = await authRequest("/api/v1/auth/signup", body);
      saveSession(data.access_token, data.user);
    },
    [saveSession]
  );

  const logout = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, signup, logout }),
    [user, token, loading, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

function AuthGate({ guest }: { guest?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <p>Loading…</p>;
  if (guest ? user : !user) return <Navigate to={guest ? "/" : "/login"} replace />;
  return <Outlet />;
}

export function ProtectedRoute() {
  return <AuthGate />;
}

export function GuestRoute() {
  return <AuthGate guest />;
}
