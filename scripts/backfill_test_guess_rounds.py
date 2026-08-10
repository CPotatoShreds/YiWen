"""一次性回填脚本：从 llm_traces 重建老测试对局（无 rounds 数据）的按轮次猜词记录。

老对局 cards 只存累计 matched + 最终 cracked，没有 per-round 的原子条目/新增/检定原因。
本脚本按 trace_id 读取 kind='test_guess' 的 trace，按 id 升序视为轮序，重建：
  - 每轮 split 输出 items（原子叙述）
  - 每轮 pair 输出 valuable+snippet（本轮新增，来自 response）
  - 每轮 verify 输出 guessed+reason
  - cracked_round（取首个 guessed=True 的轮次）

写回 test_battle_guesses.cards 的 rounds/verifies/cracked_round 字段。

用法：
  .venv/Scripts/python.exe scripts/backfill_test_guess_rounds.py [--dry-run]

幂等：只处理 cards 里已有任一卡含 "rounds" 键的会跳过（新流程已写），无 rounds 的才重建。
"""

from __future__ import annotations

import argparse
import json
import re

import psycopg

DB = "postgresql://ynfight:ynfight@localhost:5432/ynfight"

ITEM_RE = re.compile(r"败方道出的猜测片段：\s*\n?([^\n]+)")
ABILITY_RE = re.compile(r"对家实际使用的奇术（[^\n]*）：\s*([^\n]+)")


def items_from_trace(req: object) -> list[str]:
    resp = req
    if not isinstance(resp, dict):
        return []
    items = resp.get("items") or []
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("text"):
            out.append(it["text"])
    return out


def parse_pair(req: object) -> tuple[str, str]:
    """从 pair trace 的 system 提示词里提取 (item_text, ability_text)。"""
    if not isinstance(req, list) or not req:
        return "", ""
    sys = ""
    for m in req:
        if isinstance(m, dict) and m.get("type") == "system":
            sys = str(m.get("content") or "")
            break
    item = ITEM_RE.search(sys)
    ability = ABILITY_RE.search(sys)
    return (item.group(1).strip() if item else "", ability.group(1).strip() if ability else "")


def parse_verify(req: object) -> str:
    """从 verify trace 的 system 提示词里提取能力文本（用于按能力分组）。"""
    return parse_pair(req)[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印将要回填的行，不写库")
    parser.add_argument("--force", action="store_true", help="跳过已含 rounds 的行，强制重填（用于修正回填逻辑）")
    args = parser.parse_args()

    conn = psycopg.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT battle_id, cards::text FROM test_battle_guesses ORDER BY battle_id")
    rows = cur.fetchall()

    changed = 0
    skipped = 0
    for battle_id, cards_txt in rows:
        cards = json.loads(cards_txt)
        if not cards or (not args.force and any("rounds" in c for c in cards)):
            skipped += 1
            continue

        cur.execute(
            "SELECT id, operation, request_json, response_json FROM llm_traces "
            "WHERE kind='test_guess' AND trace_id=%s ORDER BY id",
            (str(battle_id),),
        )
        traces = cur.fetchall()

        # 按 id 顺序切轮：遇到 split 起新轮，直到下一个 split 之前的所有 trace 属于该轮
        rounds: list[dict] = []
        current: dict | None = None
        for _tid, op, req, resp in traces:
            if op == "guess_split":
                current = {"items": items_from_trace(resp), "pairs": [], "verifies": []}
                rounds.append(current)
            elif current is not None and op == "guess_pair":
                item, ability = parse_pair(req)
                if not item or not ability:
                    continue
                r = resp if isinstance(resp, dict) else {}
                current["pairs"].append(
                    {"item": item, "ability": ability, "valuable": bool(r.get("valuable")), "snippet": str(r.get("snippet") or "")}
                )
            elif current is not None and op == "guess_verify":
                ability = parse_verify(req)
                r = resp if isinstance(resp, dict) else {}
                current["verifies"].append(
                    {"ability": ability, "guessed": bool(r.get("guessed")), "reason": str(r.get("reason") or "")}
                )

        if not rounds:
            skipped += 1
            continue

        cur.execute("SELECT used_abilities::text FROM test_battle_guesses WHERE battle_id=%s", (battle_id,))
        used_row = cur.fetchone()
        used = [u["name"] for u in json.loads(used_row[0] or "[]")]

        # 用 used_abilities 名称对齐 pair/verify 的 ability 文本（名称前缀匹配）
        def norm(s: str) -> str:
            return s.replace(" ", "")

        def card_matches(ability_txt: str, ci: int, used_names: list[str]) -> bool:
            if ci >= len(used_names) or not ability_txt:
                return False
            return norm(ability_txt).startswith(norm(used_names[ci])) or norm(used_names[ci]).startswith(norm(ability_txt))

        aligned: list[dict] = []
        for ci, card in enumerate(cards):
            # 只保留有价值命中（解锁了新增条目的配对），未命中的不留占位
            card_rounds = [
                {
                    "round": ri,
                    "items": rnd["items"],
                    "pairs": [p for p in rnd["pairs"] if p["valuable"] and card_matches(p["ability"], ci, used)],
                }
                for ri, rnd in enumerate(rounds, start=1)
            ]
            verifies = []
            for ri, rnd in enumerate(rounds, start=1):
                for v in rnd["verifies"]:
                    if card_matches(v["ability"], ci, used):
                        verifies.append({"round": ri, "guessed": v["guessed"], "reason": v["reason"]})
                        break
            cracked_round = next((v["round"] for v in verifies if v["guessed"]), None)
            card["rounds"] = card_rounds
            card["verifies"] = verifies
            if card["cracked"]:
                card["cracked_round"] = cracked_round
            aligned.append(card)

        if not args.dry_run:
            cur.execute(
                "UPDATE test_battle_guesses SET cards=%s WHERE battle_id=%s",
                (json.dumps(aligned, ensure_ascii=False), battle_id),
            )
        changed += 1
        print(f"battle #{battle_id}: {len(rounds)} 轮, {len(cards)} 卡 -> 回填")

    if args.dry_run:
        print(f"[dry-run] 将回填 {changed} 行，跳过 {skipped} 行")
    else:
        conn.commit()
        print(f"已回填 {changed} 行，跳过 {skipped} 行")


if __name__ == "__main__":
    main()
