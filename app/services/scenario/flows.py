"""小天下集挑战的后台编排：奇术比对、推演/叙述/检定三站、猜词配对与主动检定。

由 `app.core.tasks.dispatch`（inline 模式）或 arq worker 经 `tasks_registry` 按名调用；
与 HTTP 壳（api/routes/scenario_domain）只通过 dispatch/注册表衔接，不反向依赖路由层。
三站解耦（docs/plans/2026-10-02-deduction-narration-split.md）：推演站产全文落
`deduction_text`（站间 checkpoint）后扇出叙述+检定两站，段间只经 DB 传递数据；
叙述/检定各自完成置 derived 标志，后到者执行终局结算（_settle_if_ready）。
"""

import asyncio
import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.tasks import dispatch
from app.db.base import async_session_factory
from app.models.scenario_domain import ScenarioChallengeRun, ScenarioRoster, ScenarioRosterProgress
from app.services.ability.pair_comparison import compare_pair
from app.services.guess.pipeline import run_guess_matching, run_guess_split, run_guess_verification
from app.services.llm.reliability import ainvoke_with_reliability, astream_with_reliability
from app.services.nodes.ability.pair_judge import build_pair_judge_chain, render_pair_report
from app.services.nodes.scenario import (
    build_scenario_deduction_llm,
    build_scenario_judge_llm,
    build_scenario_narration_challenger_stream_llm,
    build_scenario_narration_guardian_stream_llm,
)
from app.services.scenario.stream import get_scenario_stream
from app.services.scenario.views import (
    deduction_unlocked,
    guess_cards,
    public_verdict,
    visible_turn,
)


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def compare_scenario_abilities(challenger: list[dict], guardian: list[dict], challenge_id: UUID) -> str:
    """逐对奇术比对：Redis 缓存优先，未命中在并发闸内调比对节点。"""
    pairs = [(left, right) for left in challenger for right in guardian]
    if not pairs:
        return ""
    judge = build_pair_judge_chain()
    semaphore = asyncio.Semaphore(16)

    async def compare(left: dict, right: dict):
        try:
            return await compare_pair(
                left=left, right=right, judge=judge, semaphore=semaphore, challenge_id=challenge_id
            )
        except Exception:  # noqa: BLE001 - 比对不可用时仍可进入情景推演
            return None

    verdicts = [item for item in await asyncio.gather(*(compare(left, right) for left, right in pairs)) if item is not None]
    return render_pair_report(verdicts)


async def prepare_scenario_challenge(challenge_id: UUID) -> None:
    """创建挑战后自动完成奇术比对；期间不占用请求数据库连接。"""
    stream = get_scenario_stream(challenge_id)
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "preparing":
                return
            challenger_abilities = list(challenge.challenger_snapshot.get("abilities", []))
            guardian_abilities = list(challenge.roster_snapshot.get("abilities", []))
        report = await compare_scenario_abilities(challenger_abilities, guardian_abilities, challenge_id)
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "preparing":
                return
            challenge.derived = {**(challenge.derived or {}), "comparison_report": report}
            challenge.status = "active"
            await db.commit()
    except Exception:  # noqa: BLE001 - 后台失败需要向挑战者明确交代
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is not None and challenge.status == "preparing":
                challenge.status = "failed"
                await db.commit()
        await stream.publish({"type": "error", "status": "failed", "message": "奇术比对未能完成，请重新开始挑战。"})


async def stream_narration(*, stream, side: str, chain, kwargs: dict, challenge_id: UUID) -> str:
    parts: list[str] = []
    async for chunk in astream_with_reliability(
        chain,
        kwargs,
        operation=f"scenario_narration_{side}",
        max_retries=1,
        trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
    ):
        text = str(chunk)
        parts.append(text)
        await stream.publish({"type": "narration_chunk", "side": side, "text": text}, replay=False)
    return "".join(parts).strip()


def _failed_challenge(challenge_id: UUID, message: str, *, keep: bool = False) -> Awaitable[None]:
    """后台站失败：置 failed 并广播 SSE error（推演 checkpoint 默认随失败语义保留在库）。"""
    async def _mark() -> None:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is not None and challenge.status == "resolving":
                challenge.status = "failed"
                await db.commit()
        await get_scenario_stream(challenge_id).publish({"type": "error", "status": "failed", "message": message})
    return _mark()


