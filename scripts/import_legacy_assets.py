"""Import owned abilities/loadouts from a restored legacy database.

The source database is read-only. Matching is done by username, so deleted or
temporary users from the old dump are ignored. Existing assets are preserved.
"""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.ability import Ability
from app.models.character import Character, CharacterAbility
from app.models.user import User


def source_url(database: str) -> str:
    return f"{settings.DATABASE_URL.rsplit('/', 1)[0]}/{database}"


async def main(database: str) -> None:
    source_engine = create_async_engine(source_url(database), poolclass=None)
    target_engine = create_async_engine(settings.DATABASE_URL, poolclass=None)
    source_session = async_sessionmaker(source_engine, expire_on_commit=False)
    target_session = async_sessionmaker(target_engine, expire_on_commit=False)

    async with source_session() as source, target_session() as target:
        current_users = {row.username: row.id for row in (await target.scalars(select(User))).all()}
        source_users = dict((await source.execute(text("select id, username from users"))).all())
        user_map = {old_id: current_users[name] for old_id, name in source_users.items() if name in current_users}
        if not user_map:
            raise SystemExit("未找到可映射的用户，未导入任何数据")

        old_abilities = (await source.execute(text("""
            select a.id, ua.user_id, a.name, a.effect, a.detail, a.understanding, a.created_at
            from user_abilities ua join abilities a on a.id = ua.ability_id
            where ua.user_id in (select id from users)
            order by ua.user_id, ua.obtained_at, a.id
        """))).mappings().all()
        old_abilities = [row for row in old_abilities if row["user_id"] in user_map]
        ability_ids: dict[tuple[int, str], str] = {}
        abilities_added = 0
        abilities_updated = 0
        for row in old_abilities:
            owner_id = user_map[row["user_id"]]
            existing = await target.get(Ability, row["id"])
            if existing is not None and existing.owner_id == owner_id:
                ability_ids[(row["user_id"], row["id"])] = existing.id
                existing.effect = row["effect"] or ""
                existing.detail = row["detail"] or ""
                existing.understanding = row["understanding"] or ""
                existing.created_at = row["created_at"] or existing.created_at
                abilities_updated += 1
                continue
            new_id = row["id"]
            if existing is not None:
                new_id = uuid4().hex
            target.add(Ability(id=new_id, owner_id=owner_id, name=(row["name"] or "")[:50], effect=row["effect"] or "", detail=row["detail"] or "", understanding=row["understanding"] or "", created_at=row["created_at"] or datetime.utcnow()))  # noqa: DTZ003 - 历史数据迁入保持原值
            ability_ids[(row["user_id"], row["id"])] = new_id
            abilities_added += 1

        old_loadouts = (await source.execute(text("""
            select id, user_id, name, style, created_at from loadouts
            order by user_id, created_at, id
        """))).mappings().all()
        old_loadouts = [row for row in old_loadouts if row["user_id"] in user_map]
        old_links = (await source.execute(text("""
            select loadout_id, ability_id from loadout_abilities order by loadout_id, added_at
        """))).mappings().all()
        links_by_loadout: dict[int, list[str]] = defaultdict(list)
        for link in old_links:
            links_by_loadout[link["loadout_id"]].append(link["ability_id"])

        existing_characters: dict[tuple[int, str], list[Character]] = defaultdict(list)
        for character in (await target.scalars(select(Character).order_by(Character.created_at, Character.id))).all():
            existing_characters[(character.owner_id, character.name)].append(character)
        characters_added = 0
        characters_updated = 0
        bindings_added = 0
        consumed_character_slots: dict[tuple[int, str], int] = defaultdict(int)
        for row in old_loadouts:
            owner_id = user_map[row["user_id"]]
            name = (row["name"] or "")[:30]
            bio = (row["style"] or "")[:500]
            candidates = existing_characters[(owner_id, name)]
            matching = [item for item in candidates if item.bio == bio]
            slot = consumed_character_slots[(owner_id, name)]
            existing = matching[slot] if slot < len(matching) else None
            consumed_character_slots[(owner_id, name)] += 1
            if existing is None:
                character = Character(id=uuid4(), owner_id=owner_id, name=name, bio=bio, created_at=row["created_at"] or datetime.utcnow())  # noqa: DTZ003 - 历史数据迁入保持原值
                target.add(character)
                await target.flush()
                candidates.append(character)
                characters_added += 1
            else:
                character = existing
                character.bio = bio
                characters_updated += 1
            await target.execute(delete(CharacterAbility).where(CharacterAbility.character_id == character.id))
            used: set[str] = set()
            for old_id in links_by_loadout[row["id"]]:
                new_id = ability_ids.get((row["user_id"], old_id))
                if new_id and new_id not in used and len(used) < 4:
                    target.add(CharacterAbility(character_id=character.id, ability_id=new_id, position=len(used) + 1))
                    used.add(new_id); bindings_added += 1
        await target.commit()
        print(f"用户映射 {len(user_map)}；奇术新增 {abilities_added}、更新 {abilities_updated}；奇人新增 {characters_added}、更新 {characters_updated}；重建绑定 {bindings_added}")
    await source_engine.dispose()
    await target_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="ynfight_backup", help="已恢复的备份数据库名")
    asyncio.run(main(parser.parse_args().database))
