// SSE 客户端：fetch + ReadableStream 解析 text/event-stream（Cookie 会话）
import { API_BASE } from "./api";

export interface SseHandlers {
  onEvent?: (ev: { type: string; [k: string]: unknown }) => void;
  /** 流正常结束（服务端关闭） */
  onClose?: () => void;
}

// 连接超时（毫秒）：服务器无响应时提前失败，交由调用方重连，不再无限等 fetch
const CONNECT_TIMEOUT_MS = 15000;

/** 打开一条 SSE 流并逐帧回调；返回的 Promise 在流结束/出错时 resolve/reject。
 * 通过 AbortSignal 可主动断开（与内部连接超时合并生效）。 */
export async function streamEvents(
  path: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = {};
  const ctrl = new AbortController();
  const onExternalAbort = () => ctrl.abort();
  signal?.addEventListener("abort", onExternalAbort);
  const timeout = window.setTimeout(() => ctrl.abort(), CONNECT_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers, credentials: "include", signal: ctrl.signal });
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", onExternalAbort);
  }
  if (!res.ok || !res.body) throw new Error(`SSE 连接失败 HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (data) {
          try {
            handlers.onEvent?.({ type: event, ...JSON.parse(data) });
          } catch {
            /* 忽略坏帧 */
          }
        }
      }
    }
    handlers.onClose?.();
  } finally {
    reader.releaseLock();
  }
}
