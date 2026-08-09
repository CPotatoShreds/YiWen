import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import MatchCard from "../components/MatchCard";
import { BookIcon, SwordIcon } from "../components/icons";

interface HistoryItem {
  id: number;
  user_a: string;
  user_b: string;
  fighter_a: string;
  fighter_b: string;
  status: string;
  winner: string | null;
  rank_delta_a: number;
  rank_delta_b: number;
  story: { narration_a?: string; narration_b?: string } | null;
  friendly: boolean;
}

function toStatus(s: string): "pending" | "done" | "failed" {
  if (s === "pending") return "pending";
  if (s === "failed") return "failed";
  return "done";
}

export default function Books() {
  const { user } = useAuth();
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api<HistoryItem[]>("/battles").then(setHistory).catch((e: any) => setErr(e.message));
  }, []);

  const pendingCount = history?.filter((h) => h.status === "pending").length ?? 0;

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">行迹</h1>
        <p className="muted">{pendingCount > 0 ? `${pendingCount} 卷对决中` : "你摆过的场，尽数落于此"}</p>
        <Link to="/" className="btn btn-primary btn-sm">
          <SwordIcon size={14} />
          启程
        </Link>
      </div>
      {err && <p className="err">{err}</p>}

      {history === null ? (
        <div style={{ display: "grid", gap: 12 }}>
          <div className="skeleton" style={{ height: 92 }} />
          <div className="skeleton" style={{ height: 92 }} />
        </div>
      ) : history.length === 0 ? (
        <div className="empty">
          <BookIcon size={22} />
          <h3>尚无行迹</h3>
          <p>去书场启程第一场，落成之后便会永久收在案头，供回味与传阅。</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {history.map((h) => {
            const isA = h.user_a === user?.username;
            const myDelta = isA ? h.rank_delta_a : h.rank_delta_b;
            return (
            <MatchCard
              key={h.id}
              userA={h.fighter_a}
              userB={h.fighter_b}
              subA={h.user_a}
              subB={h.user_b}
              status={toStatus(h.status)}
              winner={h.winner}
              to={`/battles/${h.id}`}
              rankDelta={
                h.status === "done" ? (h.friendly ? { value: 0, note: "切磋 · 不计" } : { value: myDelta }) : undefined
              }
              footer={
                h.status === "done" ? (
                  <span>
                    {h.friendly && "切磋 · "}
                    {(h.story?.narration_a ?? h.story?.narration_b ?? "").slice(0, 26)}…
                  </span>
                ) : undefined
              }
            />
            );
          })}
        </div>
      )}
    </>
  );
}
