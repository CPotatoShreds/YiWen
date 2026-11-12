"""小天下集卷、公开刻印与单次挑战 API。"""
import asyncio
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import settings
from app.core.ratelimit import limiter
from app.core.security import get_current_admin, get_current_user
from app.core.tasks import dispatch
from app.db.base import async_session_factory, get_db
from app.models.ability import Ability
from app.models.character import Character, CharacterAbility
from app.models.scenario_domain import (
    RosterState,
    Scenario,
    ScenarioChallengeRun,
    ScenarioRoster,
    ScenarioRosterAbility,
    ScenarioRosterProgress,
    ScenarioRosterRevision,
    ScenarioRosterRevisionAbility,
    ScenarioState,
)
from app.models.user import User
from app.schemas.scenario_domain import (
    ChallengeIn,
    ChallengeOut,
    RosterIn,
    RosterOut,
    ScenarioChallengeHistoryOut,
    ScenarioIn,
    ScenarioOut,
    ScenarioRosterDetailOut,
    ScenarioRosterProgressOut,
)
from app.services.scenario.flows import now as _now
from app.services.scenario.normalization import normalize_title, slugify_title
from app.services.scenario.stream import get_scenario_stream
from app.services.scenario.views import (
    guess_cards as _guess_cards,
    public_cards as _public_cards,
    public_guess_rounds as _public_guess_rounds,
    sees_all as _sees_all,
    visible_turn as _visible_turn,
)

creator_router = APIRouter(prefix="/creator/scenarios", tags=["creator-scenario-rosters"])
creator_roster_router = APIRouter(prefix="/creator/scenario-rosters", tags=["creator-scenario-rosters"])
admin_router = APIRouter(prefix="/admin/scenarios", tags=["admin-scenarios"])
public_router = APIRouter(prefix="/scenarios", tags=["scenarios"])
public_roster_router = APIRouter(prefix="/scenario-rosters", tags=["scenario-rosters"])
challenge_router = APIRouter(tags=["scenario-challenges"])


async def _scenario_by_ref(db: AsyncSession, scenario_ref: str) -> Scenario | None:
    try:
        scenario_id = UUID(scenario_ref)
    except ValueError:
        scenario = await db.scalar(select(Scenario).where(Scenario.slug == scenario_ref))
        if scenario is not None:
            return scenario
        normalized_slug = slugify_title(scenario_ref)
        return await db.scalar(select(Scenario).where(Scenario.slug == normalized_slug))
    return await db.get(Scenario, scenario_id)


async def _unique_scenario_slug(db: AsyncSession, name: str, scenario_id: UUID) -> str:
    base = slugify_title(name) or f"scenario-{scenario_id.hex[:8]}"
    if await db.scalar(select(Scenario.id).where(Scenario.slug == base, Scenario.id != scenario_id)) is None:
        return base
    return f"{base[:71].rstrip('-')}-{scenario_id.hex[:8]}"


async def _lock_or_create_progress(db: AsyncSession, roster_id: UUID, challenger_id: int) -> ScenarioRosterProgress:
    """取进度行并加 FOR UPDATE 行锁：并发创建挑战时保证 attempts 只被顺序递增一次。

    首战的行还不存在，`FOR UPDATE` 锁不到任何东西，所以先经 SAVEPOINT 插入：两个并发请求
    都看不到行时都会尝试 INSERT，后到者撞 (roster_id, challenger_id) 主键，SAVEPOINT 让这次
    失败不牵连外层事务里已加载的 roster；随后阻塞在重锁上，读到先到者提交的行。
    """
    key = (ScenarioRosterProgress.roster_id == roster_id, ScenarioRosterProgress.challenger_id == challenger_id)
    progress = await db.scalar(select(ScenarioRosterProgress).where(*key).with_for_update())
    if progress is not None:
        return progress
    try:
        async with db.begin_nested():
            progress = ScenarioRosterProgress(roster_id=roster_id, challenger_id=challenger_id)
            db.add(progress)
            await db.flush()
    except IntegrityError:
        progress = await db.scalar(select(ScenarioRosterProgress).where(*key).with_for_update())
        if progress is None:
            raise HTTPException(409, "挑战创建冲突，请重试") from None
    return progress


