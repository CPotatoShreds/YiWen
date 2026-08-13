"""启程路由：启程 / 猜奇术 / 收手 / 再战 / 查看行迹 / 历史。"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import async_session_factory, get_db
from app.models.battle import Battle, BattleGuess
from app.models.board import BoardGuessProgress
from app.models.loadout import Loadout
from app.models.user import User
from app.schemas.battle import BattleOut, BattleStartIn, GuessBlock, GuessIn
from app.services.battle import (
    FAIL_GUESS_TEXT,
    GUESS_ATTEMPTS_MAX,
    disambiguate_fighters,
    try_start_guess,
)
from app.services.battle import give_up_guess as give_up_guess_service
from app.services.battle import rematch_battle as rematch_battle_service
from app.services.battle import start_battle as start_battle_service
from app.services.battle_stream import _get_stream
from app.services.nodes.guess_matcher import split_atomic_guesses

router = APIRouter(prefix="/battles", tags=["battles"])


def _filter_story(
    story: dict | None,
    viewer_id: int | None,
    revealed_a: bool,
    revealed_b: bool,
    a_id: int,
    b_id: int,
    unlock_all: bool = False,
) -> dict | None:
    """按查看者身份过滤：上帝视角恒不展示；叙述各看各的；奇术表/解读自己一侧可见、对家揭示后才可见。

    点将局挑战者对该刻印全部看破（unlock_all）→ 保留完整三视角（上帝 + 双方叙述 + 双方奇术表）。
    传阅页 viewer_id 即传阅者一侧（share token 决定），天然只看到传阅者自己的视角。
    """
    if story is None:
        return None
    out = dict(story)
    if unlock_all:
        return out  # 已全部看破：挑战者解锁完整三视角，不再过滤
    out.pop("narration", None)  # 上帝视角（直述双方奇术与真相）：存储但不展示
    # 叙述各看各的：A 看 narration_a，B 看 narration_b，其余全隐藏（揭示也不交换视角）
    if viewer_id == a_id:
        out.pop("narration_b", None)
    elif viewer_id == b_id:
        out.pop("narration_a", None)
    else:
        out.pop("narration_a", None)
        out.pop("narration_b", None)
    # 奇术表与解读：自己一侧始终可见，对家一侧（被猜破/reveal_on_miss 揭示）后才可见
    show_a = revealed_a or viewer_id == a_id
    show_b = revealed_b or viewer_id == b_id
    if not show_b:
        out.pop("abilities_b", None)
        out.pop("insight_b", None)
    if not show_a:
        out.pop("abilities_a", None)
        out.pop("insight_a", None)
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


async def _load_guess_rows(db: AsyncSession, battle_id: int) -> list[BattleGuess]:
    """某场全部猜词行（一行一猜测者）。"""
    rows = await db.execute(
        select(BattleGuess).where(BattleGuess.battle_id == battle_id).order_by(BattleGuess.guesser_id)
    )
    return list(rows.scalars().all())


def _row_for(rows: list[BattleGuess], guesser_id: int) -> BattleGuess | None:
    return next((r for r in rows if r.guesser_id == guesser_id), None)


def _guess_block(row: BattleGuess | None) -> GuessBlock | None:
    """猜词行 → 前端面板块（未看破卡不带真实奇术，保密）。"""
    if row is None or not row.used_abilities:
        return None
    cards = [
        {
            "index": i + 1,
            "matched": c["matched"],
            "cracked": c["cracked"],
            **({"name": used["name"], "effect": used["effect"]} if c["cracked"] else {}),
        }
        for i, (c, used) in enumerate(zip(row.cards, row.used_abilities))
    ]
    return GuessBlock(
        total=len(row.used_abilities),
        cards=cards,
        history=list(row.guess_history or []),
        attempts_used=row.attempts_used,
        attempts_max=row.attempts_max,
        done=row.done,
        flipped=row.flipped,
    )


async def _board_unlocked(db: AsyncSession, battle: Battle, viewer_id: int | None) -> bool:
    """点将局且查看者==挑战者：该挑战者对该刻印是否已全部看破（解锁完整三视角）。"""
    if battle.board_entry_id is None or viewer_id != battle.user_a_id:
        return False
    progress = await db.get(BoardGuessProgress, (viewer_id, battle.board_entry_id))
    return bool(progress and progress.flipped)


async def _to_out(
    db: AsyncSession,
    battle: Battle,
    viewer_id: int | None = None,
    *,
    names: dict[int, str] | None = None,
    fighter_names: dict[int, str] | None = None,
    guesses: dict[int, list[BattleGuess]] | None = None,
    entry_flipped: dict[int, bool] | None = None,
) -> BattleOut:
    # 后台猜词与读取可能交错：READ COMMITTED 每语句独立快照，battle 可能读到提交前、guess 读到提交后。
    # 先载 guess 行再刷新 battle，让 story/winner/revealed/guess_* 全部与最新猜词进度对齐，避免半提交态响应。
    if guesses is not None:
        rows = guesses.get(battle.id, [])
    else:
        rows = await _load_guess_rows(db, battle.id)
    if rows and guesses is None:
        await db.refresh(battle)
    # 点将局挑战者全看破解锁：entry_flipped 由列表页预加载避免 N+1，单查时现算
    if entry_flipped is not None:
        unlocked = bool(battle.board_entry_id and entry_flipped.get(battle.board_entry_id))
    else:
        unlocked = await _board_unlocked(db, battle, viewer_id)
    names = names if names is not None else await _resolve_names(db, battle)
    if fighter_names is None:
        fighters = await _resolve_fighters(db, battle)
        fighter_a = fighters["a"]
        fighter_b = fighters["b"]
    else:
        fighter_a = fighter_names.get(battle.loadout_a_id, "") if battle.loadout_a_id else ""
        fighter_b = fighter_names.get(battle.loadout_b_id, "") if battle.loadout_b_id else ""
    fighter_a = fighter_a or names.get(battle.user_a_id, "?")
    fighter_b = fighter_b or names.get(battle.user_b_id, "?")
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
    story = _filter_story(
        story,
        viewer_id,
        battle.revealed_a,
        battle.revealed_b,
        battle.user_a_id,
        battle.user_b_id,
        unlock_all=unlocked,
    )
    # 平铺字段兼容：非和局单行（败方行）为主；和局以查看者自己的行为主（my_guess 兜底）
    if battle.guess_by is not None:
        primary = rows[0] if rows else None
        my_row = primary if (viewer_id and primary and primary.guesser_id == viewer_id) else None
        opp_row = primary if (viewer_id and primary and primary.guesser_id != viewer_id) else None
    else:
        my_row = _row_for(rows, viewer_id) if viewer_id else None
        opp_row = next((r for r in rows if viewer_id and r.guesser_id != viewer_id), None)
        primary = my_row or opp_row
    is_guesser = my_row is not None
    guess_total = len(primary.used_abilities) if primary and primary.used_abilities else 0
    guess_cards = _guess_block(primary).cards if primary and primary.used_abilities else None
    guess_history = list(primary.guess_history or []) if primary else []
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
        board_entry_id=battle.board_entry_id,
        unlocked=unlocked,
        can_guess=(
            is_guesser
            and battle.status == "done"
            and my_row is not None
            and bool(my_row.used_abilities)
            and not my_row.done
            and my_row.attempts_used < my_row.attempts_max
        ),
        guessed=battle.guess_state == "done",
        guess_hit=battle.guess_hit,
        guess_score=battle.guess_score,
        guess_by=names.get(battle.guess_by) if battle.guess_by else None,
        guess_history=guess_history,
        guess_text=battle.guess_text if is_guesser else "",
        guess_total=guess_total,
        guess_cards=guess_cards,
        guess_attempts_used=primary.attempts_used if primary else 0,
        guess_attempts_max=primary.attempts_max if primary else GUESS_ATTEMPTS_MAX,
        revealed=battle.revealed,
        friendly=battle.friendly,
        my_guess=_guess_block(my_row),
        opp_guess=_guess_block(opp_row),
    )


@router.post("", response_model=BattleOut)
async def create_battle(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: BattleStartIn | None = None,
) -> BattleOut:
    """启程：创建 pending 记录，后台异步推演（返回即知对决已开始，稍后检阅行迹）。

    body.no_repeat=True 时避免与「我方奇人 × 对家奇人」同场过的具体配对。
    """
    battle = await start_battle_service(db, current, no_repeat=body.no_repeat if body else False)
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


@router.post("/{battle_id}/guess", response_model=BattleOut, status_code=status.HTTP_202_ACCEPTED)
async def guess_battle(
    battle_id: int,
    body: GuessIn,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """猜奇术（异步受理）：同步校验后 202 受理，LLM 判定在后台任务跑，结果经 SSE guess_done 回推。

    非和局仅败方可猜；和局双方各自并行独立猜。校验镜像 submit_guess 顶部检查，失败同步 400；
    判定在途再提交 → 409。
    """
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")
    if battle.status != "done":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对决尚未完成")
    if battle.guess_by is not None and battle.guess_by != current.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有战败方可以猜奇术")
    rows = await _load_guess_rows(db, battle.id)
    guess = _row_for(rows, current.id)
    if guess is None or not guess.used_abilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="本场无奇术可猜")
    if guess.done or guess.flipped:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="猜测已结束")
    if guess.attempts_used >= guess.attempts_max:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="猜测次数已用完")
    if not body.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="猜测不能为空")
    if not split_atomic_guesses(body.text):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FAIL_GUESS_TEXT)
    if not try_start_guess(battle.id, current.id, body.text):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上一轮猜测仍在判定中")
    return await _to_out(db, battle, viewer_id=current.id)


@router.post("/{battle_id}/give-up", response_model=BattleOut)
async def give_up(
    battle_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """收手：猜词者未全破即结束本轮猜词（是否揭示由被猜方 reveal_on_miss 决定）。

    和局双方都收手后结算：恰一方全破则其胜并重算名望，否则保持和局。
    """
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")
    try:
        await give_up_guess_service(db, battle, current)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await _to_out(db, battle, viewer_id=current.id)


@router.post("/{battle_id}/rematch", response_model=BattleOut)
async def rematch(
    battle_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """行迹再战：以原局快照 + 猜词状态复刻一场新对决（一律切磋不计名望），后台重推演。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if battle.board_entry_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="点将局不可再战，进度自会跨场累积")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")
    if battle.status != "done":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对决尚未完成，暂不可再战")
    new_battle = await rematch_battle_service(db, battle)
    return await _to_out(db, new_battle, viewer_id=current.id)


