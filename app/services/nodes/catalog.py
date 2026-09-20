"""LLM 节点总览与版本指纹。

`NODES` 一处枚举全部活跃节点（各模块的 `NodeSpec`），`node_fingerprint` 产出
「提示词文本 + 模型参数 + schema + 实际模型标识」的 sha256 指纹——提示词或模型一变
即得新指纹，供比对缓存的版本段（ver）使用，旧指纹缓存自然失效。

依赖方向：本模块聚合各节点模块，节点模块只依赖 `registry`，无循环导入。
"""

import hashlib
import json

from langchain_core.prompts import ChatPromptTemplate

from app.services.nodes.ability.pair_judge import SPEC as _ABILITY_PAIR
from app.services.nodes.ability.understanding import SPEC as _UNDERSTANDING
from app.services.nodes.guess.matcher import SPEC_PAIR, SPEC_VERIFY
from app.services.nodes.registry import NodeSpec, resolve_model_id
from app.services.nodes.scenario.challenger_view import SPEC as _CHALLENGER_VIEW
from app.services.nodes.scenario.god import SPEC as _GOD
from app.services.nodes.scenario.guardian_view import SPEC as _GUARDIAN_VIEW
from app.services.nodes.scenario.judge import SPEC as _JUDGE

NODES: dict[str, NodeSpec] = {
    spec.id: spec
    for spec in (
        _GOD,
        _JUDGE,
        _CHALLENGER_VIEW,
        _GUARDIAN_VIEW,
        _ABILITY_PAIR,
        _UNDERSTANDING,
        SPEC_PAIR,
        SPEC_VERIFY,
    )
}


def _template_text(template: ChatPromptTemplate) -> str:
    """逐条 message 的模板原文拼接（未格式化），作为提示词指纹的输入。"""
    parts: list[str] = []
    for message in template.messages:
        text = getattr(getattr(message, "prompt", None), "template", None)
        parts.append(str(text if text is not None else getattr(message, "content", "")))
    return "\n".join(parts)


def node_fingerprint(node_id: str, llm_config: dict | None = None) -> str:
    """节点版本指纹：提示词 + 模型参数 + schema 名 + 实际模型标识 的 sha256。"""
    spec = NODES[node_id]
    payload = {
        "prompt": _template_text(spec.template),
        "thinking": spec.thinking,
        "max_tokens": spec.max_tokens,
        "temperature": spec.temperature,
        "schema": spec.schema.__name__ if spec.schema is not None else None,
        "model": resolve_model_id(llm_config),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
