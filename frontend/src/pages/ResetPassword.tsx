import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SealStamp } from "../components/Ornaments";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setErr("两次输入的口令不一致");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password: password }) });
      setDone(true);
    } catch (e2: any) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth__card rise">
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>重置口令</h1>
        </div>
        {done ? (
          <>
            <p className="auth__sub">口令已重置，请用新口令重新登录。</p>
            <p className="auth__foot">
              <Link to="/login">前往登录</Link>
            </p>
          </>
        ) : (
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="rp-p">新口令</label>
              <input
                id="rp-p"
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="field">
              <label htmlFor="rp-p2">确认新口令</label>
              <input
                id="rp-p2"
                className="input"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            {err && <p className="err">{err}</p>}
            <button className="btn btn-primary btn-block" disabled={busy || !token || !password || !confirm}>
              {busy ? "重置中…" : "重置口令"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
