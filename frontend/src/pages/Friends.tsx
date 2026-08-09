import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { CheckIcon, PlusIcon, SwordIcon, UsersIcon } from "../components/icons";

interface Friend {
  id: number;
  username: string;
  status: string;
}

export default function Friends() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [friends, setFriends] = useState<Friend[]>([]);
  const [requests, setRequests] = useState<Friend[]>([]);
  const [addId, setAddId] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<string>("");

  async function load() {
    setFriends(await api<Friend[]>("/friends"));
    setRequests(await api<Friend[]>("/friends/requests"));
  }
  useEffect(() => {
    load().catch((e: any) => setErr(e.message));
  }, []);

  async function add() {
    if (!addId.trim()) return;
    setBusy("add");
    setErr("");
    try {
      await api("/friends/request", { method: "POST", body: JSON.stringify({ friend_id: Number(addId) }) });
      setAddId("");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  }
  async function accept(id: number) {
    try {
      await api(`/friends/${id}/accept`, { method: "POST" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function challenge(id: number) {
    setBusy(`c${id}`);
    setErr("");
    try {
      const r = await api<{ id: number }>(`/battles/challenge/${id}`, { method: "POST" });
      nav(`/battles/${r.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">故人</h1>
        <p className="muted">结识故人，随时切磋一场（切磋不计名望）</p>
      </div>
      {err && <p className="err">{err}</p>}

      <div className="panel rise">
        <div className="panel__head">
          <h3>结识故人</h3>
          <span className="muted">我的 ID #{user?.id}</span>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="对方用户 ID"
            value={addId}
            onChange={(e) => setAddId(e.target.value)}
          />
          <button className="btn btn-primary" onClick={add} disabled={busy === "add" || !addId.trim()}>
            <PlusIcon size={15} />
            递上拜帖
          </button>
        </div>
      </div>

      {requests.length > 0 && (
        <div className="panel rise rise-1">
          <div className="panel__head">
            <h3>待收拜帖</h3>
            <span className="muted">{requests.length} 条</span>
          </div>
          {requests.map((r) => (
            <div className="row" key={r.id}>
              <span className="row__name">
                {r.username}
                <span className="hash"> #{r.id}</span>
              </span>
              <button className="btn btn-primary btn-sm" onClick={() => accept(r.id)}>
                <CheckIcon size={14} />
                接受
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="section-head" style={{ marginTop: 34 }}>
        <h2 className="section-title">故人名录</h2>
        <p className="muted">{friends.length} 位</p>
      </div>
      {friends.length === 0 ? (
        <div className="empty">
          <UsersIcon size={22} />
          <h3>尚无故人</h3>
          <p>输入对方的用户 ID 递上拜帖，结为故人后即可随时切磋。</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {friends.map((f) => (
            <div className="row panel" key={f.id} style={{ padding: "16px 20px", borderRadius: 14 }}>
              <span className="row__name">
                {f.username}
                <span className="hash"> #{f.id}</span>
              </span>
              <button className="btn btn-ghost" disabled={busy === `c${f.id}`} onClick={() => challenge(f.id)}>
                <SwordIcon size={15} />
                {busy === `c${f.id}` ? "启程中…" : "切磋"}
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
