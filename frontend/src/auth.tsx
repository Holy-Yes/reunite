import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token, type User } from "./api";

type Ctx = { user: User | null; ready: boolean; signIn: (t: string, u: User) => void; signOut: () => void; refresh: () => Promise<void> };
const Auth = createContext<Ctx>({ user: null, ready: false, signIn: () => {}, signOut: () => {}, refresh: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const refresh = useCallback(async () => {
    if (!token.get()) { setUser(null); return; }
    try { setUser(await api.me()); } catch { setUser(null); }
  }, []);
  useEffect(() => { void refresh().finally(() => setReady(true)); }, [refresh]);
  useEffect(() => {
    const off = () => setUser(null);
    window.addEventListener("reunite:signout", off);
    return () => window.removeEventListener("reunite:signout", off);
  }, []);
  return (
    <Auth.Provider value={{
      user, ready, refresh,
      signIn: (t, u) => { token.set(t); setUser(u); },
      signOut: () => { token.set(null); setUser(null); },
    }}>{children}</Auth.Provider>
  );
}
export const useAuth = () => useContext(Auth);
