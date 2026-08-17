// 奇人详情：单个奇人的全部信息 + 全部行迹。点击某场行迹跳转到对应战报页
// （/admin/battles/:id，复用 BattleChainView 的讨论 / 三视角 / 猜词链路）。

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { ChevronLeftIcon, ChevronRightIcon } from "../../components/icons";
import type { AdminBattle, AdminLoadout } from "./types";
import { fmtDt, statusLabel } from "./traceParsers";

export default function LoadoutDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [loadout, setLoadout] = useState<AdminLoadout | null>(null);
  const [battles, setBattles] = useState<AdminBattle[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let stopped = false;
    setLoadout(null);
    setBattles([]);
    setErr("");
    Promise.all([
      api<AdminLoadout>(`/admin/loadouts/${id}`),
      api<AdminBattle[]>(`/admin/loadouts/${id}/battles`),
    ])
      .then(([l, rows]) => {
        if (stopped) return;
        setLoadout(l);
        setBattles(rows);
      })
      .catch((e: Error) => {
        if (!stopped) setErr(e.message);
      });
    return () => {
      stopped = true;
    };
  }, [id]);

  if (err) {
    return (
      <div className="admin-page">
        <p className="err">{err}</p>
        <button className="btn btn-ghost" onClick={() => nav("/admin/loadouts")}>返回奇人库</button>
      </div>
    );
  }
  if (!loadout) {
    return (
      <div className="admin-page">
        <p className="muted">加载中…</p>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">LOADOUT PROFILE</span>
          <h2>{loadout.name}</h2>
        </div>
        <div className="admin-toolbar__actions">
          <button className="btn btn-ghost" onClick={() => nav("/admin/loadouts")}>
            <ChevronLeftIcon size={14} /> 返回奇人库
          </button>
        </div>
      </div>
      <p className="muted">
        {loadout.username ?? "（无主）"} · {loadout.style || "无风格"} · {loadout.enabled ? "已解封" : "未解封"} · 参战 {loadout.battle_count} 场 · 创建于 {fmtDt(loadout.created_at).slice(0, 16)}
      </p>

      <section className="panel">
        <div className="panel__head">
          <h3>奇术（{loadout.abilities.length}）</h3>
          {loadout.tactic && <span className="muted">战术：{loadout.tactic}</span>}
        </div>
        <div className="tbl-list">
          {loadout.abilities.length === 0 && <p className="muted">（无奇术）</p>}
          {loadout.abilities.map((a) => (
            <div className="tbl-row tbl-row--wrap" key={a.id}>
              <span className="tbl-col tbl-col--main">
                <b>{a.name}</b>
                <small>{a.effect}</small>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel__head">
          <h3>行迹（{battles.length} 场）</h3>
        </div>
        <div className="tbl-list">
          {battles.length === 0 && <p className="muted">该奇人暂无行迹。</p>}
          {battles.map((b) => (
            <div className="tbl-row tbl-row--wrap" key={b.id}>
              <span className="tbl-col mono">#{b.id}</span>
              <span className="tbl-col tbl-col--main">
                <b>{b.user_a ?? "已离席"}</b> <i>对</i> <b>{b.user_b ?? "已离席"}</b>
              </span>
              <span className="tbl-col"><span className={`status-chip status-chip--${b.status}`}>{statusLabel(b.status)}</span></span>
              <span className="tbl-col">{b.winner ? `胜者：${b.winner}` : "—"}</span>
              <span className="tbl-col mono">{fmtDt(b.created_at).slice(0, 16)}</span>
              <span className="tbl-col tbl-actions">
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={() => nav(`/admin/battles/${b.id}`)}
                  title="查看战报：讨论 / 三视角 / 猜词链路"
                >
                  <ChevronRightIcon size={14} />
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
