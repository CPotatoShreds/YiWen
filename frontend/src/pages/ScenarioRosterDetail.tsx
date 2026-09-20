import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BookIcon, ChevronLeftIcon, ChevronRightIcon, ScrollIcon } from "../components/icons";
import { CardBack, SealStamp } from "../components/Ornaments";
import { ScenarioHistory } from "../components/ScenarioHistory";
import { isInProgress, type ScenarioHistoryItem } from "../scenarioModel";

type Feedback = { text?: string; verdict?: string; round?: number | string };
type GuessRound = {
  attempt?: number;
  matches?: { card_index?: number; text?: string; verdict?: string }[];
  comments?: { index?: number; items?: { text?: string; verdict?: string }[] }[];
};
type Card = { index: number; cracked: boolean; name?: string; effect?: string; feedback?: Feedback[] };
type Progress = {
  attempts: number;
  guess_count: number;
  guess_credits: number;
  cracked_cards: Card[];
  guess_rounds?: GuessRound[];
};
type Detail = {
  scenario: { id: string; slug: string; name: string };
  roster: {
    character_name: string;
    character_bio: string;
    owner_name: string;
    ability_count: number;
    challenger_win_rate: number | null;
  };
  viewer_role: string;
  my_progress?: Progress | null;
  my_challenges: ScenarioHistoryItem[];
};
type Clue = { text: string; verdict?: string; round?: number | string };

// 卡牌在扇面上相对居中的偏移；单张居中，多张两侧各露出一张
function relativePosition(index: number, active: number, count: number) {
  let offset = index - active;
  if (offset > count / 2) offset -= count;
  if (offset < -count / 2) offset += count;
  return offset;
}

function cardStyle(position: number, count: number): CSSProperties {
  if (count <= 2) {
    if (position === 0) {
      return {
        position: "absolute",
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -50%) scale(1)",
        opacity: 1,
        zIndex: 10,
        transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
        pointerEvents: "auto",
      };
    }
    const side = position < 0 ? -1 : 1;
    return {
      position: "absolute",
      left: `calc(50% + ${side * 34}%)`,
      top: "50%",
      transform: `translate(-50%, -50%) scale(0.78) rotate(${side * 4}deg)`,
      opacity: 0.6,
      zIndex: 5,
      transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
      pointerEvents: "auto",
    };
  }
  if (position === 0) {
    return {
      position: "absolute",
      left: "50%",
      top: "50%",
      transform: "translate(-50%, -50%) scale(1)",
      opacity: 1,
      zIndex: 10,
      transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
      pointerEvents: "auto",
    };
  }
  if (Math.abs(position) === 1) {
    const side = position < 0 ? -1 : 1;
    return {
      position: "absolute",
      left: `calc(50% + ${side * 32}%)`,
      top: "50%",
      transform: `translate(-50%, -50%) scale(0.78) rotate(${side * 5}deg)`,
      opacity: 0.55,
      zIndex: 5,
      transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
      pointerEvents: "auto",
    };
  }
  return {
    position: "absolute",
    left: "50%",
    top: "50%",
    transform: "translate(-50%, -50%) scale(0.6)",
    opacity: 0,
    zIndex: 0,
    pointerEvents: "none",
    transition: "all 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
  };
}

// 猜词检定的裁定词 → 配色语义（是=墨绿 否=朱砂 部分/不确定=中性）
function verdictClass(v?: string) {
  if (!v) return "verdict-neutral";
  if (v === "是") return "verdict-yes";
  if (v === "否") return "verdict-no";
  if (v === "部分是") return "verdict-partial";
  return "verdict-neutral";
}

