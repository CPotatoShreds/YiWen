"""小天下集对外视图的纯函数：脱敏公开形状、看破卡片与视角判定（路由端点与 flows 共用）。

视角由两条**互不相关**的判据决定，任何一处都不得把它们合成一个布尔：

- 知识状态 ``sees_all()``：这套刻印的奇术，该观看者是否全部知晓。刻印作者恒为已知
  （奇术是他自己写的）；其余人取决于对该刻印的累积看破进度。
- 侧别 ``side``：这一局里观看者是谁 —— ``challenger`` / ``guardian`` / ``both``
  （挑战者恰好就是刻印作者，即试炼局）。侧别只决定收发哪几段正文。

"这一局算不算统计"（``ScenarioChallengeRun.is_trial``）是第三件事，与上面两条无关：
试炼局不计入胜负、挑战次数、猜词次数与首胜均值，但它不决定任何可见性。
"""

from app.models.scenario_domain import ScenarioRosterProgress


def public_verdict(value: object) -> str:
    verdict = str(value or "")
    return "不确定" if verdict == "不能确定" else verdict


def public_cards(cards: list[dict] | None) -> list[dict]:
    result = []
    for index, card in enumerate(cards or [], 1):
        cracked = bool(card.get("cracked"))
        item = {"index": card.get("index", index), "cracked": cracked}
        if cracked:
            item.update({"name": card.get("name", ""), "effect": card.get("effect", "")})
        feedback = []
        for entry in card.get("feedback") or []:
            if isinstance(entry, dict):
                feedback.append({"text": str(entry.get("text", "")), "verdict": public_verdict(entry.get("verdict")), "round": entry.get("round")})
        if feedback:
            item["feedback"] = feedback
        result.append(item)
    return result


def public_guess_rounds(rounds: list[dict] | None) -> list[dict]:
    """公开累计猜词记录，过滤内部缺口与模型诊断字段。"""
    output = []
    for item in rounds or []:
        if not isinstance(item, dict):
            continue
        output.append({
            "id": item.get("id", ""),
            "challenge_id": item.get("challenge_id", ""),
            "challenge_number": item.get("challenge_number"),
            "text": item.get("text", ""),
            "attempt": item.get("attempt", 0),
            "status": item.get("status", "complete"),
            "atoms": [
                {"index": atom.get("index", index + 1), "text": str(atom.get("text", "")), "status": atom.get("status", "ready")}
                for index, atom in enumerate(item.get("atoms", []))
                if isinstance(atom, dict)
            ],
            "matches": [
                {
                    "atom_index": match.get("atom_index"),
                    "card_index": match.get("card_index"),
                    "status": match.get("status", "complete"),
                    "text": str(match.get("text", match.get("snippet", ""))),
                    "verdict": public_verdict(match.get("verdict", "不能确定")),
                }
                for match in item.get("matches", [])
                if isinstance(match, dict)
            ],
            "comments": [
                {"index": group.get("index", 0), "items": [{"text": atom.get("text", ""), "verdict": public_verdict(atom.get("verdict"))} for atom in group.get("items", [])]}
                for group in item.get("comments", []) if isinstance(group, dict)
            ],
            "created_at": item.get("created_at"),
        })
    return output


def guess_cards(progress: ScenarioRosterProgress | None, abilities: list[dict], *, owner_view: bool = False) -> list[dict]:
    """看破卡片：与刻印奇术按 position 对齐。

    ``owner_view``（观看者就是这套刻印的作者）恒为已看破——奇术是他自己写的，不存在"未看破"。
    这是视图层事实，不写回 progress：作者的看破状态不该被自挑战污染，也不该反过来
    影响其他挑战者的进度。
    """
    existing = [] if owner_view else (list(progress.cracked_cards or []) if progress else [])
    if not existing:
        return [{"index": index, "name": ability.get("name", ""), "effect": ability.get("effect", ""), "cracked": owner_view, "feedback": []} for index, ability in enumerate(abilities, 1)]
    cards = []
    for index, ability in enumerate(abilities, 1):
        old = existing[index - 1] if index - 1 < len(existing) else {}
        cards.append({
            "index": index,
            "name": ability.get("name", old.get("name", "")),
            "effect": ability.get("effect", old.get("effect", "")),
            "cracked": owner_view or bool(old.get("cracked")),
            "feedback": list(old.get("feedback") or []),
            "matched": list(old.get("matched") or []),
            "missing": old.get("missing", ""),
            "cracked_round": old.get("cracked_round"),
            "verifies": list(old.get("verifies") or []),
        })
    return cards


def sees_all(progress: ScenarioRosterProgress | None, abilities: list[dict], *, owner_view: bool = False) -> bool:
    """推演全文是否可读：刻印作者恒可读；其余人需看破该刻印全部奇术（累积进度，永久开放）。

    ``owner_view`` 是"观看者是否为本刻印作者"，由调用方按 roster.owner_id 现算，
    不复用 ``is_trial``（后者只管统计口径，见模块 docstring）。
    """
    cards = guess_cards(progress, abilities, owner_view=owner_view)
    return bool(cards) and all(bool(card.get("cracked")) for card in cards)


def visible_turn(message: dict, *, side: str, unlocked: bool) -> dict:
    """按侧别裁剪回合：刻印正文只发给 ``side="both"``（自己打自己）；推演全文仅在 unlocked 时附加。"""
    if message.get("role") != "views":
        return message
    hidden = {"omniscient"} if side == "both" else {"guardian_text", "omniscient"}
    visible = {key: value for key, value in message.items() if key not in hidden}
    if unlocked:
        visible["omniscient"] = message.get("omniscient", "")
    return visible
