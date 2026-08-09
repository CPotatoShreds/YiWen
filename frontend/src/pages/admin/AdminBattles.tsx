import { useEffect, useState } from "react";
import { api } from "../../api";
import { EyeIcon, TrashIcon, XIcon } from "../../components/icons";
import type { AdminBattle } from "./types";

function label(s: string) { return s === "pending" ? "推演中" : s === "failed" ? "失手" : "已落成"; }
function Detail({ battle, onClose }: { battle: AdminBattle; onClose: () => void }) { return <div className="modal-overlay" onClick={onClose}><div className="modal modal--wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}><div className="modal__head"><h3>行迹 #{battle.id}</h3><button className="modal__close" onClick={onClose} aria-label="关闭"><XIcon size={16} /></button></div><div className="battle-detail"><p><b>{battle.user_a ?? "已离席"}</b> 对 <b>{battle.user_b ?? "已离席"}</b> · {label(battle.status)} · {battle.winner ? `胜者：${battle.winner}` : "未决"}</p><pre className="pre-json">{JSON.stringify(battle.story, null, 2)}</pre></div></div></div>; }

export default function AdminBattles() {
  const [items, setItems] = useState<AdminBattle[]>([]); const [selected, setSelected] = useState<AdminBattle | null>(null); const [err, setErr] = useState("");
  const load = () => api<AdminBattle[]>("/admin/battles").then(setItems).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function remove(item: AdminBattle) { if (item.status === "pending") return; if (!window.confirm(`确认删除行迹 #${item.id}？猜词状态也会一并删除。`)) return; try { await api(`/admin/battles/${item.id}`, { method: "DELETE" }); await load(); } catch (e: any) { setErr(e.message); } }
  return <div className="admin-page"><div className="admin-toolbar"><div><span className="eyebrow">BATTLE RECORDS</span><h2>行迹库</h2></div><span className="muted">最近 {items.length} 场</span></div>{err && <p className="err">{err}</p>}<div className="tbl-list">{items.map((item) => <div className="tbl-row" key={item.id}><span className="tbl-col mono">#{item.id}</span><span className="tbl-col tbl-col--main"><b>{item.user_a ?? "已离席"}</b> <i>对</i> <b>{item.user_b ?? "已离席"}</b></span><span className="tbl-col"><span className={`status-chip status-chip--${item.status}`}>{label(item.status)}</span></span><span className="tbl-col">{item.winner ? `胜者：${item.winner}` : "—"}</span><span className="tbl-col tbl-actions"><button className="btn btn-ghost btn-icon btn-sm" onClick={() => setSelected(item)} title="查看完整故事"><EyeIcon size={14} /></button><button className="btn btn-danger btn-icon btn-sm" disabled={item.status === "pending"} onClick={() => remove(item)} title={item.status === "pending" ? "推演中不可删除" : "删除"}><TrashIcon size={14} /></button></span></div>)}</div>{items.length === 0 && <div className="empty"><p>暂无行迹。</p></div>}{selected && <Detail battle={selected} onClose={() => setSelected(null)} />}</div>;
}
