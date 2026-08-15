// 通知铃铛：未读角标 + 下拉面板（列表/全部已读/点击跳转并标已读）。
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useNotifications } from "../hooks/useNotifications";
import { parseUtc } from "../time";
import type { NotificationItem } from "../types";
import { BellIcon } from "./icons";

function relativeTime(iso: string): string {
  const diff = Date.now() - parseUtc(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return parseUtc(iso).toLocaleDateString("zh-CN");
}

export default function NotificationBell() {
  const nav = useNavigate();
  const { items, unread, open, toggle, close, markRead, markAllRead } = useNotifications();
  const wrapRef = useRef<HTMLDivElement>(null);

  // 点外部 / Escape 关闭面板
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  const goto = (n: NotificationItem) => {
    markRead(n.id);
    close();
    if (n.ref_type === "battle" && n.ref_id != null) nav(`/battles/${n.ref_id}`);
    else if (n.ref_type === "board") nav("/board");
  };

  return (
    <div className="notify" ref={wrapRef}>
      <button
        className="notify__bell"
        onClick={toggle}
        aria-label={unread > 0 ? `通知，${unread} 条未读` : "通知"}
        aria-expanded={open}
      >
        <BellIcon size={14} />
        {unread > 0 && <span className="notify__badge">{unread > 99 ? "99+" : unread}</span>}
        通知
      </button>
      {open && (
        <div className="notify__panel">
          <div className="notify__head">
            <b>通知</b>
            <button className="btn btn-ghost btn-sm" onClick={markAllRead} disabled={unread === 0}>
              全部已读
            </button>
          </div>
          <div className="notify__list">
            {items.length === 0 ? (
              <div className="notify__empty">暂无消息</div>
            ) : (
              items.map((n) => (
                <button key={n.id} className={`notify__item${n.read ? "" : " is-unread"}`} onClick={() => goto(n)}>
                  <span className="notify__dot" aria-hidden="true" />
                  <span className="notify__body">
                    <span className="notify__title">{n.title}</span>
                    <span className="notify__text">{n.body}</span>
                    <span className="notify__time">{relativeTime(n.created_at)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
