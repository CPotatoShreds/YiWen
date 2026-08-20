import { CheckIcon, LockIcon } from "./icons";
import type { GuessCommentaryGroup } from "../types";

export interface GuessClueCardData {
  index: number;
  cracked: boolean;
  cracked_round?: number | null;
  name?: string | null;
  effect?: string | null;
}

function Verdict({ value }: { value: string }) {
  if (value === "是") return <span className="guess-card__clue-verdict--yes">是</span>;
  if (value === "部分是") {
    return <span>部分<span className="guess-card__clue-verdict--yes">是</span></span>;
  }
  return <span>{value}</span>;
}

export function GuessClueCards({
  cards,
  comments = [],
}: {
  cards: GuessClueCardData[];
  comments?: GuessCommentaryGroup[][];
}) {
  return (
    <div className="guess-board">
      {cards.map((card) => {
        const clues = comments.flatMap((roundComments) =>
          roundComments
            .filter((group) => group.index === card.index)
            .flatMap((group) => group.items)
        );

        return (
          <div key={card.index} className={`guess-card ${card.cracked ? "guess-card--cracked" : ""}`}>
            <div className="guess-card__head">
              <span className="guess-card__no">第 {card.index} 门</span>
              {card.cracked ? (
                <span className="guess-card__label guess-card__label--hit">
                  <CheckIcon size={13} /> 已看破{card.cracked_round ? ` · 第 ${card.cracked_round} 轮` : ""}
                </span>
              ) : (
                <span className="guess-card__label">
                  <LockIcon size={13} /> 未知奇术
                </span>
              )}
            </div>
            {card.cracked ? (
              <div>
                <div className="guess-card__name">{card.name}</div>
                <p className="guess-card__effect">{card.effect}</p>
              </div>
            ) : (
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                尚未看破
              </p>
            )}
            {clues.length > 0 && (
              <div className="guess-card__clues">
                <ul>
                  {clues.map((clue, clueIndex) => (
                    <li key={clueIndex}>
                      <span className="guess-card__clue-text">「{clue.text}」</span>
                      <b className="guess-card__clue-verdict"><Verdict value={clue.verdict} /></b>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