async def _character_snapshot(db: AsyncSession, character_id: UUID, owner_id: int) -> tuple[str, str, list[dict]]:
    character = await db.get(Character, character_id)
    if character is None or character.owner_id != owner_id:
        raise HTTPException(404, "奇人不存在")
    links = list((await db.scalars(select(CharacterAbility).where(CharacterAbility.character_id == character.id).order_by(CharacterAbility.position))).all())
    if not 1 <= len(links) <= 4:
        raise HTTPException(400, "奇人必须装配 1-4 门奇术")
    abilities = []
    for link in links:
        ability = await db.get(Ability, link.ability_id)
        if ability is None or ability.owner_id != owner_id or not ability.name.strip() or not ability.effect.strip():
            raise HTTPException(400, "奇人装配的奇术内容不完整")
        abilities.append({"name": ability.name, "effect": ability.effect, "detail": ability.detail or ""})
    return character.name, character.bio or "", abilities


def _scenario_snapshot(scenario: Scenario) -> dict:
    return {
        "id": str(scenario.id),
        "slug": scenario.slug,
        "name": scenario.name,
        "subtitle": scenario.subtitle,
        "introduction": scenario.introduction,
        "background": scenario.background,
        "rules": list(scenario.rules or []),
        "victory_condition": scenario.victory_condition,
        "judgement_rules": list(scenario.judgement_rules or []),
    }


async def _roster_out(db: AsyncSession, roster: ScenarioRoster) -> RosterOut:
    owner = await db.get(User, roster.owner_id)
    revision = await db.get(ScenarioRosterRevision, roster.current_revision_id) if roster.current_revision_id else None
    if revision:
        ability_count = await db.scalar(select(func.count()).select_from(ScenarioRosterRevisionAbility).where(ScenarioRosterRevisionAbility.revision_id == revision.id)) or 0
    else:
        ability_count = await db.scalar(select(func.count()).select_from(ScenarioRosterAbility).where(ScenarioRosterAbility.roster_id == roster.id)) or 0
    character_name = revision.character_name if revision else roster.character_name
    character_bio = revision.character_bio if revision else roster.character_bio
    guidance = revision.guidance if revision else roster.guidance
    public_runs = ScenarioChallengeRun.roster_id == roster.id, ScenarioChallengeRun.is_trial.is_(False)
    wins = await db.scalar(select(func.count()).select_from(ScenarioChallengeRun).where(*public_runs, ScenarioChallengeRun.won.is_(True))) or 0
    done = await db.scalar(select(func.count()).select_from(ScenarioChallengeRun).where(*public_runs, ScenarioChallengeRun.won.is_not(None))) or 0
    return RosterOut(
        id=roster.id,
        scenario_id=roster.scenario_id,
        owner_id=roster.owner_id,
        owner_name=owner.username if owner else "已离席",
        name=roster.name,
        character_name=character_name,
        character_bio=character_bio,
        guidance=guidance,
        ability_count=ability_count,
        challenge_count=roster.challenge_count,
        challenger_win_rate=(wins / done if done else None),
        first_victory_avg_challenges=roster.first_victory_avg_challenges,
        state=roster.state,
        published_at=roster.published_at,
    )


async def _make_roster_revision(db: AsyncSession, roster: ScenarioRoster, abilities: list[dict], state: str) -> ScenarioRosterRevision:
    number = (await db.scalar(select(func.max(ScenarioRosterRevision.revision_number)).where(ScenarioRosterRevision.roster_id == roster.id)) or 0) + 1
    revision = ScenarioRosterRevision(
        roster_id=roster.id,
        revision_number=number,
        state=state,
        character_name=roster.character_name,
        character_bio=roster.character_bio,
        guidance=roster.guidance,
    )
    db.add(revision)
    await db.flush()
    db.add_all([ScenarioRosterRevisionAbility(revision_id=revision.id, position=i + 1, **ability) for i, ability in enumerate(abilities)])
    roster.current_revision_id = revision.id if state == RosterState.PUBLISHED else roster.current_revision_id
    return revision


