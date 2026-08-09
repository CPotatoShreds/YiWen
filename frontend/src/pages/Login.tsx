import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { BookIcon } from "../components/icons";
import { InkMountains, Lantern, SwordsmanScene } from "../components/Ornaments";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await login(username, password);
      nav("/");
    } catch (e2: any) {
      setErr(e2.message);
    } finally {
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
            <BookIcon size={22} />
          </span>
          <h1>异闻录</h1>
        </div>
        <p className="auth__sub">登录，重返书场</p>
        <div className="auth__gloss">
          自创奇术 · 纯机制对抗 · 战败可凭行迹线索猜穿对家的奇术，命中即逆转胜负。
        </div>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="login-u">异闻师·名号</label>
            <input
              id="login-u"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="你的名号"
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label htmlFor="login-p">口令</label>
            <input
              id="login-p"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="口令"
              autoComplete="current-password"
            />
          </div>
          {err && <p className="err">{err}</p>}
          <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>
            {busy ? "登台中…" : "入座"}
          </button>
        </form>
        <p className="auth__foot">
          没有名号？<Link to="/register">注册新异闻师</Link>
        </p>
      </div>
    </div>
  );
}
