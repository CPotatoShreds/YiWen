import type { ReactNode } from "react";
import { EmptyScroll } from "./Ornaments";
import type { Message } from "../scenarioModel";

/**
 * 行迹书页（单主视角）：自己视角的正文是书页主文；上帝全文（看破解锁后）以独立条目先呈，
 * 直播期由"遮挡块 → 己方逐字"在同一区域接替。不再有视角切换与视角标签。
 * children 落在正文下方的操纵位（起笔 / 策略输入）。
 */
export function ScenarioManuscript({
  messages,
  own,
  ownLabel,
  title,
  liveText = "",
  liveGod = "",
  note,
  emptyText,
  pending,
  children,
}: {
  messages: Message[];
  own: "challenger" | "guardian";
  ownLabel: string;
  title: string;
  liveText?: string;
  liveGod?: string;
  note: string;
  emptyText: string;
  pending?: boolean;
  children?: ReactNode;
}) {
  const ownTextOf = (message: Message): string =>
    own === "challenger"
      ? (message.challenger_text ?? (message.role === "guardian" ? (message.text ?? "") : ""))
      : (message.guardian_text ?? (message.role === "guardian" ? (message.text ?? "") : ""));

  const entries: ReactNode[] = [];
  messages.forEach((message, index) => {
    if (message.role === "challenger") {
      entries.push(
        <article className="ink-entry ink-entry--guide" key={`guide-${message.created_at}-${index}`}>
          <span>本次策略</span>
          <p>{message.text || "（跳过指导，由奇人自行应对）"}</p>
        </article>,
      );
      return;
    }
    if (message.omniscient) {
      entries.push(
        <article className="ink-entry ink-entry--god" key={`god-${message.created_at}-${index}`}>
          <span>上帝视角 · 看破已全</span>
          <p>{message.omniscient}</p>
        </article>,
      );
    }
    const content = ownTextOf(message);
    if (content) {
      entries.push(
        <article className="ink-entry" key={`own-${message.created_at}-${index}`}>
          <span>{ownLabel}</span>
          <p>{content}</p>
        </article>,
      );
    }
  });

  return (
    <section className="scenario-manuscript" aria-live="polite">
      <header>
        <div>
          <span className="eyebrow">行迹</span>
          <h2>{title}</h2>
        </div>
        <span className="muted">{note}</span>
      </header>
      <div className="scenario-manuscript__body">
        {entries}
        {liveGod && (
          <article className="ink-entry ink-entry--veil is-streaming">
            <span>上帝视角 · 推演中</span>
            <p className="ink-veil" aria-label="上帝视角推演进度">{liveGod}</p>
          </article>
        )}
        {liveText && (
          <article className="ink-entry is-streaming">
            <span>{ownLabel} · 正在落墨</span>
            <p>{liveText}</p>
          </article>
        )}
        {!messages.length && !liveText && !liveGod && (
          <div className="scenario-opening">
            <EmptyScroll size={132} />
            <span>{emptyText}</span>
          </div>
        )}
        {pending && <div className="scenario-thinking">一轮策略已锁定，正在完成整场推演。</div>}
      </div>
      {children}
    </section>
  );
}