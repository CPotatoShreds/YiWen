"""LLM 节点统一建模：NodeSpec 描述一个节点，build_node 统一构建其调用链路。

节点唯一标识 `NodeSpec.id` 即调用时传的 `operation=` 值（`scenario_god_reply` 等），
一处总览见 `catalog.NODES`，版本指纹见 `catalog.node_fingerprint`。

本模块**不导入任何节点模块**（节点模块反向导入本模块取 build_node），避免循环导入；
聚合点在 `catalog.py`。
"""

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.llm.client import build_chat_model


@dataclass(frozen=True)
class NodeSpec:
    """一个 LLM 节点的声明：提示词模板 + 模型参数 + 输出 schema。

    提示词只「引用」模块内的冻结模板常量，绝不复制文本；模型参数与 schema 由本声明
    统一承载，`build_*` 函数仅作一行委托，改参数只改这里。
    """

    id: str
    template: ChatPromptTemplate
    thinking: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    schema: type[BaseModel] | None = None
    pipes_template: bool = True


def resolve_model_id(llm_config: dict | None) -> str:
    """节点实际使用的模型标识：用户方案覆盖优先，否则回退 env 默认。"""
    if llm_config and llm_config.get("model"):
        return str(llm_config["model"])
    return get_settings().LLM_MODEL


def build_node(spec: NodeSpec, *, llm_config: dict | None = None) -> Runnable:
    """按 NodeSpec 构建 LLM 链路。

    - 结构化输出一律 `method="function_calling"`（DeepSeek 对 json_schema 返回 400），收敛于此一处。
    - `pipes_template=False` 时只返回模型链，调用方自行 format_messages（保留对 build_chat_model 的桩兼容）。
    """
    tail: Runnable = build_chat_model(
        thinking=spec.thinking,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
        llm_config=llm_config,
    )
    if spec.schema is not None:
        tail = tail.with_structured_output(spec.schema, method="function_calling")
    else:
        tail = tail | StrOutputParser()
    if not spec.pipes_template:
        return tail
    return spec.template | tail
