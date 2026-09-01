"""小天下集情景模板、公开阵容与单次挑战 API。"""
import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, get_current_user
from app.db.base import async_session_factory, get_db
from app.models.creator_asset import (
    AbilityRevisionContent,
    CharacterRevisionAbility,
    CharacterRevisionContent,
    CreatorAsset,
    CreatorAssetRevision,
)
from app.models.scenario_domain import (
    RosterKind,
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
    ScenarioOwnerChallengeOut,
    ScenarioRosterDetailOut,
    ScenarioRosterProgressOut,
)
from app.services.creator.normalization import normalize_title
from app.services.guess.pipeline import run_guess_commentary, run_guess_verification
from app.services.llm.reliability import ainvoke_with_reliability, astream_with_reliability
from app.services.nodes.ability.pair_judge import build_pair_judge_chain, render_pair_report
from app.services.nodes.collection import (
    JUDGE_TEMPLATE,
    build_collection_challenger_view_stream_llm,
    build_collection_god_llm,
    build_collection_guardian_view_stream_llm,
    build_collection_judge_llm,
    parse_collection_god_reply,
)
from app.services.scenario.stream import get_scenario_stream

creator_router = APIRouter(prefix="/creator/scenarios", tags=["creator-scenario-rosters"])
creator_roster_router = APIRouter(prefix="/creator/scenario-rosters", tags=["creator-scenario-rosters"])
admin_router = APIRouter(prefix="/admin/scenarios", tags=["admin-scenarios"])
admin_roster_router = APIRouter(prefix="/admin/scenario-rosters", tags=["admin-scenario-rosters"])
public_router = APIRouter(prefix="/scenarios", tags=["scenarios"])
public_roster_router = APIRouter(prefix="/scenario-rosters", tags=["scenario-rosters"])
challenge_router = APIRouter(tags=["scenario-challenges"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _render_scenario_ability(ability: dict) -> str:
    lines = [f"- {ability.get('name', '')}：{ability.get('effect', '')}"]
    if ability.get("detail"):
        lines.append(f"  详细解释：{ability['detail']}")
    return "\n".join(lines)


async def _compare_scenario_abilities(challenger: list[dict], guardian: list[dict], challenge_id: UUID) -> str:
    """以与常规对战相同的奇术比对节点准备情景挑战上下文。"""
    pairs = [(left, right) for left in challenger for right in guardian]
    if not pairs:
        return ""
    judge = build_pair_judge_chain()
    semaphore = asyncio.Semaphore(4)

    async def compare(left: dict, right: dict):
        try:
            async with semaphore:
                return await ainvoke_with_reliability(
                    judge,
                    {"ability_a": _render_scenario_ability(left), "ability_b": _render_scenario_ability(right)},
                    operation="scenario_ability_pair",
                    trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
                )
        except Exception:  # noqa: BLE001 - 比对不可用时仍可进入情景推演
            return None

    verdicts = [item for item in await asyncio.gather(*(compare(left, right) for left, right in pairs)) if item is not None]
    return render_pair_report(verdicts)


def _scenario_history(messages: list[dict]) -> str:
    records = [item.get("omniscient") or item.get("text", "") for item in messages[-12:]]
    return "\n".join(record for record in records if record)


async def _prepare_scenario_challenge(challenge_id: UUID) -> None:
    """创建挑战后自动完成奇术比对；期间不占用请求数据库连接。"""
    stream = get_scenario_stream(challenge_id)
    try:
        await stream.publish({"type": "stage", "stage": "compare"})
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "preparing":
                return
            challenger_abilities = list(challenge.challenger_snapshot.get("abilities", []))
            guardian_abilities = list(challenge.roster_snapshot.get("abilities", []))
        report = await _compare_scenario_abilities(challenger_abilities, guardian_abilities, challenge_id)
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "preparing":
                return
            challenge.derived = {**(challenge.derived or {}), "comparison_report": report}
            challenge.status = "active"
            await db.commit()
        await stream.publish({"type": "stage", "stage": "ready"})
    except Exception:  # noqa: BLE001 - 后台失败需要向挑战者明确交代
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is not None and challenge.status == "preparing":
                challenge.status = "failed"
                await db.commit()
        await stream.publish({"type": "error", "status": "failed", "message": "奇术比对未能完成，请重新开始挑战。"})


async def _stream_scenario_view(*, stream, side: str, chain, kwargs: dict, challenge_id: UUID) -> str:
    parts: list[str] = []
    async for chunk in astream_with_reliability(
        chain,
        kwargs,
        operation=f"scenario_{side}_view",
        max_retries=1,
        trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
    ):
        text = str(chunk)
        parts.append(text)
        await stream.publish({"type": "view_chunk", "side": side, "text": text}, replay=False)
    return "".join(parts).strip()


async def _resolve_scenario_action(challenge_id: UUID) -> None:
    """后台处理一条玩家行动：上帝裁定完成后，并发流式转写双方视角。"""
    stream = get_scenario_stream(challenge_id)
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "resolving":
                return
            scenario = dict(challenge.scenario_snapshot)
            roster = dict(challenge.roster_snapshot)
            challenger = dict(challenge.challenger_snapshot)
            messages = list(challenge.messages)
            comparison_report = str((challenge.derived or {}).get("comparison_report", ""))
            action = str(messages[-1].get("text", ""))

        await stream.publish({"type": "stage", "stage": "thinking"})
        history = _scenario_history(messages)
        if comparison_report:
            history = f"{history}\n\n{comparison_report}".strip()
        action_fact = f"挑战者奇人“{challenger.get('character_name', '挑战者奇人')}”执行行动意图：\n“{action}”"
        god_parts: list[str] = []
        async for chunk in astream_with_reliability(
            build_collection_god_llm(),
            {
                "volume": scenario.get("name", "小天下集情景"),
                "requirements": scenario.get("summary", ""),
                "victory_condition": scenario.get("victory_condition", ""),
                "tianji": "（当前情景未配置额外天机）",
                "opening": scenario.get("background", ""),
                "brief": roster.get("guidance", ""),
                "defenders": [roster],
                "challengers": [challenger],
                "history": history or "（开场尚未行动）",
                "action": action_fact,
                "remaining": "充足",
            },
            operation="scenario_god_reply",
            max_retries=1,
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
        ):
            god_parts.append(str(chunk))
        god = parse_collection_god_reply("".join(god_parts))
        await stream.publish({"type": "god", "text": god.omniscient_view, "state_summary": god.state_summary}, replay=False)
        await stream.publish({"type": "stage", "stage": "views"})

        previous_challenger = next((item.get("challenger_text", item.get("text", "")) for item in reversed(messages[:-1]) if item.get("challenger_text") or item.get("text")), "")
        previous_guardian = next((item.get("guardian_text", "") for item in reversed(messages) if item.get("guardian_text")), "")
        common = {
            "challenger_name": challenger.get("character_name", "挑战者奇人"),
            "guardian_name": roster.get("character_name", "守方奇人"),
            "opening": scenario.get("background", ""),
            "god": god.omniscient_view,
            "state_summary": god.state_summary,
        }
        challenger_view, guardian_view = await asyncio.gather(
            _stream_scenario_view(stream=stream, side="challenger", chain=build_collection_challenger_view_stream_llm(), kwargs={**common, "previous_view": previous_challenger or "（首轮，无上一轮视角记录）"}, challenge_id=challenge_id),
            _stream_scenario_view(stream=stream, side="guardian", chain=build_collection_guardian_view_stream_llm(), kwargs={**common, "previous_view": previous_guardian or "（首轮，无上一轮视角记录）"}, challenge_id=challenge_id),
        )

        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "resolving":
                return
            turn = {
                "role": "views",
                "challenger_text": challenger_view,
                "guardian_text": guardian_view,
                "omniscient": god.omniscient_view,
                "state_summary": god.state_summary,
                "created_at": _now().isoformat(),
            }
            challenge.messages = [*challenge.messages, turn]
            challenge.status = "active"
            await db.commit()
        await stream.publish({"type": "turn", "turn": turn}, replay=False)
        await stream.publish({"type": "stage", "stage": "ready"})
    except Exception:  # noqa: BLE001 - 流式节点失败后留下可恢复的挑战状态
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is not None and challenge.status == "resolving":
                challenge.status = "active"
                await db.commit()
        await stream.publish({"type": "error", "status": "active", "message": "本回合衍算未能完成，请稍后重试。"})


async def _character_snapshot(db: AsyncSession, asset_id: UUID, owner_id: int) -> tuple[str, str, list[dict]]:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.owner_id != owner_id or asset.kind != "character" or asset.deleted_at is not None:
        raise HTTPException(404, "私有奇人不存在")
    revision_id = await db.scalar(
        select(CreatorAssetRevision.id)
        .where(CreatorAssetRevision.asset_id == asset.id)
        .order_by(CreatorAssetRevision.revision_number.desc())
        .limit(1)
    )
    if revision_id is None:
        raise HTTPException(409, "奇人没有可用修订")
    content = await db.get(CharacterRevisionContent, revision_id)
    links = list((await db.execute(select(CharacterRevisionAbility).where(CharacterRevisionAbility.revision_id == revision_id).order_by(CharacterRevisionAbility.position))).scalars())
    if content is None or not 1 <= len(links) <= 4:
        raise HTTPException(400, "奇人必须装配 1-4 门奇术")
    abilities = []
    for link in links:
        ability = await db.get(AbilityRevisionContent, link.ability_revision_id)
        if ability is None or not ability.name.strip() or not ability.effect.strip():
            raise HTTPException(400, "奇人装配的奇术内容不完整")
        abilities.append({"name": ability.name, "effect": ability.effect, "detail": ability.detail or ""})
    return content.name, content.bio or content.style or "", abilities


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
    public_runs = ScenarioChallengeRun.roster_id == roster.id, ScenarioChallengeRun.is_preview.is_(False)
    wins = await db.scalar(select(func.count()).select_from(ScenarioChallengeRun).where(*public_runs, ScenarioChallengeRun.won.is_(True))) or 0
    done = await db.scalar(select(func.count()).select_from(ScenarioChallengeRun).where(*public_runs, ScenarioChallengeRun.won.is_not(None))) or 0
    return RosterOut(id=roster.id, scenario_id=roster.scenario_id, owner_id=roster.owner_id, owner_name=owner.username if owner else "已离席", kind=roster.kind, name=roster.name, character_name=character_name, character_bio=character_bio, guidance=guidance, ability_count=ability_count, challenge_count=roster.challenge_count, challenger_win_rate=(wins / done if done else None), first_victory_avg_challenges=roster.first_victory_avg_challenges, state=roster.state, published_at=roster.published_at)


async def _make_roster_revision(db: AsyncSession, roster: ScenarioRoster, abilities: list[dict], state: str) -> ScenarioRosterRevision:
    number = (await db.scalar(select(func.max(ScenarioRosterRevision.revision_number)).where(ScenarioRosterRevision.roster_id == roster.id)) or 0) + 1
    revision = ScenarioRosterRevision(roster_id=roster.id, revision_number=number, state=state, character_name=roster.character_name, character_bio=roster.character_bio, guidance=roster.guidance)
    db.add(revision)
    await db.flush()
    db.add_all([ScenarioRosterRevisionAbility(revision_id=revision.id, position=i + 1, **ability) for i, ability in enumerate(abilities)])
    roster.current_revision_id = revision.id if state == RosterState.PUBLISHED else roster.current_revision_id
    roster.work_revision_id = revision.id if state != RosterState.PUBLISHED else None
    return revision


async def _roster_abilities(db: AsyncSession, roster: ScenarioRoster) -> list:
    if roster.current_revision_id:
        return list((await db.execute(select(ScenarioRosterRevisionAbility).where(ScenarioRosterRevisionAbility.revision_id == roster.current_revision_id).order_by(ScenarioRosterRevisionAbility.position))).scalars())
    return list((await db.execute(select(ScenarioRosterAbility).where(ScenarioRosterAbility.roster_id == roster.id).order_by(ScenarioRosterAbility.position))).scalars())


def _encode_cursor(created_at: datetime, item_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime, UUID] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        created, item_id = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(created), UUID(item_id)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "无效的分页游标")


def _public_cards(cards: list[dict] | None) -> list[dict]:
    result = []
    for index, card in enumerate(cards or [], 1):
        cracked = bool(card.get("cracked"))
        item = {"index": card.get("index", index), "cracked": cracked}
        if cracked:
            item.update({"name": card.get("name", ""), "effect": card.get("effect", "")})
        result.append(item)
    return result


async def _challenge_history_out(db: AsyncSession, challenge: ScenarioChallengeRun) -> ScenarioChallengeHistoryOut:
    snapshot = challenge.challenger_snapshot or {}
    return ScenarioChallengeHistoryOut(
        id=challenge.id,
        status=challenge.status,
        challenge_number=challenge.challenge_number,
        is_preview=challenge.is_preview,
        won=challenge.won,
        guess_attempts=challenge.guess_attempts,
        created_at=challenge.created_at,
        finished_at=challenge.finished_at,
        challenger_character_name=snapshot.get("character_name"),
    )


@admin_router.get("", response_model=list[ScenarioOut])
async def admin_list_scenarios(_: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)], state: str | None = Query(None, alias="status")):
    query = select(Scenario).order_by(Scenario.created_at.desc())
    if state: query = query.where(Scenario.status == state)
    return list((await db.execute(query)).scalars())