async def run_scenario_deduction(challenge_id: UUID) -> None:
    """推演站：全知推演全文流式生成（只播字数进度），落 deduction_text 站间 checkpoint 后扇出叙述+检定。"""
    stream = get_scenario_stream(challenge_id)
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "resolving" or (challenge.deduction_text or "").strip():
                return  # 状态不符或已有 checkpoint（幂等：重派/续跑不重推）
            scenario = dict(challenge.scenario_snapshot)
            roster = dict(challenge.roster_snapshot)
            challenger = dict(challenge.challenger_snapshot)
            messages = list(challenge.messages)
            comparison_report = str((challenge.derived or {}).get("comparison_report", ""))
            action = str(messages[-1].get("text", "")) if messages else ""

        action_fact = f"挑战者奇人“{challenger.get('character_name', '挑战者奇人')}”执行行动意图：\n“{action}”"
        god_kwargs = {
            "volume": scenario.get("name", "小天下集卷"),
            "subtitle": scenario.get("subtitle", ""),
            "introduction": scenario.get("introduction", ""),
            "rules": "\n".join(f"- {rule}" for rule in scenario.get("rules", [])),
            "judgement_rules": "\n".join(f"- {rule}" for rule in scenario.get("judgement_rules", [])),
            "victory_condition": scenario.get("victory_condition", ""),
            "tianji": "（当前卷未配置额外天机）",
            "opening": scenario.get("background", ""),
            "brief": roster.get("guidance", ""),
            "defenders": [roster],
            "challengers": [challenger],
            "comparison_report": comparison_report or "（无直接冲突的奇术比对结论）",
            "action": action_fact,
        }
        # 推演流式：真实文本不出站，只发累计字数供前端合成遮挡进度
        deduction_parts: list[str] = []
        deduction_chars = 0
        async for chunk in astream_with_reliability(
            build_scenario_deduction_llm(),
            god_kwargs,
            operation="scenario_deduction",
            max_retries=1,
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
        ):
            text = str(chunk)
            deduction_parts.append(text)
            deduction_chars += len(text)
            await stream.publish({"type": "deduction_progress", "chars": deduction_chars}, replay=False)
        deduction = "".join(deduction_parts).strip()

        async with async_session_factory() as db:
            challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
            if challenge is None or challenge.status != "resolving" or (challenge.deduction_text or "").strip():
                return  # 行锁下复核，防并发双推
            challenge.deduction_text = deduction
            await db.commit()
        await dispatch("scenario_narration", challenge_id)
        await dispatch("scenario_judgement", challenge_id)
    except Exception:  # noqa: BLE001 - 推演站失败整场失败（checkpoint 未落，天然为空）
        await _failed_challenge(challenge_id, "本次推演未能完成，请重新开始挑战。")


async def run_scenario_narration(challenge_id: UUID) -> None:
    """叙述站：读推演 checkpoint，并发产出双侧叙述流式转写；置完成标志，双齐则结算。"""
    stream = get_scenario_stream(challenge_id)
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "resolving":
                return
            deduction = challenge.deduction_text or ""
            if not deduction.strip():
                return  # 推演 checkpoint 未就绪（时序异常/误派），无输入可跑
            scenario = dict(challenge.scenario_snapshot)
            roster = dict(challenge.roster_snapshot)
            challenger = dict(challenge.challenger_snapshot)

        info = json.dumps({"scenario": scenario, "roster": roster, "challenger": challenger}, ensure_ascii=False)
        common = {
            "challenger_name": challenger.get("character_name", "挑战者奇人"),
            "guardian_name": roster.get("character_name", "守方奇人"),
            "opening": scenario.get("background", ""),
            "god": deduction,  # key 为提示词占位符（冻结区文本），不可改名
            "info": info,
        }
        challenger_view, guardian_view = await asyncio.gather(
            stream_narration(stream=stream, side="challenger", chain=build_scenario_narration_challenger_stream_llm(), kwargs=common, challenge_id=challenge_id),
            stream_narration(stream=stream, side="guardian", chain=build_scenario_narration_guardian_stream_llm(), kwargs=common, challenge_id=challenge_id),
        )
        async with async_session_factory() as db:
            challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
            if challenge is None or challenge.status != "resolving":
                return
            if (challenge.derived or {}).get("narration_done"):
                return  # 已完成（重入）
            challenge.derived = {
                **(challenge.derived or {}),
                "narration_texts": {"challenger": challenger_view, "guardian": guardian_view},
                "narration_done": True,
            }
            await db.commit()
        await _settle_if_ready(challenge_id, stream)
    except Exception:  # noqa: BLE001 - 叙述站失败整场失败（推演 checkpoint 保留审计）
        await _failed_challenge(challenge_id, "本次推演未能完成，请重新开始挑战。")


