import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { PlusIcon, ScrollIcon, TrashIcon } from "../../components/icons";
import type { Scenario, ScenarioDraft } from "../../types";

// 字段上限与后端 ScenarioIn 逐项对齐（app/schemas/scenario_domain.py:8-15）。
// 后端 schema 若有改动必须同步这里，否则会撞上 pydantic 的英文 422 文案被直接上屏。
const LIMITS = { name: 30, subtitle: 60, introduction: 120, background: 2000, victory: 300, rule: 500 } as const;
const RULES_CAP = 20;

type RuleRow = { id: number; text: string };

// 行的稳定 key：模块级自增。StrictMode 下 useState 的初始化函数跑两次只会跳号，无副作用；
// 不要改在 render 体内的 ref 自增——那才是每帧递增。
let rowSeq = 0;
const row = (text = ""): RuleRow => ({ id: ++rowSeq, text });

type Draft = Omit<ScenarioDraft, "rules" | "judgement_rules"> & { rules: RuleRow[]; judgement_rules: RuleRow[] };

const blank = (): Draft => ({
  name: "",
  subtitle: "",
  introduction: "",
  background: "",
  rules: [row()],
  victory_condition: "",
  judgement_rules: [row()],
});

const countClass = (value: string, max: number) => `char-count${value.length > max ? " char-count--over" : ""}`;

/** 规则组：1-20 条，且每条 trim 后不得为空——后端 min_length=1 会放行纯空格，只有前端能兜住 */
function rulesIssue(rows: RuleRow[], label: string) {
  if (rows.length === 0) return `${label}至少写一条。`;
  if (rows.length > RULES_CAP) return `${label}至多 ${RULES_CAP} 条。`;
  const index = rows.findIndex((r) => !r.text.trim());
  if (index >= 0) return `${label}第 ${index + 1} 条还是空的，补上或删掉它。`;
  return "";
}

function validate(draft: Draft) {
  if (!draft.name.trim()) return "还没题卷名。";
  if (!draft.subtitle.trim()) return "还没写副名。";
  if (!draft.introduction.trim()) return "还没写介绍。";
  if (!draft.background.trim()) return "还没写背景。";
  const ruleIssue = rulesIssue(draft.rules, "规则");
  if (ruleIssue) return ruleIssue;
  if (!draft.victory_condition.trim()) return "还没写胜利条件。";
  return rulesIssue(draft.judgement_rules, "判定规则");
}

