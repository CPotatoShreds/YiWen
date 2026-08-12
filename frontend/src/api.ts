// API 客户端：Cookie 会话 + 统一错误处理 + 连接超时 + GET 网络失败重试
export const API_BASE = "/api";

const CONNECT_TIMEOUT_MS = 15000;
const GET_RETRIES = 2;

export class ApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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

export async function api<T>(path: string, opts: RequestInit & { timeout?: number } = {}): Promise<T> {
  const { timeout, ...fetchOpts } = opts;
  const connectTimeout = timeout ?? CONNECT_TIMEOUT_MS;
  const method = (fetchOpts.method || "GET").toUpperCase();
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