async def run_scenario_judgement(challenge_id: UUID) -> None:
    """检定站：读推演 checkpoint 与卷规则，结构化判定胜负；置完成标志，双齐则结算。"""
    stream = get_scenario_stream(challenge_id)
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None or challenge.status != "resolving":
                return
            deduction = challenge.deduction_text or ""
            if not deduction.strip():
                return  # 推演 checkpoint 未就绪
            scenario = dict(challenge.scenario_snapshot)

        judge_kwargs = {
            "volume": scenario.get("name", "小天下集卷"),
            "rules": "\n".join(f"- {rule}" for rule in scenario.get("rules", [])),
            "victory_condition": scenario.get("victory_condition", ""),
            "judgement_rules": "\n".join(f"- {rule}" for rule in scenario.get("judgement_rules", [])),
            "opening": scenario.get("background", ""),
            "history": deduction,
        }
        judgement = await ainvoke_with_reliability(
            build_scenario_judge_llm(),
            judge_kwargs,
            operation="scenario_goal_judgement",
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
        )
        async with async_session_factory() as db:
            challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
            if challenge is None or challenge.status != "resolving":
                return
            if (challenge.derived or {}).get("judgement_done"):
                return  # 已完成（重入）
            challenge.derived = {
                **(challenge.derived or {}),
                "judgement_result": {"achieved": bool(judgement.achieved), "reason": judgement.reason},
                "judgement_done": True,
            }
            await db.commit()
        await _settle_if_ready(challenge_id, stream)
    except Exception:  # noqa: BLE001 - 检定站失败整场失败（推演 checkpoint 保留审计）
        await _failed_challenge(challenge_id, "本次推演未能完成，请重新开始挑战。")


async def _settle_if_ready(challenge_id: UUID, stream) -> None:
    """后到者结算：行锁下叙述/检定双标志齐则一次事务写 turn、定胜负，随后广播门控后的终局事件。"""
    async with async_session_factory() as db:
        challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
        if challenge is None or challenge.status != "resolving":
            return
        derived = challenge.derived or {}
        if not (derived.get("narration_done") and derived.get("judgement_done")):
            return  # 先到者：标志已落，等对方触发结算
        narration = derived.get("narration_texts") or {}
        judge = derived.get("judgement_result") or {}
        challenger_view = str(narration.get("challenger", ""))
        guardian_view = str(narration.get("guardian", ""))
        achieved = bool(judge.get("achieved"))
        reason = str(judge.get("reason", ""))
        deduction = challenge.deduction_text or ""
        turn = {
            "role": "views",
            "challenger_text": challenger_view,
            "guardian_text": guardian_view,
            "omniscient": deduction,
            "achieved": achieved,
            "reason": reason,
            "created_at": now().isoformat(),
        }
        challenge.messages = [*challenge.messages, turn]
        challenge.won = achieved
        challenge.finished_at = now()
        challenge.derived = {
            key: value
            for key, value in {**derived, "achieved": achieved, "reason": reason}.items()
            if key not in {"narration_done", "judgement_done", "narration_texts", "judgement_result"}
        }
        challenge.status = "won" if achieved else "lost"
        if not challenge.is_preview and not challenge.guess_granted:
            progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
            if progress:
                progress.guess_credits += 3
            challenge.guess_granted = True
        if achieved and not challenge.is_preview:
            progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
            if progress and progress.first_victory_challenges is None:
                progress.first_victory_challenges = progress.attempts
                values = list((await db.execute(select(ScenarioRosterProgress.first_victory_challenges).where(ScenarioRosterProgress.roster_id == challenge.roster_id, ScenarioRosterProgress.first_victory_challenges.is_not(None)))).scalars())
                roster_row = await db.get(ScenarioRoster, challenge.roster_id)
                if roster_row and values:
                    roster_row.first_victory_avg_challenges = sum(values) / len(values)
                    roster_row.completed_count = len(values)
        roster_abilities = list(challenge.roster_snapshot.get("abilities", []))
        roster_id, challenger_id, is_preview = challenge.roster_id, challenge.challenger_id, challenge.is_preview
        await db.commit()

    # turn 按侧拆分并施推演门控：挑战者侧永远只含己方正文；推演全文仅在看破全部后携带（试炼为作者自看）
    async with async_session_factory() as db:
        progress = await db.get(ScenarioRosterProgress, {"roster_id": roster_id, "challenger_id": challenger_id})
        unlocked = is_preview or deduction_unlocked(progress, roster_abilities)
    await stream.publish({"type": "turn", "side": "challenger", "turn": visible_turn(turn, unlocked=unlocked)}, replay=False)
    await stream.publish(
        {"type": "turn", "side": "guardian", "turn": {"role": "guardian", "text": guardian_view, "created_at": turn["created_at"]}},
        replay=False,
    )
    await stream.publish({"type": "done", "status": "won" if achieved else "lost"})


