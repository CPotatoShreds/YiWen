import { useEffect, useState } from "react";
import { api } from "../../api";
import BarChart from "../../components/BarChart";
import { ClockIcon, TargetIcon, UsersIcon, BookIcon } from "../../components/icons";
import type { Stats, Traffic } from "./types";

function Stat({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof UsersIcon }) {
  return <div className="admin-stat"><span className="admin-stat__icon"><Icon size={18} /></span><span className="admin-stat__body"><span className="muted">{label}</span><b>{value}</b></span></div>;
}

function statusLabel(status: string) {
  return status === "pending" ? "推演中" : status === "failed" ? "失手" : "已落成";
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [traffic, setTraffic] = useState<Traffic | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api<Stats>("/admin/stats"), api<Traffic>("/admin/traffic")])
      .then(([s, t]) => { setStats(s); setTraffic(t); })
      .catch((e: Error) => setErr(e.message));
  }, []);

  if (err) return <p className="err">{err}</p>;
  if (!stats || !traffic) return <div className="skeleton" style={{ height: 420 }} />;

  return <div className="admin-page">
    <div className="admin-stats">
      <Stat label="异闻师" value={stats.total_users} icon={UsersIcon} />
      <Stat label="奇术" value={stats.total_abilities} icon={BookIcon} />
      <Stat label="奇人" value={stats.total_loadouts} icon={TargetIcon} />
      <Stat label="行迹" value={stats.total_battles} icon={ClockIcon} />
    </div>
    <div className="admin-grid admin-grid--wide">
      <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">LAST SEVEN DAYS</span><h2>请求流量</h2></div><span className="admin-total">{traffic.total_requests} 次</span></div><BarChart data={traffic.daily.map((d) => ({ label: d.date.slice(5), value: d.count }))} /></section>
      <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">BATTLE STATUS</span><h2>行迹状态</h2></div></div><div className="status-list"><div><span className="lamp lamp--done" />已落成 <b>{stats.battles_done}</b></div><div><span className="lamp lamp--pending" />推演中 <b>{stats.battles_pending}</b></div><div><span className="lamp lamp--failed" />失手 <b>{stats.battles_failed}</b></div></div></section>
    </div>
    <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">RECENT RECORDS</span><h2>最近行迹</h2></div><span className="muted">最新十场</span></div>{stats.recent_battles.length === 0 ? <p className="muted">尚无行迹。</p> : <div className="tbl-list">{stats.recent_battles.map((battle) => <div className="tbl-row" key={battle.id}><span className="tbl-col mono">#{battle.id}</span><span className="tbl-col tbl-col--main">{battle.user_a ?? "已离席"} <i>对</i> {battle.user_b ?? "已离席"}</span><span className="tbl-col">{battle.winner ? `胜者：${battle.winner}` : "—"}</span><span className="tbl-col"><span className={`status-chip status-chip--${battle.status}`}>{statusLabel(battle.status)}</span></span></div>)}</div>}</section>
  </div>;
}
