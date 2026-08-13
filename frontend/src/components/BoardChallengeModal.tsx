// 点将挑战弹窗：挑一位自己的出战奇人 vs 榜上刻印（奇人榜列表与条目详情共用）。
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { CheckIcon, SwordIcon, XIcon } from "./icons";
import type { BoardEntry, Loadout } from "../types";

interface Props {
  entry: BoardEntry;
  onClose(): void;
  onDone(battleId: number): void;
}

export default function BoardChallengeModal({ entry, onClose, onDone }: Props) {
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [picked, setPicked] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    api<Loadout[]>("/loadouts")
      .then((ls) => setLoadouts(ls))
      .catch((e: any) => setErr(e.message));
  }, []);

  const pickable = loadouts.filter((l) => l.enabled && l.abilities.length > 0);

  async function doChallenge() {
    if (picked == null) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ battle_id: number }>(`/board/${entry.id}/challenge`, {
        method: "POST",
        body: JSON.stringify({ loadout_id: picked }),
      });
      onDone(r.battle_id);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>点将出战：挑战「{entry.name}」</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <p className="muted" style={{ padding: "2px 2px 12px", lineHeight: 1.7 }}>
          {entry.user} 的「{entry.name}」刻印于此（奇术保密）。挑一位自己的奇人出战，切磋不计名望。
        </p>
        {pickable.length === 0 ? (
          <p className="muted" style={{ padding: "4px 2px 10px", lineHeight: 1.7 }}>
            你还没有已解封且装奇术的奇人，无法点将。去 <Link to="/abilities">异闻录</Link> 编排后再来。
          </p>
        ) : (
          <div className="picker">
            {pickable.map((l) => (
              <button
                key={l.id}
                className={`picker-item${picked === l.id ? " is-on" : ""}`}
                onClick={() => setPicked(l.id)}
              >
                <span className="picker-item__name">{l.name}</span>
                <span className="picker-item__eff">
                  {l.style || "未写风格"} · {l.abilities.length} 门奇术
                </span>
                {picked === l.id && (
                  <span className="picker-item__check">
                    <CheckIcon size={16} />
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
        {err && <p className="err" style={{ margin: "4px 2px 0" }}>{err}</p>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 14 }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-primary" onClick={doChallenge} disabled={busy || picked == null}>
            <SwordIcon size={15} />
            {busy ? "递帖中…" : "递上挑战"}
          </button>
        </div>
      </div>
    </div>
  );
}
