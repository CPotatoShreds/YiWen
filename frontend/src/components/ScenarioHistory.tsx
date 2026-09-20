import { Link } from "react-router-dom";
import type { ScenarioHistoryItem } from "../scenarioModel";

/**
 * 挑战记录列表：阵容页与战斗界面共用。
 * resolveHref 返回该记录详情页链接；挑战进行中时由战斗页自身渲染当前回合。
 */
export function ScenarioHistory({
  items,
  resolveHref,
  emptyText,
}: {
  items: ScenarioHistoryItem[];
  resolveHref: (item: ScenarioHistoryItem) => string | null;
  emptyText: string;
}) {
  if (!items.length) return <p className="roster-book__empty">{emptyText}</p>;
  return (
    <div className="roster-history">
      {items.map((item) => {
        const href = resolveHref(item);
        const verdict = item.won === true ? "胜" : item.won === false ? "负" : "待定";
        const row = (
          <>
            <span className="roster-history__num">{item.challenge_number}</span>
            <span className="roster-history__info">
              <strong>{item.challenger_character_name || "未知挑战者"}</strong>
              <small>{item.strategy || "跳过策略，由奇人自行应对"}</small>
            </span>
            <span
              className={`roster-history__verdict ${item.won === true ? "is-won" : item.won === false ? "is-lost" : "is-pending"}`}
            >
              {verdict}
            </span>
          </>
        );
        return href ? (
          <Link className="roster-history__row" to={href} key={item.id}>
            {row}
          </Link>
        ) : (
          <div className="roster-history__row is-current" key={item.id} aria-current="true">
            {row}
          </div>
        );
      })}
    </div>
  );
}
