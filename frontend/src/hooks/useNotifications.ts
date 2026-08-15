// 通知铃铛状态：拉列表 + SSE 实时收新通知 + 断线指数退避重连（重连后重拉对账）。
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { streamEvents } from "../sse";
import type { NotificationItem } from "../types";

const RETRY_BASE = 3000; // 3s → 6s → 12s → … → 30s，最多 10 次
const RETRY_CAP_MS = 30000;
const MAX_RETRIES = 10;

export function useNotifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    api<{ items: NotificationItem[]; unread: number }>("/notifications")
      .then((d) => {
        setItems(d.items);
        setUnread(d.unread);
      })
      .catch(() => {
        /* 网络失败静默：下次重连/聚焦再对账 */
      });
  }, []);

  useEffect(() => {
    let alive = true;
    let ctrl: AbortController | null = null;
    let timer: number | undefined;
    let retries = 0;

    const connect = () => {
      if (!alive) return;
      ctrl = new AbortController();
      streamEvents(
        "/notifications/stream",
        {
          onEvent: (ev) => {
            if (ev.type === "notification") load(); // 新通知落库 → 重拉列表
          },
          onClose: () => reconnect(),
        },
        ctrl.signal,
      ).catch(() => reconnect(true));
    };
    const reconnect = (immediate = false) => {
      if (!alive) return;
      if (retries >= MAX_RETRIES) return; // 重连耗尽：靠聚焦刷新兜底
      const delay = immediate ? 0 : Math.min(RETRY_BASE * 2 ** retries, RETRY_CAP_MS);
      timer = window.setTimeout(() => {
        retries += 1;
        connect();
      }, delay);
    };

    load();
    connect();
    // 断线重连耗尽时的兜底：切回前台标签页即对账
    window.addEventListener("focus", load);
    return () => {
      alive = false;
      ctrl?.abort();
      if (timer) clearTimeout(timer);
      window.removeEventListener("focus", load);
    };
  }, [load]);

  const markRead = useCallback(
    (id: number) => {
      // 等 POST 落库再重拉，否则读到未 commit 的旧未读数，红点卡住
      api(`/notifications/${id}/read`, { method: "POST" })
        .catch(() => {})
        .finally(() => load());
    },
    [load],
  );

  const markAllRead = useCallback(() => {
    api("/notifications/read-all", { method: "POST" })
      .catch(() => {})
      .finally(() => load());
  }, [load]);

  return {
    items,
    unread,
    open,
    toggle: useCallback(() => {
      setOpen((o) => {
        if (!o) load(); // 打开面板时对账一次（SSE 掉线期间的遗漏兜底）
        return !o;
      });
    }, [load]),
    close: useCallback(() => setOpen(false), []),
    markRead,
    markAllRead,
  };
}