@router.get("/{battle_id}", response_model=BattleOut)
async def get_battle(
    battle_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BattleOut:
    """查看行迹（仅参战双方可见；点将局榜主不可看单场）。"""
    battle = await db.get(Battle, battle_id)
    if battle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
    if current.id not in (battle.user_a_id, battle.user_b_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看")
    if battle.board_entry_id is not None and current.id == battle.user_b_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="榜主不查看点将单场")
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
    """推演/猜词实时流（SSE）：推送观看者自己视角的分段转写，结束后推 done/error。仅参战双方可订阅。

    status 为 pending 或猜词阶段（done + 有猜词行未结束）时订阅事件总线，逐段推送；
    其余已结束状态立即回一个 done/error 事件。
    """
    async with async_session_factory() as db:
        battle = await db.get(Battle, battle_id)
        if battle is None or current.id not in (battle.user_a_id, battle.user_b_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
        if battle.board_entry_id is not None and current.id == battle.user_b_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行迹不存在")
        a_id, b_id, status_ = battle.user_a_id, battle.user_b_id, battle.status
        guess_state_ = battle.guess_state
        story_json = battle.story  # 已结束战斗的错误信息存于 story.error_message

    def _encode(ev: dict) -> str:
        return f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    async def gen():
        # 猜词阶段 = 已落定且有未结束的猜词行（guess_state "guessing"）：流保持开放，
        # 猜词后台任务/收手经总线推 guess_done。无猜词行（"none"）或已全结束（"done"）→ 短接。
        guess_phase = status_ == "done" and guess_state_ == "guessing"
        if status_ == "failed":
            msg = "铺陈推演失败"
            if story_json:
                msg = json.loads(story_json).get("error_message", msg)
            yield _encode({"type": "error", "message": msg})
            return
        if status_ != "pending" and not guess_phase:
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
    """我的行迹（历次对决记录）。点将局不记榜主行迹：榜主只看得到榜单聚合的被挑战次数。"""
    result = await db.execute(
        select(Battle)
        .where(
            or_(Battle.user_a_id == current.id, Battle.user_b_id == current.id),
            ~and_(Battle.board_entry_id.isnot(None), Battle.user_b_id == current.id),
        )
        .order_by(Battle.created_at.desc())
        .limit(50)
    )
    battles = result.scalars().all()
    if not battles:
        return []
    # 预加载当前用户作为挑战者的点将局看破进度（entry_id → flipped），避免 _to_out N+1
    entry_flipped: dict[int, bool] = {}
    entry_ids = {
        b.board_entry_id for b in battles if b.board_entry_id is not None and b.user_a_id == current.id
    }
    if entry_ids:
        prog_rows = (
            await db.execute(
                select(BoardGuessProgress).where(
                    BoardGuessProgress.challenger_id == current.id,
                    BoardGuessProgress.board_entry_id.in_(entry_ids),
                )
            )
        ).scalars().all()
        entry_flipped = {p.board_entry_id: p.flipped for p in prog_rows}
    user_ids = {user_id for battle in battles for user_id in (battle.user_a_id, battle.user_b_id, battle.winner_id) if user_id}
    loadout_ids = {loadout_id for battle in battles for loadout_id in (battle.loadout_a_id, battle.loadout_b_id) if loadout_id}
    names = {
        user.id: user.username
        for user in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    }
    fighter_names = {
        loadout.id: (loadout.name or "").strip()
        for loadout in (await db.execute(select(Loadout).where(Loadout.id.in_(loadout_ids)))).scalars().all()
    }
    guess_rows = (
        await db.execute(
            select(BattleGuess).where(BattleGuess.battle_id.in_(b.id for b in battles))
        )
    ).scalars().all()
    guesses: dict[int, list[BattleGuess]] = {}
    for g in guess_rows:
        guesses.setdefault(g.battle_id, []).append(g)
    for gs in guesses.values():
        gs.sort(key=lambda r: r.guesser_id)
    return [
        await _to_out(
            db,
            battle,
            viewer_id=current.id,
            names=names,
            fighter_names=fighter_names,
            guesses=guesses,
            entry_flipped=entry_flipped,
        )
        for battle in battles
    ]


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
    if battle.board_entry_id is not None and battle.share_token_b == token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="传阅不存在")  # 榜主侧不开放传阅
    # viewer_id 取传阅者一侧，_filter_story 只留该侧视角叙述与（揭示前）该侧奇术
    viewer_id = battle.user_a_id if battle.share_token == token else battle.user_b_id
    return await _to_out(db, battle, viewer_id=viewer_id)
