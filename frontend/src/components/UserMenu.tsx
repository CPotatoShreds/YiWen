import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { GearIcon, LogoutIcon, ShieldIcon, UserRoundIcon } from "./icons";

/** 右上角悬浮用户入口：头像字+名号按钮，展开纸面下拉（信息 / 设置 / 后台 / 退出）。 */
export default function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  return (
    <div className="user-menu" ref={rootRef}>
      <button
        type="button"
        className={"user-menu__trigger" + (open ? " is-open" : "")}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="user-menu__avatar" aria-hidden="true">
          {user.username.slice(0, 1)}
        </span>
        <span className="user-menu__name">{user.username}</span>
      </button>
      {open && (
        <div className="user-menu__panel" role="menu">
          <div className="user-menu__identity">
            <span className="user-menu__avatar user-menu__avatar--lg" aria-hidden="true">
              {user.username.slice(0, 1)}
            </span>
            <div className="user-menu__who">
              <strong>{user.username}</strong>
              <span>{user.email || "未绑定邮箱"}</span>
            </div>
          </div>
          <Link role="menuitem" className="user-menu__item" to="/me" onClick={() => setOpen(false)}>
            <UserRoundIcon size={15} /> 用户信息
          </Link>
          <Link role="menuitem" className="user-menu__item" to="/settings" onClick={() => setOpen(false)}>
            <GearIcon size={15} /> 设置
          </Link>
          {user.is_admin && (
            <Link role="menuitem" className="user-menu__item" to="/admin" onClick={() => setOpen(false)}>
              <ShieldIcon size={15} /> 管理
            </Link>
          )}
          <button
            role="menuitem"
            type="button"
            className="user-menu__item user-menu__item--quit"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            <LogoutIcon size={15} /> 退出登录
          </button>
        </div>
      )}
    </div>
  );
}
