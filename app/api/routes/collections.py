"""小天下集：卷、册、点将、交互世界线与堪算。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.ability import Ability
from app.models.collection import (
    CollectionBooklet,
    CollectionChallenge,
    CollectionGuessProgress,
    CollectionMessage,
    CollectionVolume,
    CollectionWorldline,
)
from app.models.loadout import Loadout, LoadoutAbility
from app.models.user import User, loadout_capacity
from app.models.user_ability import UserAbility
from app.schemas.collection import (
    ActionIn,
    BookletIn,
    BookletOut,
    ChallengeIn,
    ChallengeOut,
    ChallengeSummaryOut,
    CollectionGuessOut,
    CollectionMessageOut,
    CollectionParticipantOut,
    CollectionRosterMemberIn,
    CollectionStatsOut,
    GuessIn,
    VolumeDetailOut,
    VolumeIn,
    VolumeOut,
    WorldlineOut,
)
from app.services.guess.pipeline import (
    run_guess_commentary,
    run_guess_verification,
    strip_commentary_reason,
)
from app.services.llm.reliability import ainvoke_with_reliability
from app.services.loadouts.service import loadout_snapshot
from app.services.nodes.collection import (
    CHALLENGER_VIEW_TEMPLATE,
    GUARDIAN_VIEW_TEMPLATE,
    JUDGE_TEMPLATE,
    build_collection_challenger_view_llm,
    build_collection_god_llm,
    build_collection_guardian_view_llm,
    build_collection_judge_llm,
    parse_collection_god_reply,
)

router = APIRouter(prefix="/collections", tags=["collections"])
WORLDLINE_TOKEN_BUDGET = 24_000


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _token_estimate(*texts: str) -> int:
    return max(1, sum(len(text.encode("utf-8")) for text in texts) // 3)


def _abilities(snapshot: list[dict]) -> list[dict]:
    return [ability for member in snapshot for ability in (member.get("abilities") or [])]


def _private_terms(snapshot: list[dict]) -> list[str]:
    terms = []
    for member in snapshot:
        for ability in member.get("abilities") or []:
            terms.extend(
                str(ability.get(field, ""))
                for field in ("name", "effect", "detail", "understanding")
                if ability.get(field)
            )
    return terms


def _redact_view_context(text: str, *private_groups: list[str]) -> str:
    """在视角节点前确定性移除对方奇术和守册意图，避免仅靠提示词防泄露。"""
    for term in sorted({term for group in private_groups for term in group if term}, key=len, reverse=True):
        text = text.replace(term, "（视角不可见信息）")
    return text


def _participants(snapshot: list[dict]) -> list[CollectionParticipantOut]:
    return [CollectionParticipantOut(**member) for member in snapshot]


def _public_participants(snapshot: list[dict]) -> list[CollectionParticipantOut]:
    return [CollectionParticipantOut(name=member.get("name", ""), style=member.get("style", ""), tactic=member.get("tactic", ""), abilities=[]) for member in snapshot]


def _is_admin(user: User) -> bool:
    return bool(user.is_admin)


async def _usernames(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.username).where(User.id.in_(ids)))).all()
    return {uid: username for uid, username in rows}


async def _get_volume(db: AsyncSession, volume_id: int) -> CollectionVolume:
    volume = await db.get(CollectionVolume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="卷不存在")
    return volume


async def _get_booklet(db: AsyncSession, booklet_id: int) -> CollectionBooklet:
    booklet = await db.get(CollectionBooklet, booklet_id)
    if booklet is None:
        raise HTTPException(status_code=404, detail="册不存在")
    return booklet


async def _get_challenge(db: AsyncSession, challenge_id: int) -> CollectionChallenge:
    challenge = await db.get(CollectionChallenge, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="挑战不存在")
    return challenge


async def _owned_snapshot(
    db: AsyncSession, user: User, members: list[CollectionRosterMemberIn]
) -> list[dict]:
    loadout_ids = [member.loadout_id for member in members if member.loadout_id is not None]
    if len(loadout_ids) != len(set(loadout_ids)):
        raise HTTPException(status_code=400, detail="阵容不能重复选择同一奇人")
    rows = (await db.execute(select(Loadout).where(Loadout.id.in_(loadout_ids), Loadout.user_id == user.id))).scalars().all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(loadout_ids):
        raise HTTPException(status_code=404, detail="阵容中的奇人不存在")
    snapshots = []
    for member in members:
        if member.loadout_id is not None:
            if member.abilities or member.name or member.style or member.tactic:
                raise HTTPException(status_code=400, detail="既有奇人与临时奇人设定不能混用")
            snapshots.append(await loadout_snapshot(db, by_id[member.loadout_id]))
            continue
        name = member.name.strip()
        abilities = [ability.model_dump() for ability in member.abilities]
        if not name or not abilities:
            raise HTTPException(status_code=400, detail="临时奇人须填写姓名并至少编入一门奇术")
        snapshots.append({"name": name, "style": member.style.strip(), "tactic": member.tactic.strip(), "abilities": abilities})
    if any(not member["abilities"] for member in snapshots):
        raise HTTPException(status_code=400, detail="每位登场奇人至少须装有一门奇术")
    return snapshots


async def _get_progress(
    db: AsyncSession, challenge: CollectionChallenge, booklet: CollectionBooklet
) -> CollectionGuessProgress:
    progress = await db.get(CollectionGuessProgress, (challenge.challenger_id, booklet.id))
    if progress is None:
        progress = CollectionGuessProgress(
            challenger_id=challenge.challenger_id,
            booklet_id=booklet.id,
            cards=[{"cracked": False, "missing": ""} for _ in _abilities(booklet.defenders or [])],
        )
        db.add(progress)
        await db.flush()
    return progress


def _guess_out(progress: CollectionGuessProgress, abilities: list[dict] | None = None) -> CollectionGuessOut:
    abilities = abilities or []
    cards = []
    for index, card in enumerate(progress.cards or []):
        item = {**card, "index": index + 1}
        if card.get("cracked") and index < len(abilities):
            item["name"] = abilities[index].get("name", "")
            item["effect"] = abilities[index].get("effect", "")
        cards.append(item)
    return CollectionGuessOut(
        total=len(cards),
        cards=cards,
        history=progress.history or [],
        comments=strip_commentary_reason(progress.comments or []),
        atom_count=progress.atom_count,
        can_verify=bool(progress.history and progress.verified_round != len(progress.history)),
        cracked=progress.cracked_at is not None,
    )


async def _booklet_stats(db: AsyncSession, booklet: CollectionBooklet) -> CollectionStatsOut:
    today = datetime.now(UTC).date().isoformat()
    if booklet.stats_date == today:
        return CollectionStatsOut(**(booklet.stats or {}))
    challenge_count = (
        await db.execute(select(func.count()).select_from(CollectionChallenge).where(CollectionChallenge.booklet_id == booklet.id))
    ).scalar_one()
    progresses = (
        await db.execute(select(CollectionGuessProgress).where(CollectionGuessProgress.booklet_id == booklet.id))
    ).scalars().all()
    derived = [item for item in progresses if item.first_derived_at is not None]
    cracked = [item for item in progresses if item.cracked_at is not None]
    stats = CollectionStatsOut(
        challenge_count=challenge_count,
        derived_count=len(derived),
        cracked_count=len(cracked),
        avg_worldlines_to_derive=(
            sum(item.first_derived_worldlines or 0 for item in derived) / len(derived) if derived else None
        ),
        avg_atoms_to_crack=(
            sum(item.first_cracked_atoms or 0 for item in cracked) / len(cracked) if cracked else None
        ),
    )
    booklet.stats_date = today
    booklet.stats = stats.model_dump()
    await db.commit()
    return stats


async def _volume_out(
    db: AsyncSession, volume: CollectionVolume, viewer: User, names: dict[int, str] | None = None
) -> VolumeOut:
    names = names or await _usernames(db, {volume.user_id})
    booklet_count = (
        await db.execute(select(func.count()).select_from(CollectionBooklet).where(CollectionBooklet.volume_id == volume.id))
    ).scalar_one()
    return VolumeOut(
        id=volume.id,
        title=volume.title,
        introduction=volume.introduction,
        booklet_requirements=volume.booklet_requirements,
        victory_condition=volume.victory_condition,
        tianji=volume.tianji or [],
        author=names.get(volume.user_id, "?"),
        mine=volume.user_id == viewer.id,
        can_manage=_is_admin(viewer),
        booklet_count=booklet_count,
        created_at=volume.created_at,
    )


async def _booklet_out(
    db: AsyncSession, booklet: CollectionBooklet, viewer: User, names: dict[int, str] | None = None
) -> BookletOut:
    names = names or await _usernames(db, {booklet.user_id})
    history_query = select(CollectionChallenge).where(CollectionChallenge.booklet_id == booklet.id)
    if viewer.id != booklet.user_id and not _is_admin(viewer):
        history_query = history_query.where(CollectionChallenge.challenger_id == viewer.id)
    challenges = (await db.execute(history_query.order_by(CollectionChallenge.created_at.desc()))).scalars().all()
    history = []
    for challenge in challenges:
        worldline_count = (
            await db.execute(select(func.count()).select_from(CollectionWorldline).where(CollectionWorldline.challenge_id == challenge.id))
        ).scalar_one()
        progress = await db.get(CollectionGuessProgress, (challenge.challenger_id, booklet.id))
        history.append(
            ChallengeSummaryOut(
                id=challenge.id,
                status=challenge.status,
                derived=challenge.derived_at is not None,
                cracked=bool(progress and progress.cracked_at),
                worldline_count=worldline_count,
                created_at=challenge.created_at,
            )
        )
    return BookletOut(
        id=booklet.id,
        volume_id=booklet.volume_id,
        author=names.get(booklet.user_id, "?"),
        defenders=(
            _participants(booklet.defenders or [])
            if viewer.id == booklet.user_id or _is_admin(viewer)
            else _public_participants(booklet.defenders or [])
        ),
        defender_people=len(booklet.defenders or []),
        defender_ability_count=len(_abilities(booklet.defenders or [])),
        opening=booklet.opening,
        challenges_open=booklet.challenges_open,
        mine=booklet.user_id == viewer.id,
        can_manage=_is_admin(viewer),
        stats=await _booklet_stats(db, booklet),
        history=history,
        created_at=booklet.created_at,
    )


async def _finish_if_double(
    db: AsyncSession, challenge: CollectionChallenge, progress: CollectionGuessProgress
) -> None:
    if challenge.derived_at is None or progress.cracked_at is None:
        return
    challenge.cracked_at = progress.cracked_at
    challenge.status = "completed"
    challenge.finished_at = _now()
    active_lines = (
        await db.execute(
            select(CollectionWorldline).where(
                CollectionWorldline.challenge_id == challenge.id, CollectionWorldline.status == "active"
            )
        )
    ).scalars().all()
    for line in active_lines:
        line.status, line.ended_at = "completed", _now()


async def _challenge_out(db: AsyncSession, challenge: CollectionChallenge, viewer: User) -> ChallengeOut:
    booklet = await _get_booklet(db, challenge.booklet_id)
    if viewer.id not in {challenge.challenger_id, booklet.user_id} and not _is_admin(viewer):
        raise HTTPException(status_code=403, detail="只能查看自己参与的挑战")
    is_challenger = viewer.id == challenge.challenger_id
    is_admin = _is_admin(viewer)
    names = await _usernames(db, {challenge.challenger_id})
    lines = (
        await db.execute(
            select(CollectionWorldline).where(CollectionWorldline.challenge_id == challenge.id).order_by(CollectionWorldline.sequence)
        )
    ).scalars().all()
    progress = await _get_progress(db, challenge, booklet) if is_challenger else None
    # 参与者即使拥有管理员权限，也必须保持自己的脱敏视角；管理员旁观时才看上帝视角。
    is_guardian = viewer.id == booklet.user_id
    out_lines = []
    for line in lines:
        messages = (
            await db.execute(
                select(CollectionMessage).where(CollectionMessage.worldline_id == line.id).order_by(CollectionMessage.sequence)
            )
        ).scalars().all()
        out_messages = []
        for message in messages:
            message_text = message.challenger_text if is_challenger else message.guardian_text
            if is_admin and not is_challenger and not is_guardian:
                message_text = message.omniscient_text
            out_messages.append(
                CollectionMessageOut(
                    id=message.id,
                    sequence=message.sequence,
                    role=message.role,
                    text=message_text,
                    omniscient_text=message.omniscient_text if is_admin else None,
                    created_at=message.created_at,
                )
            )
        out_lines.append(
            WorldlineOut(
                id=line.id,
                sequence=line.sequence,
                status=line.status,
                token_budget=line.token_budget,
                tokens_used=line.tokens_used,
                derived=line.derived,
                messages=out_messages,
                guess=_guess_out(progress, _abilities(booklet.defenders or [])) if progress else None,
                created_at=line.created_at,
            )
        )
    return ChallengeOut(
        id=challenge.id,
        booklet_id=booklet.id,
        opening=booklet.opening,
        challenger=names.get(challenge.challenger_id, "?"),
        challengers=_participants(challenge.challengers or []) if is_challenger or is_admin else [],
        status=challenge.status,
        derived=challenge.derived_at is not None,
        cracked=bool(progress and progress.cracked_at) if progress else challenge.cracked_at is not None,
        worldlines=out_lines,
        created_at=challenge.created_at,
    )


@router.get("/volumes", response_model=list[VolumeOut])
async def list_volumes(
    current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> list[VolumeOut]:
    volumes = (await db.execute(select(CollectionVolume).order_by(CollectionVolume.created_at.desc()))).scalars().all()
    names = await _usernames(db, {volume.user_id for volume in volumes})
    return [await _volume_out(db, volume, current, names) for volume in volumes]


@router.post("/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED)
async def create_volume(
    body: VolumeIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> VolumeOut:
    if not _is_admin(current):
        raise HTTPException(status_code=403, detail="只有管理员可以新添卷")
    values = [body.title.strip(), body.introduction.strip(), body.booklet_requirements.strip(), body.victory_condition.strip()]
    if not all(values):
        raise HTTPException(status_code=400, detail="卷名、介绍、入卷标准和胜利条件不能为空")
    tianji = [{"name": item.name.strip(), "description": item.description.strip()} for item in body.tianji]
    if any(not item["name"] or not item["description"] for item in tianji):
        raise HTTPException(status_code=400, detail="每条天机均须填写名称与说明")
    volume = CollectionVolume(
        user_id=current.id,
        title=values[0],
        introduction=values[1],
        booklet_requirements=values[2],
        victory_condition=values[3],
        tianji=tianji,
    )
    db.add(volume)
    await db.commit()
    await db.refresh(volume)
    return await _volume_out(db, volume, current, {current.id: current.username})


@router.get("/volumes/{volume_id}", response_model=VolumeDetailOut)
async def volume_detail(
    volume_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> VolumeDetailOut:
    volume = await _get_volume(db, volume_id)
    booklets = (
        await db.execute(select(CollectionBooklet).where(CollectionBooklet.volume_id == volume.id).order_by(CollectionBooklet.created_at.desc()))
    ).scalars().all()
    names = await _usernames(db, {volume.user_id, *(booklet.user_id for booklet in booklets)})
    return VolumeDetailOut(
        **(await _volume_out(db, volume, current, names)).model_dump(),
        booklets=[await _booklet_out(db, booklet, current, names) for booklet in booklets],
    )


@router.post("/volumes/{volume_id}/booklets", response_model=BookletOut, status_code=status.HTTP_201_CREATED)
async def create_booklet(
    volume_id: int, body: BookletIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> BookletOut:
    volume = await _get_volume(db, volume_id)
    if len(body.defenders) != 1:
        raise HTTPException(status_code=400, detail="小天下集当前只支持一位奇人登场")
    defenders = await _owned_snapshot(db, current, body.defenders)
    opening, brief = body.opening.strip(), body.guardian_brief.strip()
    if not opening or not brief:
        raise HTTPException(status_code=400, detail="公开开场和私密守册意图不能为空")
    booklet = CollectionBooklet(volume_id=volume.id, user_id=current.id, defenders=defenders, opening=opening, guardian_brief=brief)
    db.add(booklet)
    await db.commit()
    await db.refresh(booklet)
    return await _booklet_out(db, booklet, current, {current.id: current.username})


@router.post("/booklets/{booklet_id}/close", status_code=status.HTTP_204_NO_CONTENT)
async def close_booklet(
    booklet_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    if not _is_admin(current):
        raise HTTPException(status_code=403, detail="只有管理员可以关闭册")
    booklet = await _get_booklet(db, booklet_id)
    booklet.challenges_open = False
    await db.commit()


@router.post("/booklets/{booklet_id}/challenges", response_model=ChallengeOut, status_code=status.HTTP_201_CREATED)
async def start_challenge(
    booklet_id: int, body: ChallengeIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> ChallengeOut:
    booklet = await _get_booklet(db, booklet_id)
    if not booklet.challenges_open:
        raise HTTPException(status_code=409, detail="此册已关闭新挑战")
    if booklet.user_id == current.id:
        raise HTTPException(status_code=400, detail="不能挑战自己新添的册")
    if len(body.challengers) != 1:
        raise HTTPException(status_code=400, detail="小天下集当前只支持一位挑战奇人")
    challengers = await _owned_snapshot(db, current, body.challengers)
    challenge = CollectionChallenge(booklet_id=booklet.id, challenger_id=current.id, challengers=challengers)
    db.add(challenge)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="此册已有一场未结束挑战") from exc
    progress = await _get_progress(db, challenge, booklet)
    if progress.cracked_at is not None:
        challenge.cracked_at = progress.cracked_at
    line = CollectionWorldline(challenge_id=challenge.id, sequence=1, token_budget=WORLDLINE_TOKEN_BUDGET)
    db.add(line)
    await db.commit()
    return await _challenge_out(db, challenge, current)


@router.get("/challenges/{challenge_id}", response_model=ChallengeOut)
async def challenge_detail(
    challenge_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> ChallengeOut:
    return await _challenge_out(db, await _get_challenge(db, challenge_id), current)


@router.post("/challenges/{challenge_id}/worldlines", response_model=WorldlineOut, status_code=status.HTTP_201_CREATED)
async def restart_worldline(
    challenge_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> WorldlineOut:
    challenge = await _get_challenge(db, challenge_id)
    if challenge.challenger_id != current.id:
        raise HTTPException(status_code=403, detail="只能回溯自己的挑战")
    if challenge.status != "active" or challenge.derived_at is not None:
        raise HTTPException(status_code=409, detail="此挑战不能再新开世界线")
    active = (
        await db.execute(
            select(CollectionWorldline.id).where(
                CollectionWorldline.challenge_id == challenge.id, CollectionWorldline.status == "active"
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(status_code=409, detail="请先封存当前世界线")
    sequence = (
        await db.execute(select(func.coalesce(func.max(CollectionWorldline.sequence), 0)).where(CollectionWorldline.challenge_id == challenge.id))
    ).scalar_one() + 1
    line = CollectionWorldline(challenge_id=challenge.id, sequence=sequence, token_budget=WORLDLINE_TOKEN_BUDGET)
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return WorldlineOut(id=line.id, sequence=line.sequence, status=line.status, token_budget=line.token_budget, tokens_used=0, derived=False, created_at=line.created_at)


@router.post("/worldlines/{worldline_id}/end", status_code=status.HTTP_204_NO_CONTENT)
async def end_worldline(
    worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    line = await db.get(CollectionWorldline, worldline_id)
    if line is None:
        raise HTTPException(status_code=404, detail="世界线不存在")
    challenge = await _get_challenge(db, line.challenge_id)
    if challenge.challenger_id != current.id or line.status != "active":
        raise HTTPException(status_code=409, detail="此世界线不能封存")
    line.status, line.ended_at = "ended", _now()
    await db.commit()


@router.post("/challenges/{challenge_id}/concede", status_code=status.HTTP_204_NO_CONTENT)
async def concede_challenge(
    challenge_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    challenge = await _get_challenge(db, challenge_id)
    if challenge.challenger_id != current.id or challenge.status != "active":
        raise HTTPException(status_code=409, detail="此挑战不能结束")
    challenge.status, challenge.finished_at = "conceded", _now()
    lines = (
        await db.execute(
            select(CollectionWorldline).where(CollectionWorldline.challenge_id == challenge.id, CollectionWorldline.status == "active")
        )
    ).scalars().all()
    for line in lines:
        line.status, line.ended_at = "ended", _now()
    await db.commit()


@router.post("/worldlines/{worldline_id}/actions", response_model=WorldlineOut)
async def submit_action(
    worldline_id: int, body: ActionIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> WorldlineOut:
    line = await db.get(CollectionWorldline, worldline_id)
    if line is None:
        raise HTTPException(status_code=404, detail="世界线不存在")
    challenge = await _get_challenge(db, line.challenge_id)
    if challenge.challenger_id != current.id or challenge.status != "active" or line.status != "active":
        raise HTTPException(status_code=409, detail="此世界线不能继续衍算")
    booklet = await _get_booklet(db, challenge.booklet_id)
    volume = await _get_volume(db, booklet.volume_id)
    action = body.text.strip()
    messages = (
        await db.execute(
            select(CollectionMessage).where(CollectionMessage.worldline_id == line.id).order_by(CollectionMessage.sequence)
        )
    ).scalars().all()
    # 只将上帝节点生成的权威回合记录回灌；原始行动消息保留用于审计，
    # 但不能未经裁定地成为下一轮的世界事实。
    history = "\n".join(
        message.omniscient_text
        for message in messages[-12:]
        if message.role == "guardian" and message.omniscient_text
    )
    challenger_name = (challenge.challengers or [{}])[0].get("name", "挑战者奇人")
    guardian_name = (booklet.defenders or [{}])[0].get("name", "守方奇人")
    action_fact = (
        f"挑战者奇人“{challenger_name}”受到异闻师的指引。\n"
        f"异闻师要求其采取以下行动：\n“{action}”\n"
        "请将其视为该奇人在当前局面下真实执行的行动意图。"
    )
    god_raw = await ainvoke_with_reliability(
        build_collection_god_llm(),
        {
            "volume": f"{volume.title}：{volume.introduction}",
            "requirements": volume.booklet_requirements,
            "victory_condition": volume.victory_condition,
            "tianji": volume.tianji,
            "opening": booklet.opening,
            "brief": booklet.guardian_brief,
            "defenders": booklet.defenders,
            "challengers": challenge.challengers,
            "history": history or "（开场尚未行动）",
            "action": action_fact,
            "remaining": max(0, line.token_budget - line.tokens_used),
        },
        operation="collection_god_reply",
        trace_context={"kind": "collection", "trace_id": str(line.id)},
    )
    god = parse_collection_god_reply(god_raw) if isinstance(god_raw, str) else god_raw
    omniscient_text = f"{god.omniscient_view}\n\n【权威状态摘要】\n{god.state_summary}\n\n【行动结果】\n{god.action_result}"
    challenger_history = "\n".join(message.challenger_text for message in messages[-6:] if message.challenger_text)
    guardian_history = "\n".join(message.guardian_text for message in messages[-6:] if message.guardian_text)

    async def _view(builder, template, operation, previous_view):
        hidden_terms = _private_terms(booklet.defenders if operation == "collection_challenger_view" else challenge.challengers)
        hidden_terms.append(booklet.guardian_brief)
        return await ainvoke_with_reliability(
            builder(),
            {
                "challenger_name": challenger_name,
                "guardian_name": guardian_name,
                "opening": booklet.opening,
                "previous_view": previous_view or "（首轮，无上一轮视角记录）",
                "god": _redact_view_context(god.omniscient_view, hidden_terms),
                "state_summary": _redact_view_context(god.state_summary, hidden_terms),
            },
            operation=operation,
            trace_context={"kind": "collection", "trace_id": str(line.id)},
        )

    challenger_result, guardian_result = await asyncio.gather(
        _view(build_collection_challenger_view_llm, CHALLENGER_VIEW_TEMPLATE, "collection_challenger_view", challenger_history),
        _view(build_collection_guardian_view_llm, GUARDIAN_VIEW_TEMPLATE, "collection_guardian_view", guardian_history),
        return_exceptions=True,
    )
    challenger_view = (
        challenger_result.text if hasattr(challenger_result, "text") else str(challenger_result)
        if not isinstance(challenger_result, Exception)
        else f"{challenger_name}经历了这一轮局势变化，但挑战者视角暂未生成，请稍后查看本世界线。"
    )
    guardian_view = (
        guardian_result.text if hasattr(guardian_result, "text") else str(guardian_result)
        if not isinstance(guardian_result, Exception)
        else f"{guardian_name}完成了这一轮应对，但守方视角暂未生成，请稍后查看本世界线。"
    )
    used = _token_estimate(history, action_fact, omniscient_text, challenger_view, guardian_view)
    if line.tokens_used + used >= line.token_budget:
        line.tokens_used, line.status, line.ended_at = line.token_budget, "exhausted", _now()
    else:
        line.tokens_used += used
    sequence = len(messages) + 1
    db.add(CollectionMessage(worldline_id=line.id, sequence=sequence, role="challenger", challenger_text=action, guardian_text="挑战者行动已提交。", omniscient_text=action))
    db.add(CollectionMessage(worldline_id=line.id, sequence=sequence + 1, role="guardian", challenger_text=challenger_view, guardian_text=guardian_view, omniscient_text=omniscient_text, tokens_input=used))
    await db.commit()
    response = await _challenge_out(db, challenge, current)
    return next(item for item in response.worldlines if item.id == line.id)


@router.post("/worldlines/{worldline_id}/derive", response_model=WorldlineOut)
async def derive_worldline(
    worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> WorldlineOut:
    line = await db.get(CollectionWorldline, worldline_id)
    if line is None:
        raise HTTPException(status_code=404, detail="世界线不存在")
    challenge = await _get_challenge(db, line.challenge_id)
    if challenge.challenger_id != current.id or line.status != "active":
        raise HTTPException(status_code=409, detail="此世界线不能检定")
    booklet = await _get_booklet(db, challenge.booklet_id)
    volume = await _get_volume(db, booklet.volume_id)
    messages = (
        await db.execute(
            select(CollectionMessage).where(CollectionMessage.worldline_id == line.id).order_by(CollectionMessage.sequence)
        )
    ).scalars().all()
    history = "\n".join(f"{message.role}：{message.omniscient_text}" for message in messages)
    verdict = await ainvoke_with_reliability(
        build_collection_judge_llm(),
        JUDGE_TEMPLATE.format_messages(
            volume=f"{volume.title}：{volume.introduction}",
            victory_condition=volume.victory_condition,
            tianji=volume.tianji,
            opening=booklet.opening,
            history=history or "（尚未行动）",
        ),
        operation="collection_derive",
        trace_context={"kind": "collection", "trace_id": str(line.id)},
    )
    if verdict.achieved:
        line.derived, line.status, line.ended_at = True, "derived", _now()
        challenge.derived_at = challenge.derived_at or _now()
        progress = await _get_progress(db, challenge, booklet)
        if progress.first_derived_at is None:
            progress.first_derived_at = _now()
            progress.first_derived_worldlines = line.sequence
        await _finish_if_double(db, challenge, progress)
    await db.commit()
    response = await _challenge_out(db, challenge, current)
    return next(item for item in response.worldlines if item.id == line.id)


@router.post("/worldlines/{worldline_id}/guess", response_model=CollectionGuessOut)
async def collection_guess(
    worldline_id: int, body: GuessIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> CollectionGuessOut:
    line = await db.get(CollectionWorldline, worldline_id)
    if line is None:
        raise HTTPException(status_code=404, detail="世界线不存在")
    challenge = await _get_challenge(db, line.challenge_id)
    if challenge.challenger_id != current.id or challenge.status != "active":
        raise HTTPException(status_code=409, detail="此挑战不能继续堪算")
    booklet = await _get_booklet(db, challenge.booklet_id)
    progress = await _get_progress(db, challenge, booklet)
    if progress.cracked_at is not None:
        return _guess_out(progress, _abilities(booklet.defenders or []))
    groups = await run_guess_commentary(
        text=body.text.strip(),
        abilities=_abilities(booklet.defenders or []),
        cards=progress.cards or [],
        trace_context={"kind": "collection", "trace_id": str(line.id)},
    )
    progress.history = [*(progress.history or []), body.text.strip()]
    progress.comments = [*(progress.comments or []), groups]
    progress.atom_count += sum(len(group.get("items") or []) for group in groups)
    await db.commit()
    return _guess_out(progress, _abilities(booklet.defenders or []))


@router.post("/worldlines/{worldline_id}/guess/verify", response_model=CollectionGuessOut)
async def verify_collection_guess(
    worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> CollectionGuessOut:
    line = await db.get(CollectionWorldline, worldline_id)
    if line is None:
        raise HTTPException(status_code=404, detail="世界线不存在")
    challenge = await _get_challenge(db, line.challenge_id)
    if challenge.challenger_id != current.id or challenge.status != "active":
        raise HTTPException(status_code=409, detail="此挑战不能检定堪算")
    booklet = await _get_booklet(db, challenge.booklet_id)
    progress = await _get_progress(db, challenge, booklet)
    if progress.verified_round == len(progress.history or []):
        raise HTTPException(status_code=409, detail="请先提出新的堪算")
    await run_guess_verification(
        history=progress.history or [],
        comments=progress.comments or [],
        abilities=_abilities(booklet.defenders or []),
        cards=progress.cards or [],
        round_no=len(progress.history or []),
        trace_context={"kind": "collection", "trace_id": str(line.id)},
    )
    progress.verified_round = len(progress.history or [])
    if all(card.get("cracked") for card in (progress.cards or [])) and progress.cracked_at is None:
        progress.cracked_at, progress.first_cracked_atoms = _now(), progress.atom_count
        await _finish_if_double(db, challenge, progress)
    await db.commit()
    return _guess_out(progress, _abilities(booklet.defenders or []))


@router.post("/challenges/{challenge_id}/persist", response_model=list[int])
async def persist_challenge_lineup(
    challenge_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> list[int]:
    challenge = await _get_challenge(db, challenge_id)
    if challenge.challenger_id != current.id:
        raise HTTPException(status_code=403, detail="只能持久化自己的点将阵容")
    existing = (await db.execute(select(func.count()).select_from(Loadout).where(Loadout.user_id == current.id))).scalar_one()
    if existing + len(challenge.challengers or []) > loadout_capacity(current.exp):
        raise HTTPException(status_code=400, detail="见闻不足，未能解锁更多奇人槽位")
    ids = []
    for member in challenge.challengers or []:
        loadout = Loadout(user_id=current.id, name=member.get("name", ""), style=member.get("style", ""), tactic=member.get("tactic", ""), enabled=False)
        db.add(loadout)
        await db.flush()
        ids.append(loadout.id)
        for ability_data in member.get("abilities") or []:
            ability_id = sha256(f"{current.id}:{ability_data['name']}:{ability_data['effect']}".encode()).hexdigest()[:16]
            ability = await db.get(Ability, ability_id)
            if ability is None:
                ability = Ability(id=ability_id, name=ability_data["name"], effect=ability_data["effect"], detail=ability_data.get("detail", ""), understanding=ability_data.get("understanding", ""))
                db.add(ability)
            if await db.get(UserAbility, (current.id, ability_id)) is None:
                db.add(UserAbility(user_id=current.id, ability_id=ability_id))
            db.add(LoadoutAbility(loadout_id=loadout.id, ability_id=ability_id))
    await db.commit()
    return ids
