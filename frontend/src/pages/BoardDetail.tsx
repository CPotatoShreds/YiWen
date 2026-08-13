// 奇人榜条目详情：刻印基本信息 + 查看者（挑战者）的看破进度追踪 + 与该刻印的对战记录。
// 榜主被动：自己看刻印全貌、无任何挑战者行迹（battles 恒空）。
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import BoardChallengeModal from "../components/BoardChallengeModal";
import { CheckIcon, LockIcon, ScrollIcon, SwordIcon } from "../components/icons";
import type { Battle, BoardDetail } from "../types";

function winLabel(b: Battle): string {
  if (!b.winner) return "平局";
  // 点将局挑战者恒为 user_a；本页对局记录全是查看者自己的点将局
  return b.winner === b.user_a ? "你胜" : "刻印胜";
}

export default function BoardDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [detail, setDetail] = useState<BoardDetail | null>(null);
  const [err, setErr] = useState("");
  const [challengeOpen, setChallengeOpen] = useState(false);

  async function load() {
    if (!id) return;
    try {
      setDetail(await api<BoardDetail>(`/board/${id}`));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (err) {
    return (
      <>
        <p className="err">{err}</p>
        <Link to="/board" className="btn btn-ghost btn-sm">
          ← 返回奇人榜
        </Link>
      </>
    );
  }
  if (!detail) return <div className="skeleton" style={{ height: 320 }} />;

  const cracked = detail.progress.filter((c) => c.cracked).length;
  const fmt = (s: string) =>
    new Date(s).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">
          <ScrollIcon size={22} /> {detail.name}
        </h1>
        <p className="muted">
          <Link to="/board">← 返回奇人榜</Link>
        </p>
      </div>

      {/* 刻印基本信息 */}
      <div
        className="panel"
        style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 18px" }}
      >
        <span className="seal" style={{ flex: "none" }}>
          榜
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <b style={{ fontSize: 16 }}>{detail.name}</b>
            <span className="muted" style={{ fontSize: 12 }}>
              {detail.user}
            </span>
            {detail.mine && (
              <span className="chip chip--ability" style={{ fontSize: 11, padding: "2px 8px" }}>
                我的刻印
              </span>
            )}
          </div>
          <p className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>
            {detail.style || "（未写风格）"} · {detail.ability_count} 门奇术 · 被挑战{" "}
            {detail.challenge_count} 次 · {fmt(detail.created_at)}
          </p>
        </div>
        {!detail.mine && (
          <button className="btn btn-primary" onClick={() => setChallengeOpen(true)}>
            <SwordIcon size={15} />
            点将挑战
          </button>
        )}
      </div>

      {/* 看破进度 */}
      <div className="panel">
        <div className="panel__head">
          <h3>
            看破进度{" "}
            <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
              已看破 {cracked} / {detail.progress.length} 门
            </span>
          </h3>
        </div>
        {detail.mine && (
          <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            榜主视角：这是你的刻印，奇术全貌对你可见；挑战者各自的进度保密。
          </p>
        )}
        <div className="guess-board">
          {detail.progress.map((c) => (
            <div key={c.index} className={`guess-card ${c.cracked ? "guess-card--cracked" : ""}`}>
              <div className="guess-card__head">
                <span className="guess-card__no">第 {c.index} 门</span>
                {c.cracked ? (
                  <span className="guess-card__label guess-card__label--hit">
                    <CheckIcon size={13} /> {detail.mine ? "刻印" : "已看破"}
                  </span>
                ) : (
                  <span className="guess-card__label">
                    <LockIcon size={13} /> 未知奇术
                  </span>
                )}
              </div>
              {c.cracked ? (
                <div>
                  <div className="guess-card__name">{c.name}</div>
                  <p className="guess-card__effect">{c.effect}</p>
                </div>
              ) : (
                c.matched.length > 0 && (
                  <ul className="guess-card__matched">
                    {c.matched.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                )
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 对战记录（榜主恒空，发帖语义） */}
      <div className="panel">
        <div className="panel__head">
          <h3>你对战记录</h3>
        </div>
        {detail.mine ? (
          <p className="muted" style={{ fontSize: 13 }}>
            榜主视角：点将挑战的行迹保密，你只能看到被挑战次数，无法追溯每一位挑战者。
          </p>
        ) : detail.battles.length === 0 ? (
          <div className="empty" style={{ padding: "12px 0" }}>
            <ScrollIcon size={20} />
            <p>尚未点将挑战过这个刻印。</p>
          </div>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {detail.battles.map((b) => (
              <div
                key={b.id}
                className="panel"
                onClick={() => nav(`/battles/${b.id}`)}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", marginBottom: 0, cursor: "pointer" }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14 }}>
                    「{b.fighter_a}」 vs 刻印「{b.fighter_b}」
                  </div>
                  <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
                    {fmt(b.created_at)} · {winLabel(b)}
                  </p>
                </div>
                <span className="muted" style={{ fontSize: 12, flex: "none" }}>
                  查看 ›
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {challengeOpen && detail && (
        <BoardChallengeModal
          entry={detail}
          onClose={() => setChallengeOpen(false)}
          onDone={(bid) => nav(`/battles/${bid}`)}
        />
      )}
    </>
  );
}
