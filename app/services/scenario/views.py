"""小天下集对外视图的纯函数：脱敏公开形状、看破卡片与上帝门控（路由端点与 flows 共用）。"""

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


def guess_cards(progress: ScenarioRosterProgress | None, abilities: list[dict]) -> list[dict]:
    existing = list(progress.cracked_cards or []) if progress else []
    if not existing:
        return [{"index": index, "name": ability.get("name", ""), "effect": ability.get("effect", ""), "cracked": False, "feedback": []} for index, ability in enumerate(abilities, 1)]
    cards = []
    for index, ability in enumerate(abilities, 1):
        old = existing[index - 1] if index - 1 < len(existing) else {}
        cards.append({
            "index": index,
            "name": ability.get("name", old.get("name", "")),
            "effect": ability.get("effect", old.get("effect", "")),
            "cracked": bool(old.get("cracked")),
            "feedback": list(old.get("feedback") or []),
            "matched": list(old.get("matched") or []),
            "missing": old.get("missing", ""),
            "cracked_round": old.get("cracked_round"),
            "verifies": list(old.get("verifies") or []),
        })
    return cards


def god_unlocked(progress: ScenarioRosterProgress | None, abilities: list[dict]) -> bool:
    """上帝视角解锁：该挑战者对本阵容全部奇术均已看破（逐阵容累积进度，解锁后永久开放）。"""
    cards = guess_cards(progress, abilities)
    return bool(cards) and all(bool(card.get("cracked")) for card in cards)


def visible_turn(message: dict, *, unlocked: bool) -> dict:
    """挑战者可见的回合形状：永远只含己方视角正文；上帝全文仅在看破全部后携带（守方正文不给）。"""
    if message.get("role") != "views":
        return message
    visible = {key: value for key, value in message.items() if key not in {"guardian_text", "omniscient"}}
    if unlocked:
        visible["omniscient"] = message.get("omniscient", "")
    return visible
