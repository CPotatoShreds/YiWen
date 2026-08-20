// LLM 链路适配视图组件：按环节渲染 trace 的解析结果（与 traceViews.ts 的纯函数配套）。

import Markdown from "../../components/Markdown";
import type { LlmTraceDetail } from "./types";
import {
  CAT_DEDUCE,
  CAT_DISCUSS,
  CAT_GUESS_COMMENTARY,
  CAT_GUESS_VERIFY,
  CAT_REPAIR,
  CAT_TRANSCRIBE,
  CAT_USAGE,
  CAT_VALIDATE,
  commentaryInfo,
  buildPairReport,
  extractVar,
  foldPrompt,
  systemContent,
  verifyInfo,
} from "./traceParsers";

function pretty(obj: unknown): string {
  return JSON.stringify(obj ?? null, null, 2);
}

/** battle 环节的"输入"横条：关键变量摘要（info/god/narration/violations）。 */
function BattleInputBar({ d }: { d: LlmTraceDetail }) {
  const info = extractVar(d, "info");
  return (
    <div className="trace-v__input">
      <span className="trace-v__label">输入</span>
      <span className="trace-v__text">{info ? foldPrompt(info) : "（无输入变量）"}</span>
    </div>
  );
}

const Kv = ({ k, v }: { k: string; v: string }) =>
  v ? (
    <span className="trace-v__kv">
      <span className="trace-v__k">{k}</span>
      <span>{v}</span>
    </span>
  ) : null;

const JsonToggle = ({ label, obj }: { label: string; obj: unknown }) => (
  <details className="trace-v__json">
    <summary>{label}</summary>
    <pre className="pre-json">{pretty(obj)}</pre>
  </details>
);

export function TraceView({ d }: { d: LlmTraceDetail }) {
  if (d.operation === "ability_pair") {
    return (
      <div className="trace-v">
        <div className="trace-v__resp">
          <span className="trace-v__label">奇术对比判定</span>
          <Markdown className="trace-v__text" text={buildPairReport([d])} />
        </div>
        <JsonToggle label="查看原始请求" obj={d.request_json} />
      </div>
    );
  }
  switch (d.operation) {
    case CAT_DISCUSS:
      return (
        <div className="trace-v">
          <div className="trace-v__resp">
            <span className="trace-v__label">战前讨论报告</span>
            <Markdown className="trace-v__text" text={typeof d.response_json === "string" ? d.response_json : "（非文本输出）"} />
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );

    case CAT_DEDUCE:
      return (
        <div className="trace-v">
          <BattleInputBar d={d} />
          <div className="trace-v__resp">
            <span className="trace-v__label">上帝视角全文</span>
            <p className="trace-v__text">{typeof d.response_json === "string" ? d.response_json : "（非文本输出）"}</p>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );

    case CAT_TRANSCRIBE:
      return (
        <div className="trace-v">
          <BattleInputBar d={d} />
          <div className="trace-v__cols">
            <div className="trace-v__col">
              <span className="trace-v__label">甲 视角</span>
              <p className="trace-v__text">{extractVar(d, "narration_a") || "（无）"}</p>
            </div>
            <div className="trace-v__col">
              <span className="trace-v__label">乙 视角</span>
              <p className="trace-v__text">{extractVar(d, "narration_b") || "（无）"}</p>
            </div>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );

    case CAT_VALIDATE: {
      const resp = (d.response_json ?? {}) as Record<string, unknown>;
      const violations = Array.isArray(resp.violations) ? (resp.violations as string[]) : [];
      return (
        <div className="trace-v">
          <BattleInputBar d={d} />
          <div className="trace-v__resp">
            <span className="trace-v__label">校验结果</span>
            <div className="trace-v__chips">
              <Kv k="通过" v={resp.passes ? "是" : "否"} />
              <Kv k="违规" v={violations.length ? violations.join("；") : "无"} />
            </div>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );
    }

    case CAT_REPAIR:
      return (
        <div className="trace-v">
          <BattleInputBar d={d} />
          <div className="trace-v__resp">
            <span className="trace-v__label">修复稿</span>
            <p className="trace-v__text">{typeof d.response_json === "string" ? d.response_json : "（非文本输出）"}</p>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );

    case CAT_USAGE: {
      const resp = (d.response_json ?? {}) as Record<string, unknown>;
      const indices = Array.isArray(resp.indices) ? (resp.indices as (string | number)[]).map(Number) : [];
      const sys = systemContent(d);
      const abilitiesTxt = sys.match(/赢家装配奇术清单（按 1 起编号）：\n([\s\S]*?)\n\n上帝视角/)?.[1];
      const abilities = (abilitiesTxt ?? "")
        .split("\n")
        .map((l) => l.replace(/^\d+\.\s*/, "").trim())
        .filter(Boolean);
      return (
        <div className="trace-v">
          <BattleInputBar d={d} />
          <div className="trace-v__resp">
            <span className="trace-v__label">判定结果 · 实际使用</span>
            {abilities.length ? (
              <div className="trace-v__chips">
                {abilities.map((a, i) => (
                  <span key={i} className={`trace-v__chip ${indices.includes(i + 1) ? "is-used" : ""}`}>{a}</span>
                ))}
              </div>
            ) : (
              <span className="muted">（无奇术清单）</span>
            )}
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );
    }

    case CAT_GUESS_COMMENTARY: {
      const info = commentaryInfo(d);
      return (
        <div className="trace-v">
          <div className="trace-v__input">
            <span className="trace-v__label">输入 · 猜测</span>
            <span className="trace-v__text">{info.text || "（无）"}</span>
          </div>
          <div className="trace-v__resp">
            <span className="trace-v__label">点评</span>
            <p className="trace-v__text">{info.commentary || "（空）"}</p>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );
    }

    case CAT_GUESS_VERIFY: {
      const info = verifyInfo(d);
      return (
        <div className="trace-v">
          <div className="trace-v__input">
            <span className="trace-v__label">判定对象</span>
            <span className="trace-v__text">{info.ability || "（未解析）"}</span>
          </div>
          <div className="trace-v__resp">
            <span className="trace-v__label">判定结果</span>
            <div className="trace-v__chips">
              <span className={`trace-v__chip ${info.cracked ? "is-used" : ""}`}>
                {info.cracked ? "看破" : "未看破"}
              </span>
            </div>
            {info.missing && <p className="trace-v__text">{info.missing}</p>}
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );
    }

    default:
      return (
        <div className="trace-v">
          <div className="trace-v__resp">
            <span className="trace-v__label">响应</span>
            <pre className="pre-json">{pretty(d.response_json)}</pre>
          </div>
          <JsonToggle label="查看原始请求" obj={d.request_json} />
        </div>
      );
  }
}
