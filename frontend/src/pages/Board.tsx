// 奇人榜：刻印条目全量展示（奇术保密，仅展示数量）。
// 他人条目可点将挑战（先自选出战奇人，切磋不计名望）；自己条目可下榜。
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { CheckIcon, ScrollIcon, SwordIcon, TrashIcon, XIcon } from "../components/icons";
import type { BoardEntry, Loadout } from "../types";

export default function Board() {
  const nav = useNavigate();
  const [entries, setEntries] = useState<BoardEntry[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 点将弹窗：挑战对象 + 我可选的出战奇人
  const [challenge, setChallenge] = useState<BoardEntry | null>(null);
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [picked, setPicked] = useState<number | null>(null);
  const [challengeErr, setChallengeErr] = useState("");

  async function load() {
    try {
      setEntries(await api<BoardEntry[]>("/board"));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!challenge) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setChallenge(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [challenge]);

  function openChallenge(e: BoardEntry) {
    setChallenge(e);
    setPicked(null);
    setChallengeErr("");
    api<Loadout[]>("/loadouts")
      .then((ls) => setLoadouts(ls))
      .catch((e: any) => setChallengeErr(e.message));
  }

  const pickable = loadouts.filter((l) => l.enabled && l.abilities.length > 0);

  async function doChallenge() {
    if (!challenge || picked == null) return;
    setBusy(true);
    setChallengeErr("");
    try {
      const r = await api<{ battle_id: number }>(`/board/${challenge.id}/challenge`, {
        method: "POST",
        body: JSON.stringify({ loadout_id: picked }),
      });
      setChallenge(null);
      nav(`/battles/${r.battle_id}`);
    } catch (e: any) {
      setChallengeErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function takeOff(e: BoardEntry) {
    setBusy(true);
    setErr("");
    try {
      await api(`/board/${e.id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">
          <ScrollIcon size={22} /> 奇人榜
        </h1>
        <p className="muted">
          上榜即刻印——奇人当前状态被冻结于此，任天下异闻师点将切磋（不计名望）。奇术保密，只看门数。
        </p>
      </div>
      {err && <p className="err">{err}</p>}

      {entries === null ? (
        <div className="skeleton" style={{ height: 240 }} />
      ) : entries.length === 0 ? (
        <div className="empty">
          <ScrollIcon size={22} />
          <h3>奇人榜空空如也</h3>
          <p>去异闻录把已装奇术的奇人刻印上榜，让江湖看到你的手笔。</p>
          <Link to="/abilities" className="btn btn-primary">
            去上榜
          </Link>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {entries.map((e) => (
            <div
              className="panel"
              key={e.id}
              style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", marginBottom: 0 }}
            >
              <span className="seal" style={{ flex: "none" }}>
                榜
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                  <b style={{ fontSize: 15 }}>{e.name}</b>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {e.user}
                  </span>
                  {e.mine && (
                    <span className="chip chip--ability" style={{ fontSize: 11, padding: "2px 8px" }}>
                      我
                    </span>
                  )}
                </div>
                <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
                  {e.style || "（未写风格）"} · {e.ability_count} 门奇术 · 被挑战 {e.challenge_count} 次
                </p>
              </div>
              <span className="muted" style={{ fontSize: 12, flex: "none" }}>
                {fmt(e.created_at)}
              </span>
              {e.mine ? (
                <button className="btn btn-ghost btn-sm" onClick={() => takeOff(e)} disabled={busy}>
                  <TrashIcon size={14} />
                  下榜
                </button>
              ) : (
                <button className="btn btn-primary btn-sm" onClick={() => openChallenge(e)} disabled={busy}>
                  <SwordIcon size={14} />
                  点将挑战
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {challenge && (
        <div className="modal-overlay" onClick={() => setChallenge(null)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h3>点将出战：挑战「{challenge.name}」</h3>
              <button className="modal__close" onClick={() => setChallenge(null)} aria-label="关闭">
                <XIcon size={16} />
              </button>
            </div>
            <p className="muted" style={{ padding: "2px 2px 12px", lineHeight: 1.7 }}>
              {challenge.user} 的「{challenge.name}」刻印于此（奇术保密）。挑一位自己的奇人出战，切磋不计名望。
            </p>
            {pickable.length === 0 ? (
              <p className="muted" style={{ padding: "4px 2px 10px", lineHeight: 1.7 }}>
                你还没有已解封且装奇术的奇人，无法点将。去 <Link to="/abilities">异闻录</Link> 编排后再来。
              </p>
            ) : (
              <div className="picker">
                {pickable.map((l) => (
                  <button
                    key={l.id}
                    className={`picker-item${picked === l.id ? " is-on" : ""}`}
                    onClick={() => setPicked(l.id)}
                  >
                    <span className="picker-item__name">{l.name}</span>
                    <span className="picker-item__eff">
                      {l.style || "未写风格"} · {l.abilities.length} 门奇术
                    </span>
                    {picked === l.id && (
                      <span className="picker-item__check">
                        <CheckIcon size={16} />
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
            {challengeErr && <p className="err" style={{ margin: "4px 2px 0" }}>{challengeErr}</p>}
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 14 }}>
              <button className="btn btn-ghost" onClick={() => setChallenge(null)}>
                作罢
              </button>
              <button className="btn btn-primary" onClick={doChallenge} disabled={busy || picked == null}>
                <SwordIcon size={15} />
                {busy ? "递帖中…" : "递上挑战"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