async def _roster_abilities(db: AsyncSession, roster: ScenarioRoster) -> list:
    if roster.current_revision_id:
        return list((await db.execute(select(ScenarioRosterRevisionAbility).where(ScenarioRosterRevisionAbility.revision_id == roster.current_revision_id).order_by(ScenarioRosterRevisionAbility.position))).scalars())
    return list((await db.execute(select(ScenarioRosterAbility).where(ScenarioRosterAbility.roster_id == roster.id).order_by(ScenarioRosterAbility.position))).scalars())


async def _challenge_history_out(db: AsyncSession, challenge: ScenarioChallengeRun) -> ScenarioChallengeHistoryOut:
    snapshot = challenge.challenger_snapshot or {}
    strategy = next((item.get("text", "") for item in challenge.messages or [] if isinstance(item, dict) and item.get("role") == "challenger"), "")
    return ScenarioChallengeHistoryOut(
        id=challenge.id,
        status=challenge.status,
        is_trial=challenge.is_trial,
        won=challenge.won,
        guess_attempts=challenge.guess_attempts,
        created_at=challenge.created_at,
        finished_at=challenge.finished_at,
        challenger_character_name=snapshot.get("character_name"),
        challenger_character_id=snapshot.get("character_id"),
        strategy=strategy,
    )


@admin_router.get("", response_model=list[ScenarioOut])
async def admin_list_scenarios(_: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)], state: str | None = Query(None, alias="status")):
    query = select(Scenario).order_by(Scenario.created_at.desc())
    if state:
        query = query.where(Scenario.status == state)
    return list((await db.execute(query)).scalars())


@admin_router.post("", response_model=ScenarioOut, status_code=201)
async def admin_create_scenario(body: ScenarioIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario_id = uuid4()
    scenario = Scenario(
        id=scenario_id,
        created_by=admin.id,
        name=body.name.strip(),
        slug=await _unique_scenario_slug(db, body.name, scenario_id),
        normalized_name=normalize_title(body.name),
        subtitle=body.subtitle.strip(),
        introduction=body.introduction.strip(),
        background=body.background.strip(),
        rules=[rule.strip() for rule in body.rules],
        victory_condition=body.victory_condition.strip(),
        judgement_rules=[rule.strip() for rule in body.judgement_rules],
    )
    db.add(scenario)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "卷名字已存在")
    await audit(db, admin.id, "scenario.create", target_type="scenario", target_id=scenario.id, detail={"name": scenario.name})
    await db.commit()
    await db.refresh(scenario)
    return scenario


@admin_router.get("/{scenario_id}", response_model=ScenarioOut)
async def admin_get_scenario(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "卷不存在")
    return scenario


@admin_router.put("/{scenario_id}", response_model=ScenarioOut)
async def admin_update_scenario(scenario_id: UUID, body: ScenarioIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "卷不存在")
    if scenario.status != ScenarioState.DRAFT:
        raise HTTPException(409, "已发布卷不可编辑")
    scenario.name = body.name.strip()
    scenario.slug = await _unique_scenario_slug(db, body.name, scenario.id)
    scenario.normalized_name = normalize_title(body.name)
    scenario.subtitle = body.subtitle.strip()
    scenario.introduction = body.introduction.strip()
    scenario.background = body.background.strip()
    scenario.rules = [rule.strip() for rule in body.rules]
    scenario.victory_condition = body.victory_condition.strip()
    scenario.judgement_rules = [rule.strip() for rule in body.judgement_rules]
    await audit(db, admin.id, "scenario.update", target_type="scenario", target_id=scenario.id, detail={"name": scenario.name})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "卷名字已存在")
    await db.refresh(scenario)
    return scenario