function RuleEditor({ label, hint, rows, disabled, onChange }: { label: string; hint: string; rows: RuleRow[]; disabled: boolean; onChange: (rows: RuleRow[]) => void }) {
  const edit = (id: number, text: string) => onChange(rows.map((r) => (r.id === id ? { ...r, text } : r)));
  return (
    <div className="rule-editor">
      <div className="rule-editor__head">
        <b>{label}</b>
        <span className="rule-editor__hint">{hint} · <span className="mono">{rows.length}/{RULES_CAP}</span></span>
      </div>
      {rows.map((r, index) => (
        <div className="rule-row" key={r.id}>
          <span className="rule-row__no" aria-hidden="true">{index + 1}</span>
          <div className="rule-row__body">
            <textarea
              className="textarea"
              rows={2}
              maxLength={LIMITS.rule}
              value={r.text}
              disabled={disabled}
              aria-label={`${label}第 ${index + 1} 条`}
              onChange={(e) => edit(r.id, e.target.value)}
            />
            <span className="rule-row__count">{r.text.length}/{LIMITS.rule}</span>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-icon btn-sm"
            disabled={disabled || rows.length <= 1}
            title={rows.length <= 1 ? "至少留一条" : "删掉这一条"}
            aria-label={`删掉${label}第 ${index + 1} 条`}
            onClick={() => onChange(rows.filter((item) => item.id !== r.id))}
          >
            <TrashIcon size={14} />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-ghost btn-sm rule-editor__add"
        disabled={disabled || rows.length >= RULES_CAP}
        title={rows.length >= RULES_CAP ? `至多 ${RULES_CAP} 条` : "添一条"}
        onClick={() => onChange([...rows, row()])}
      >
        <PlusIcon size={14} />
        添一条
      </button>
    </div>
  );
}

export default function AdminScenarioNew() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Draft>(blank);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const update = (patch: Partial<Draft>) => setDraft((value) => ({ ...value, ...patch }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return; // 连点 + Enter 双保险
    const invalid = validate(draft);
    if (invalid) {
      setErr(invalid);
      return;
    }
    setBusy(true);
    setErr("");
    // 全字段 trim 后再交：与后端路由里的 .strip() 结果一致，避免纯空格落库
    const body: ScenarioDraft = {
      name: draft.name.trim(),
      subtitle: draft.subtitle.trim(),
      introduction: draft.introduction.trim(),
      background: draft.background.trim(),
      rules: draft.rules.map((r) => r.text.trim()),
      victory_condition: draft.victory_condition.trim(),
      judgement_rules: draft.judgement_rules.map((r) => r.text.trim()),
    };
    try {
      await api<Scenario>("/admin/scenarios", { method: "POST", body: JSON.stringify(body) });
      // 回列表：/admin/ 前缀不走缓存，列表挂载即拉到新卷（created_at desc，必在首位）
      navigate("/admin/scenarios", { replace: true });
    } catch (cause) {
      setErr(cause instanceof Error ? cause.message : "立卷未成，请稍后再试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">SCROLL DRAFTING</span>
          <h2>立卷</h2>
          <p className="muted">题名、背景、规则一次写全。立卷只落草稿，发布是列表页的下一步。</p>
        </div>
        <div className="admin-toolbar__actions">
          <Link className="btn btn-ghost" to="/admin/scenarios">返回各卷</Link>
        </div>
      </div>

      <form className="scenario-compose" onSubmit={submit} noValidate>
        <div className="scenario-compose__sheet">
          <div className="scenario-compose__row">
            <div className="field">
              <label htmlFor="scenario-name">卷名</label>
              <span className={countClass(draft.name, LIMITS.name)}>{draft.name.length}/{LIMITS.name}</span>
              <input id="scenario-name" className="input" value={draft.name} maxLength={LIMITS.name} autoFocus placeholder="不可与现有卷重名" onChange={(e) => update({ name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="scenario-subtitle">副名</label>
              <span className={countClass(draft.subtitle, LIMITS.subtitle)}>{draft.subtitle.length}/{LIMITS.subtitle}</span>
              <input id="scenario-subtitle" className="input" value={draft.subtitle} maxLength={LIMITS.subtitle} placeholder="卷名下方的一行短句" onChange={(e) => update({ subtitle: e.target.value })} />
            </div>
          </div>

          <div className="field">
            <label htmlFor="scenario-introduction">介绍</label>
            <span className={countClass(draft.introduction, LIMITS.introduction)}>{draft.introduction.length}/{LIMITS.introduction}</span>
            <input id="scenario-introduction" className="input" value={draft.introduction} maxLength={LIMITS.introduction} placeholder="卷首的一句提要" onChange={(e) => update({ introduction: e.target.value })} />
          </div>

          <div className="field">
            <label htmlFor="scenario-background">背景</label>
            <span className={countClass(draft.background, LIMITS.background)}>{draft.background.length}/{LIMITS.background}</span>
            <textarea id="scenario-background" className="textarea" rows={6} value={draft.background} maxLength={LIMITS.background} placeholder="双方所处的场地、处境与前情" onChange={(e) => update({ background: e.target.value })} />
          </div>

          <RuleEditor label="规则" hint="此卷最高优先级，推演与检定都以此为准" rows={draft.rules} disabled={busy} onChange={(rules) => update({ rules })} />

          <div className="field">
            <label htmlFor="scenario-victory">胜利条件</label>
            <span className={countClass(draft.victory_condition, LIMITS.victory)}>{draft.victory_condition.length}/{LIMITS.victory}</span>
            <textarea id="scenario-victory" className="textarea" rows={3} value={draft.victory_condition} maxLength={LIMITS.victory} placeholder="挑战者做到什么算胜" onChange={(e) => update({ victory_condition: e.target.value })} />
          </div>

          <RuleEditor label="判定规则" hint="规则之外的补充判定，如平局与边界情形" rows={draft.judgement_rules} disabled={busy} onChange={(judgement_rules) => update({ judgement_rules })} />

          {err && <p className="err" role="alert">{err}</p>}

          <div className="scenario-compose__foot">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              <ScrollIcon size={15} />
              {busy ? "正在立卷…" : "立卷（存为草稿）"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