export default function ScenarioRosterDetail() {
  const { scenarioSlug, rosterId } = useParams<{ scenarioSlug: string; rosterId: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [activeCard, setActiveCard] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!scenarioSlug || !rosterId) return;
    api<Detail>(`/scenarios/${scenarioSlug}/rosters/${rosterId}`)
      .then(setDetail)
      .catch((cause: Error) => setError(cause.message));
  }, [scenarioSlug, rosterId]);

  const cards = useMemo(() => {
    const source = detail?.my_progress?.cracked_cards ?? [];
    const count = detail?.roster.ability_count ?? source.length;
    const byIndex = new Map(source.map((c) => [c.index, c]));
    return Array.from({ length: count }, (_, i) => byIndex.get(i + 1) ?? { index: i + 1, cracked: false });
  }, [detail]);

  useEffect(() => {
    setActiveCard((cur) => (cards.length ? cur % cards.length : 0));
  }, [cards.length]);

  const progress = detail?.my_progress;
  const current = cards[activeCard];

  const clues = useMemo<Clue[]>(() => {
    if (!current || !progress) return [];
    const collected: Clue[] = [];
    for (const item of current.feedback ?? []) {
      if (item.text) collected.push({ text: item.text, verdict: item.verdict, round: item.round });
    }
    for (const [ri, round] of (progress.guess_rounds ?? []).entries()) {
      for (const m of round.matches ?? [])
        if (m.card_index === current.index && m.text)
          collected.push({ text: m.text, verdict: m.verdict, round: round.attempt ?? ri + 1 });
      for (const g of round.comments ?? [])
        if (g.index === current.index)
          for (const c of g.items ?? [])
            if (c.text) collected.push({ text: c.text, verdict: c.verdict, round: round.attempt ?? ri + 1 });
    }
    const unique = new Map<string, Clue>();
    for (const clue of collected) unique.set(`${clue.round}-${clue.text}`, clue);
    return [...unique.values()].reverse();
  }, [current, progress]);

  const moveCard = (step: number) => {
    if (cards.length) setActiveCard((i) => (i + step + cards.length) % cards.length);
  };

  if (error) return <p className="roster-error">{error}</p>;
  if (!detail) return <div className="roster-skeleton" />;

  const cracked = cards.filter((c) => c.cracked).length;
  const winRatePct = detail.roster.challenger_win_rate == null ? null : Math.round(detail.roster.challenger_win_rate * 100);
  const showArrows = cards.length > 1;

  return (
    <div className="roster-page">
      {/* 上区：奇人信息 + 奇术卡扇形轮盘 */}
      <section className="roster-stage">
        <div className="roster-metrics">
          <div className="roster-metrics__identity">
            <div className="roster-metrics__name-row">
              <ScrollIcon size={15} />
              <h2>{detail.roster.character_name}</h2>
            </div>
            <p className="roster-metrics__owner">
              {detail.scenario.name} · {detail.roster.owner_name}
            </p>
          </div>
          <p className="roster-metrics__bio">{detail.roster.character_bio || "暂无简介"}</p>
          <div className="roster-metrics__footer">
            <div className="roster-metrics__row">
              <div className="roster-metrics__stat">
                <b>{cracked}</b>
                <span>/{cards.length} 已知</span>
              </div>
              <div className="roster-metrics__divider" />
              <div className="roster-metrics__stat">
                <b>{progress?.attempts ?? 0}</b>
                <span>次推演</span>
              </div>
              <div className="roster-metrics__divider" />
              <div className="roster-metrics__stat">
                <b>{progress?.guess_credits ?? 0}</b>
                <span>可提问</span>
              </div>
            </div>
            {winRatePct != null && (
              <div className="roster-metrics__winrate">
                <span>全体挑战者胜率</span>
                <b>{winRatePct}%</b>
              </div>
            )}
          </div>
          <Link className="roster-metrics__back" to={`/scenarios/${detail.scenario.slug}`}>
            返回卷册
          </Link>
        </div>

        <div
          className="roster-wheel"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") moveCard(-1);
            if (e.key === "ArrowRight") moveCard(1);
          }}
          aria-label="奇术卡片轮转"
        >
          <div className="roster-wheel__label">
            <span>奇术卡片</span>
            <small>
              当前选中 · {activeCard + 1} / {cards.length || 0}
            </small>
          </div>

          {showArrows && (
            <button
              type="button"
              className="roster-wheel__arrow roster-wheel__arrow--prev"
              aria-label="上一门奇术"
              onClick={() => moveCard(-1)}
            >
              <ChevronLeftIcon size={20} />
            </button>
          )}

          <div className="roster-wheel__track">
            {cards.map((card, index) => {
              const pos = relativePosition(index, activeCard, cards.length);
              return (
                <article
                  className={`roster-card ${card.cracked ? "is-cracked" : "is-unknown"} ${pos === 0 ? "is-active" : ""}`}
                  style={cardStyle(pos, cards.length)}
                  key={card.index}
                  aria-hidden={Math.abs(pos) > 1 && cards.length > 2}
                >
                  {!card.cracked && <CardBack />}
                  <header className="roster-card__head">
                    <span className="roster-card__label">第 {card.index} 门奇术</span>
                    {card.cracked && <SealStamp char="破" size={24} className="roster-card__seal" />}
                  </header>
                  {card.cracked ? (
                    <>
                      <h3>{card.name || "已看破奇术"}</h3>
                      <p>{card.effect || "已揭示效果，暂无详述。"}</p>
                    </>
                  ) : (
                    <span className="roster-card__veiled">未看破</span>
                  )}
                </article>
              );
            })}
          </div>

          {showArrows && (
            <button
              type="button"
              className="roster-wheel__arrow roster-wheel__arrow--next"
              aria-label="下一门奇术"
              onClick={() => moveCard(1)}
            >
              <ChevronRightIcon size={20} />
            </button>
          )}

          <div className="roster-wheel__action">
            <Link
              className="btn btn-primary"
              to={`/scenarios/${scenarioSlug}/rosters/${rosterId}/battle`}
            >
              起笔
            </Link>
          </div>
        </div>
      </section>

      {/* 下区：挑战记录 + 当前卡线索（各自内部滚动） */}
      <section className="roster-book">
        <div className="roster-book__page">
          <header className="roster-book__header">
            <div className="roster-book__header-left">
              <BookIcon size={16} />
              <h2>挑战记录</h2>
            </div>
            <span className="roster-book__meta">左页 · 翻阅</span>
          </header>
          <div className="roster-book__body">
            <ScenarioHistory
              items={detail.my_challenges}
              emptyText="完成第一场挑战后，这里会留下记录。"
              resolveHref={(item) =>
                isInProgress(item.status)
                  ? `/scenarios/${scenarioSlug}/rosters/${rosterId}/battle`
                  : `/scenarios/${scenarioSlug}/rosters/${rosterId}/records?run=${item.id}`
              }
            />
          </div>
        </div>

        <div className="roster-book__page roster-book__page--clues">
          <header className="roster-book__header">
            <div className="roster-book__header-left">
              <span className="roster-book__mark">当前卡</span>
              <h2>{current?.cracked ? current.name || "已看破奇术" : `第 ${current?.index ?? "?"} 门奇术`}</h2>
            </div>
            <span className="roster-book__meta">右页 · 行迹线索</span>
          </header>
          <div className="roster-book__body">
            {clues.length ? (
              <div className="roster-clues" aria-live="polite">
                {clues.map((clue, i) => (
                  <article key={`${clue.round}-${clue.text}-${i}`} className="roster-clue">
                    <p className="roster-clue__text">{clue.text}</p>
                    {clue.verdict && (
                      <span className={`roster-clue__verdict ${verdictClass(clue.verdict)}`}>{clue.verdict}</span>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <p className="roster-book__empty">尚无关于此门奇术的线索记录。</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