@admin_router.post("/{scenario_id}/publish", response_model=ScenarioOut)
async def admin_publish_scenario(scenario_id: UUID, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "卷不存在")
    scenario.status, scenario.published_at = ScenarioState.PUBLISHED, _now()
    await audit(db, admin.id, "scenario.publish", target_type="scenario", target_id=scenario.id, detail={"name": scenario.name})
    await db.commit()
    await db.refresh(scenario)
    return scenario


@admin_router.post("/{scenario_id}/delete", response_model=ScenarioOut)
async def admin_delete_scenario(scenario_id: UUID, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "卷不存在")
    scenario.status, scenario.deleted_at = ScenarioState.DELETED, _now()
    await audit(db, admin.id, "scenario.delete", target_type="scenario", target_id=scenario.id, detail={"name": scenario.name})
    await db.commit()
    await db.refresh(scenario)
    return scenario


@admin_router.get("/{scenario_id}/rosters", response_model=list[RosterOut])
async def admin_rosters(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario_id).order_by(ScenarioRoster.created_at))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


@creator_router.get("/{scenario_id}/rosters", response_model=list[RosterOut])
async def creator_rosters(scenario_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario_id, ScenarioRoster.owner_id == current.id, ScenarioRoster.deleted_at.is_(None)))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


