import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { InkMountains, Lantern, SealStamp, SwordsmanScene } from "../components/Ornaments";

/** 注册页：邮箱 + 用户名 + 口令（邮箱为找回口令凭证，注册时不做验证）。 */
export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      setErr("请填写有效的邮箱地址");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await register(username.trim(), password, email.trim());
      nav("/home");
    } catch (e2: any) {
      setErr(e2?.message || "注册失败，请稍后重试");
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      {/* 书坊正门：月牙侠客 + 远山 + 两盏灯笼 */}
      <div className="auth__scene" aria-hidden="true">
        <SwordsmanScene className="scene-moon" />
        <InkMountains className="scene-mountains" />
      </div>
      <div className="auth__lanterns" aria-hidden="true">
        <span className="lantern lantern--l">
          <Lantern size={34} />
        </span>
        <span className="lantern lantern--r">
          <Lantern size={30} />
        </span>
      </div>
      <div className="auth__card rise">
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>异闻录</h1>
        </div>
        <p className="auth__sub">注册，成为下一位异闻师</p>
        <div className="auth__gloss">
          注册即得三座奇人空槽与一座奇术篇——立起你的奇人，写下奇术，启程较量，摇签对家。
        </div>

        {err && (
          <div className="auth-alert" role="alert">
            {err}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="reg-email">邮箱</label>
            <input
              id="reg-email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              spellCheck={false}
            />
            <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              用于找回口令；注册时不发验证邮件。
            </p>
          </div>

          <div className="field">
            <label htmlFor="reg-username">用户名</label>
            <input
              id="reg-username"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="2-20 字"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
            />
          </div>

          <div className="field">
            <label htmlFor="reg-password">口令</label>
            <div className="input-wrap">
              <input
                id="reg-password"
                className="input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 位"
                autoComplete="new-password"
              />
              <button
                type="button"
                className="input-trail"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "隐藏口令" : "显示口令"}
              >
                {showPassword ? "隐藏" : "显示"}
              </button>
            </div>
          </div>

          <label className="field" style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13 }}>
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              我已阅读并同意
              <Link to="/terms" target="_blank">《用户协议》</Link>
              与
              <Link to="/privacy" target="_blank">《隐私政策》</Link>
            </span>
          </label>

          <button className="btn btn-primary btn-block" disabled={busy || !email || !username || !password || !agreed}>
            {busy ? "注册中…" : "注册并入座"}
          </button>
        </form>

        <p className="auth__foot">
          已有名号？<Link to="/login">直接登录</Link>
        </p>
      </div>
    </div>
  );
}
