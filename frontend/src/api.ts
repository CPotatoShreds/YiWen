// API 客户端：JWT 注入 + 统一错误处理 + 连接超时 + GET 失败自动重试
export const API_BASE = "http://localhost:8102/api";

let token: string | null = localStorage.getItem("token");

export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}
export function getToken() {
  return token;
}

// 连接超时（毫秒）：服务器无响应时提前失败，避免请求无限挂起（后端 LLM 请求同理已加硬超时）
const CONNECT_TIMEOUT_MS = 15000;
// GET 失败自动重试次数（网络错误/超时才重试；HTTP 错误态不重试）。POST 不重试，防重复启程/猜奇术。
const GET_RETRIES = 2;

export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const method = (opts.method || "GET").toUpperCase();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const maxAttempts = method === "GET" ? GET_RETRIES + 1 : 1;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), CONNECT_TIMEOUT_MS);
    try {
      const res = await fetch(`${API_BASE}${path}`, { ...opts, headers, signal: ctrl.signal });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const j = await res.json();
          const d = j.detail;
          if (typeof d === "string") {
            detail = d;
          } else if (Array.isArray(d)) {
            // FastAPI 校验错误：detail 是 [{loc, msg, type}, ...]，直接 toString 会变 [object Object]
            detail = d
              .map((x: any) => (x && typeof x.msg === "string" ? x.msg : String(x)))
              .join("；");
          } else if (d != null) {
            detail = String(d);
          }
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      // 204/205 无 body：DELETE 成功返回空，直接返回 null，避免 res.json() 抛 "Unexpected end of JSON input"
      if (res.status === 204 || res.status === 205) return null as T;
      return res.json() as Promise<T>;
    } catch (e) {
      const retriable = method === "GET" && attempt < maxAttempts - 1;
      if (retriable) {
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1))); // 500ms → 1s
        continue;
      }
      throw e instanceof Error ? e : new Error(String(e));
    } finally {
      window.clearTimeout(timer);
    }
  }
  throw new Error("请求失败");
}
