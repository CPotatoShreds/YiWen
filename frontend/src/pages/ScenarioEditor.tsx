import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

type Scenario = { id: string; work_revision?: { id: string; status: string; lock_version: number; content: Record<string, unknown> } | null };
export default function ScenarioEditor() {
  const { id } = useParams<{ id: string }>(); const navigate = useNavigate(); const [scenario, setScenario] = useState<Scenario | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (id) api<Scenario>(`/creator/scenarios/${id}`).then(setScenario).catch((e: Error) => setError(e.message)); }, [id]);
  const submit = async () => { if (!id) return; setBusy(true); try { await api(`/creator/scenarios/${id}/submit`, { method: "POST" }); navigate("/creator"); } catch (e) { setError(e instanceof Error ? e.message : "提交失败"); } finally { setBusy(false); } };
  if (!scenario) return <p className="err">{error || "正在读取草稿…"}</p>;
  const content = scenario.work_revision?.content ?? {}; const status = scenario.work_revision?.status;
  return <section className="scenario-composer panel"><div className="section-head"><div><h1 className="section-title">{String(content.name || "完整异闻")}</h1><p className="muted">状态：{status === "draft" ? "草稿" : status || "未知"}</p></div><Link className="muted" to="/creator">返回创作台</Link></div><div className="scenario-preview"><p>{String(content.summary || "")}</p><h3>背景</h3><p>{String(content.background || "")}</p><h3>胜利条件</h3><p>{String(content.victory_condition || "")}</p><h3>指导策略</h3><p>{String(content.guidance || "")}</p><h3>守方</h3><p>{String(content.guardian_name || "")}</p></div>{error && <p className="err">{error}</p>}<div className="creator-canvas__actions"><button className="btn btn-primary" disabled={busy || status !== "draft"} onClick={() => void submit()}>提交管理员审核</button></div></section>;
}
