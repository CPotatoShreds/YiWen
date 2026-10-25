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
 * 行迹书页（单主视角）：己方叙述正文是书页主文；推演全文（看破解锁后）以独立条目先呈，
 * 直播期由"遮挡块 → 己方逐字"在同一区域接替。不再有视角切换与视角标签。
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
  note?: ReactNode;
  emptyText: string;
  variant?: "page" | "book";
  runningHead?: { left: ReactNode; right: ReactNode };
  folio?: { left: ReactNode; right: ReactNode };
}) {
  const bare = variant === "book";

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
    if (message.omniscient) {
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
        {/* 遮挡块与逐字互斥：第一个字到达就撤掉方块，正文从开头起长 */}
        {liveDeduction && !liveText && (
          <article className="ink-entry ink-entry--veil is-streaming">
            {!bare && <span>推演中</span>}
            <p className="ink-veil" aria-label="推演进度">
              {liveDeduction}
            </p>
          </article>
        )}
        {liveText && (
          <article className="ink-entry is-streaming">
            {!bare && <span>{ownLabel} · 正在落墨</span>}
            <Prose text={liveText} />
          </article>
        )}
        {!bare && !entries.length && !liveText && !liveDeduction && (
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
