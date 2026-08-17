// 奇人榜：刻印条目全量展示（奇术保密，仅展示数量）。
// 点击条目进详情页；他人条目可点将挑战（先自选出战奇人，切磋不计名望）；自己条目可下榜。
// 刻印入口在异闻录改为本页「刻印我的奇人」弹窗（选中即上榜）。
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import BoardChallengeModal from "../components/BoardChallengeModal";
import { ScrollIcon, SwordIcon, TrashIcon, XIcon } from "../components/icons";
import { parseUtc } from "../time";
import type { BoardEntry, Loadout } from "../types";

// 刻印弹窗：列出我的奇人，点击即冻结上榜（需装有 ≥1 奇术）。
function EngraveModal({
  loadouts,
  busy,
  err,
  onEngrave,
  onClose,
}: {
  loadouts: Loadout[];
  busy: boolean;
  err: string;
  onEngrave: (l: Loadout) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>刻印我的奇人</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <p className="muted" style={{ padding: "2px 2px 12px", lineHeight: 1.7 }}>
          刻印 = 把奇人当前状态冻结上榜，任天下异闻师点将切磋（不计名望）。一奇人可多席，随时可下榜。
        </p>
        {loadouts.length === 0 ? (
          <p className="muted" style={{ padding: "4px 2px 10px", lineHeight: 1.7 }}>
            你还没有奇人。去 <Link to="/abilities">异闻录</Link> 立起一位，装入奇术后再来刻印。
          </p>
        ) : (
          <div className="picker">
            {loadouts.map((l) => {
              const ok = l.abilities.length > 0;
              return (
                <button
                  key={l.id}
                  className="picker-item"
                  disabled={!ok || busy}
                  onClick={() => ok && onEngrave(l)}
                  title={ok ? "刻印上榜" : "这位奇人还没有奇术，先装入再刻印"}
                >
                  <span className="picker-item__name">{l.name || `奇人#${l.id}`}</span>
                  <span className="picker-item__eff">
                    {l.enabled ? "已解封" : "未解封"} · {l.abilities.length} 门奇术
                  </span>
                  {!ok && <span className="muted" style={{ fontSize: 11, flex: "none" }}>暂无奇术</span>}
                </button>
              );
            })}
          </div>
        )}
        {err && <p className="err" style={{ margin: "4px 2px 0" }}>{err}</p>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 14 }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            作罢
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Board() {
  const nav = useNavigate();
  const [entries, setEntries] = useState<BoardEntry[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 点将弹窗：挑战对象（条目详情页复用同一弹窗组件）
  const [challenge, setChallenge] = useState<BoardEntry | null>(null);
  // 刻印弹窗：我的奇人列表 + 上榜中状态
  const [engraveOpen, setEngraveOpen] = useState(false);
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [engraving, setEngraving] = useState(false);
  const [notice, setNotice] = useState("");

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

  async function openEngrave() {
    setErr("");
    setNotice("");
    try {
      setLoadouts(await api<Loadout[]>("/loadouts"));
      setEngraveOpen(true);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function doEngrave(l: Loadout) {
    if (l.abilities.length === 0) return;
    setEngraving(true);
    setErr("");
    setNotice("");
    try {
      await api("/board", { method: "POST", body: JSON.stringify({ loadout_id: l.id }) });
      setEngraveOpen(false);
      setNotice(`「${l.name}」已刻印上榜，可被天下异闻师点将。`);
      window.setTimeout(() => setNotice(""), 4000);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setEngraving(false);
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
    parseUtc(s).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });

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
        <button className="btn btn-primary btn-sm" onClick={openEngrave}>
          <ScrollIcon size={14} />
          刻印我的奇人
        </button>
      </div>
      {err && <p className="err">{err}</p>}
      {notice && (
        <div className="banner banner--hit" style={{ marginTop: 12 }}>
          <span className="banner__icon"><ScrollIcon size={18} /></span>
          <div><p>{notice}</p></div>
        </div>
      )}

      {entries === null ? (
        <div className="skeleton" style={{ height: 240 }} />
      ) : entries.length === 0 ? (
        <div className="empty">
          <ScrollIcon size={22} />
          <h3>奇人榜空空如也</h3>
          <p>把已装奇术的奇人刻印上榜，让江湖看到你的手笔。</p>
          <button className="btn btn-primary" onClick={openEngrave}>
            <ScrollIcon size={15} />
            刻印我的奇人
          </button>
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
                  {e.cracked && (
                    <span className="chip chip--cracked" style={{ fontSize: 11, padding: "2px 8px" }}>
                      已看破
                    </span>
                  )}
                </div>
                <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
                  {e.style || "（未写风格）"} · {e.ability_count} 门奇术 · 被挑战 {e.challenge_count} 次 · 挑战者胜率{" "}
                  {e.win_rate == null ? "—" : `${Math.round(e.win_rate * 100)}%`} · 每门奇术被看破所费平均{" "}
                  {e.avg_crack_attempts == null ? "—" : `${e.avg_crack_attempts.toFixed(1)} 次`}
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

      {engraveOpen && (
        <EngraveModal
          loadouts={loadouts}
          busy={engraving}
          err={err}
          onEngrave={doEngrave}
          onClose={() => setEngraveOpen(false)}
        />
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
