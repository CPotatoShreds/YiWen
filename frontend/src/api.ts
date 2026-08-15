// API 客户端：Cookie 会话 + 统一错误处理 + 连接超时 + GET 网络失败重试 + GET 内存 SWR 缓存
export const API_BASE = "/api";

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

// ── GET 客户端缓存（staleness-while-revalidate）──
// 读多写少的稳定数据做内存缓存：TTL 内命中直接返回；过期返回旧值并后台刷新；
// 无缓存时 in-flight 去重。进行中的对战/分享页由 SSE 实时驱动、管理端要实时，均豁免。
type CacheEntry = { data: unknown; at: number };
const cacheStore = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<unknown>>();
const refreshing = new Set<string>();

// 状态敏感的读路径用短 TTL：板子/跨场进度随推演结果变化，短暂过期可接受且后台自愈
const CACHE_TTL_BY_PREFIX: [string, number][] = [["/board", 10_000]];

function ttlFor(path: string): number {
  for (const [prefix, ttl] of CACHE_TTL_BY_PREFIX) {
    if (path.startsWith(prefix)) return ttl;
  }
  return CACHE_TTL_MS;
}

function cachePolicyFor(path: string): "cache" | "skip" {
  if (path.includes("?")) return "skip"; // 带查询参数的结果随条件变化，不缓存
  if (path.startsWith("/admin/")) return "skip"; // 管理工具要实时
  if (path.startsWith("/battles/")) return "skip"; // 进行中对战/分享，SSE 实时驱动
  return "cache";
}

// 变更请求成功后按前缀失效缓存：同一资源的 POST/DELETE 后，缓存数据已过期
const MUTATE_PREFIXES = [
  "/auth",
  "/loadouts",
  "/abilities",
  "/battles",
  "/board",
  "/friends",
  "/leaderboard",
  "/llm-profiles",
];

function invalidateCache(): void {
  for (const key of cacheStore.keys()) {
    if (MUTATE_PREFIXES.some((p) => key.startsWith(p))) cacheStore.delete(key);
  }
}

export function clearApiCache(): void {
  cacheStore.clear();
}

function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
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

async function rawFetch<T>(path: string, fetchOpts: RequestInit, connectTimeout: number, method: string): Promise<T> {
  const maxAttempts = method === "GET" ? GET_RETRIES + 1 : 1;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const ctrl = new AbortController();
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
      return res.json() as Promise<T>;
    } catch (error) {
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
    }
  }
  throw new Error("请求失败");
}

function scheduleRefetch(path: string): void {
  if (refreshing.has(path)) return;
  refreshing.add(path);
  rawFetch<unknown>(path, {}, CONNECT_TIMEOUT_MS, "GET")
    .then((data) => {
      if (data != null) cacheStore.set(path, { data, at: Date.now() });
    })
    .catch(() => {
      // 静默：旧值继续可用，下轮再刷
    })
    .finally(() => refreshing.delete(path));
}

export async function api<T>(path: string, opts: RequestInit & { timeout?: number } = {}): Promise<T> {
  const { timeout, ...fetchOpts } = opts;
  const connectTimeout = timeout ?? CONNECT_TIMEOUT_MS;
  const method = (fetchOpts.method || "GET").toUpperCase();

  if (method === "GET" && cachePolicyFor(path) === "cache") {
    const hit = cacheStore.get(path);
    if (hit) {
      if (Date.now() - hit.at < ttlFor(path)) return hit.data as T; // TTL 内：直接命中
      scheduleRefetch(path); // 过期：旧值先用，后台刷新
      return hit.data as T;
    }
    const inFlight = inflight.get(path);
    if (inFlight) return inFlight as Promise<T>;
    const p = rawFetch<T>(path, fetchOpts, connectTimeout, method).then((data) => {
      if (data != null) cacheStore.set(path, { data, at: Date.now() });
      return data;
    });
    inflight.set(path, p);
    try {
      return await p;
    } finally {
      inflight.delete(path);
    }
  }

  const data = await rawFetch<T>(path, fetchOpts, connectTimeout, method);
  if (method !== "GET") invalidateCache();
  return data;
}
