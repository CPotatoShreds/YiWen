// 行迹链路还原：按编号搜索某场真实行迹，展示其讨论 / 三视角 / 猜词链路。
// 展示逻辑在共享组件 BattleChainView（奇人库同样复用）。

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BattleChainView } from "./chainViews";

export default function BattleChain() {
  const [params, setParams] = useSearchParams();
  const idParam = params.get("id") ?? "";
  const [input, setInput] = useState(idParam);
  const [err, setErr] = useState("");

  const id = Number(idParam);
  const valid = Number.isInteger(id) && id > 0;

  useEffect(() => {
    setInput(idParam);
  }, [idParam]);

  function search() {
    const v = input.trim();
    if (!v) return;
    const n = Number(v);
    if (Number.isInteger(n) && n > 0) {
      setErr("");
      setParams({ id: v });
    } else {
      setErr("请输入有效的行迹编号");
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">BATTLE CHAIN</span>
          <h2>行迹链路还原</h2>
        </div>
        <p className="muted">按行迹编号，从 LLM 调用链还原战前讨论 / 三视角 / 猜词判定</p>
      </div>
      <div className="panel">
        <div className="admin-form-grid">
          <div className="field">
            <label>行迹编号</label>
            <div className="admin-toolbar__actions" style={{ marginTop: 4 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={input}
                onChange={(e) => {
                  setErr("");
                  setInput(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="如 43"
              />
              <button className="btn btn-primary" onClick={search}>还原</button>
            </div>
          </div>
        </div>
        {err && <p className="err">{err}</p>}
        {!valid && !err && <p className="muted">输入行迹编号后点「还原」查看其 LLM 链路。</p>}
      </div>

      {valid && <BattleChainView id={id} />}
    </div>
  );
}
