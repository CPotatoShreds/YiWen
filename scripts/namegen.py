"""异闻师 / 奇人 名字生成器（词库组合，零依赖，可 seed 复现）。

两段式：意象前缀 × 称号后缀 → 异闻师称号名；姓氏 × 名 → 奇人人名。
- gen_username()      异闻师用户名（3~5 字，如 赤焰君临 / 霜语者 / 星屑收集者）
- gen_loadout_name()  奇人人名（2~4 字，如 沈青梧 / 温沉舟 / 百里含章）
- gen_loadout_style() 奇人战斗风格（四字短语，如 远程狙杀）

用法：uv run python -m scripts.namegen --count 10 [--seed 1]
"""

from __future__ import annotations

import argparse
import random

# ---- 意象前缀（2 字）：称号的"根" ----
PREFIX = [
    "赤焰", "霜语", "虚空", "千面", "星屑", "影流", "深渊", "碧海", "苍穹", "幽冥",
    "焚天", "寒渊", "风雷", "琉璃", "墨染", "云隐", "月照", "星坠", "雷殛", "冰魄",
    "焰心", "暗影", "灵枢", "万象", "沧海", "断崖", "寂夜", "流萤", "逐风", "破晓",
    "沉渊", "太虚", "天罡", "梦魇", "归墟", "烛龙", "白泽", "鲲鹏", "朱雀", "玄策",
    "残照", "浮光", "惊鸿", "燎原", "裂空", "龙渊", "落霞", "暮霭", "逆鳞", "观澜",
]

# 可接单字"者"的动词性前缀（霜语者 / 驭风者 这类读起来顺的）
_VERBISH = {
    "霜语", "驭风", "观星", "听澜", "逐风", "燎原", "浮光", "逐日",
    "破阵", "引潮", "执火", "衔烛", "踏月", "摘星", "望舒", "听雨",
}

# ---- 称号后缀：2 字重 / 3 字轻 ----
SUFFIX_2 = [
    "君临", "旅人", "织影", "主宰", "回响", "之主", "行者", "织梦", "驭风", "临渊",
    "逐日", "观星", "引潮", "破阵", "执火", "衔烛", "踏月", "摘星", "听澜", "望舒",
    "倚楼", "折桂", "断水", "掠影", "归舟", "守寂",
]

SUFFIX_3 = [
    "摆渡人", "收集者", "守夜人", "聆听者", "摘星手", "踏月客", "断水流",
    "噬魂者", "抚琴人", "观星者", "逐风者", "燎原者", "浮光者", "破阵者", "引潮者",
]

# ---- 奇人人名：姓 × 名 ----
SURNAMES_1 = [
    "沈", "顾", "楚", "苏", "洛", "温", "陆", "白", "叶", "江", "燕", "裴", "萧",
    "韩", "林", "唐", "宋", "秦", "纪", "祁", "简", "闻", "谢", "周", "墨", "陶",
]
SURNAMES_2 = ["百里", "慕容", "东方", "司马", "上官", "夏侯", "端木", "尉迟"]

GIVEN_2 = [
    "青梧", "长风", "云澜", "暮雪", "九尘", "沉舟", "忘机", "子墨", "惊鸿", "若水",
    "无咎", "拾遗", "听澜", "望舒", "扶摇", "偃月", "疏影", "折桂", "观棋", "点灯",
    "拾芥", "听雨", "眠月", "执明", "含章", "清让", "怀瑾", "时遇", "昭雪", "晏清",
    "无涯", "未央", "南山", "北望", "东篱", "西楼", "归晚", "晚棠", "揽星", "拂晓",
    "夜阑", "云岫", "烟汀", "霜降", "春和", "景明", "孤鸿", "照野", "栖梧", "离墨",
]
GIVEN_1 = ["澜", "澄", "澈", "修", "玥", "笙", "樽", "砚", "墨", "鹤", "云", "川", "霜"]

# ---- 奇人战斗风格 ----
STYLES = [
    "刚猛近战", "阴柔控场", "远程狙杀", "灵动游走", "防御壁垒", "诡术缠斗",
    "元素爆破", "精神压制", "暗杀奇袭", "幻术扰敌", "愈疗辅助", "召唤制敌",
    "音律惑心", "剧毒侵蚀", "冰火双修", "身法宗师", "空间位移", "时间干涉",
]


def gen_username(rng: random.Random) -> str:
    """异闻师称号名：4 字为主（2+2），混 3 字「X者」与 5 字（2+3）。"""
    prefix = rng.choice(PREFIX)
    roll = rng.random()
    if roll < 0.70:
        return prefix + rng.choice(SUFFIX_2)
    if roll < 0.88:
        return prefix + rng.choice(SUFFIX_3)
    verb = rng.choice(sorted(_VERBISH))
    return verb + "者"


def gen_loadout_name(rng: random.Random) -> str:
    """奇人人名：姓氏（1~2 字）× 名（1~2 字）。"""
    surname = rng.choice(SURNAMES_2) if rng.random() < 0.15 else rng.choice(SURNAMES_1)
    given = rng.choice(GIVEN_2) if rng.random() < 0.85 else rng.choice(GIVEN_1)
    return surname + given


def gen_loadout_style(rng: random.Random) -> str:
    return rng.choice(STYLES)


def gen_distinct(fn, rng: random.Random, n: int) -> list[str]:
    """生成 n 个互不重复的名字；撞车则重抽。"""
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < n:
        name = fn(rng)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="预览异闻师/奇人名字组合")
    parser.add_argument("--count", type=int, default=10, help="生成多少位异闻师")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（固定复现）")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    print(f"{'异闻师':<10} {'奇人数量':<6} 奇人名")
    print("-" * 48)
    for uname in gen_distinct(gen_username, rng, args.count):
        n_loadouts = rng.randint(1, 3)
        lnames = gen_distinct(gen_loadout_name, rng, n_loadouts)
        print(f"{uname:<10} {n_loadouts:<6} {', '.join(lnames)}")


if __name__ == "__main__":
    main()
