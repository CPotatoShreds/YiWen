// VS 对战卡：签名元素，贯穿书场话本 / 话本详情头 / 传阅页。
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { ChevronRightIcon, TrophyIcon } from "./icons";

interface Props {
  userA: string; // 主字：奇人名字
  userB: string;
  subA?: string; // 副字：异闻师名字（与主字相同时不重复显示）
  subB?: string;
  status: "pending" | "done" | "failed";
  winner?: string | null;
  footer?: ReactNode;
  rankDelta?: { value: number; note?: string } | null; // 我的名望增减徽标（行迹列表着重显示）
  to?: string;
  variant?: "default" | "hero";
}

function StatusLine({ status, winner }: { status: Props["status"]; winner?: string | null }) {
  const lamp =
    status === "done" ? "lamp lamp--done" : status === "failed" ? "lamp lamp--failed" : "lamp lamp--pending";
  if (status === "done") {
    return winner ? (
      <>
        <span className={lamp} />
        <span>
          胜者 <b>{winner}</b>
        </span>
      </>
    ) : (
      <>
        <span className={lamp} />
        <span>
          <b>和局</b> · 未分胜负
        </span>
      </>
    );
  }
  if (status === "pending") {
    return (
      <>
        <span className={lamp} />
        <span>对决中…</span>
      </>
    );
  }
  return (
    <>
      <span className={lamp} />
      <span>铺陈败落</span>
    </>
  );
}

export default function MatchCard({
  userA,
  userB,
  subA,
  subB,
  status,
  winner,
  footer,
  rankDelta,
  to,
  variant = "default",
}: Props) {
  const fighter = (name: string, sub: string | undefined, side: "a" | "b") => {
    // 胜者是异闻师（用户名），对应用户名所在那侧（sub）；奇人名与用户名相同时按名字兜底
    const win = status === "done" && (winner === name || winner === sub);
    return (
      <div className="match-card__fighter" style={side === "b" ? { textAlign: "right" } : undefined}>
        <b className={win ? "win" : undefined}>
          {name}
          {win && (
            <span className="win-tag">
              <TrophyIcon size={12} />
              胜
            </span>
          )}
        </b>
        {sub && sub !== name && <span className="match-card__sub">{sub}</span>}
      </div>
    );
  };

  const card = (
    <div className={`match-card${variant === "hero" ? " match-card--hero" : ""}`}>
      <div className="match-card__fighters">
        {fighter(userA, subA, "a")}
        <div className="vs-mark match-card__vs">VS</div>
        {fighter(userB, subB, "b")}
      </div>
      <div className="match-card__meta">
        <StatusLine status={status} winner={winner} />
        {rankDelta && (
          <span className={`rank-delta${rankDelta.value > 0 ? " is-up" : rankDelta.value < 0 ? " is-down" : ""}`}>
            {rankDelta.note ?? (rankDelta.value > 0 ? `名望 +${rankDelta.value}` : `名望 ${rankDelta.value}`)}
          </span>
        )}
        {footer}
        {to && (
          <span className="go">
            翻阅行迹 <ChevronRightIcon size={14} />
          </span>
        )}
      </div>
    </div>
  );

  return to ? (
    <Link to={to} style={{ display: "block", textDecoration: "none" }}>
      {card}
    </Link>
  ) : (
    card
  );
}
