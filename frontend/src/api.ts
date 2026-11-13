import { queryClient } from "./queryClient";
// 传输负责 Cookie、续签与超时；服务端数据缓存由 TanStack Query 统一管理。
export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const CONNECT_TIMEOUT_MS = 15000;
const GET_RETRIES = 2;
const CACHE_TTL_MS = 30_000;

export class ApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// 状态敏感的读路径用短 TTL：跨场进度随推演结果变化，短暂过期可接受且后台自愈
const CACHE_TTL_BY_PREFIX: [string, number][] = [["/scenarios", 10_000]];

function ttlFor(path: string): number {
  for (const [prefix, ttl] of CACHE_TTL_BY_PREFIX) {
    if (path.startsWith(prefix)) return ttl;
  }
  return CACHE_TTL_MS;
}

function cachePolicyFor(path: string): "cache" | "skip" {
  if (path.includes("?")) return "skip"; // 带查询参数的结果随条件变化，不缓存
  if (path.startsWith("/admin/")) return "skip"; // 管理工具要实时
  if (path.startsWith("/scenario-challenges/")) return "skip"; // 小天下集进行中推演，SSE 实时驱动
  return "cache";
}

export function clearApiCache(): void {
  queryClient.clear();
}

function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    // AppError 信封：{detail: 文案, code: 错误码}（code 供后续按码分支，此处只取文案）
    const envelope = detail as { detail?: unknown };
    if (typeof envelope.detail === "string") return envelope.detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") return item.msg;
        return String(item);
      })
      .join("；");
  }
  return detail == null ? `HTTP ${status}` : String(detail);
}

// ── 401 自动续签：access 过期时先调 /auth/refresh（refresh cookie 限路径自动携带），成功则重放原请求 ──
let refreshingSession: Promise<boolean> | null = null;

function tryRefreshSession(): Promise<boolean> {
  if (!refreshingSession) {
    refreshingSession = rawFetch<void>("/auth/refresh", { method: "POST" }, CONNECT_TIMEOUT_MS, "POST")
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        refreshingSession = null;
      });
  }
  return refreshingSession;
}

async function fetchWithAuth<T>(path: string, fetchOpts: RequestInit, connectTimeout: number, method: string): Promise<T> {
  try {
    return await rawFetch<T>(path, fetchOpts, connectTimeout, method);
  } catch (error) {
    // /auth/* 自身的 401 就是"该重新登录了"，不进入续签循环
    if (error instanceof ApiError && error.status === 401 && !path.startsWith("/auth/") && (await tryRefreshSession())) {
      return rawFetch<T>(path, fetchOpts, connectTimeout, method);
    }
    throw error;
  }
}

async function rawFetch<T>(path: string, fetchOpts: RequestInit, connectTimeout: number, method: string): Promise<T> {
  const maxAttempts = method === "GET" ? GET_RETRIES + 1 : 1;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const ctrl = new AbortController();
    const cancel = () => ctrl.abort(fetchOpts.signal?.reason);
    if (fetchOpts.signal?.aborted) cancel();
    else fetchOpts.signal?.addEventListener("abort", cancel, { once: true });
    const timer = window.setTimeout(() => ctrl.abort(), connectTimeout);
    try {
      const headers = new Headers(fetchOpts.headers);
      if (fetchOpts.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      const res = await fetch(`${API_BASE}${path}`, { ...fetchOpts, headers, credentials: "include", signal: ctrl.signal });
      if (!res.ok) {
        let detail: unknown;
        try {
          detail = (await res.json()).detail;
        } catch {
          detail = undefined;
        }
        throw new ApiError(res.status, detailMessage(detail, res.status));
      }
      if (res.status === 204 || res.status === 205) return null as T;
      return await res.json() as T;
    } catch (error) {
      if (fetchOpts.signal?.aborted) throw error;
      const retryable = method === "GET" && attempt < maxAttempts - 1 && !(error instanceof ApiError);
      if (retryable) {
        await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
        continue;
      }
      // 连接超时主动 abort：把浏览器原始 DOMException 换成可读文案，不把 "signal is aborted" 抛给界面
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError(0, "请求超时，请稍后重试");
      }
      throw error instanceof Error ? error : new Error(String(error));
    } finally {
      window.clearTimeout(timer);
      fetchOpts.signal?.removeEventListener("abort", cancel);
    }
  }
  throw new Error("请求失败");
}

export async function request<T>(path: string, opts: RequestInit & { timeout?: number } = {}): Promise<T> {
  const { timeout, ...fetchOpts } = opts;
  return fetchWithAuth<T>(path, fetchOpts, timeout ?? CONNECT_TIMEOUT_MS, (opts.method || "GET").toUpperCase());
}

export async function api<T>(path: string, opts: RequestInit & { timeout?: number } = {}): Promise<T> {
  const { timeout, ...fetchOpts } = opts;
  const connectTimeout = timeout ?? CONNECT_TIMEOUT_MS;
  const method = (fetchOpts.method || "GET").toUpperCase();

  if (method === "GET" && cachePolicyFor(path) === "cache") {
    return queryClient.fetchQuery<T>({
      queryKey: ["api", path],
      queryFn: ({ signal }) => fetchWithAuth<T>(path, { ...fetchOpts, signal }, connectTimeout, method),
      staleTime: ttlFor(path),
    });
  }

  const data = await fetchWithAuth<T>(path, fetchOpts, connectTimeout, method);
  if (method !== "GET") {
    // 会话切换立即隔离旧用户数据，不在已退出的会话上触发受保护查询重取。
    if (path === "/auth/logout" || path === "/auth/login" || (path === "/auth/me" && method === "DELETE")) {
      clearApiCache();
    } else {
      await queryClient.invalidateQueries({ queryKey: ["api"] });
    }
  }
  return data;
}
