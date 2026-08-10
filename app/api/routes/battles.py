"""启程路由：启程 / 猜奇术 / 查看行迹 / 历史。"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import async_session_factory, get_db
from app.models.battle import Battle, BattleGuess
from app.models.loadout import Loadout
from app.models.user import User
from app.schemas.battle import BattleOut, GuessIn
from app.services.battle import GUESS_ATTEMPTS_MAX, disambiguate_fighters, submit_guess
from app.services.battle import start_battle as start_battle_service
from app.services.battle_stream import _get_stream

router = APIRouter(prefix="/battles", tags=["battles"])


def _filter_story(
    story: dict | None,
    viewer_id: int | None,
    revealed: bool,
    a_id: int,
    b_id: int,
) -> dict | None:
    """按查看者身份过滤：上帝视角恒不展示；叙述各看各的；奇术表/解读揭示前自己可见、对家隐藏。

    传阅页 viewer_id 即传阅者一侧（share token 决定），天然只看到传阅者自己的视角。
    """
    if story is None:
        return None
    out = dict(story)
    out.pop("narration", None)  # 上帝视角（直述双方奇术与真相）：存储但不展示
    # 叙述各看各的：A 看 narration_a，B 看 narration_b，其余全隐藏（揭示也不交换视角）
    if viewer_id == a_id:
        out.pop("narration_b", None)
    elif viewer_id == b_id:
        out.pop("narration_a", None)
    else:
        out.pop("narration_a", None)
        out.pop("narration_b", None)
    # 奇术表与解读：自己一侧始终可见，对家一侧揭示后才可见
    if not revealed:
        if viewer_id == a_id:
            out.pop("abilities_b", None)
            out.pop("insight_b", None)
        elif viewer_id == b_id:
            out.pop("abilities_a", None)
            out.pop("insight_a", None)
        else:  # 未登录/公开：揭示前奇术表与解读全部隐藏
            out.pop("abilities_a", None)
            out.pop("abilities_b", None)
            out.pop("insight_a", None)
            out.pop("insight_b", None)
    return out


async def _resolve_names(db: AsyncSession, battle: Battle) -> dict:
    ids = {battle.user_a_id, battle.user_b_id}
    if battle.winner_id:
        ids.add(battle.winner_id)
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    by_id = {u.id: u.username for u in rows.scalars().all()}
    return by_id


async def _resolve_fighters(db: AsyncSession, battle: Battle) -> dict[str, str]:
    """本场出战的奇人名字（loadout_a/b_id 快照）；未取名时留空，由调用方兜底异闻师名。"""
    ids = [i for i in (battle.loadout_a_id, battle.loadout_b_id) if i]
    if not ids:
        return {"a": "", "b": ""}
    rows = await db.execute(select(Loadout).where(Loadout.id.in_(ids)))
    by_id = {l.id: (l.name or "").strip() for l in rows.scalars().all()}
    return {"a": by_id.get(battle.loadout_a_id, ""), "b": by_id.get(battle.loadout_b_id, "")}


async def _to_out(db: AsyncSession, battle: Battle, viewer_id: int | None = None) -> BattleOut:
    names = await _resolve_names(db, battle)
    fighters = await _resolve_fighters(db, battle)
    fighter_a = fighters["a"] or names.get(battle.user_a_id, "?")
    fighter_b = fighters["b"] or names.get(battle.user_b_id, "?")
    # 双方同名时以「奇人名（异闻师名）」区分（与推演时命名规则一致，保证胜者名对得上叙述）
    fighter_a, fighter_b = disambiguate_fighters(
        fighter_a, fighter_b, names.get(battle.user_a_id, "?"), names.get(battle.user_b_id, "?")
    )
    winner_fighter = None
    if battle.winner_id == battle.user_a_id:
        winner_fighter = fighter_a
    elif battle.winner_id == battle.user_b_id:
        winner_fighter = fighter_b
    story = json.loads(battle.story) if battle.story else None
    story = _filter_story(story, viewer_id, battle.revealed, battle.user_a_id, battle.user_b_id)
    guess = await db.get(BattleGuess, battle.id)
    is_guesser = viewer_id is not None and battle.guess_by == viewer_id
    guess_cards = None
    guess_total = 0
    guess_history: list[str] = []
    if guess is not None and guess.used_abilities:
        # 猜词数据对双方可见：赢家据此实时看到败方猜词进度（卡片片段/看破 + 每次猜测原文）。
        # 未看破卡不带真实奇术（保密）；看破卡揭示该门名称/效果。
        guess_total = len(guess.used_abilities)
        guess_cards = [
            {
                "index": i + 1,
                "matched": c["matched"],
                "cracked": c["cracked"],
                **({"name": used["name"], "effect": used["effect"]} if c["cracked"] else {}),
            }
            for i, (c, used) in enumerate(zip(guess.cards, guess.used_abilities))
        ]
        guess_history = list(guess.guess_history or [])
    return BattleOut(
        id=battle.id,
        user_a=names.get(battle.user_a_id, "?"),
        user_b=names.get(battle.user_b_id, "?"),
        fighter_a=fighter_a,
        fighter_b=fighter_b,
        status=battle.status,
        winner=names.get(battle.winner_id) if battle.winner_id else None,
        winner_fighter=winner_fighter,
        story=story,
        rank_delta_a=battle.rank_delta_a,
        rank_delta_b=battle.rank_delta_b,
        share_token=battle.share_token,
        share_token_b=battle.share_token_b,
        created_at=battle.created_at,
        can_guess=(
            is_guesser
            and battle.status == "done"
            and guess is not None
            and bool(guess.used_abilities)
            and battle.guess_state != "done"
            and guess.attempts_used < guess.attempts_max
        ),
        guessed=battle.guess_state == "done",
        guess_hit=battle.guess_hit,
        guess_score=battle.guess_score,
        guess_by=names.get(battle.guess_by) if battle.guess_by else None,
        guess_history=guess_history,
        guess_text=battle.guess_text if is_guesser else "",
        guess_total=guess_total,
        guess_cards=guess_cards,
        guess_attempts_used=guess.attempts_used if guess else 0,
        guess_attempts_max=guess.attempts_max if guess else GUESS_ATTEMPTS_MAX,
        revealed=battle.revealed,
        friendly=battle.friendly,
    )


@router.post("", response_model=BattleOut)
async def create_battle(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """启程：创建 pending 记录，后台异步推演（返回即知对决已开始，稍后检阅行迹）。"""
    battle = await start_battle_service(db, current)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="暂无可匹配的对手（需先让已解封的奇人装入奇术）")
    return await _to_out(db, battle, viewer_id=current.id)


@router.post("/challenge/{user_id}", response_model=BattleOut)
async def challenge(
    user_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """向指定故人递上切磋帖（切磋局，不计名望）。"""
    if user_id == current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能与自己切磋")
    battle = await start_battle_service(db, current, opponent_id=user_id, friendly=True)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对方无法应战（用户不存在或无已解封奇术）")
    return await _to_out(db, battle, viewer_id=current.id)


@router.post("/{battle_id}/guess", response_model=BattleOut)
async def guess_battle(
    battle_id: int,
    body: GuessIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """败方猜奇术（迭代式）：逐次道出猜测，命中内容上卡并解锁猜测条；全破逆转，次数耗尽按设置揭示。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")
    try:
        await submit_guess(db, battle, current, body.text)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return await _to_out(db, battle, viewer_id=current.id)


