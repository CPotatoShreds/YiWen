import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { InkMountains, Lantern, SealStamp, SwordsmanScene } from "../components/Ornaments";

/** 登录页：居中卡片 + 明确层级 + 口令可见切换 + 错误提示 + 条款微文案。 */
export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setErr("");
    try {
      await login(username.trim(), password);
      nav("/home");
    } catch (e2: any) {
      setErr(e2?.message || "登录失败，请稍后重试");
      setBusy(false); // 登录失败保持表单可用；成功后不再恢复（页面即将跳转）
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
        <p className="auth__sub">登录，重返书场</p>

        {err && (
          <div className="auth-alert" role="alert">
            {err}
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="login-username">用户名</label>
            <input
              id="login-username"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="你的名号"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
            />
          </div>

          <div className="field">
            <div className="field-label-row">
              <label htmlFor="login-password">口令</label>
              <Link className="field-link" to="/forgot-password">
                忘记口令？
              </Link>
            </div>
            <div className="input-wrap">
              <input
                id="login-password"
                className="input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 位"
                autoComplete="current-password"
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

          <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>
            {busy ? "登台中…" : "登录"}
          </button>
        </form>

        <p className="auth__foot">
          还没有名号？<Link to="/register">立即注册</Link>
        </p>
        <p className="auth-legal">
          登录即表示同意
          <Link to="/terms" target="_blank">《用户协议》</Link>
          与
          <Link to="/privacy" target="_blank">《隐私政策》</Link>
        </p>
      </div>
    </div>
  );
}
