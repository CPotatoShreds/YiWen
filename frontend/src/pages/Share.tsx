import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { Battle } from "../types";
import MatchCard from "../components/MatchCard";
import { LockIcon, TrophyIcon } from "../components/icons";


function toStatus(s: string): "pending" | "done" | "failed" {
  if (s === "pending") return "pending";
  if (s === "failed") return "failed";
  return "done";
}

export default function Share() {
  const { token } = useParams();
  const [b, setB] = useState<Battle | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api<Battle>(`/battles/share/${token}`).then(setB).catch((e: any) => setErr(e.message));
  }, [token]);

  if (err) return <p className="err">{err}</p>;
  if (!b) {
    return (
      <>
        <div className="share-hero">
          <div className="skeleton" style={{ height: 180, maxWidth: 520, margin: "0 auto" }} />
        </div>
      </>
    );
  }

  const abA = b.story?.abilities_a || [];
  const abB = b.story?.abilities_b || [];

  return (
    <>
      <div className="share-hero">
        <p className="eyebrow">公开行迹</p>
        <h1 style={{ fontSize: 30, margin: "8px 0 24px" }}>异闻录 · 行迹传阅</h1>
        <div style={{ maxWidth: 640, margin: "0 auto", textAlign: "left" }}>
          <MatchCard
            userA={b.fighter_a}
            userB={b.fighter_b}
            subA={b.user_a}
            subB={b.user_b}
            status={toStatus(b.status)}
            winner={b.winner}
            variant="hero"
          />
        </div>
      </div>

      {b.status === "pending" && (
        <p className="summary" style={{ textAlign: "center" }}>
          对决中…
        </p>
      )}
      {b.status === "failed" && <p className="err" style={{ textAlign: "center" }}>铺陈败落。</p>}
      {b.status !== "pending" && b.status !== "failed" && b.story && (
        <>
          <div className="panel narration">{b.story.narration_a ?? b.story.narration_b ?? "（无行迹内容）"}</div>

          <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
            {b.revealed ? (
              <>
                <div className="panel">
                  <div className="panel__head">
                    <h3>{b.fighter_a} 的奇术</h3>
                  </div>
                  {abA.map((a, i) => (
                    <div className="ability-item" key={i}>
                      <div className="ability-item__body">
                        <div className="ability-item__name">{a.name}</div>
                        <p className="ability-item__effect">{a.effect}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="panel">
                  <div className="panel__head">
                    <h3>{b.fighter_b} 的奇术</h3>
                  </div>
                  {abB.map((a, i) => (
                    <div className="ability-item" key={i}>
                      <div className="ability-item__body">
                        <div className="ability-item__name">{a.name}</div>
                        <p className="ability-item__effect">{a.effect}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="panel">
                <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--muted)", fontSize: 13 }}>
                  <LockIcon size={16} />
                  双方奇术仍保密——只有猜中的败家才能看破它们。
                </div>
              </div>
            )}
          </div>

          {b.winner && (
            <p className="muted" style={{ marginTop: 18, display: "flex", alignItems: "center", gap: 6 }}>
              <TrophyIcon size={14} /> 胜者：{b.winner}
            </p>
          )}
        </>
      )}
    </>
  );
}