@router.get("/{battle_id}", response_model=BattleOut)
async def get_battle(
    battle_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """查看行迹（仅参战双方可见）。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看")
    return await _to_out(db, battle, viewer_id=current.id)


def _filter_for_viewer(ev: dict, viewer_id: int, a_id: int, b_id: int) -> dict | None:
    """SSE 事件按观看者身份过滤：segment 只透传自己一侧的叙述，其余事件原样透传。

    上帝叙述从不进入事件（转写管线只 publish narration_a/b）；这里确保对面一侧的
    叙述也不离开服务器。
    """
    if ev.get("type") == "segment":
        side = "a" if viewer_id == a_id else "b"
        narration = ev.get(f"narration_{side}")
        if not narration:
            return None
        return {"type": "segment", "round": ev.get("round", 0), "narration": narration}
    return ev


@router.get("/{battle_id}/stream")
async def battle_stream(
    battle_id: int,
    current: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """推演实时流（SSE）：推送观看者自己视角的分段转写，结束后推 done/error。仅参战双方可订阅。

    status 为 pending 时订阅事件总线，逐段推送；已结束则立即回一个 done/error 事件。
    """
    async with async_session_factory() as db:
        battle = await db.get(Battle, battle_id)
        if battle is None or current.id not in (battle.user_a_id, battle.user_b_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
        a_id, b_id, status_ = battle.user_a_id, battle.user_b_id, battle.status
        story_json = battle.story  # 已结束战斗的错误信息存于 story.error_message

    def _encode(ev: dict) -> str:
        return f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    async def gen():
        if status_ != "pending":
            if status_ == "failed":
                msg = "铺陈推演失败"
                if story_json:
                    msg = json.loads(story_json).get("error_message", msg)
                yield _encode({"type": "error", "message": msg})
            else:
                yield _encode({"type": "done", "status": status_})
            return
        stream = _get_stream(battle_id)
        q, snapshot = stream.subscribe()
        try:
            for ev in snapshot:  # 补发此前已发出的分段（中途订阅不漏段）
                payload = _filter_for_viewer(ev, current.id, a_id, b_id)
                if payload:
                    yield _encode(payload)
            while True:
                ev = await q.get()
                if ev is None:  # 关闭哨兵
                    break
                payload = _filter_for_viewer(ev, current.id, a_id, b_id)
                if payload:
                    yield _encode(payload)
        finally:
            stream.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=list[BattleOut])
async def my_battles(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BattleOut]:
    """我的行迹（历次对决记录）。"""
    result = await db.execute(
        select(Battle)
        .where(or_(Battle.user_a_id == current.id, Battle.user_b_id == current.id))
        .order_by(Battle.created_at.desc())
        .limit(50)
    )
    return [await _to_out(db, b, viewer_id=current.id) for b in result.scalars().all()]


@router.get("/share/{token}", response_model=BattleOut)
async def share_battle(token: str, db: Annotated[AsyncSession, Depends(get_db)]) -> BattleOut:
    """公开行迹传阅页（凭令牌，免登录）。传阅 = 传阅者自己的视角。

    token 命中 A 侧（share_token）→ 传阅的是 A 视角；命中 B 侧（share_token_b）→ B 视角。
    看破后才含双方奇术表。
    """
    result = await db.execute(
        select(Battle).where(or_(Battle.share_token == token, Battle.share_token_b == token))
    )
    battle = result.scalar_one_or_none()
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="传阅不存在")
    # viewer_id 取传阅者一侧，_filter_story 只留该侧视角叙述与（揭示前）该侧奇术
    viewer_id = battle.user_a_id if battle.share_token == token else battle.user_b_id
    return await _to_out(db, battle, viewer_id=viewer_id)
