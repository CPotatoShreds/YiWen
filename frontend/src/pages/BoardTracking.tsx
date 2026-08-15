// 榜主追踪挑战者：搜索某刻印的挑战者，查看其在该刻印下的逐条猜词路径。
// 每条记录 = 提交文本 + 本猜词爆出的线索 + 截至目前看破门数；点击跳转到对应战报（榜主己方视角，不显示猜词）。
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ChevronRightIcon, ScrollIcon } from "../components/icons";
import { parseUtc } from "../time";
import type { BoardChallenger, BoardDetail, GuessPathRecord } from "../types";

export default function BoardTracking() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [detail, setDetail] = useState<BoardDetail | null>(null);
  const [search, setSearch] = useState("");
  const [challengers, setChallengers] = useState<BoardChallenger[] | null>(null);
  const [selected, setSelected] = useState<BoardChallenger | null>(null);
  const [path, setPath] = useState<GuessPathRecord[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!id) return;
    api<BoardDetail>(`/board/${id}`).then(setDetail).catch((e: any) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const load = () => {
    if (!id) return;
    api<BoardChallenger[]>(
      `/board/${id}/tracking/challengers${search ? `?search=${encodeURIComponent(search)}` : ""}`
    )
      .then((r) => {
        setChallengers(r);
        setSelected(null);
        setPath(null);
      })
      .catch((e: any) => setErr(e.message));
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function openPath(c: BoardChallenger) {
    if (!id) return;
    setSelected(c);
    setPath(null);
    try {
      setPath(await api<GuessPathRecord[]>(`/board/${id}/tracking/challengers/${c.user_id}/guess-path`));
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const fmt = (s: string) =>
    parseUtc(s).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">
          <ScrollIcon size={22} /> 追踪挑战者
        </h1>
        <p className="muted">
          <Link to="/board">← 返回奇人榜</Link>
        </p>
      </div>
      {err && <p className="err">{err}</p>}

      {detail && (
        <>
          <p className="muted" style={{ marginBottom: 12 }}>
            「{detail.name}」的挑战者猜词路径——逐条复盘每位挑战者如何试探你的刻印。
          </p>
          <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            挑战者胜率 {detail.win_rate == null ? "—" : `${Math.round(detail.win_rate * 100)}%`} · 每门奇术被看破所费平均{" "}
            {detail.avg_crack_attempts == null ? "—" : `${detail.avg_crack_attempts.toFixed(1)} 次`} · 被挑战{" "}
            {detail.challenge_count} 次
          </p>
        </>
      )}

      {/* 挑战者搜索与列表 */}
      <div className="panel">
        <div className="panel__head">
          <h3>选择挑战者</h3>
        </div>
        <input
          className="input"
          placeholder="搜索挑战者名号"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        {challengers === null ? (
          <div className="skeleton" style={{ height: 80 }} />
        ) : challengers.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>
            没有找到有猜词记录的挑战者。
          </p>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {challengers.map((c) => (
              <div
                key={c.user_id}
                className="panel"
                onClick={() => openPath(c)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 14px",
                  marginBottom: 0,
                  cursor: "pointer",
                  ...(selected?.user_id === c.user_id
                    ? { outline: "1px solid var(--accent)" }
                    : {}),
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <b style={{ fontSize: 14 }}>{c.username}</b>
                  <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
                    累计 {c.total_guesses} 猜 · 已看破 {c.cracked} / {c.total} 门
                  </p>
                </div>
                <span className="muted" style={{ fontSize: 12, flex: "none" }}>
                  猜词路径 ›
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 选中挑战者的猜词路径 */}
      {selected && (
        <div className="panel">
          <div className="panel__head">
            <h3>
              「{selected.username}」的猜词路径{" "}
              <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                已看破 {selected.cracked} / {selected.total} 门 · 累计 {selected.total_guesses} 猜
              </span>
            </h3>
          </div>
          {path === null ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : path.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>
              该挑战者还没有猜词记录。
            </p>
          ) : (
            <ol style={{ display: "grid", gap: 8, margin: 0, paddingLeft: 22 }}>
              {path.map((r) => (
                <li key={`${r.battle_id}-${r.round}`}>
                  <div
                    className="panel"
                    onClick={() => nav(`/battles/${r.battle_id}`)}
                    style={{ padding: "10px 14px", marginBottom: 0, cursor: "pointer" }}
                  >
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 13 }}>
                        第 <b>{r.round}</b> 猜「<b>{r.text}</b>」
                      </span>
                      <span className="muted" style={{ fontSize: 11 }}>
                        {fmt(r.at)}
                      </span>
                    </div>
                    {r.clue.length > 0 && (
                      <ul className="guess-card__matched" style={{ margin: "6px 0 0" }}>
                        {r.clue.map((c, i) => (
                          <li key={i}>
                            命中「{c.name}」：{c.fragments.join("、")}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>
                      此时已看破 {r.cracked_after} / {selected.total} 门
                      <span style={{ marginLeft: 12 }}>
                        查看战报 <ChevronRightIcon size={12} />
                      </span>
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </>
  );
}
