import type { ReactNode } from "react";
import { EmptyScroll } from "./Ornaments";
import type { Message } from "../scenarioModel";

/**
 * 叙述正文分段：模型按写作习惯用空行断段，后端原样存。整段塞进一个 <p> 时
 * `text-indent` 只吃块内第一行，且 `white-space: pre-wrap` 会把 `\n\n` 留成一个空行——
 * 于是「首段缩进、其余不缩进、段间空一行」。这里按换行（一个或连续多个）切成独立 <p>，
 * 每段各自首行缩进两格，段间间距交给 CSS 决定（书页为 0，记录页约一行）。
 */
function Prose({ text }: { text: string }) {
  const paragraphs = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!paragraphs.length) return null;
  return (
    <>
      {paragraphs.map((line, index) => (
        <p key={index}>{line}</p>
      ))}
    </>
  );
}

/**
 * 推演占位：三道墨线先后写过去，第三道只走到一半便停笔，随后整体转呼吸。
 * 纯 CSS 驱动、零计时器——React 卸载即等于「停」，无需清理逻辑。契约上明说「在写，没写完」，
 * 故不宣称完成；观感上是一条正在落墨的纸页，而非通用骨架屏。
 */
export function ScenarioVeil() {
  return (
    <div className="scenario-veil" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

/**
 * 行迹书页（单主视角）：己方叙述正文是书页主文；推演全文（看破解锁后）以独立条目先呈，
 * 直播期由"实时推演正文 → 己方逐字"在同一区域接替。不再有视角切换与视角标签。
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
  title,
  liveText = "",
  liveDeduction = "",
  placeholder,
  note,
  emptyText,
  variant = "page",
  runningHead,
  folio,
}: {
  messages: Message[];
  own: "challenger" | "guardian";
  ownLabel: string;
  title?: ReactNode;
  liveText?: string;
  liveDeduction?: string;
  placeholder?: ReactNode;
  note?: ReactNode;
  emptyText: string;
  variant?: "page" | "book";
  runningHead?: { left: ReactNode; right: ReactNode };
  folio?: { left: ReactNode; right: ReactNode };
}) {
  const bare = variant === "book";
  // 同屏唯一真源：推演正文要么由实时块承担，要么由结算后的 turn.omniscient 承担，绝不并排。
  // 必须看 messages 而不是只靠「turn 事件到达时清空 live」——2 秒轮询可能先一步把回合写进
  // messages，那一帧若只靠清空就会双份显示。
  const settled = messages.some((message) => message.role === "views");
  const liveGod = liveDeduction !== "" && !settled;

  const ownTextOf = (message: Message): string =>
    own === "challenger"
      ? (message.challenger_text ?? (message.role === "guardian" ? (message.text ?? "") : ""))
      : (message.guardian_text ?? (message.role === "guardian" ? (message.text ?? "") : ""));

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
      entries.push(
        <article className="ink-entry ink-entry--god" key={`god-${message.created_at}-${index}`}>
          {!bare && <span>推演 · 看破已全</span>}
          <Prose text={message.omniscient} />
        </article>,
      );
    }
    const content = ownTextOf(message);
    if (content) {
      entries.push(
        <article className="ink-entry" key={`own-${message.created_at}-${index}`}>
          {!bare && <span>{ownLabel}</span>}
          <Prose text={content} />
        </article>,
      );
    }
  });

  return (
    <section
      className={bare ? "scenario-manuscript scenario-manuscript--book" : "scenario-manuscript"}
      aria-live="polite"
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
      <div className="scenario-manuscript__body">
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
        {!bare && !entries.length && !liveText && !liveGod && !placeholder && (
          <div className="scenario-opening">
            <EmptyScroll size={132} />
            <span>{emptyText}</span>
          </div>
        )}
      </div>
      {bare && folio && (
        <div className="scenario-manuscript__folio">
          <span>{folio.left}</span>
          <span className="scenario-manuscript__page">{folio.right}</span>
        </div>
      )}
    </section>
  );
}
