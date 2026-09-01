"""扁平异闻：组合创作、审核、公开浏览与挑战。"""
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, get_current_user
from app.db.base import get_db
from app.models.creator_asset import (
    AbilityRevisionContent,
    CharacterRevisionAbility,
    CharacterRevisionContent,
    CreatorAsset,
    CreatorAssetRevision,
    RevisionStatus,
)
from app.models.scenario import (
    CreatorScenario,
    ScenarioChallenge,
    ScenarioGuessProgress,
    ScenarioMessage,
    ScenarioRevision,
    ScenarioRevisionAbility,
    ScenarioRevisionGuardian,
    ScenarioRevisionStory,
    ScenarioStatus,
    ScenarioWorldline,
)
from app.models.user import User
from app.schemas.scenario import (
    ScenarioChallengeIn,
    ScenarioChallengeOut,
    ScenarioDraftIn,
    ScenarioMessageOut,
    ScenarioOut,
    ScenarioPage,
    ScenarioPublicOut,
    ScenarioRevisionOut,
    ScenarioWorldlineOut,
)
from app.services.creator.normalization import normalize_title

creator_router = APIRouter(prefix="/creator/scenarios", tags=["creator-scenarios"])
admin_router = APIRouter(prefix="/admin/creator/scenarios", tags=["admin-scenarios"])
public_router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _content(body: ScenarioDraftIn) -> dict:
    values = body.model_dump(exclude={"lock_version", "guardian_abilities", "guardian_character_asset_id"})
    values = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
    if any(not values[key] for key in ("name", "summary", "background", "victory_condition")):
        raise HTTPException(400, "异闻本体与守方奇人信息不能为空")
    if body.guardian_character_asset_id is None and (not body.guardian_name.strip() or not 1 <= len(body.guardian_abilities) <= 4):
        raise HTTPException(400, "守方必须装配 1-4 门奇术")
    return values


async def _character_snapshot(db: AsyncSession, asset_id: UUID, owner_id: int) -> tuple[dict, list[dict]]:
    asset = await db.get(CreatorAsset, asset_id)
    if asset is None or asset.owner_id != owner_id or asset.kind != "character" or asset.deleted_at is not None:
        raise HTTPException(404, "私有奇人不存在")
    revision_id = asset.current_published_revision_id or await db.scalar(
        select(CreatorAssetRevision.id).where(
            CreatorAssetRevision.asset_id == asset.id,
            CreatorAssetRevision.status.in_([RevisionStatus.DRAFT.value, RevisionStatus.PUBLISHED.value]),
        ).order_by(CreatorAssetRevision.revision_number.desc()).limit(1)
    )
    if revision_id is None:
        raise HTTPException(409, "奇人没有可用修订")
    content = await db.get(CharacterRevisionContent, revision_id)
    links = list((await db.execute(select(CharacterRevisionAbility).where(CharacterRevisionAbility.revision_id == revision_id).order_by(CharacterRevisionAbility.position))).scalars())
    if content is None or not 1 <= len(links) <= 4:
        raise HTTPException(400, "守方必须装配 1-4 门奇术")
    abilities: list[dict] = []
    for link in links:
        ability = await db.get(AbilityRevisionContent, link.ability_revision_id)
        if ability is None or not ability.name.strip() or not ability.effect.strip():
            raise HTTPException(400, "奇人装配的奇术内容不完整")
        abilities.append({"name": ability.name, "effect": ability.effect, "detail": ability.detail or ""})
    return {"name": content.name, "style": content.style, "tactic": content.tactic}, abilities


async def _scenario(db: AsyncSession, scenario_id: UUID, user: User | None = None) -> CreatorScenario:
    scenario = await db.get(CreatorScenario, scenario_id)
    if scenario is None or (user is not None and scenario.owner_id != user.id):
        raise HTTPException(404, "异闻不存在")
    return scenario


async def _revision_data(db: AsyncSession, revision_id: UUID) -> dict:
    story = await db.get(ScenarioRevisionStory, revision_id)
    guardian = await db.get(ScenarioRevisionGuardian, revision_id)
    abilities = list((await db.execute(select(ScenarioRevisionAbility).where(ScenarioRevisionAbility.revision_id == revision_id).order_by(ScenarioRevisionAbility.position))).scalars())
    if story is None or guardian is None:
        raise HTTPException(500, "异闻修订快照缺失")
    return {"name": story.name, "summary": story.summary, "background": story.background, "victory_condition": story.victory_condition, "guidance": story.guidance, "guardian_name": guardian.name, "guardian_style": guardian.style, "guardian_tactic": guardian.tactic, "guardian_abilities": [{"name": a.name, "effect": a.effect, "detail": a.detail} for a in abilities]}


