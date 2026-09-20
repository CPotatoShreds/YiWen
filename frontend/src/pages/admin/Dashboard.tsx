import { useEffect, useState } from "react";
import { api } from "../../api";
import BarChart from "../../components/BarChart";
import { TargetIcon, UsersIcon, BookIcon } from "../../components/icons";
import type { Stats, Traffic } from "./types";

function Stat({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof UsersIcon }) {
  return <div className="admin-stat"><span className="admin-stat__icon"><Icon size={18} /></span><span className="admin-stat__body"><span className="muted">{label}</span><b>{value}</b></span></div>;
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
      <Stat label="小天下集" value="启用中" icon={TargetIcon} />
    </div>
    <div className="admin-grid admin-grid--wide">
      <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">LAST SEVEN DAYS</span><h2>请求流量</h2></div><span className="admin-total">{traffic.total_requests} 次</span></div><BarChart data={traffic.daily.map((d) => ({ label: d.date.slice(5), value: d.count }))} /></section>
      <section className="panel admin-panel"><div className="panel__head"><div><span className="eyebrow">ACTIVE DOMAIN</span><h2>现役玩法</h2></div></div><p className="muted">小天下集</p></section>
    </div>
  </div>;
}
