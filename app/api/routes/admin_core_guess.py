"""【临时试验功能】奇术核心一句话试验：选奇术 → 生成核心一句话 → 逐条猜测比对检定。

配套 app/services/nodes/ability_describer.py、guess_core_judge.py 与前端
pages/admin/CoreGuessLab.tsx，纯试验用途，不接业务链路，不写任何玩家表。

删除方式（一次性删干净，无需调整其它逻辑）：
1. 删本文件；
2. 删 app/api/router.py 中 `admin_core_guess` 一行 include；
3. 删前端 pages/admin/CoreGuessLab.tsx，及 App.tsx 中其 import/路由、AdminLayout.tsx 中导航项；
4. 删 app/services/nodes/ability_describer.py、guess_core_judge.py 与根目录 repro_core_guess.py。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin
from app.db.base import get_db
from app.models.ability import Ability
from app.models.user import User
from app.services.nodes.ability.describer import DESCRIBE_TEMPLATE, build_describer_llm
from app.services.nodes.guess.core_judge import (
    GUESS_CORE_JUDGE_TEMPLATE,
    CoreGuessVerdict,
    build_core_judge_llm,
)
from app.services.llm.reliability import ainvoke_with_reliability

router = APIRouter(prefix="/admin/core-guess", tags=["admin", "core-guess"])


class CoreDescribeIn(BaseModel):
    ability_id: str


class CoreDescribeOut(BaseModel):
    core_desc: str


class CoreJudgeIn(BaseModel):
    ability_id: str
    core_desc: str
    user_guess: str


async def _ability_txt(ability: Ability) -> str:
    return (
        f"名称：{ability.name}\n效果：{ability.effect}\n"
        f"补充说明：{ability.detail}"
    )


@router.post("/describe", response_model=CoreDescribeOut)
async def core_guess_describe(
    body: CoreDescribeIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CoreDescribeOut:
    """生成某奇术的核心一句话描述（失败由可靠性层重试，耗尽抛 500 由全局兜底）。"""
    ability = await db.get(Ability, body.ability_id)
    if ability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇术不存在")
    core = await ainvoke_with_reliability(
        build_describer_llm(),
        DESCRIBE_TEMPLATE.format_messages(
            name=ability.name,
            effect=ability.effect,
            detail=ability.detail,
        ),
        operation="core_desc",
        trace_context={"kind": "core_guess", "trace_id": body.ability_id},
    )
    return CoreDescribeOut(core_desc=(core or "").strip())


@router.post("/judge", response_model=CoreGuessVerdict)
async def core_guess_judge(
    body: CoreJudgeIn,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CoreGuessVerdict:
    """用户猜测 vs 核心一句话的比对检定：说对/说错/遗漏 + 是否命中核心。"""
    if not body.user_guess.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="猜测不能为空")
    ability = await db.get(Ability, body.ability_id)
    if ability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="奇术不存在")
    return await ainvoke_with_reliability(
        build_core_judge_llm(),
        GUESS_CORE_JUDGE_TEMPLATE.format_messages(
            user_guess=body.user_guess,
            core_desc=body.core_desc,
            ability=await _ability_txt(ability),
        ),
        operation="core_judge",
        trace_context={"kind": "core_guess", "trace_id": body.ability_id},
    )
