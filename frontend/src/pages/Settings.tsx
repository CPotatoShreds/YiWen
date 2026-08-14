import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { GearIcon } from "../components/icons";
import ModelProfiles from "../components/ModelProfiles";

export default function Settings() {
  const { user, refresh } = useAuth();
  const [reveal, setReveal] = useState<boolean>(user?.reveal_on_miss ?? false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setReveal(user?.reveal_on_miss ?? false);
  }, [user?.reveal_on_miss]);

  async function save() {
    setBusy(true);
    setMsg("");
    try {
      await api("/auth/settings", {
        method: "PUT",
        body: JSON.stringify({ reveal_on_miss: reveal }),
      });
      await refresh();
      setMsg("已保存");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">设置</h1>
        <p className="muted">你的偏好与模型配置</p>
      </div>
      <div className="panel rise">
        <div className="panel__head">
          <h3>基础设置</h3>
          <span className="muted" style={{ textAlign: "right" }} />
        </div>
        <label className="toggle" style={{ marginBottom: 6 }}>
          <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />
          <span className="toggle__track" />
          <span className="toggle__label">展示奇术</span>
        </label>
        <p className="toggle__desc" style={{ marginBottom: 16 }}>
          如此奇术，岂能我一人独享？开启后，即使对手窥秘失败，也可以查看你的奇术；
        </p>
        <button className="btn btn-primary" onClick={save} disabled={busy}>
          <GearIcon size={15} />
          {busy ? "保存中…" : "保存"}
        </button>
        {msg && <p className="summary">{msg}</p>}
      </div>
      <ModelProfiles />
    </>
  );
}
