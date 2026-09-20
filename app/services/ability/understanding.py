"""奇术因果槽位服务：保存奇术后台异步生成结构化槽位并写回 `Ability.understanding`。

复用 `Ability.understanding` 字段（曾弃用，现重新启用）。槽位完全忠实于异闻师写下的效果
与详细解释，把用户描述的启动前置 / 运作机制 / 代价反噬归位到契相 / 显相 / 果相，判定是否「零相
空想」，作为奇术比对与推演的主要依据。比对节点 `pair_judge._render_pair_ability` 会把
understanding 作为因果槽位附入对比输入。保存后由路由后台触发，失败静默（不阻塞奇术保存，
比对时退回原始字段）。节点声明（提示词/schema/构建链）见 `nodes/ability/understanding`。
"""

import json
from contextlib import suppress

from cryptography.fernet import InvalidToken

from app.db.base import async_session_factory
from app.models.ability import Ability
from app.models.llm_profile import LlmProfile
from app.models.user import User
from app.services.llm.client import profile_to_llm_config
from app.services.llm.reliability import ainvoke_with_reliability
from app.services.nodes.ability.understanding import (
    UNDERSTANDING_TEMPLATE,
    build_understanding_chain,
)


async def ensure_ability_understanding(ability_id: str) -> None:
    """生成并保存奇术因果槽位（紧凑 JSON 字符串）；失败静默（推演时退回原始字段）。"""
    async with async_session_factory() as db:
        ability = await db.get(Ability, ability_id)
        if ability is None or not (ability.name.strip() and ability.effect.strip()):
            return
        owner_id = ability.owner_id
        owner = await db.get(User, owner_id) if owner_id is not None else None
        profile = await db.get(LlmProfile, owner.active_profile_id) if owner and owner.active_profile_id else None
        try:
            llm_config = profile_to_llm_config(profile)
        except InvalidToken:  # api_key 解密失败 → 回退默认模型（qwen）
            llm_config = None
        with suppress(Exception):  # 槽位生成失败静默（可靠性层已记日志），推演时回退原始字段
            out = await ainvoke_with_reliability(
                build_understanding_chain(llm_config=llm_config),
                UNDERSTANDING_TEMPLATE.format_messages(
                    name=ability.name,
                    effect=ability.effect,
                    detail=ability.detail,
                ),
                operation="understanding",
                trace_context={"kind": "background", "trace_id": str(ability_id)},
            )
            ability.understanding = json.dumps(out.model_dump(), ensure_ascii=False)
            await db.commit()