@creator_router.post("/{scenario_id}/rosters", response_model=RosterOut, status_code=201)
async def creator_create_roster(scenario_id: UUID, body: RosterIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None:
        raise HTTPException(404, "小天下集卷不存在")
    name, bio, abilities = await _character_snapshot(db, body.character_id, current.id)
    roster = ScenarioRoster(
        scenario_id=scenario_id,
        owner_id=current.id,
        character_id=body.character_id,
        name=name,
        character_name=name,
        character_bio=bio,
        guidance=body.guidance,
        state=RosterState.PUBLISHED,
        published_at=_now(),
    )
    db.add(roster)
    await db.flush()
    db.add_all([ScenarioRosterAbility(roster_id=roster.id, position=i + 1, **ability) for i, ability in enumerate(abilities)])
    await db.flush()
    await _make_roster_revision(db, roster, abilities, RosterState.PUBLISHED)
    await db.commit()
    await db.refresh(roster)
    return await _roster_out(db, roster)


@creator_router.get("/rosters/{roster_id}", response_model=RosterOut)
async def creator_get_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.owner_id != current.id:
        raise HTTPException(404, "刻印不存在")
    return await _roster_out(db, roster)


@creator_roster_router.get("/{roster_id}", response_model=RosterOut)
async def creator_get_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_get_roster(roster_id, current, db)


@creator_router.post("/rosters/{roster_id}/copy", response_model=RosterOut, status_code=201)
async def creator_copy_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    source = await db.get(ScenarioRoster, roster_id)
    if source is None or source.owner_id != current.id:
        raise HTTPException(404, "刻印不存在")
    roster = ScenarioRoster(
        scenario_id=source.scenario_id,
        owner_id=current.id,
        character_id=source.character_id,
        name=f"{source.name} 副本",
        character_name=source.character_name,
        character_bio=source.character_bio,
        guidance=source.guidance,
        state=RosterState.PUBLISHED,
        published_at=_now(),
    )
    db.add(roster)
    await db.flush()
    abilities = (await db.execute(select(ScenarioRosterAbility).where(ScenarioRosterAbility.roster_id == source.id).order_by(ScenarioRosterAbility.position))).scalars().all()
    snapshots = [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in abilities]
    db.add_all([ScenarioRosterAbility(roster_id=roster.id, position=a.position, name=a.name, effect=a.effect, detail=a.detail) for a in abilities])
    await db.flush()
    await _make_roster_revision(db, roster, snapshots, RosterState.PUBLISHED)
    await db.commit()
    await db.refresh(roster)
    return await _roster_out(db, roster)


@creator_router.post("/rosters/{roster_id}/delete", status_code=204)
async def creator_delete_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.owner_id != current.id:
        raise HTTPException(404, "刻印不存在")
    roster.state, roster.deleted_at = RosterState.DELETED, _now()
    await db.commit()


@creator_roster_router.post("/{roster_id}/copy", response_model=RosterOut, status_code=201)
async def creator_copy_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_copy_roster(roster_id, current, db)


@creator_roster_router.post("/{roster_id}/delete", status_code=204)
async def creator_delete_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_delete_roster(roster_id, current, db)


@public_router.get("", response_model=list[ScenarioOut])
async def public_scenarios(db: Annotated[AsyncSession, Depends(get_db)]):
    return list((await db.execute(select(Scenario).where(Scenario.status == ScenarioState.PUBLISHED, Scenario.deleted_at.is_(None)).order_by(Scenario.published_at.desc()))).scalars())


@public_router.get("/{scenario_ref}/rosters/{roster_id}", response_model=ScenarioRosterDetailOut)
async def public_roster_detail(
    scenario_ref: str,
    roster_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    scenario = await _scenario_by_ref(db, scenario_ref)
    roster = await db.get(ScenarioRoster, roster_id)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None:
        raise HTTPException(404, "小天下集卷不存在")
    if roster is None or roster.scenario_id != scenario.id or roster.state != RosterState.PUBLISHED or roster.deleted_at is not None:
        raise HTTPException(404, "刻印不存在")

    progress = await db.get(ScenarioRosterProgress, {"roster_id": roster.id, "challenger_id": current.id})
    my_query = select(ScenarioChallengeRun).where(ScenarioChallengeRun.roster_id == roster.id, ScenarioChallengeRun.challenger_id == current.id).order_by(desc(ScenarioChallengeRun.created_at), desc(ScenarioChallengeRun.id)).limit(100)
    my_rows = list((await db.execute(my_query)).scalars())
    my_history = [await _challenge_history_out(db, row) for row in my_rows]

    owner_view = roster.owner_id == current.id
    progress_out = None
    if owner_view:
        # 作者看自己的刻印：这套奇术是他自己写的，卡面恒为已知。这里不写 progress，
        # 免得"自看"把别人的看破进度或统计口径搅在一起。
        ability_dicts = [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in await _roster_abilities(db, roster)]
        progress_out = ScenarioRosterProgressOut(
            roster_id=roster.id,
            challenger_id=current.id,
            attempts=progress.attempts if progress else 0,
            first_victory_challenges=progress.first_victory_challenges if progress else None,
            cracked_cards=_public_cards(_guess_cards(progress, ability_dicts, owner_view=True)),
            guess_count=len(progress.guess_history or []) if progress else 0,
            guess_credits=progress.guess_credits if progress else 0,
            guess_rounds=_public_guess_rounds(progress.guess_rounds if progress else []),
            updated_at=progress.updated_at if progress else None,
        )
    elif progress is not None:
        progress_out = ScenarioRosterProgressOut(
            roster_id=progress.roster_id,
            challenger_id=progress.challenger_id,
            attempts=progress.attempts,
            first_victory_challenges=progress.first_victory_challenges,
            cracked_cards=_public_cards(progress.cracked_cards),
            guess_count=len(progress.guess_history or []),
            guess_credits=progress.guess_credits,
            guess_rounds=_public_guess_rounds(progress.guess_rounds),
            updated_at=progress.updated_at,
        )
    return ScenarioRosterDetailOut(
        scenario=ScenarioOut.model_validate(scenario),
        roster=await _roster_out(db, roster),
        viewer_role="owner" if owner_view else "challenger",
        my_progress=progress_out,
        my_challenges=my_history,
    )


@public_router.get("/{scenario_ref}", response_model=ScenarioOut)
async def public_scenario(scenario_ref: str, db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await _scenario_by_ref(db, scenario_ref)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None:
        raise HTTPException(404, "小天下集卷不存在")
    return scenario


@public_router.get("/{scenario_ref}/rosters", response_model=list[RosterOut])
async def public_rosters(scenario_ref: str, db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await _scenario_by_ref(db, scenario_ref)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None:
        raise HTTPException(404, "小天下集卷不存在")
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario.id, ScenarioRoster.state == RosterState.PUBLISHED, ScenarioRoster.deleted_at.is_(None)).order_by(ScenarioRoster.created_at))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


@public_router.get("/rosters/{roster_id}", response_model=RosterOut)
async def public_roster(roster_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.state != RosterState.PUBLISHED or roster.deleted_at is not None:
        raise HTTPException(404, "刻印不存在")
    return await _roster_out(db, roster)


@public_roster_router.get("/{roster_id}", response_model=RosterOut)
async def public_roster_alias(roster_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    return await public_roster(roster_id, db)


@challenge_router.post("/scenario-rosters/{roster_id}/challenges", response_model=ChallengeOut, status_code=201)
@limiter.limit(settings.RATELIMIT_CHALLENGE)
async def create_challenge(roster_id: UUID, request: Request, body: ChallengeIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    scenario = await db.get(Scenario, roster.scenario_id) if roster else None
    if roster is None or scenario is None or roster.state != RosterState.PUBLISHED:
        raise HTTPException(404, "刻印不存在")
    # 试炼局：发起人就是刻印作者。该标记**只管统计口径**（不计次数、胜负与猜词次数），
    # 不参与任何可见性判断——视角一律由下面读取时的关系推导（见 services/scenario/views.py）。
    is_trial = roster.owner_id == current.id
    challenger_name, challenger_bio, challenger_abilities = await _character_snapshot(db, body.character_id, current.id)
    # 进度行加锁：并发下两个请求顺序读到递增后的 attempts，不会拿同一个序号，
    # 配合 uq_scenario_challenge_runs_number 兜住漏网的撞号。
    progress = await _lock_or_create_progress(db, roster.id, current.id)
    if not is_trial:
        progress.attempts += 1
    roster_abilities = await _roster_abilities(db, roster)
    challenge = ScenarioChallengeRun(
        roster_id=roster.id,
        challenger_id=current.id,
        is_trial=is_trial,
        status="preparing",
        # 内部序号（不下发）：正式局 = 递增后的 attempts，试炼局恒 1（partial index 已排除）
        challenge_number=progress.attempts if not is_trial else 1,
        scenario_snapshot=_scenario_snapshot(scenario),
        roster_snapshot={
            "character_name": roster.character_name,
            "character_bio": roster.character_bio,
            "guidance": roster.guidance,
            "abilities": [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in roster_abilities],
        },
        challenger_snapshot={
            "character_id": str(body.character_id),
            "character_name": challenger_name,
            "character_bio": challenger_bio,
            "abilities": challenger_abilities,
        },
    )
    db.add(challenge)
    if not is_trial:
        roster.challenge_count += 1
    await db.commit()
    await db.refresh(challenge)
    await dispatch("scenario_prepare", challenge.id)
    return ChallengeOut(id=challenge.id, roster_id=roster.id, scenario_id=scenario.id, status=challenge.status, is_trial=challenge.is_trial, created_at=challenge.created_at)


@challenge_router.get("/scenario-challenges/{challenge_id}")
async def challenge_detail(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None:
        raise HTTPException(404, "挑战不存在")
    roster = await db.get(ScenarioRoster, challenge.roster_id)
    if challenge.challenger_id == current.id:
        progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
        abilities = list(challenge.roster_snapshot.get("abilities", []))
        # 两条互相独立的判据：知识状态（作者恒已知 / 否则看全破进度）与侧别（这一局你是谁）。
        # 二者都由关系现算，不看 is_trial——那个标记只管这一局算不算统计。
        owner_view = roster is not None and roster.owner_id == current.id
        side = "both" if owner_view else "challenger"
        cards = _guess_cards(progress, abilities, owner_view=owner_view)
        unlocked = _sees_all(progress, abilities, owner_view=owner_view)
        messages = [_visible_turn(message, side=side, unlocked=unlocked) for message in (challenge.messages or [])]
        return {
            "id": challenge.id,
            "roster_id": challenge.roster_id,
            "scenario_id": challenge.scenario_snapshot.get("id"),
            "status": challenge.status,
            "is_trial": challenge.is_trial,
            "created_at": challenge.created_at,
            # 挑战者恰好就是刻印作者（试炼局）：两边都是己方，推演与双方正文全部下发。
            "viewer_role": side,
            "scenario": challenge.scenario_snapshot,
            "roster": challenge.roster_snapshot,
            "challenger": challenge.challenger_snapshot,
            "messages": messages,
            "god_unlocked": unlocked,  # API 契约字段名保持英文稳定；仅函数/术语换新
            "guess_attempts": challenge.guess_attempts,
            "guesses": _public_guess_rounds(challenge.guesses),
            "guess_rounds": _public_guess_rounds(progress.guess_rounds if progress else []),
            "guess_cards": _public_cards(cards),
            "guess_credits": progress.guess_credits if progress else 0,
            "guess_in_flight": challenge.guess_in_flight,
            "verify_in_flight": challenge.verify_in_flight,
            "won": challenge.won,
            "derived": challenge.derived,
        }
    if roster is None or roster.owner_id != current.id:
        raise HTTPException(404, "挑战不存在")
    # 刻印作者看**别人的**对局：只有刻印正文。挑战者正文、猜词原文和私有资产快照均不出站。
    # 作者的自家试炼不会走到这里——那时 challenger_id 就是他本人，上面那条分支已返回。
    guardian_messages = []
    for message in challenge.messages or []:
        if message.get("role") == "views" and message.get("guardian_text"):
            guardian_messages.append({"role": "guardian", "text": message["guardian_text"], "created_at": message.get("created_at")})
    challenger = await db.get(User, challenge.challenger_id)
    return {
        "id": challenge.id,
        "roster_id": challenge.roster_id,
        "scenario_id": challenge.scenario_snapshot.get("id"),
        "status": challenge.status,
        "is_trial": challenge.is_trial,
        "created_at": challenge.created_at,
        "viewer_role": "owner",
        "scenario": challenge.scenario_snapshot,
        "roster": challenge.roster_snapshot,
        "challenger": {
            "character_name": challenge.challenger_snapshot.get("character_name", "挑战者"),
            "username": challenger.username if challenger else "已离席",
        },
        "guess_attempts": 0,
        "messages": guardian_messages,
        "guesses": [],
        "won": challenge.won,
        "derived": {
            "achieved": (challenge.derived or {}).get("achieved"),
            "reason": (challenge.derived or {}).get("reason", ""),
        },
    }


@challenge_router.get("/scenario-challenges/{challenge_id}/stream")
async def challenge_stream(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)]) -> StreamingResponse:
    """小天下集推演实时流：推演正文（仅对该局已解锁者）与己方叙述逐字转写（阶段进度由前端轮询驱动）。"""
    async with async_session_factory() as db:
        challenge = await db.get(ScenarioChallengeRun, challenge_id)
        roster = await db.get(ScenarioRoster, challenge.roster_id) if challenge else None
        if challenge is None or (challenge.challenger_id != current.id and (roster is None or roster.owner_id != current.id)):
            raise HTTPException(404, "挑战不存在")
        status = challenge.status
        if challenge.challenger_id == current.id:
            # 侧别由关系推导：挑战者本人就是刻印作者 → both，一条连接同时收两侧叙述
            side = "both" if roster is not None and roster.owner_id == current.id else "challenger"
        else:
            side = "guardian"

    def encode(event: dict) -> str:
        return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def events():
        if status == "failed":
            yield encode({"type": "error", "message": "挑战准备失败，请重新开始。"})
            return
        if status in {"won", "lost"}:
            yield encode({"type": "done", "status": status})
            return
        stream = get_scenario_stream(challenge_id)
        queue, snapshot = await stream.subscribe(side=side)
        try:
            for event in snapshot:
                yield encode(event)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield encode(event)
        finally:
            stream.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@challenge_router.post("/scenario-challenges/{challenge_id}/actions", status_code=202)
async def challenge_action(challenge_id: UUID, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "挑战不存在")
    if challenge.won is True:
        raise HTTPException(409, "挑战已经结束")
    if challenge.status != "active":
        raise HTTPException(409, "奇术比对尚未完成或挑战已结束")
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "行动不能为空")
    challenge.messages = [*challenge.messages, {"role": "challenger", "text": text, "created_at": _now().isoformat()}]
    challenge.status = "resolving"
    await db.commit()
    await dispatch("scenario_deduction", challenge.id)
    return {"challenge_id": challenge.id, "status": challenge.status, "text": text}


@challenge_router.post("/scenario-challenges/{challenge_id}/guess", status_code=202)
async def challenge_guess(challenge_id: UUID, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "挑战不存在")
    if challenge.status == "failed":
        raise HTTPException(409, "挑战已失败，请重新开始")
    if challenge.guess_in_flight:
        raise HTTPException(409, "上一轮猜测仍在判定中")
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "猜词不能为空")
    progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
    if progress is None or progress.guess_credits <= 0:
        raise HTTPException(400, "当前没有可用的提问次数")
    progress.guess_credits -= 1
    challenge.guess_attempts += 1
    round_id = str(uuid4())
    record = {
        "id": round_id,
        "challenge_id": str(challenge.id),
        "text": text,
        "attempt": challenge.guess_attempts,
        "status": "splitting",
        "atoms": [],
        "matches": [],
        "comments": [],
        "created_at": _now().isoformat(),
    }
    challenge.guesses = [*challenge.guesses, record]
    progress.guess_history = [*(progress.guess_history or []), text]
    progress.guess_rounds = [*(progress.guess_rounds or []), record]
    challenge.guess_in_flight = True
    await db.commit()
    await dispatch("guess_round", challenge.id, round_id, text)
    return {"status": "accepted", "round_id": round_id, "guess_attempts": challenge.guess_attempts, "guess_credits": progress.guess_credits}


@challenge_router.post("/scenario-challenges/{challenge_id}/guess/verify", status_code=202)
async def challenge_verify(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "挑战不存在")
    if challenge.status == "failed":
        raise HTTPException(409, "挑战已失败，请重新开始")
    if challenge.guess_in_flight:
        raise HTTPException(409, "上一轮猜测仍在判定中")
    if challenge.verify_in_flight:
        raise HTTPException(409, "检定仍在进行中")
    progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
    if progress is None or not progress.guess_rounds:
        raise HTTPException(400, "请先道出猜测")
    challenge.verify_in_flight = True
    await db.commit()
    await dispatch("guess_verify", challenge.id)
    return {"status": "accepted", "verify_in_flight": True, "guess_credits": progress.guess_credits}


@challenge_router.post("/scenario-challenges/{challenge_id}/derive", status_code=202)
async def challenge_derive(challenge_id: UUID, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "挑战不存在")
    if challenge.status != "active" or challenge.won is not None:
        raise HTTPException(409, "挑战已经开始或已经结束")
    strategy = str(payload.get("strategy", "")).strip()
    challenge.messages = [{"role": "challenger", "text": strategy, "skipped": not bool(strategy), "created_at": _now().isoformat()}]
    challenge.status = "resolving"
    await db.commit()
    await dispatch("scenario_deduction", challenge.id)
    return {"status": challenge.status, "challenge_id": challenge.id}


__all__ = ["admin_router", "challenge_router", "creator_roster_router", "creator_router", "public_roster_router", "public_router"]
