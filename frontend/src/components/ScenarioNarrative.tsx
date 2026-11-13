import { useEffect, useRef, useState, type ReactNode } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { EmptyScroll } from "./Ornaments";
import { InkWriting } from "./InkWriting";
import type { Message } from "../scenarioModel";

/** 全破局书页的三页签：推演全文、挑战者正文、刻印正文各占一页。 */
type Pane = "deduction" | "challenger" | "guardian";
const PANES: { key: Pane; label: string }[] = [
  { key: "deduction", label: "推演" },
  { key: "challenger", label: "挑战者视角" },
  { key: "guardian", label: "刻印视角" },
];

/**
 * 叙述正文分段：模型按写作习惯用空行断段，后端原样存。整段塞进一个 <p> 时
 * `text-indent` 只吃块内第一行，且 `white-space: pre-wrap` 会把 `\n\n` 留成一个空行——
 * 于是「首段缩进、其余不缩进、段间空一行」。这里按换行（一个或连续多个）切成独立 <p>，
 * 每段各自首行缩进两格，段间间距交给 CSS 决定（书页为 0，记录页约一行）。
 *
 * 模型会用最朴素的 Markdown：`**加粗**` 与行首 `* ` 列表符。书页不做整排 Markdown，
 * 只把成对 `**…**` 转成强调、剥掉行首列表符；不成对的记号原样保留——流式途中
 * 半截记号先到属正常，补齐后半自然成形。
 */
function Prose({ text }: { text: string }) {
  const paragraphs = text
    .split(/\n+/)
    .map((line) => line.trim().replace(/^[*•-]\s+/, ""))
    .filter(Boolean);
  if (!paragraphs.length) return null;
  return (
    <>
      {paragraphs.map((line, index) => (
        <p key={index}>
          {line.split(/\*\*([^*]+)\*\*/g).map((part, i) =>
            i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
          )}
        </p>
      ))}
    </>
  );
}

/**
 * 行迹书页：己方叙述正文是书页主文；推演全文（看破解锁后）以独立条目先呈，
 * 直播期由"实时推演正文 → 己方逐字"在同一区域接替。不再有视角切换与视角标签。
 *
 * 例外：一页要容下的内容不止一段时——自己打自己的刻印（推演 + 双方正文），
 * 或已看破全部奇术的挑战者（推演 + 己方正文）——书页改成内嵌页签，同一时刻只读一页；
 * 本局尚未落定时，空着的那页照常演笔墨占位。记录页保持逐条堆叠：那是按时间读的行迹。
 *
 * 两种形态：
 * - `page`（默认）：书页标题头（行迹 / 第 N 次推演），记录页展开行用它；
 * - `book`：对战页书页，无标题头，改书眉与页脚，正文按 38px 行网格排（见 index.css 的
 *   `.scenario-manuscript--book`）。此形态只呈推演正文——策略与各种提示文字一律不出，
 *   纸页高度固定、正文在内滚动。落墨不跟随滚动：读者不自己下翻就不会被拽动。
 */
