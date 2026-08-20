"""转写流内审查：在对家异能名单上做关键词遮蔽，边生成边净化上屏文本。

流式转写的敏感内容是**对家异能的确切名称/效果**（其余细微泄露由事后校验节点兜底）。
denylist 取对家异能 name/effect/detail/understanding 的原文；命中即同长「□」替换，
保证索引稳定。发布时保留一个安全窗口（=最长词长，上限 WINDOW_CAP），整段 buffer 先遮蔽
再发布前半——任何完整落入 buffer 的词在跨发布边界时其前缀也是 □（不泄露）；正在生成中、
未完整的词必然起于窗口之后，不会发布。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

# 安全窗口上限：兼顾 TTFT 与防泄露。超长词（如长效果原文）只在完整落入 buffer 时被遮蔽，
# 其前缀无法流内兜住——由事后校验节点修复存储稿。
WINDOW_CAP = 12


def build_denylist(abilities) -> list[str]:
    """从异能对象收集敏感词：名称/效果/详细解释/因果槽位原文，去空去重。"""
    seen: set[str] = set()
    for a in abilities:
        for field in ("name", "effect", "detail", "understanding"):
            text = getattr(a, field, None)
            if isinstance(text, str) and text.strip():
                seen.add(text.strip())
    return sorted(seen, key=len, reverse=True)


def mask_terms(text: str, terms: list[str]) -> str:
    """把 text 中所有命中的敏感词替换为同长「□」（先长后短，防止子串重复替换）。"""
    for t in terms:
        if t in text:
            text = text.replace(t, "□" * len(t))
    return text


async def mask_stream_chunks(agen: AsyncIterator[str], terms: list[str]) -> AsyncIterator[str]:
    """流式遮蔽生成器：保持安全窗口，逐块吐出净化后的增量文本。

    对长于窗口上限的词尽力而为（完整落入 buffer 即遮蔽）；窗口内保护 ≤WINDOW_CAP 词长。
    """
    max_term = min(max((len(t) for t in terms), default=0), WINDOW_CAP)
    buffer = ""
    published = 0
    async for chunk in agen:
        if not chunk:
            continue
        buffer += chunk
        pub_end = max(published, len(buffer) - max_term)
        if pub_end > published:
            yield mask_terms(buffer, terms)[published:pub_end]
            published = pub_end
    masked = mask_terms(buffer, terms)
    if published < len(masked):
        yield masked[published:]
