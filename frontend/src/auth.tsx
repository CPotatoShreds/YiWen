// 认证上下文：token 管理 + 当前用户
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken, setToken } from "./api";

export interface User {
  id: number;
  username: string;
  exp: number; // 见闻：唯一养成属性
  rank_points: number; // 名望：天梯分
  max_loadouts: number; // 按见闻解锁的奇人槽位上限
  reveal_on_miss: boolean;
  is_admin: boolean;
}

interface AuthCtx {
  user: User | null;
  initializing: boolean;
  login: (u: string, p: string) => Promise<void>;
  register: (u: string, p: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // 挂载时用 localStorage 里的 token 恢复会话（刷新不登出）；恢复完成前不发任何路由跳转
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    if (getToken()) {
      api<User>("/auth/me")
        .then(setUser)
        .catch(() => setUser(null))
        .finally(() => setInitializing(false));
    } else {
      setInitializing(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);

  async function login(username: string, password: string) {
    const r = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(r.access_token);
    await refresh();
  }

  async function register(username: string, password: string) {
    await api("/auth/register", { method: "POST", body: JSON.stringify({ username, password }) });
    await login(username, password);
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  return (
    <Ctx.Provider value={{ user, initializing, login, register, logout, refresh }}>{children}</Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
