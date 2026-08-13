// 奇人榜：刻印条目全量展示（奇术保密，仅展示数量）。
// 点击条目进详情页；他人条目可点将挑战（先自选出战奇人，切磋不计名望）；自己条目可下榜。
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import BoardChallengeModal from "../components/BoardChallengeModal";
import { ScrollIcon, SwordIcon, TrashIcon } from "../components/icons";
import type { BoardEntry } from "../types";

export default function Board() {
  const nav = useNavigate();
  const [entries, setEntries] = useState<BoardEntry[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 点将弹窗：挑战对象（条目详情页复用同一弹窗组件）
  const [challenge, setChallenge] = useState<BoardEntry | null>(null);

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
          点击条目可查看看破进度与你对该刻印的对战记录。
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
              onClick={() => nav(`/board/${e.id}`)}
              style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", marginBottom: 0, cursor: "pointer" }}
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
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    takeOff(e);
                  }}
                  disabled={busy}
                >
                  <TrashIcon size={14} />
                  下榜
                </button>
              ) : (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setChallenge(e);
                  }}
                >
                  <SwordIcon size={14} />
                  点将挑战
                </button>
              )}
              <span className="muted" style={{ fontSize: 12, flex: "none" }}>
                详情 ›
              </span>
            </div>
          ))}
        </div>
      )}

      {challenge && (
        <BoardChallengeModal
          entry={challenge}
          onClose={() => setChallenge(null)}
          onDone={(id) => {
            setChallenge(null);
            nav(`/battles/${id}`);
          }}
        />
      )}
    </>
  );
}
