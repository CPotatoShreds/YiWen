import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { api, clearApiCache } from "../api";

/** 危险区（P3）：个人数据导出 + 账号注销（软删匿名化，不可恢复）。 */
export default function DangerZone() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const confirmRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function exportData() {
    setBusy(true);
    setErr("");
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE || "/api"}/auth/me/export`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`导出失败 HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ynfight_export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault();
    const password = confirmRef.current?.value ?? "";
    if (!password) return;
    if (!window.confirm("注销后账号将匿名化且不可恢复，确定继续？")) return;
    setBusy(true);
    setErr("");
    try {
      await api("/auth/me", { method: "DELETE", body: JSON.stringify({ password }) });
      clearApiCache();
      await refresh();
      nav("/login");
    } catch (e2: any) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2 className="panel-title">数据与账号</h2>
      <p className="muted">导出你的创作与推演数据（JSON）。</p>
      <button className="btn" onClick={exportData} disabled={busy}>导出我的数据</button>
      <p className="muted" style={{ marginTop: 16 }}>
        注销账号：名号与邮箱将被匿名化且不可恢复，已登录会话全部失效；你创作的奇术、奇人与阵容会保留但归属显示为已注销。
      </p>
      <form onSubmit={deleteAccount} className="inline-form">
        <input
          ref={confirmRef}
          className="input"
          type="password"
          placeholder={`输入 ${user?.username ?? ""} 的口令以确认注销`}
          autoComplete="current-password"
        />
        <button className="btn" disabled={busy}>注销账号</button>
      </form>
      {err && <p className="err">{err}</p>}
    </div>
  );
}
