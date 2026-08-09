import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { BookIcon } from "../components/icons";
import { InkMountains, Lantern, SwordsmanScene } from "../components/Ornaments";

export default function Register() {
  const { register } = useAuth();
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
      await register(username, password);
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
        <p className="auth__sub">注册，成为下一位异闻师</p>
        <div className="auth__gloss">
          注册即得三座奇人空槽与一座奇术篇——立起你的奇人，写下奇术，启程较量，摇签对家。
        </div>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="reg-u">异闻师·名号</label>
            <input
              id="reg-u"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="2-20 字"
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label htmlFor="reg-p">口令</label>
            <input
              id="reg-p"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 6 位"
              autoComplete="new-password"
            />
          </div>
          {err && <p className="err">{err}</p>}
          <button className="btn btn-primary btn-block" disabled={busy || !username || !password}>
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
