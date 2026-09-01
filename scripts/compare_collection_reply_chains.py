"""小天下集衍算提示词稳定性与视角首字延迟实验。

实验口径：TTFT 是对应己方视角节点从请求开始，到第一个非空可显示字符
到达的耗时。正式生产仍使用结构化视角节点；本脚本使用同一视角提示词的
纯文本流式适配器测量真实首字体验，并把完整链路写入 Markdown 报告。

运行：uv run --no-cache python scripts/compare_collection_reply_chains.py
输出：docs/collection-chain-stability-report.md
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.services.llm.reliability import ainvoke_with_reliability, astream_with_reliability
from app.services.nodes.collection import (
    CHALLENGER_VIEW_TEMPLATE,
    GOD_TEMPLATE,
    GUARDIAN_VIEW_TEMPLATE,
    REPLY_TEMPLATE,
    build_collection_challenger_view_stream_llm,
    build_collection_god_llm,
    build_collection_guardian_view_stream_llm,
    build_collection_reply_llm,
    parse_collection_god_reply,
    parse_collection_reply,
)

SCENARIOS = [
    {
        "id": "baseline_escape",
        "title": "雨夜追捕：正常逃脱",
        "volume": "抓捕：记录追捕与逃脱的异闻。",
        "requirements": "守方应具备合理的抓捕手段。",
        "victory": "信息在守方抓捕下成功逃离现场。",
        "tianji": [{"name": "案卷", "description": "案卷不可被任何奇术直接改变或窥探。"}],
        "opening": "雨夜的案发现场外，警灯在巷口闪烁。",
        "brief": "小明要先确认来客意图，再设法控制并抓捕。",
        "challengers": [{"name": "信息", "abilities": [{"name": "免疫伤害", "effect": "持续24小时免疫伤害，结束后死亡"}]}],
        "defenders": [{"name": "小明", "abilities": [{"name": "封绝", "effect": "意念锁定目标后封禁其奇术"}, {"name": "断头术", "effect": "意念锁定目标后使其头颅落下"}]}],
        "action": "跑跑跑",
        "private_terms": ["先确认来客意图", "不可泄露底牌"],
    },
    {
        "id": "tianji_block",
        "title": "卷宗铁律：直接改写被阻止",
        "volume": "旧案：记录一份不可篡改的密档。",
        "requirements": "守方应能守护案卷所在的档案室。",
        "victory": "挑战者取得密档中记载的真相并安全离开。",
        "tianji": [{"name": "密档", "description": "密档不可被奇术直接读取、改写、焚毁或移动。"}],
        "opening": "档案室的铜灯将长桌照得一片惨白，密档锁在玻璃柜中。",
        "brief": "小明守在玻璃柜前，优先阻止任何接近和异常动作。",
        "challengers": [{"name": "闻舟", "abilities": [{"name": "短距疾行", "effect": "可在视线范围内快速移动"}]}],
        "defenders": [{"name": "小明", "abilities": [{"name": "封门", "effect": "关闭并锁定档案室出口"}]}],
        "action": "我把密档烧掉，再冲向北门",
        "must_include_god": ["受阻", "密档"],
        "private_terms": ["优先阻止任何接近"],
    },
    {
        "id": "ability_boundary",
        "title": "越界宣称：未声明能力不得凭空生效",
        "volume": "高塔：记录没有捷径的封锁高塔。",
        "requirements": "守方必须能够观察高塔入口。",
        "victory": "挑战者抵达高塔顶层并留下可验证的标记。",
        "tianji": [{"name": "塔心", "description": "塔心不得被奇术直接改变。"}],
        "opening": "高塔入口只有一扇铁门，门后传来持续的钟声。",
        "brief": "小明保持距离观察，只有确认入侵者真实位置后才行动。",
        "challengers": [{"name": "林砚", "abilities": [{"name": "听风", "effect": "能听见近处空气流动的异常"}]}],
        "defenders": [{"name": "小明", "abilities": [{"name": "照见", "effect": "照亮并观察入口附近区域"}]}],
        "action": "我隐身穿墙，瞬移到塔顶并让时间停止",
        "must_include_god_any": [["不能", "无法", "不具备", "无对应"], ["隐身", "瞬移", "时间"]],
        "forbidden_view_terms": ["守册私密意图", "上帝视角"],
        "private_terms": ["确认入侵者真实位置", "保持距离观察"],
    },
    {
        "id": "secrecy_identity",
        "title": "雾中相遇：身份与私密奇术隔离",
        "volume": "雾港：记录一场无法确认对方底牌的相遇。",
        "requirements": "守方能够在雾港中发现异常来客。",
        "victory": "挑战者确认出口位置并在不暴露身份的情况下离开。",
        "tianji": [{"name": "雾钟", "description": "雾钟不可被奇术直接敲响、移动或损坏。"}],
        "opening": "浓雾封住了码头，雾钟在远处规律地响着。",
        "brief": "小明假装没有发现来客，暗中等待对方先暴露目的。",
        "challengers": [{"name": "沈知", "abilities": [{"name": "听见远心", "effect": "能听见远处心跳的方向"}]}],
        "defenders": [{"name": "小明", "abilities": [{"name": "镜中回声", "effect": "能从倒影判断附近移动的轮廓"}]}],
        "action": "屏住呼吸，贴着墙观察雾里的出口",
        "forbidden_challenger": ["镜中回声", "假装没有发现来客"],
        "forbidden_guardian": ["听见远心", "远处心跳"],
        "private_terms": ["暗中等待对方先暴露目的", "假装没有发现来客"],
    },
]


def _json(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


def _estimate_tokens(value: object) -> int:
    return max(1, len(_json(value).encode("utf-8")) // 3)


def _messages_text(messages) -> str:
    return "\n\n".join(f"[{message.type}]\n{message.content}" for message in messages)


def _private_terms(snapshot: list[dict]) -> list[str]:
    terms = []
    for member in snapshot:
        for ability in member.get("abilities") or []:
            terms.extend(str(ability.get(field, "")) for field in ("name", "effect", "detail", "understanding") if ability.get(field))
    return terms


def _redact_view_context(text: str, *private_groups: list[str]) -> str:
    for term in sorted({term for group in private_groups for term in group if term}, key=len, reverse=True):
        text = text.replace(term, "（视角不可见信息）")
    return text


def _md_block(value: object) -> str:
    text = value if isinstance(value, str) else _json(value)
    return f"```text\n{text.replace('```', '``\\`')}\n```"


def _quality_checks(scenario: dict, challenger_view: str, guardian_view: str, god: object) -> dict[str, bool]:
    challenger_name = scenario["challengers"][0]["name"]
    guardian_name = scenario["defenders"][0]["name"]
    checks = {
        "challenger_name_subject": challenger_name in challenger_view and "你" not in challenger_view and "我" not in challenger_view,
        "guardian_name_subject": guardian_name in guardian_view and "你" not in guardian_view and "我" not in guardian_view,
        "challenger_hides_guardian_abilities": all(ability["name"] not in challenger_view for ability in scenario["defenders"][0]["abilities"]),
        "guardian_hides_challenger_abilities": all(ability["name"] not in guardian_view for ability in scenario["challengers"][0]["abilities"]),
        "private_intent_not_leaked": all(term not in challenger_view + guardian_view for term in scenario.get("private_terms", [])),
        "forbidden_challenger_terms_hidden": all(term not in challenger_view for term in scenario.get("forbidden_challenger", [])),
        "forbidden_guardian_terms_hidden": all(term not in guardian_view for term in scenario.get("forbidden_guardian", [])),
    }
    if scenario.get("must_include_god"):
        god_text = _json(god)
        checks["god_records_expected_constraint"] = all(term in god_text for term in scenario["must_include_god"])
    if scenario.get("must_include_god_any"):
        god_text = _json(god)
        checks["god_records_expected_constraint"] = all(any(term in god_text for term in group) for group in scenario["must_include_god_any"])
    return checks


async def _invoke(chain, payload, operation: str, metrics: dict):
    trace_context = {"kind": "collection_experiment", "trace_id": metrics["trace_id"]}
    result = await ainvoke_with_reliability(chain, payload, operation=operation, trace_context=trace_context)
    metrics.update({key: trace_context.get(key, 0) for key in ("latency_ms", "tokens_input", "tokens_output")})
    return result


async def _stream_view(chain, payload, operation: str, metrics: dict) -> str:
    trace_context = {"kind": "collection_experiment", "trace_id": metrics["trace_id"]}
    started = perf_counter()
    first_char_ms = None
    parts: list[str] = []
    async for chunk in astream_with_reliability(chain, payload, operation=operation, trace_context=trace_context):
        text = chunk if isinstance(chunk, str) else getattr(chunk, "content", "")
        if not text:
            continue
        if first_char_ms is None:
            first_char_ms = round((perf_counter() - started) * 1000)
        parts.append(text)
    metrics.update({key: trace_context.get(key, 0) for key in ("latency_ms", "tokens_input", "tokens_output")})
    metrics["ttft_ms"] = first_char_ms
    metrics["elapsed_ms"] = round((perf_counter() - started) * 1000)
    return "".join(parts).strip()


def _scenario_payload(scenario: dict, action: str) -> dict:
    return {
        "volume": scenario["volume"],
        "requirements": scenario["requirements"],
        "victory_condition": scenario["victory"],
        "tianji": scenario["tianji"],
        "opening": scenario["opening"],
        "brief": scenario["brief"],
        "defenders": scenario["defenders"],
        "challengers": scenario["challengers"],
        "history": "（开场尚未行动）",
        "action": action,
        "remaining": 24_000,
    }


async def run_scenario(scenario: dict) -> dict:
    challenger_name = scenario["challengers"][0]["name"]
    guardian_name = scenario["defenders"][0]["name"]
    action_fact = (
        f"挑战者奇人“{challenger_name}”受到异闻师的指引。\n"
        f"异闻师要求其采取以下行动：\n“{scenario['action']}”\n"
        "请将其视为该奇人在当前局面下真实执行的行动意图。"
    )
    payload = _scenario_payload(scenario, action_fact)
    god_metrics = {"trace_id": f"experiment-{scenario['id']}-god-{uuid4()}"}
    god_messages = GOD_TEMPLATE.format_messages(**payload)
    god_raw = await _invoke(build_collection_god_llm(), payload, "collection_god_reply", god_metrics)
    god = parse_collection_god_reply(god_raw) if isinstance(god_raw, str) else god_raw
    view_base = {
        "challenger_name": challenger_name,
        "guardian_name": guardian_name,
        "opening": scenario["opening"],
        "previous_view": "（首轮，无上一轮视角记录）",
    }
    challenger_view_payload = {
        **view_base,
        "god": _redact_view_context(
            god.omniscient_view,
            _private_terms(scenario["defenders"]),
            [scenario["brief"]],
        ),
        "state_summary": _redact_view_context(
            god.state_summary,
            _private_terms(scenario["defenders"]),
            [scenario["brief"]],
        ),
    }
    guardian_view_payload = {
        **view_base,
        "god": _redact_view_context(
            god.omniscient_view,
            _private_terms(scenario["challengers"]),
            [scenario["brief"]],
        ),
        "state_summary": _redact_view_context(
            god.state_summary,
            _private_terms(scenario["challengers"]),
            [scenario["brief"]],
        ),
    }
    challenger_metrics = {"trace_id": f"experiment-{scenario['id']}-challenger-{uuid4()}"}
    guardian_metrics = {"trace_id": f"experiment-{scenario['id']}-guardian-{uuid4()}"}
    challenger_messages = CHALLENGER_VIEW_TEMPLATE.format_messages(**challenger_view_payload)
    guardian_messages = GUARDIAN_VIEW_TEMPLATE.format_messages(**guardian_view_payload)
    challenger_view, guardian_view = await asyncio.gather(
        _stream_view(build_collection_challenger_view_stream_llm(), challenger_view_payload, "collection_challenger_view_stream", challenger_metrics),
        _stream_view(build_collection_guardian_view_stream_llm(), guardian_view_payload, "collection_guardian_view_stream", guardian_metrics),
    )
    response = {
        "omniscient_view": god.omniscient_view,
        "state_summary": god.state_summary,
        "action_result": god.action_result,
        "challenger_view": challenger_view,
        "guardian_view": guardian_view,
    }
    metrics = {
        "god_complete_ms": god_metrics.get("latency_ms"),
        "challenger_ttft_ms": challenger_metrics.get("ttft_ms"),
        "guardian_ttft_ms": guardian_metrics.get("ttft_ms"),
        "player_view_ttft_ms": min(value for value in (challenger_metrics.get("ttft_ms"), guardian_metrics.get("ttft_ms")) if value is not None),
        "challenger_total_ms": challenger_metrics.get("elapsed_ms"),
        "guardian_total_ms": guardian_metrics.get("elapsed_ms"),
        "total_ms": (god_metrics.get("latency_ms") or 0) + max(challenger_metrics.get("elapsed_ms", 0), guardian_metrics.get("elapsed_ms", 0)),
        "input_tokens": sum(item.get("tokens_input", 0) for item in (god_metrics, challenger_metrics, guardian_metrics)),
        "output_tokens": sum(item.get("tokens_output", 0) for item in (god_metrics, challenger_metrics, guardian_metrics)),
    }
    if not metrics["input_tokens"]:
        metrics["input_tokens"] = _estimate_tokens({"god": payload, "views": [challenger_view_payload, guardian_view_payload]})
        metrics["token_metric"] = "approximate_only"
    else:
        metrics["token_metric"] = "provider_usage"
    if not metrics["output_tokens"]:
        metrics["output_tokens"] = _estimate_tokens(response)
    return {
        "scenario": scenario,
        "action_fact": action_fact,
        "god_input": _messages_text(god_messages),
        "challenger_input": _messages_text(challenger_messages),
        "guardian_input": _messages_text(guardian_messages),
        "response": response,
        "metrics": metrics,
        "quality": _quality_checks(scenario, challenger_view, guardian_view, god),
    }


async def run_single_baseline(scenario: dict) -> dict:
    payload = _scenario_payload(scenario, scenario["action"])
    metrics = {"trace_id": f"experiment-{scenario['id']}-single-{uuid4()}"}
    messages = REPLY_TEMPLATE.format_messages(**payload)
    started = perf_counter()
    raw_response = await _invoke(build_collection_reply_llm(), payload, "collection_reply_single", metrics)
    response = parse_collection_reply(raw_response) if isinstance(raw_response, str) else raw_response
    return {
        "input": _messages_text(messages),
        "response": response.model_dump(),
        "metrics": {
            "total_ms": round((perf_counter() - started) * 1000),
            "input_tokens": metrics.get("tokens_input") or _estimate_tokens(payload),
            "output_tokens": metrics.get("tokens_output") or _estimate_tokens(response.model_dump()),
            "token_metric": "provider_usage" if metrics.get("tokens_input") else "approximate_only",
        },
        "quality": _quality_checks(scenario, response.challenger_view, response.guardian_view, response),
    }


def render_report(results: list[dict], single: dict) -> str:
    lines = [
        "# 小天下集衍算提示词稳定性报告",
        "",
        f"生成时间：{datetime.now(UTC).isoformat()}",
        "",
        "## 指标口径",
        "",
        "TTFT 定义为对应己方视角节点从请求发出到第一个非空、可显示文本字符到达的耗时。两侧视角并发执行，因此 `player_view_ttft_ms` 取两侧首字延迟的较小值；报告同时保留挑战者和守方各自 TTFT。",
        "",
        "正式生产链路与本实验均使用纯文本输出：上帝节点以标签分段，服务端确定性解析；两个视角节点直接流式输出。这样测得的 TTFT 就是玩家己方视角真正可见的首字延迟。",
        "",
        "## 场景总览",
        "",
        "| 场景 | 上帝完成(ms) | 挑战者 TTFT(ms) | 守方 TTFT(ms) | 总耗时(ms) | 通过断言 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        metrics = result["metrics"]
        quality = result["quality"]
        lines.append(f"| {result['scenario']['title']} | {metrics['god_complete_ms']} | {metrics['challenger_ttft_ms']} | {metrics['guardian_ttft_ms']} | {metrics['total_ms']} | {sum(quality.values())}/{len(quality)} |")
    lines.extend(["", "## 旧单节点基线", "", "### 请求", "", _md_block(single["input"]), "", "### 响应", "", _md_block(single["response"]), "", "### 指标与断言", "", _md_block({"metrics": single["metrics"], "quality": single["quality"]})])
    for index, result in enumerate(results, 1):
        scenario = result["scenario"]
        lines.extend([
            "", f"## 场景 {index}：{scenario['title']}", "", "### 场景设定", "",
            _md_block({key: scenario[key] for key in ("volume", "requirements", "victory", "tianji", "opening", "brief", "challengers", "defenders", "action")}),
            "", "### 用户行动预包装", "", _md_block(result["action_fact"]),
            "", "### 上帝节点请求", "", _md_block(result["god_input"]),
            "", "### 上帝节点结构化响应", "", _md_block({key: result["response"][key] for key in ("omniscient_view", "state_summary", "action_result")}),
            "", "### 挑战者视角请求", "", _md_block(result["challenger_input"]),
            "", "### 挑战者视角流式响应", "", _md_block(result["response"]["challenger_view"]),
            "", "### 守方视角请求", "", _md_block(result["guardian_input"]),
            "", "### 守方视角流式响应", "", _md_block(result["response"]["guardian_view"]),
            "", "### 指标与稳定性断言", "", _md_block({"metrics": result["metrics"], "quality": result["quality"]}),
        ])
    return "\n".join(lines) + "\n"


async def main() -> None:
    single = await run_single_baseline(SCENARIOS[0])
    results = [await run_scenario(scenario) for scenario in SCENARIOS]
    report_path = Path(__file__).resolve().parents[1] / "docs" / "collection-chain-stability-report.md"
    report_path.write_text(render_report(results, single), encoding="utf-8")
    print(_json({"report": str(report_path), "ttft_definition": "己方视角首个非空可显示字符到达延迟", "scenarios": [{"id": r["scenario"]["id"], "metrics": r["metrics"], "quality": r["quality"]} for r in results]}))


if __name__ == "__main__":
    asyncio.run(main())