async def save_guess_split(challenge_id: UUID, round_id: str, atoms: list[str]) -> None:
    async with async_session_factory() as db:
        # FOR UPDATE 行锁替代旧进程内锁：多实例下由 DB 串行化 JSON 读改写（固定先 challenge 后 progress 防死锁）
        challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
        if challenge is None:
            return
        atom_records = [{"index": index, "text": value, "status": "ready"} for index, value in enumerate(atoms, 1)]
        def update(item: dict) -> dict:
            if item.get("id") != round_id:
                return item
            return {**item, "status": "matching", "atoms": atom_records}
        challenge.guesses = [update(item) for item in challenge.guesses]
        progress = (await db.execute(select(ScenarioRosterProgress).where(ScenarioRosterProgress.roster_id == challenge.roster_id, ScenarioRosterProgress.challenger_id == challenge.challenger_id).with_for_update())).scalar_one_or_none()
        if progress:
            progress.guess_rounds = [update(item) for item in progress.guess_rounds]
        await db.commit()


async def save_guess_match(challenge_id: UUID, round_id: str, match: dict) -> None:
    """逐配对落库；旧 comments/feedback/matched 字段同步维护。"""
    async with async_session_factory() as db:
        # FOR UPDATE 行锁替代旧进程内锁（固定先 challenge 后 progress 防死锁）
        challenge = (await db.execute(select(ScenarioChallengeRun).where(ScenarioChallengeRun.id == challenge_id).with_for_update())).scalar_one_or_none()
        if challenge is None:
            return
        progress = (await db.execute(select(ScenarioRosterProgress).where(ScenarioRosterProgress.roster_id == challenge.roster_id, ScenarioRosterProgress.challenger_id == challenge.challenger_id).with_for_update())).scalar_one_or_none()
        cards = guess_cards(progress, challenge.roster_snapshot.get("abilities", []))
        atom_index = int(match.get("atom_index", 0))
        card_index = int(match.get("card_index", 0))
        text = str(match.get("text", match.get("snippet", ""))).strip()
        verdict = public_verdict(match.get("verdict", "不能确定"))
        public_match = {
            "atom_index": atom_index,
            "card_index": card_index,
            "status": match.get("status", "complete"),
            "text": text,
            "verdict": verdict,
        }
        if text and 1 <= card_index <= len(cards):
            card = cards[card_index - 1]
            if verdict in {"是", "部分是"} and text not in card.get("matched", []):
                card["matched"] = [*card.get("matched", []), text]
            if not any(entry.get("text") == text and entry.get("round") == round_id for entry in card.get("feedback", [])):
                card["feedback"] = [*card.get("feedback", []), {"text": text, "verdict": verdict, "round": round_id}]
        def update(item: dict) -> dict:
            if item.get("id") != round_id:
                return item
            comments = list(item.get("comments", []))
            if text and 1 <= card_index:
                group = next((entry for entry in comments if entry.get("index") == card_index), None)
                atom = {"text": text, "verdict": verdict}
                if group is None:
                    comments.append({"index": card_index, "items": [atom]})
                elif not any(existing.get("text") == text and existing.get("verdict") == verdict for existing in group.get("items", [])):
                    group["items"] = [*group.get("items", []), atom]
            return {**item, "status": "matching", "matches": [*item.get("matches", []), public_match], "comments": comments}
        challenge.guesses = [update(item) for item in challenge.guesses]
        if progress:
            progress.cracked_cards = cards
            progress.guess_rounds = [update(item) for item in progress.guess_rounds]
        await db.commit()