def _revision_out(revision: ScenarioRevision, data: dict) -> ScenarioRevisionOut:
    return ScenarioRevisionOut(id=revision.id, scenario_id=revision.scenario_id, revision_number=revision.revision_number, status=revision.status, lock_version=revision.lock_version, review_reason=revision.review_reason, content=data, created_at=revision.created_at, published_at=revision.published_at)


async def _work(db: AsyncSession, scenario_id: UUID) -> ScenarioRevision | None:
    return await db.scalar(select(ScenarioRevision).where(ScenarioRevision.scenario_id == scenario_id, ScenarioRevision.status.in_([ScenarioStatus.DRAFT, ScenarioStatus.PENDING_REVIEW])))


async def _scenario_out(db: AsyncSession, scenario: CreatorScenario) -> ScenarioOut:
    work = await _work(db, scenario.id)
    return ScenarioOut(id=scenario.id, owner_id=scenario.owner_id, current_revision_id=scenario.current_revision_id, challenge_count=scenario.challenge_count, created_at=scenario.created_at, updated_at=scenario.updated_at, work_revision=_revision_out(work, await _revision_data(db, work.id)) if work else None)


@creator_router.post("", response_model=ScenarioRevisionOut, status_code=201)
async def create_scenario(body: ScenarioDraftIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    values = _content(body)
    if body.guardian_character_asset_id:
        guardian_data, guardian_abilities = await _character_snapshot(db, body.guardian_character_asset_id, current.id)
        values.update({"guardian_name": guardian_data["name"], "guardian_style": guardian_data["style"], "guardian_tactic": guardian_data["tactic"]})
    else:
        guardian_abilities = body.guardian_abilities
    scenario = CreatorScenario(owner_id=current.id, normalized_name=normalize_title(values["name"]))
    db.add(scenario)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback(); raise HTTPException(409, "已有同名异闻")
    revision = ScenarioRevision(scenario_id=scenario.id, revision_number=1)
    db.add(revision); await db.flush()
    db.add(ScenarioRevisionStory(revision_id=revision.id, name=values["name"], summary=values["summary"], background=values["background"], victory_condition=values["victory_condition"], guidance=values["guidance"]))
    db.add(ScenarioRevisionGuardian(revision_id=revision.id, name=values["guardian_name"], style=values["guardian_style"], tactic=values["guardian_tactic"]))
    db.add_all([ScenarioRevisionAbility(revision_id=revision.id, position=i + 1, name=a["name"].strip(), effect=a["effect"].strip(), detail=a.get("detail", "").strip()) if isinstance(a, dict) else ScenarioRevisionAbility(revision_id=revision.id, position=i + 1, name=a.name.strip(), effect=a.effect.strip(), detail=a.detail.strip()) for i, a in enumerate(guardian_abilities)])
    scenario.work_revision_id = revision.id
    await db.commit(); await db.refresh(revision)
    return _revision_out(revision, await _revision_data(db, revision.id))


@creator_router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    return await _scenario_out(db, await _scenario(db, scenario_id, current))


@creator_router.put("/{scenario_id}/draft", response_model=ScenarioRevisionOut)
async def save_scenario(scenario_id: UUID, body: ScenarioDraftIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await _scenario(db, scenario_id, current); revision = await _work(db, scenario.id)
    if revision is None or revision.status != ScenarioStatus.DRAFT: raise HTTPException(409, "当前修订不可编辑")
    if body.lock_version is not None and body.lock_version != revision.lock_version: raise HTTPException(409, {"lock_version": revision.lock_version})
    values = _content(body)
    if body.guardian_character_asset_id:
        guardian_data, guardian_abilities = await _character_snapshot(db, body.guardian_character_asset_id, current.id)
        values.update({"guardian_name": guardian_data["name"], "guardian_style": guardian_data["style"], "guardian_tactic": guardian_data["tactic"]})
    else:
        guardian_abilities = body.guardian_abilities
    existing = await _revision_data(db, revision.id)
    if scenario.challenge_count:
        changed_story = any(values[key] != existing[key] for key in ("name", "summary", "background", "victory_condition"))
        changed_guardian = any(values[key] != existing[key] for key in ("guardian_name", "guardian_style", "guardian_tactic"))
        submitted_abilities = [{"name": a["name"], "effect": a["effect"], "detail": a.get("detail", "")} if isinstance(a, dict) else {"name": a.name, "effect": a.effect, "detail": a.detail} for a in guardian_abilities]
        if submitted_abilities != existing["guardian_abilities"]:
            changed_guardian = True
        if changed_story or changed_guardian:
            raise HTTPException(409, "已有挑战记录，异闻本体与守方配置已冻结")
    story = await db.get(ScenarioRevisionStory, revision.id); guardian = await db.get(ScenarioRevisionGuardian, revision.id)
    story.name, story.summary, story.background, story.victory_condition, story.guidance = values["name"], values["summary"], values["background"], values["victory_condition"], values["guidance"]
    guardian.name, guardian.style, guardian.tactic = values["guardian_name"], values["guardian_style"], values["guardian_tactic"]
    await db.execute(ScenarioRevisionAbility.__table__.delete().where(ScenarioRevisionAbility.revision_id == revision.id))
    db.add_all([ScenarioRevisionAbility(revision_id=revision.id, position=i + 1, name=a["name"].strip(), effect=a["effect"].strip(), detail=a.get("detail", "").strip()) if isinstance(a, dict) else ScenarioRevisionAbility(revision_id=revision.id, position=i + 1, name=a.name.strip(), effect=a.effect.strip(), detail=a.detail.strip()) for i, a in enumerate(guardian_abilities)])
    revision.lock_version += 1; scenario.normalized_name = normalize_title(values["name"])
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "已有同名异闻")
    await db.refresh(revision); return _revision_out(revision, await _revision_data(db, revision.id))


@creator_router.post("/{scenario_id}/submit", response_model=ScenarioRevisionOut, status_code=202)
async def submit_scenario(scenario_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await _scenario(db, scenario_id, current); revision = await _work(db, scenario.id)
    if revision is None or revision.status != ScenarioStatus.DRAFT: raise HTTPException(409, "没有可提交审核的草稿")
    revision.status, revision.submitted_at = ScenarioStatus.PENDING_REVIEW, now(); await db.commit(); await db.refresh(revision)
    return _revision_out(revision, await _revision_data(db, revision.id))


@creator_router.get("/{scenario_id}/revisions", response_model=list[ScenarioRevisionOut])
async def list_scenario_revisions(scenario_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    await _scenario(db, scenario_id, current)
    rows = (await db.execute(select(ScenarioRevision).where(ScenarioRevision.scenario_id == scenario_id).order_by(ScenarioRevision.revision_number.desc()))).scalars().all()
    return [_revision_out(row, await _revision_data(db, row.id)) for row in rows]


@creator_router.post("/{scenario_id}/revisions/{revision_id}/copy", response_model=ScenarioRevisionOut, status_code=201)
async def copy_scenario(scenario_id: UUID, revision_id: UUID, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await _scenario(db, scenario_id, current)
    if await _work(db, scenario.id): raise HTTPException(409, "已有工作修订")
    source = await db.get(ScenarioRevision, revision_id)
    if source is None or source.scenario_id != scenario.id: raise HTTPException(404, "修订不存在")
    data = await _revision_data(db, source.id); number = (await db.scalar(select(ScenarioRevision.revision_number).where(ScenarioRevision.scenario_id == scenario.id).order_by(ScenarioRevision.revision_number.desc()).limit(1)) or 0) + 1
    revision = ScenarioRevision(scenario_id=scenario.id, revision_number=number, based_on_revision_id=source.id)
    db.add(revision); await db.flush()
    db.add(ScenarioRevisionStory(revision_id=revision.id, name=data["name"], summary=data["summary"], background=data["background"], victory_condition=data["victory_condition"], guidance=data["guidance"]))
    db.add(ScenarioRevisionGuardian(revision_id=revision.id, name=data["guardian_name"], style=data["guardian_style"], tactic=data["guardian_tactic"]))
    db.add_all([ScenarioRevisionAbility(revision_id=revision.id, position=i + 1, **ability) for i, ability in enumerate(data["guardian_abilities"])])
    scenario.work_revision_id = revision.id; await db.commit(); await db.refresh(revision)
    return _revision_out(revision, data)


@public_router.get("", response_model=ScenarioPage)
async def list_scenarios(db: Annotated[AsyncSession, Depends(get_db)], q: str | None = Query(None, max_length=30), limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), cursor: str | None = None):
    """公开异闻列表；cursor 与 offset 兼容，cursor 为上一页返回的数字游标。"""
    if cursor:
        try:
            offset = max(0, int(cursor))
        except ValueError:
            raise HTTPException(400, "游标无效")
    query = select(CreatorScenario, ScenarioRevision, ScenarioRevisionStory, ScenarioRevisionGuardian).join(ScenarioRevision, ScenarioRevision.id == CreatorScenario.current_revision_id).join(ScenarioRevisionStory, ScenarioRevisionStory.revision_id == ScenarioRevision.id).join(ScenarioRevisionGuardian, ScenarioRevisionGuardian.revision_id == ScenarioRevision.id).where(ScenarioRevision.status == ScenarioStatus.PUBLISHED, CreatorScenario.deleted_at.is_(None)).order_by(ScenarioRevision.published_at.desc()).offset(offset).limit(limit + 1)
    if q: query = query.where(ScenarioRevisionStory.name.contains(q.strip()))
    rows = list((await db.execute(query)).all()); next_cursor = str(offset + limit) if len(rows) > limit else None; rows = rows[:limit]
    return ScenarioPage(items=[ScenarioPublicOut(id=s.id, revision_id=r.id, name=story.name, summary=story.summary, background=story.background, victory_condition=story.victory_condition, guardian_name=guardian.name, guardian_ability_count=(await db.scalar(select(ScenarioRevisionAbility.position).where(ScenarioRevisionAbility.revision_id == r.id).order_by(ScenarioRevisionAbility.position.desc()).limit(1)) or 0), challenge_count=s.challenge_count, published_at=r.published_at) for s, r, story, guardian in rows], next_cursor=next_cursor)


@public_router.get("/{scenario_id}", response_model=ScenarioPublicOut)
async def get_public_scenario(scenario_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    row = (await db.execute(select(CreatorScenario, ScenarioRevision, ScenarioRevisionStory, ScenarioRevisionGuardian).join(ScenarioRevision, ScenarioRevision.id == CreatorScenario.current_revision_id).join(ScenarioRevisionStory, ScenarioRevisionStory.revision_id == ScenarioRevision.id).join(ScenarioRevisionGuardian, ScenarioRevisionGuardian.revision_id == ScenarioRevision.id).where(CreatorScenario.id == scenario_id, ScenarioRevision.status == ScenarioStatus.PUBLISHED, CreatorScenario.deleted_at.is_(None)))).first()
    if row is None: raise HTTPException(404, "异闻不存在")
    s, r, story, guardian = row; count = await db.scalar(select(ScenarioRevisionAbility.position).where(ScenarioRevisionAbility.revision_id == r.id).order_by(ScenarioRevisionAbility.position.desc()).limit(1)) or 0
    return ScenarioPublicOut(id=s.id, revision_id=r.id, name=story.name, summary=story.summary, background=story.background, victory_condition=story.victory_condition, guardian_name=guardian.name, guardian_ability_count=count, challenge_count=s.challenge_count, published_at=r.published_at)


@public_router.post("/{scenario_id}/challenges", response_model=ScenarioChallengeOut, status_code=201)
async def challenge_scenario(scenario_id: UUID, body: ScenarioChallengeIn, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(CreatorScenario, scenario_id); revision = await db.scalar(select(ScenarioRevision).where(ScenarioRevision.id == scenario.current_revision_id, ScenarioRevision.status == ScenarioStatus.PUBLISHED)) if scenario else None
    if scenario is None or revision is None: raise HTTPException(404, "异闻不存在")
    if scenario.owner_id == current.id: raise HTTPException(400, "作者请使用创作台预览试炼")
    if body.character_asset_id:
        character_data, character_abilities = await _character_snapshot(db, body.character_asset_id, current.id)
        challenger_snapshot = {"character_name": character_data["name"], "character_style": character_data["style"], "character_tactic": character_data["tactic"], "abilities": character_abilities}
    else:
        if not body.character_name.strip() or not 1 <= len(body.abilities) <= 4:
            raise HTTPException(400, "挑战奇人必须装配 1-4 门奇术")
        challenger_snapshot = body.model_dump(exclude={"character_asset_id"})
    data = await _revision_data(db, revision.id)
    challenge = ScenarioChallenge(scenario_revision_id=revision.id, challenger_id=current.id, scenario_snapshot=data, challenger_snapshot=challenger_snapshot)
    db.add(challenge); scenario.challenge_count += 1
    try: await db.flush()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "已有进行中的挑战")
    line = ScenarioWorldline(challenge_id=challenge.id, sequence=1); db.add(line); await db.commit(); await db.refresh(challenge); await db.refresh(line)
    return ScenarioChallengeOut(id=challenge.id, scenario_id=scenario.id, status=challenge.status, opening=data["background"], worldline_id=line.id, created_at=challenge.created_at)


scenario_query = APIRouter(prefix="/scenario-challenges", tags=["scenario-challenges"])
worldline_query = APIRouter(prefix="/scenario-worldlines", tags=["scenario-worldlines"])


@scenario_query.get("/{challenge_id}")
async def challenge_detail(challenge_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    challenge = await db.get(ScenarioChallenge, challenge_id)
    if challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "挑战不存在")
    lines = (await db.execute(select(ScenarioWorldline).where(ScenarioWorldline.challenge_id == challenge.id).order_by(ScenarioWorldline.sequence))).scalars().all()
    return {"id": challenge.id, "scenario_id": str((await db.get(ScenarioRevision, challenge.scenario_revision_id)).scenario_id), "status": challenge.status, "worldlines": [{"id": line.id, "sequence": line.sequence, "status": line.status} for line in lines]}


@worldline_query.post("/{worldline_id}/actions", response_model=ScenarioWorldlineOut)
async def scenario_action(worldline_id: int, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    line = await db.get(ScenarioWorldline, worldline_id); challenge = await db.get(ScenarioChallenge, line.challenge_id) if line else None
    if line is None or challenge is None or challenge.challenger_id != current.id: raise HTTPException(404, "世界线不存在")
    text = str(payload.get("text", "")).strip()
    if not text: raise HTTPException(400, "行动不能为空")
    sequence = (await db.scalar(select(ScenarioMessage.sequence).where(ScenarioMessage.worldline_id == line.id).order_by(ScenarioMessage.sequence.desc()).limit(1)) or 0) + 1
    db.add(ScenarioMessage(worldline_id=line.id, sequence=sequence, role="challenger", challenger_text=text, guardian_text="", omniscient_text=f"挑战者采取行动：{text}"))
    await db.commit(); messages = (await db.execute(select(ScenarioMessage).where(ScenarioMessage.worldline_id == line.id).order_by(ScenarioMessage.sequence))).scalars().all()
    return ScenarioWorldlineOut(id=line.id, sequence=line.sequence, status=line.status, tokens_used=line.tokens_used, messages=[ScenarioMessageOut(id=m.id, sequence=m.sequence, role=m.role, text=m.challenger_text or m.guardian_text, created_at=m.created_at) for m in messages])


async def _worldline_out(db: AsyncSession, line: ScenarioWorldline) -> ScenarioWorldlineOut:
    messages = (await db.execute(select(ScenarioMessage).where(ScenarioMessage.worldline_id == line.id).order_by(ScenarioMessage.sequence))).scalars().all()
    return ScenarioWorldlineOut(id=line.id, sequence=line.sequence, status=line.status, tokens_used=line.tokens_used, messages=[ScenarioMessageOut(id=m.id, sequence=m.sequence, role=m.role, text=m.challenger_text or m.guardian_text or m.omniscient_text, created_at=m.created_at) for m in messages])


@worldline_query.get("/{worldline_id}", response_model=ScenarioWorldlineOut)
async def get_worldline(worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    line = await db.get(ScenarioWorldline, worldline_id)
    challenge = await db.get(ScenarioChallenge, line.challenge_id) if line else None
    if line is None or challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "世界线不存在")
    return await _worldline_out(db, line)


@worldline_query.post("/{worldline_id}/guess")
async def guess_worldline(worldline_id: int, payload: dict, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    line = await db.get(ScenarioWorldline, worldline_id)
    challenge = await db.get(ScenarioChallenge, line.challenge_id) if line else None
    if line is None or challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "世界线不存在")
    text = str(payload.get("text", payload.get("guess", ""))).strip()
    if not text:
        raise HTTPException(400, "猜词不能为空")
    progress = await db.get(ScenarioGuessProgress, {"challenger_id": current.id, "challenge_id": challenge.id})
    if progress is None:
        progress = ScenarioGuessProgress(challenger_id=current.id, challenge_id=challenge.id, cards=[], history=[], comments=[])
        db.add(progress)
    progress.history = [*(progress.history or []), text]
    progress.comments = [*(progress.comments or []), [{"index": i + 1, "items": [{"text": "已记录，待检定", "verdict": "不能确定"}]} for i, _ in enumerate(challenge.scenario_snapshot.get("guardian_abilities", []))]]
    await db.commit()
    return {"history": progress.history, "comments": progress.comments, "cards": progress.cards, "attempts_used": len(progress.history)}


@worldline_query.post("/{worldline_id}/guess/verify")
async def verify_worldline(worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    line = await db.get(ScenarioWorldline, worldline_id)
    challenge = await db.get(ScenarioChallenge, line.challenge_id) if line else None
    if line is None or challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "世界线不存在")
    progress = await db.get(ScenarioGuessProgress, {"challenger_id": current.id, "challenge_id": challenge.id})
    if progress is None:
        raise HTTPException(400, "暂无可检定的猜词")
    progress.verified_round = len(progress.history or [])
    await db.commit()
    return {"cards": progress.cards, "verified_round": progress.verified_round, "cracked": False}


@worldline_query.post("/{worldline_id}/derive")
async def derive_worldline(worldline_id: int, current: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    line = await db.get(ScenarioWorldline, worldline_id)
    challenge = await db.get(ScenarioChallenge, line.challenge_id) if line else None
    if line is None or challenge is None or challenge.challenger_id != current.id:
        raise HTTPException(404, "世界线不存在")
    line.derived = True
    challenge.derived_at = now()
    await db.commit()
    return await _worldline_out(db, line)


@admin_router.get("", response_model=list[ScenarioRevisionOut])
async def review_list(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)], review_status: str = Query(ScenarioStatus.PENDING_REVIEW, alias="status")):
    rows = (await db.execute(select(ScenarioRevision).where(ScenarioRevision.status == review_status).order_by(ScenarioRevision.submitted_at))).scalars().all()
    return [_revision_out(row, await _revision_data(db, row.id)) for row in rows]


@admin_router.post("/{scenario_id}/approve", response_model=ScenarioRevisionOut)
async def review_approve(scenario_id: UUID, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(CreatorScenario, scenario_id)
    revision = await db.scalar(select(ScenarioRevision).where(ScenarioRevision.scenario_id == scenario_id, ScenarioRevision.status == ScenarioStatus.PENDING_REVIEW))
    if scenario is None or revision is None: raise HTTPException(404, "待审核异闻不存在")
    revision.status, revision.reviewed_by, revision.reviewed_at, revision.published_at = ScenarioStatus.PUBLISHED, admin.id, now(), now()
    scenario.current_revision_id, scenario.work_revision_id = revision.id, None
    await db.commit(); await db.refresh(revision)
    return _revision_out(revision, await _revision_data(db, revision.id))


@admin_router.post("/{scenario_id}/reject", response_model=ScenarioRevisionOut)
async def review_reject(scenario_id: UUID, payload: dict, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    scenario = await db.get(CreatorScenario, scenario_id)
    revision = await db.scalar(select(ScenarioRevision).where(ScenarioRevision.scenario_id == scenario_id, ScenarioRevision.status == ScenarioStatus.PENDING_REVIEW))
    reason = str(payload.get("reason", "")).strip()
    if scenario is None or revision is None: raise HTTPException(404, "待审核异闻不存在")
    if not reason: raise HTTPException(400, "驳回原因不能为空")
    revision.status, revision.reviewed_by, revision.reviewed_at, revision.review_reason = ScenarioStatus.REJECTED, admin.id, now(), reason
    scenario.work_revision_id = None
    await db.commit(); await db.refresh(revision)
    return _revision_out(revision, await _revision_data(db, revision.id))


__all__ = ["admin_router", "creator_router", "public_router", "scenario_query", "worldline_query"]