@admin_router.post("", response_model=ScenarioOut, status_code=201)
async def admin_create_scenario(body: ScenarioIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = Scenario(created_by=admin.id, name=body.name.strip(), normalized_name=normalize_title(body.name), summary=body.summary.strip(), background=body.background.strip(), victory_condition=body.victory_condition.strip())
    db.add(scenario)
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "情景名字已存在")
    await db.refresh(scenario); return scenario


@admin_router.get("/{scenario_id}", response_model=ScenarioOut)
async def admin_get_scenario(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None: raise HTTPException(404, "情景不存在")
    return scenario


@admin_router.put("/{scenario_id}", response_model=ScenarioOut)
async def admin_update_scenario(scenario_id: UUID, body: ScenarioIn, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None: raise HTTPException(404, "情景不存在")
    if scenario.status != ScenarioState.DRAFT: raise HTTPException(409, "已发布情景不可编辑")
    scenario.name, scenario.normalized_name, scenario.summary, scenario.background, scenario.victory_condition = body.name.strip(), normalize_title(body.name), body.summary.strip(), body.background.strip(), body.victory_condition.strip()
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "情景名字已存在")
    await db.refresh(scenario); return scenario


@admin_router.post("/{scenario_id}/publish", response_model=ScenarioOut)
async def admin_publish_scenario(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None: raise HTTPException(404, "情景不存在")
    scenario.status, scenario.published_at = ScenarioState.PUBLISHED, _now(); await db.commit(); await db.refresh(scenario); return scenario


@admin_router.post("/{scenario_id}/delete", response_model=ScenarioOut)
async def admin_delete_scenario(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None: raise HTTPException(404, "情景不存在")
    scenario.status, scenario.deleted_at = ScenarioState.DELETED, _now(); await db.commit(); await db.refresh(scenario); return scenario


@admin_router.get("/{scenario_id}/rosters", response_model=list[RosterOut])
async def admin_rosters(scenario_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario_id).order_by(ScenarioRoster.created_at))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


async def _admin_roster(roster_id: UUID, db: AsyncSession) -> ScenarioRoster:
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.kind != RosterKind.OFFICIAL:
        raise HTTPException(404, "官方阵容不存在")
    return roster


@admin_roster_router.post("/{roster_id}/publish", response_model=RosterOut)
async def admin_publish_roster(roster_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await _admin_roster(roster_id, db)
    revision = await db.get(ScenarioRosterRevision, roster.work_revision_id) if roster.work_revision_id else None
    if revision is None:
        revision = await db.scalar(select(ScenarioRosterRevision).where(ScenarioRosterRevision.roster_id == roster.id).order_by(ScenarioRosterRevision.revision_number.desc()))
    if revision is None:
        raise HTTPException(409, "阵容没有可发布修订")
    revision.state = RosterState.PUBLISHED
    revision.published_at = _now()
    roster.current_revision_id = revision.id
    roster.work_revision_id = None
    roster.state, roster.published_at = RosterState.PUBLISHED, _now()
    await db.commit(); await db.refresh(roster)
    return await _roster_out(db, roster)


@admin_roster_router.post("/{roster_id}/delete", response_model=RosterOut)
async def admin_delete_roster(roster_id: UUID, _: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await _admin_roster(roster_id, db)
    roster.state, roster.deleted_at = RosterState.DELETED, _now()
    await db.commit(); await db.refresh(roster)
    return await _roster_out(db, roster)


@admin_router.post("/{scenario_id}/rosters", response_model=RosterOut, status_code=201)
async def admin_create_roster(scenario_id: UUID, body: RosterIn, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != ScenarioState.DRAFT: raise HTTPException(409, "只能为情景草稿创建官方阵容")
    name, bio, abilities = await _character_snapshot(db, body.character_asset_id, admin.id)
    roster = ScenarioRoster(scenario_id=scenario_id, owner_id=admin.id, kind=RosterKind.OFFICIAL, name=name, character_name=name, character_bio=bio, guidance=body.guidance, state=RosterState.DRAFT)
    db.add(roster); await db.flush(); db.add_all([ScenarioRosterAbility(roster_id=roster.id, position=i + 1, **ability) for i, ability in enumerate(abilities)]); await db.flush(); await _make_roster_revision(db, roster, abilities, RosterState.DRAFT); await db.commit(); await db.refresh(roster); return await _roster_out(db, roster)


@creator_router.get("/{scenario_id}/rosters", response_model=list[RosterOut])
async def creator_rosters(scenario_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario_id, ScenarioRoster.owner_id == current.id, ScenarioRoster.kind == RosterKind.PLAYER, ScenarioRoster.deleted_at.is_(None)))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


@creator_router.post("/{scenario_id}/rosters", response_model=RosterOut, status_code=201)
async def creator_create_roster(scenario_id: UUID, body: RosterIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None: raise HTTPException(404, "小天下集情景不存在")
    name, bio, abilities = await _character_snapshot(db, body.character_asset_id, current.id)
    roster = ScenarioRoster(scenario_id=scenario_id, owner_id=current.id, kind=RosterKind.PLAYER, name=name, character_name=name, character_bio=bio, guidance=body.guidance, state=RosterState.PUBLISHED, published_at=_now())
    db.add(roster); await db.flush(); db.add_all([ScenarioRosterAbility(roster_id=roster.id, position=i + 1, **ability) for i, ability in enumerate(abilities)]); await db.flush(); await _make_roster_revision(db, roster, abilities, RosterState.PUBLISHED); await db.commit(); await db.refresh(roster); return await _roster_out(db, roster)


@creator_router.get("/rosters/{roster_id}", response_model=RosterOut)
async def creator_get_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.owner_id != current.id: raise HTTPException(404, "阵容不存在")
    return await _roster_out(db, roster)


@creator_roster_router.get("/{roster_id}", response_model=RosterOut)
async def creator_get_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_get_roster(roster_id, current, db)


@creator_router.post("/rosters/{roster_id}/copy", response_model=RosterOut, status_code=201)
async def creator_copy_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    source = await db.get(ScenarioRoster, roster_id)
    if source is None or source.owner_id != current.id: raise HTTPException(404, "阵容不存在")
    roster = ScenarioRoster(scenario_id=source.scenario_id, owner_id=current.id, kind=RosterKind.PLAYER, name=f"{source.name} 副本", character_name=source.character_name, character_bio=source.character_bio, guidance=source.guidance, state=RosterState.PUBLISHED, published_at=_now())
    db.add(roster); await db.flush(); abilities = (await db.execute(select(ScenarioRosterAbility).where(ScenarioRosterAbility.roster_id == source.id).order_by(ScenarioRosterAbility.position))).scalars().all(); snapshots = [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in abilities]; db.add_all([ScenarioRosterAbility(roster_id=roster.id, position=a.position, name=a.name, effect=a.effect, detail=a.detail) for a in abilities]); await db.flush(); await _make_roster_revision(db, roster, snapshots, RosterState.PUBLISHED); await db.commit(); await db.refresh(roster); return await _roster_out(db, roster)


@creator_router.post("/rosters/{roster_id}/delete", status_code=204)
async def creator_delete_roster(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.owner_id != current.id: raise HTTPException(404, "阵容不存在")
    roster.state, roster.deleted_at = RosterState.DELETED, _now(); await db.commit()


@creator_roster_router.post("/{roster_id}/copy", response_model=RosterOut, status_code=201)
async def creator_copy_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_copy_roster(roster_id, current, db)


@creator_roster_router.post("/{roster_id}/delete", status_code=204)
async def creator_delete_roster_alias(roster_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await creator_delete_roster(roster_id, current, db)


@public_router.get("", response_model=list[ScenarioOut])
async def public_scenarios(db: Annotated[AsyncSession, Depends(get_db)]):
    return list((await db.execute(select(Scenario).where(Scenario.status == ScenarioState.PUBLISHED, Scenario.deleted_at.is_(None)).order_by(Scenario.published_at.desc()))).scalars())


@public_router.get("/{scenario_id}/rosters/{roster_id}", response_model=ScenarioRosterDetailOut)
async def public_roster_detail(
    scenario_id: UUID,
    roster_id: UUID,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    scenario = await db.get(Scenario, scenario_id)
    roster = await db.get(ScenarioRoster, roster_id)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None:
        raise HTTPException(404, "小天下集情景不存在")
    if roster is None or roster.scenario_id != scenario_id or roster.state != RosterState.PUBLISHED or roster.deleted_at is not None:
        raise HTTPException(404, "阵容不存在")

    progress = await db.get(ScenarioRosterProgress, {"roster_id": roster.id, "challenger_id": current.id})
    my_query = select(ScenarioChallengeRun).where(ScenarioChallengeRun.roster_id == roster.id, ScenarioChallengeRun.challenger_id == current.id).order_by(desc(ScenarioChallengeRun.created_at), desc(ScenarioChallengeRun.id)).limit(100)
    my_rows = list((await db.execute(my_query)).scalars())
    my_history = [await _challenge_history_out(db, row) for row in my_rows]

    owner_history: list[ScenarioOwnerChallengeOut] = []
    next_cursor = None
    if roster.owner_id == current.id:
        owner_query = select(ScenarioChallengeRun).where(ScenarioChallengeRun.roster_id == roster.id, ScenarioChallengeRun.is_preview.is_(False)).order_by(desc(ScenarioChallengeRun.created_at), desc(ScenarioChallengeRun.id))
        decoded = _decode_cursor(cursor)
        if decoded:
            created_at, item_id = decoded
            owner_query = owner_query.where((ScenarioChallengeRun.created_at < created_at) | ((ScenarioChallengeRun.created_at == created_at) & (ScenarioChallengeRun.id < item_id)))
        owner_rows = list((await db.execute(owner_query.limit(limit + 1))).scalars())
        has_more = len(owner_rows) > limit
        owner_rows = owner_rows[:limit]
        for row in owner_rows:
            challenger = await db.get(User, row.challenger_id)
            item = await _challenge_history_out(db, row)
            owner_history.append(ScenarioOwnerChallengeOut(**item.model_dump(), challenger_id=row.challenger_id, challenger_name=challenger.username if challenger else "已离席"))
        if has_more and owner_rows:
            next_cursor = _encode_cursor(owner_rows[-1].created_at, owner_rows[-1].id)

    progress_out = None
    if progress is not None:
        progress_out = ScenarioRosterProgressOut(
            roster_id=progress.roster_id,
            challenger_id=progress.challenger_id,
            attempts=progress.attempts,
            first_victory_challenges=progress.first_victory_challenges,
            cracked_cards=_public_cards(progress.cracked_cards),
            guess_count=len(progress.guess_history or []),
            updated_at=progress.updated_at,
        )
    return ScenarioRosterDetailOut(
        scenario=ScenarioOut.model_validate(scenario),
        roster=await _roster_out(db, roster),
        viewer_role="owner" if roster.owner_id == current.id else "challenger",
        my_progress=progress_out,
        my_challenges=my_history,
        owner_challenges=owner_history,
        next_cursor=next_cursor,
    )


@public_router.get("/{scenario_id}", response_model=ScenarioOut)
async def public_scenario(scenario_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != ScenarioState.PUBLISHED or scenario.deleted_at is not None: raise HTTPException(404, "小天下集情景不存在")
    return scenario


@public_router.get("/{scenario_id}/rosters", response_model=list[RosterOut])
async def public_rosters(scenario_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.execute(select(ScenarioRoster).where(ScenarioRoster.scenario_id == scenario_id, ScenarioRoster.state == RosterState.PUBLISHED, ScenarioRoster.deleted_at.is_(None)).order_by(ScenarioRoster.kind, ScenarioRoster.created_at))).scalars().all()
    return [await _roster_out(db, row) for row in rows]


@public_router.get("/rosters/{roster_id}", response_model=RosterOut)
async def public_roster(roster_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id)
    if roster is None or roster.state != RosterState.PUBLISHED or roster.deleted_at is not None: raise HTTPException(404, "阵容不存在")
    return await _roster_out(db, roster)


@public_roster_router.get("/{roster_id}", response_model=RosterOut)
async def public_roster_alias(roster_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    return await public_roster(roster_id, db)


@challenge_router.post("/scenario-rosters/{roster_id}/challenges", response_model=ChallengeOut, status_code=201)
async def create_challenge(roster_id: UUID, body: ChallengeIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    roster = await db.get(ScenarioRoster, roster_id); scenario = await db.get(Scenario, roster.scenario_id) if roster else None
    if roster is None or scenario is None or roster.state != RosterState.PUBLISHED: raise HTTPException(404, "阵容不存在")
    is_preview = roster.owner_id == current.id
    challenger_name, challenger_bio, challenger_abilities = await _character_snapshot(db, body.character_asset_id, current.id)
    progress = await db.get(ScenarioRosterProgress, {"roster_id": roster.id, "challenger_id": current.id})
    if progress is None:
        progress = ScenarioRosterProgress(roster_id=roster.id, challenger_id=current.id)
        db.add(progress)
        await db.flush()
    if not is_preview:
        progress.attempts += 1
    roster_abilities = await _roster_abilities(db, roster)
    challenge = ScenarioChallengeRun(roster_id=roster.id, challenger_id=current.id, is_preview=is_preview, status="preparing", challenge_number=progress.attempts if not is_preview else 1, scenario_snapshot={"id": str(scenario.id), "name": scenario.name, "summary": scenario.summary, "background": scenario.background, "victory_condition": scenario.victory_condition}, roster_snapshot={"character_name": roster.character_name, "character_bio": roster.character_bio, "guidance": roster.guidance, "abilities": [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in roster_abilities]}, challenger_snapshot={"character_name": challenger_name, "character_bio": challenger_bio, "abilities": challenger_abilities})
    db.add(challenge)
    if not is_preview:
        roster.challenge_count += 1
    await db.commit(); await db.refresh(challenge)
    asyncio.create_task(_prepare_scenario_challenge(challenge.id))
    return ChallengeOut(id=challenge.id, roster_id=roster.id, scenario_id=scenario.id, status=challenge.status, challenge_number=challenge.challenge_number, is_preview=challenge.is_preview, created_at=challenge.created_at)


@challenge_router.get("/scenario-challenges/{challenge_id}")
async def challenge_detail(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None:
        raise HTTPException(404, "挑战不存在")
    roster = await db.get(ScenarioRoster, challenge.roster_id)
    if challenge.challenger_id == current.id:
        return {"id": challenge.id, "roster_id": challenge.roster_id, "scenario_id": challenge.scenario_snapshot.get("id"), "status": challenge.status, "challenge_number": challenge.challenge_number, "is_preview": challenge.is_preview, "viewer_role": "challenger", "scenario": challenge.scenario_snapshot, "roster": challenge.roster_snapshot, "challenger": challenge.challenger_snapshot, "guess_attempts": challenge.guess_attempts, "messages": challenge.messages, "guesses": challenge.guesses, "won": challenge.won}
    if roster is None or roster.owner_id != current.id:
        raise HTTPException(404, "挑战不存在")
    # 阵容作者只能查看守方视角；挑战者正文、猜词原文和私有资产快照均不出站。
    guardian_messages = []
    for message in challenge.messages or []:
        if message.get("role") == "views" and message.get("guardian_text"):
            guardian_messages.append({"role": "guardian", "text": message["guardian_text"], "created_at": message.get("created_at")})
    challenger = await db.get(User, challenge.challenger_id)
    return {"id": challenge.id, "roster_id": challenge.roster_id, "scenario_id": challenge.scenario_snapshot.get("id"), "status": challenge.status, "challenge_number": challenge.challenge_number, "is_preview": challenge.is_preview, "viewer_role": "owner", "scenario": challenge.scenario_snapshot, "roster": challenge.roster_snapshot, "challenger": {"character_name": challenge.challenger_snapshot.get("character_name", "挑战者"), "username": challenger.username if challenger else "已离席"}, "guess_attempts": 0, "messages": guardian_messages, "guesses": [], "won": challenge.won}


@challenge_router.get("/scenario-challenges/{challenge_id}/stream")
async def challenge_stream(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)]) -> StreamingResponse:
    """小天下集推演实时流：比对、上帝裁定状态及双方视角逐字转写。"""
    async with async_session_factory() as db:
        challenge = await db.get(ScenarioChallengeRun, challenge_id)
        roster = await db.get(ScenarioRoster, challenge.roster_id) if challenge else None
        if challenge is None or (challenge.challenger_id != current.id and (roster is None or roster.owner_id != current.id)):
            raise HTTPException(404, "挑战不存在")
        status = challenge.status

    def encode(event: dict) -> str:
        return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def events():
        if status == "failed":
            yield encode({"type": "error", "message": "挑战准备失败，请重新开始。"})
            return
        if status == "won":
            yield encode({"type": "done", "status": status})
            return
        stream = get_scenario_stream(challenge_id)
        queue, snapshot = stream.subscribe()
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
    if challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "挑战不存在")
    if challenge.won is not None: raise HTTPException(409, "挑战已经结束")
    if challenge.status != "active": raise HTTPException(409, "当前回合仍在衍算中")
    text = str(payload.get("text", "")).strip()
    if not text: raise HTTPException(400, "行动不能为空")
    challenge.messages = [*challenge.messages, {"role": "challenger", "text": text, "created_at": _now().isoformat()}]
    challenge.status = "resolving"
    await db.commit()
    asyncio.create_task(_resolve_scenario_action(challenge.id))
    return {"challenge_id": challenge.id, "status": challenge.status, "text": text}


@challenge_router.post("/scenario-challenges/{challenge_id}/guess")
async def challenge_guess(challenge_id: UUID, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "挑战不存在")
    if challenge.won is not None: raise HTTPException(409, "挑战已经结束")
    text = str(payload.get("text", "")).strip()
    if not text: raise HTTPException(400, "猜词不能为空")
    progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
    abilities = challenge.roster_snapshot.get("abilities", [])
    cards = progress.cracked_cards if progress and progress.cracked_cards else [{"name": ability.get("name", ""), "cracked": False} for ability in abilities]
    await run_guess_commentary(text=text, abilities=abilities, cards=cards, trace_context={"kind": "scenario", "trace_id": str(challenge.id)})
    challenge.guess_attempts += 1
    challenge.guesses = [*challenge.guesses, {"text": text, "attempt": challenge.guess_attempts, "created_at": _now().isoformat()}]
    if progress:
        progress.guess_history = [*(progress.guess_history or []), text]
        progress.cracked_cards = cards
        progress.guess_history = [*(progress.guess_history or [])]
    await db.commit()
    return {"guess_attempts": challenge.guess_attempts, "text": text, "status": challenge.status, "guesses": challenge.guesses}


@challenge_router.post("/scenario-challenges/{challenge_id}/guess/verify")
async def challenge_verify(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "挑战不存在")
    progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
    verified = False
    if progress and progress.guess_history:
        cards = progress.cracked_cards or [{"name": ability.get("name", ""), "cracked": False} for ability in challenge.roster_snapshot.get("abilities", [])]
        await run_guess_verification(history=progress.guess_history, comments=[], abilities=challenge.roster_snapshot.get("abilities", []), cards=cards, round_no=len(progress.guess_history), trace_context={"kind": "scenario", "trace_id": str(challenge.id)})
        progress.cracked_cards = cards
        verified = all(card.get("cracked") for card in cards)
    if verified and challenge.won is None:
        challenge.won = True
        challenge.status = "won"
        challenge.finished_at = _now()
        progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
        if progress and progress.first_victory_challenges is None and not challenge.is_preview:
            progress.first_victory_challenges = progress.attempts
            values = list((await db.execute(select(ScenarioRosterProgress.first_victory_challenges).join(ScenarioRoster, ScenarioRoster.id == ScenarioRosterProgress.roster_id).where(ScenarioRosterProgress.roster_id == challenge.roster_id, ScenarioRosterProgress.first_victory_challenges.is_not(None), ScenarioRosterProgress.challenger_id != ScenarioRoster.owner_id))).scalars())
            roster = await db.get(ScenarioRoster, challenge.roster_id)
            if roster and values:
                roster.first_victory_avg_challenges = sum(values) / len(values)
                roster.completed_count = len(values)
    await db.commit()
    return {"verified": verified, "guess_attempts": challenge.guess_attempts, "guesses": challenge.guesses, "won": challenge.won}


@challenge_router.post("/scenario-challenges/{challenge_id}/derive")
async def challenge_derive(challenge_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallengeRun, challenge_id)
    if challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "挑战不存在")
    history = "\n".join(item.get("omniscient", item.get("text", "")) for item in challenge.messages)
    verdict = await ainvoke_with_reliability(
        build_collection_judge_llm(),
        JUDGE_TEMPLATE.format_messages(
            volume=challenge.scenario_snapshot.get("name", "小天下集情景"),
            victory_condition=challenge.scenario_snapshot.get("victory_condition", ""),
            tianji="（当前情景未配置额外天机）",
            opening=challenge.scenario_snapshot.get("background", ""),
            history=history or "（尚未行动）",
        ),
        operation="scenario_derive",
        trace_context={"kind": "scenario", "trace_id": str(challenge.id)},
    )
    achieved = bool(getattr(verdict, "achieved", False))
    challenge.derived = {"status": "won" if achieved else "checked", "message_count": len(challenge.messages), "guess_count": len(challenge.guesses), "note": getattr(verdict, "note", "")}
    if achieved and challenge.won is None:
        challenge.won = True
        challenge.status = "won"
        challenge.finished_at = _now()
        progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": current.id})
        if progress and progress.first_victory_challenges is None and not challenge.is_preview:
            progress.first_victory_challenges = progress.attempts
            values = list((await db.execute(select(ScenarioRosterProgress.first_victory_challenges).join(ScenarioRoster, ScenarioRoster.id == ScenarioRosterProgress.roster_id).where(ScenarioRosterProgress.roster_id == challenge.roster_id, ScenarioRosterProgress.first_victory_challenges.is_not(None), ScenarioRosterProgress.challenger_id != ScenarioRoster.owner_id))).scalars())
            roster = await db.get(ScenarioRoster, challenge.roster_id)
            if roster and values:
                roster.first_victory_avg_challenges = sum(values) / len(values)
                roster.completed_count = len(values)
    await db.commit()
    return {"status": challenge.status, "challenge_id": challenge.id, "derived": challenge.derived}


__all__ = ["admin_roster_router", "admin_router", "challenge_router", "creator_roster_router", "creator_router", "public_roster_router", "public_router"]