async def run_guess_round(challenge_id: UUID, round_id: str, text: str) -> None:
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None:
                return
            progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
            abilities = list(challenge.roster_snapshot.get("abilities", []))
            cards = guess_cards(progress, abilities)
        items = await run_guess_split(text)
        await save_guess_split(challenge_id, round_id, items)
        await run_guess_matching(
            items=items,
            abilities=abilities,
            cards=cards,
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
            on_match=lambda match: save_guess_match(challenge_id, round_id, match),
        )
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id}) if challenge else None
            if challenge:
                challenge.guesses = [{**item, "status": "complete"} if item.get("id") == round_id else item for item in challenge.guesses]
            if progress:
                progress.guess_rounds = [{**item, "status": "complete"} if item.get("id") == round_id else item for item in progress.guess_rounds]
                progress.cracked_cards = guess_cards(progress, list(challenge.roster_snapshot.get("abilities", [])))
            if challenge:
                challenge.guess_in_flight = False
            await db.commit()
    except Exception:  # noqa: BLE001 - 流式节点失败后留下可恢复的挑战状态
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge:
                progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
                challenge.guesses = [{**item, "status": "failed"} if item.get("id") == round_id else item for item in challenge.guesses]
                challenge.guess_in_flight = False
                if progress:
                    progress.guess_credits += 1
                    progress.guess_rounds = [{**item, "status": "failed"} if item.get("id") == round_id else item for item in progress.guess_rounds]
                await db.commit()


async def save_verify_result(challenge_id: UUID, card_index: int, verdict: dict) -> None:
    async with async_session_factory() as db:
        challenge = await db.get(ScenarioChallengeRun, challenge_id)
        if challenge is None:
            return
        progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
        if progress is None:
            return
        cards = guess_cards(progress, challenge.roster_snapshot.get("abilities", []))
        card = cards[card_index]
        card["verifies"] = [*card.get("verifies", []), {"round": len(progress.guess_rounds), "cracked": verdict["cracked"], "missing": verdict["missing"]}]
        if verdict["cracked"]:
            card["cracked"] = True
            card["cracked_round"] = len(progress.guess_rounds)
            card["missing"] = ""
        else:
            card["missing"] = verdict["missing"]
        progress.cracked_cards = cards
        await db.commit()


async def run_guess_verify(challenge_id: UUID) -> None:
    try:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge is None:
                return
            progress = await db.get(ScenarioRosterProgress, {"roster_id": challenge.roster_id, "challenger_id": challenge.challenger_id})
            if progress is None:
                return
            abilities = list(challenge.roster_snapshot.get("abilities", []))
            cards = guess_cards(progress, abilities)
            rounds = list(progress.guess_rounds or [])
            history = [item.get("text", "") for item in rounds]
            comments = [item.get("comments", []) for item in rounds]
        await run_guess_verification(
            history=history,
            comments=comments,
            abilities=abilities,
            cards=cards,
            round_no=len(rounds),
            trace_context={"kind": "scenario", "trace_id": str(challenge_id)},
            on_result=lambda index, verdict: save_verify_result(challenge_id, index, verdict),
        )
    finally:
        async with async_session_factory() as db:
            challenge = await db.get(ScenarioChallengeRun, challenge_id)
            if challenge:
                challenge.verify_in_flight = False
                await db.commit()
