import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Loadout } from "../types";
import { LOADOUT_NUMBERS, loadoutLabel } from "../types";
import { LockIcon, PencilIcon, PlusIcon, SwordIcon } from "../components/icons";
import { BattleBanner, InkMountains } from "../components/Ornaments";
import StatNumber from "../components/StatNumber";

export default function Home() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [loadouts, setLoadouts] = useState<Loadout[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [noRepeat, setNoRepeat] = useState(false);
  const [err, setErr] = useState("");

  async function reload() {
    try {
      setLoadouts(await api<Loadout[]>("/loadouts"));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => {
    refresh(); // 同步最新名望/见闻：数值变化时由 StatNumber 浮出 ±N
    reload();
  }, [refresh]);

  const canFight = !!loadouts?.some((l) => l.enabled && l.abilities.length > 0);
  const enabledCount = loadouts?.filter((l) => l.enabled).length ?? 0;
  const armedCount = loadouts?.filter((l) => l.enabled && l.abilities.length > 0).length ?? 0;

  async function fight() {
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ id: number }>("/battles", {
        method: "POST",
        body: JSON.stringify({ no_repeat: noRepeat }),
      });
      nav(`/battles/${r.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function setEnabled(l: Loadout, value: boolean) {
    if (value && l.abilities.length === 0) {
      setErr("这位奇人尚无奇术，至少装入一个才能解封。");
      return;
    }
    setErr("");
    try {
      await api(`/loadouts/${l.id}`, { method: "PUT", body: JSON.stringify({ enabled: value }) });
      await reload();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  if (!user) return null;
  return (
    <>
      {/* 异闻师档案：记分牌 */}
      <section className="rise">
        <p className="eyebrow">驿路 · 人在途中</p>
        <h1 style={{ fontSize: 38, margin: "6px 0 20px" }}>{user.username}</h1>
        <div className="scoreboard">
          <div className="score">
            <span className="score__label">名望</span>
            <StatNumber value={user.rank_points} className="score__value accent" />
          </div>
          <div className="score">
            <span className="score__label">见闻</span>
            <StatNumber value={user.exp} className="score__value" />
          </div>
          <div className="score">
            <span className="score__label">已解封奇人</span>
            <span className="score__value">
              {enabledCount}
              <span className="muted" style={{ fontSize: 12 }}>
                / {user.max_loadouts}
              </span>
            </span>
          </div>
        </div>
      </section>

      {/* 启程：战斗大厅 */}
      <section className="rise rise-1">
        <div className="section-head">
          <h2 className="section-title">启程</h2>
          <p className="muted">见异闻，斗奇术</p>
        </div>
        {loadouts === null ? (
          <div className="skeleton" style={{ height: 120 }} />
        ) : canFight ? (
          <div
            className="panel"
            style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18 }}
          >
            <BattleBanner className={`battle-banner${busy ? " banner-sway" : ""}`} />
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <button className="btn btn-primary btn-lg" onClick={fight} disabled={busy}>
                <SwordIcon size={18} />
                {busy ? "对决中…" : "启程"}
              </button>
              <label className="checkline">
                <input
                  type="checkbox"
                  checked={noRepeat}
                  onChange={(e) => setNoRepeat(e.target.checked)}
                  disabled={busy}
                />
                <span>不匹配相同对决</span>
              </label>
            </div>
            <p className="muted" style={{ flex: 1, minWidth: 220, margin: 0 }}>
              已解封 {armedCount} 位奇人，将从其中随机挑一位出战；开场约 10-30 秒。
              {noRepeat && " 勾选后不会匹配到同一位对家奇人的重复对阵。"}
            </p>
          </div>
        ) : (
          <div className="empty">
            <LockIcon size={22} />
            <h3>尚未解封可启程的奇人</h3>
            <p>
              先在奇术篇写下奇术，装入任意一位奇人并解封。解封 = 可主动启程，也会被他人摇签点名。
            </p>
            <Link to="/abilities" className="btn btn-primary">
              去编排奇人
            </Link>
          </div>
        )}
        {busy && <p className="summary">正在摇签对家并铺陈战局…</p>}
        {err && <p className="err">{err}</p>}
      </section>

      {/* 异闻录·奇人：随时解封 / 未解封 */}
      <section className="rise rise-2">
        <div className="section-head">
          <h2 className="section-title">异闻录·奇人</h2>
          <p className="muted">奇人一旦解封，既可主动出击，也要随时准备好迎接其他异闻师的挑战</p>
          <Link to="/abilities" className="btn btn-ghost btn-sm">
            <PencilIcon size={14} />
            打开异闻录
          </Link>
        </div>
        {loadouts === null ? (
          <div className="char-grid">
            <div className="skeleton" style={{ height: 150 }} />
            <div className="skeleton" style={{ height: 150 }} />
            <div className="skeleton" style={{ height: 150 }} />
          </div>
        ) : loadouts.length === 0 ? (
          <div className="empty">
            <PencilIcon size={22} />
            <h3>奇人录空空如也</h3>
            <p>去异闻录立起第一位奇人——起个名字，装入奇术，解封即可启程。</p>
            <Link to="/abilities" className="btn btn-primary">
              去异闻录立起奇人
            </Link>
          </div>
        ) : (
          <div className="char-grid">
            {loadouts.map((l, i) => (
              <div className={`char-card${l.enabled ? " is-on" : ""}`} key={l.id}>
                <div className="char-card__head">
                  <span className="char-card__name">
                    <span className="seal">{LOADOUT_NUMBERS[i] ?? i + 1}</span>
                    {loadoutLabel(l, i)}
                  </span>
                  <span className="char-card__count">{l.abilities.length} 奇术</span>
                </div>
                {l.style && (
                  <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>
                    {l.style}
                  </p>
                )}
                <div className="char-card__chips">
                  {l.abilities.slice(0, 3).map((a) => (
                    <span className="chip chip--ability" key={a.id} style={{ fontSize: 12, padding: "4px 10px" }}>
                      {a.name}
                    </span>
                  ))}
                  {l.abilities.length > 3 && (
                    <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>
                      +{l.abilities.length - 3}
                    </span>
                  )}
                </div>
                {l.enabled && l.abilities.length === 0 && (
                  <p className="muted" style={{ fontSize: 12 }}>已解封但无奇术，不会被摇签点名。</p>
                )}
                <div className="char-card__foot">
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={l.enabled}
                      onChange={(e) => setEnabled(l, e.target.checked)}
                    />
                    <span className="toggle__track" />
                    <span className="toggle__label">{l.enabled ? "已解封" : "未解封"}</span>
                  </label>
                  <Link to="/abilities" className="char-card__manage">
                    编排奇术 →
                  </Link>
                </div>
              </div>
            ))}
            {loadouts.length < user.max_loadouts && (
              <Link to="/abilities" className="char-card char-card--add" title="去异闻录新建奇人">
                <PlusIcon size={22} />
                新建奇人
              </Link>
            )}
          </div>
        )}
        <p className="muted" style={{ marginTop: 18 }}>
          回忆过往的江湖旧事：<Link to="/books">行迹 →</Link>
        </p>
      </section>

      {/* 远山脚：卷底收尾的水墨山影 */}
      <div className="ink-footer" aria-hidden="true">
        <InkMountains />
      </div>
    </>
  );
}