export function ScenarioManuscript({
  messages,
  own,
  ownLabel,
  guardianLabel = "",
  title,
  liveText = "",
  liveGuardian = "",
  liveDeduction = "",
  placeholder,
  note,
  emptyText,
  variant = "page",
  runningHead,
  folio,
  pending = false,
  unlocked = false,
}: {
  messages: Message[];
  // both = 自己打自己的刻印：书页分成推演/挑战者/刻印三页，记录页依次堆叠
  own: "challenger" | "guardian" | "both";
  ownLabel: string;
  guardianLabel?: string;
  title?: ReactNode;
  liveText?: string;
  liveGuardian?: string;
  liveDeduction?: string;
  placeholder?: ReactNode;
  note?: ReactNode;
  emptyText: string;
  variant?: "page" | "book";
  runningHead?: { left: ReactNode; right: ReactNode };
  folio?: { left: ReactNode; right: ReactNode };
  /** 本局尚未落定：三页签里还没内容的页显示笔墨占位（落定后空页即静默）。 */
  pending?: boolean;
  /** 本局推演全文是否已对读者解锁（后端 `god_unlocked`）：决定书页是否多出「推演」一页。 */
  unlocked?: boolean;
}) {
  const bare = variant === "book";
  // 书页上会同时出现不止一段时才分页签：全知者读得到推演，自己打自己的刻印两侧正文都在。
  // 只看书页形态（记录页 variant="page" 仍是逐条堆叠的时间流）；未全破的局只有一段，不分页。
  const panes: Pane[] =
    own === "both"
      ? ["deduction", "challenger", "guardian"]
      : own === "challenger" && unlocked
        ? ["deduction", "challenger"]
        : [];
  const tabbed = bare && panes.length > 1;
  const [pane, setPane] = useState<Pane>("deduction");
  // 读过哪几页：其余页随后进了正文就点一粒墨点提示，免得读者以为只写了推演
  const [seen, setSeen] = useState<Set<Pane>>(() => new Set<Pane>(["deduction"]));
  // 页签集合会随解锁状态变化（中途全破会补出「推演」页），当前页必须落在集合内
  const active: Pane = panes.includes(pane) ? pane : (panes[0] ?? "deduction");
  const choose = (next: Pane) => {
    setPane(next);
    setSeen((prev) => (prev.has(next) ? prev : new Set(prev).add(next)));
  };
  // 换页即回页首：上一页读到一半的滚动位置对新的一页没有意义
  const bodyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (tabbed) bodyRef.current?.scrollTo({ top: 0 });
  }, [active, tabbed]);
  // 同屏唯一真源：推演正文要么由实时块承担，要么由结算后的 turn.omniscient 承担，绝不并排。
  // 必须看 messages 而不是只靠「turn 事件到达时清空 live」——2 秒轮询可能先一步把回合写进
  // messages，那一帧若只靠清空就会双份显示。
  const settled = messages.some((message) => message.role === "views");
  const liveGod = liveDeduction !== "" && !settled;

  // 一条 views 消息可能同时含两侧正文（自己打自己的刻印）；按视角拆成若干条目
  type View = { side: "challenger" | "guardian"; text: string; label: string };
  const viewsOf = (message: Message): View[] => {
    const challengerText = message.challenger_text ?? "";
    const guardianText = message.guardian_text ?? (message.role === "guardian" ? (message.text ?? "") : "");
    if (own === "both") {
      return [
        { side: "challenger" as const, text: challengerText, label: ownLabel },
        { side: "guardian" as const, text: guardianText, label: guardianLabel },
      ].filter((view) => view.text);
    }
    const content = own === "challenger" ? challengerText : guardianText;
    return content ? [{ side: own, text: content, label: ownLabel }] : [];
  };

  // entries 是记录页/单侧书页的顺次条目；groups 是全破局三个页签各自的条目
  const groups: Record<Pane, ReactNode[]> = { deduction: [], challenger: [], guardian: [] };
  const entries: ReactNode[] = [];
  messages.forEach((message, index) => {
    // 策略条目只在记录页呈现；对战书页不自呈策略
    if (message.role === "challenger") {
      if (bare) return;
      entries.push(
        <article className="ink-entry ink-entry--guide" key={`guide-${message.created_at}-${index}`}>
          <span>本次策略</span>
          <Prose text={message.text || "（跳过指导，由奇人自行应对）"} />
        </article>,
      );
      return;
    }
    if (message.omniscient && !liveGod) {
      const god = (
        <article className="ink-entry ink-entry--god" key={`god-${message.created_at}-${index}`}>
          {!bare && <span>推演 · 看破已全</span>}
          <Prose text={message.omniscient} />
        </article>
      );
      entries.push(god);
      groups.deduction.push(god);
    }
    viewsOf(message).forEach((view) => {
      const entry = (
        <article className="ink-entry" key={`${view.side}-${message.created_at}-${index}`}>
          {!bare && <span>{view.label}</span>}
          <Prose text={view.text} />
        </article>
      );
      entries.push(entry);
      groups[view.side].push(entry);
    });
  });

  // 三页各自的实时正文与「有没有内容」：实时块按页挂，不再挤在同一个正文流里
  const liveOf: Record<Pane, string> = {
    deduction: liveGod ? liveDeduction : "",
    challenger: liveText,
    guardian: liveGuardian,
  };
  const filled = (key: Pane) => groups[key].length > 0 || liveOf[key] !== "";

  return (
    <Tabs.Root value={active} onValueChange={(value) => choose(value as Pane)} asChild>
    <section
      className={bare ? "scenario-manuscript scenario-manuscript--book" : "scenario-manuscript"}
      aria-busy={pending}
    >
      {bare ? (
        runningHead && (
          <div className="scenario-manuscript__running">
            <span>{runningHead.left}</span>
            <span>{runningHead.right}</span>
          </div>
        )
      ) : (
        <header>
          <div>
            <span className="eyebrow">行迹</span>
            <h2>{title}</h2>
          </div>
          <span className="muted">{note}</span>
        </header>
      )}
      {tabbed && (
        <Tabs.List className="scenario-panes" aria-label="本局视角">
          {PANES.filter((item) => panes.includes(item.key)).map((item) => {
            const name =
              item.key === "challenger" ? ownLabel : item.key === "guardian" ? guardianLabel : "";
            return (
              <Tabs.Trigger
                key={item.key}
                value={item.key}
                title={name ? `${item.label} · ${name}` : item.label}
                className={`scenario-pane${active === item.key ? " is-active" : ""}`}
              >
                {item.label}
                {/* 其余页已经进了正文而读者还没翻过去：点一粒墨点提示，别让人以为只写了推演 */}
                {active !== item.key && filled(item.key) && !seen.has(item.key) && (
                  <span className="scenario-pane__mark" aria-hidden="true" />
                )}
              </Tabs.Trigger>
            );
          })}
        </Tabs.List>
      )}
      <div className="scenario-manuscript__body" ref={bodyRef}>
        {tabbed ? (
          <Tabs.Content value={active} key={active} className="narrative-pane">
            {groups[active]}
            {liveOf[active] !== "" && (
              <article
                className={`ink-entry${active === "deduction" ? " ink-entry--god" : ""} is-streaming`}
                key={`live-${active}`}
              >
                <Prose text={liveOf[active]} />
              </article>
            )}
            {/* 这一页的正文还没到：照旧演笔墨，别让读者对着空纸等 */}
            {!filled(active) &&
              (pending ? <InkWriting /> : <p className="scenario-pane__empty">此页未留正文。</p>)}
          </Tabs.Content>
        ) : (
          <>
            {entries}
            {/* 推演正文与己方叙述各成一条、各自渲染：解锁者在转写阶段会同时持有两段，
                旧的「有己方叙述就撤推演块」互斥会把推演正文整块吞掉 */}
            {liveGod && (
              <article className="ink-entry ink-entry--god is-streaming">
                {!bare && <span>推演 · 正在落墨</span>}
                <Prose text={liveDeduction} />
              </article>
            )}
            {placeholder}
            {liveText && (
              <article className="ink-entry is-streaming">
                {!bare && <span>{ownLabel} · 正在落墨</span>}
                <Prose text={liveText} />
              </article>
            )}
            {liveGuardian && (
              <article className="ink-entry is-streaming">
                {!bare && <span>{guardianLabel} · 正在落墨</span>}
                <Prose text={liveGuardian} />
              </article>
            )}
            {!bare && !entries.length && !liveText && !liveGuardian && !liveGod && !placeholder && (
              <div className="scenario-opening">
                <EmptyScroll size={132} />
                <span>{emptyText}</span>
              </div>
            )}
          </>
        )}
      </div>
      {bare && folio && (
        <div className="scenario-manuscript__folio">
          <span>{folio.left}</span>
          <span className="scenario-manuscript__page">{folio.right}</span>
        </div>
      )}
    </section>
    </Tabs.Root>
  );
}
