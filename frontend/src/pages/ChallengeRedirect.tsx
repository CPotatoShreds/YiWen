import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

/** 旧单局归档路由（/scenario-challenges/:id）的兼容跳转：解析归属后送往记录阅读页。 */
export default function ChallengeRedirect() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    let alive = true;
    (async () => {
      try {
        const detail = await api<{ scenario_id?: string; roster_id: string }>(`/scenario-challenges/${id}`);
        const scenario = await api<{ slug: string }>(`/scenarios/${detail.scenario_id}`);
        if (!alive) return;
        nav(`/scenarios/${scenario.slug}/rosters/${detail.roster_id}/records?run=${id}`, { replace: true });
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "记录不存在");
      }
    })();
    return () => {
      alive = false;
    };
  }, [id, nav]);

  return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;
}