"""猜词节点：原子配对判定 → 玩家主动检定。

挑战流程分为切分、配对和玩家主动检定三个动作：

1. 配对（pair）：输入 = 一个原子猜测 + 一门实际奇术，并发输出一个四态原子判定。
2. 检定（verify）：独立、由玩家主动发起。输入 = 全部「猜测+点评」聊天记录 + 一门未看破能力
   → 布尔判定该能力是否已看破，未看破时指出还缺什么。

关键约束（玩法冻结后不可改）：配对判定绝不能泄露奇术真实名称/效果原文——这是胜负关键。
提示词为用户可手调的草稿；配对/检定采用单条消息（提示词即用户消息），无冗余收尾。
"""

import re
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.services.nodes.registry import NodeSpec, build_node


def split_atomic_guesses(text: str) -> list[str]:
    """把用户输入切成原子条目（换行与中英文逗号/顿号分隔，去首尾句点）。"""
    items: list[str] = []
    for line in re.split(r"\n", text):
        for piece in re.split(r"[，,；;、]", line):
            piece = piece.strip().strip("。．.")
            if piece:
                items.append(piece)
    return items

GUESS_PAIR_PROMPT = """用户正在根据一段叙述文本猜测里面的人物拥有什么能力。以下是用户的一条原子猜测与人物实际使用的一门奇术。
只对这一条原子猜测给出四态判定，不要自动检定是否已经看破奇术。

用户的猜测：
{item_text}

人物实际使用的能力（绝密，仅供内部比对）：
{ability}

用户之前已猜出的线索（仅用于去重）：
{existing}

判定只取四值之一：是、否、部分是、不能确定。
- 是：这条原子猜测准确命中该门奇术的真实特征。
- 否：这条原子猜测与该门奇术相悖。
- 部分是：方向沾边但不精确或不完整。
- 不能确定：仅凭该条无法判断。

输出 text 时忠实引用用户原子猜测，输出 reason 仅供内部调试，不得泄露奇术名称或效果原文。
只输出结构化字段，不要补充用户没有说过的内容。"""

# 环节二：检定。输入 = 全部「猜测+点评」聊天记录 + 一门能力，判定是否已看破；未看破指出还缺什么。
GUESS_VERIFY_PROMPT = """你是一个海龟汤主持人，现在要判断用户是否已经看破其中一门奇术。
你会拿到全部“用户猜测+主持人点评”的聊天记录，以及数据库中这一门实际奇术的完整资料。
数据库资料是绝密判定依据，绝不能原样或变相泄露给用户。

全部聊天记录：
{history}

这一门实际奇术（绝密，仅供内部比对）：
{ability}

判定方法：
1. 只把用户明确说出的内容，以及点评已经明确确认过的用户内容，作为用户已经获得的线索；不要把主持人的内部判断扩展成新的线索。
2. 结合这门奇术本身，判断用户是否已经说中足以识别它的核心机制。语义相同的自然转述可以接受，不要求用户使用数据库原文。
3. 不要把“范围、发动方式、效果、实现方式、表现形式、限制参数”等固定字段全部强制要求。哪些要素是这门奇术的关键，必须由这门奇术本身决定：核心已经说中且足以区分它时可以看破；只说中外围特征、通用特征，或只说中效果但仍缺少这门奇术的关键区分点时，不算看破。
4. 重点区分“用户已经说中的部分”和“仍未覆盖的要素”。未看破时只说缺失的类别或方向，例如“还缺具体效果”“还缺核心限制”“还缺主要表现形式”“范围和效果的对应关系还没说清”，不能说出该类别的实际内容。
5. 后续追问仍按同一规则处理。用户问“是不是……”时，只有在问题本身触及真实资料时，才回答是、不是、部分正确或无法这样判断；不能借回答顺便透露更具体的限制或机制。

下面是判定尺度示例。假设数据库中有以下四门奇术：索命咒（发射魔咒命中即死）、瞬移（到任何看到的地方）、视域之魂（获得全图视野）、杀意波动（全图范围的杀意冲击，使目标昏厥）。用户已经得到过如下点评：
- “全图精神冲击”被确认有一门对应。
- “全图范围”被确认有两门对应。
- “瞬移”被确认有一门对应。
- “即死”被确认有一门对应，但“全图”被否定。

则逐门检定应遵循：
- 杀意波动：用户的“全图范围精神冲击”已经足够接近核心本质，cracked=true。
- 视域之魂：用户只看破“全图范围”，没有看破具体效果，cracked=false，missing 可为“已覆盖全图范围，但还缺具体效果。”
- 瞬移：用户已看破“瞬移效果”，但尚未说中其核心限制，cracked=false，missing 可为“已覆盖瞬移效果，但还缺核心限制。”
- 索命咒：用户已看破“即死效果”，但尚未看破主要表现形式，cracked=false，missing 可为“已覆盖即死效果，但还缺主要表现形式。”
- 在后续连续追问中，用户依次确认“只能瞬移到满足条件的地点”“和视觉有关”“瞬移到任何看到的地方”后，瞬移的核心限制已被说中，应在下一次检定中判为 cracked=true；用户随后把“第二门全图的”推到“获得全图视野”，视域之魂也可在下一次检定中判为 cracked=true。

示例只说明覆盖尺度：真实对局输出不得出现示例奇术名或示例原文中用户尚未说过的具体内容。

输出约束：
- cracked=true：表示核心机制已经被用户准确且足够独特地说中；missing 必须为空字符串。
- cracked=false：missing 只写一句简短反馈，可以先确认用户已经说中的部分，再指出缺失类别，例如“已覆盖瞬移效果，但还缺核心限制”。其中所有具体名词都必须来自用户聊天记录，缺失部分只能写类别/方向，不能写答案。也不能通过举例的方式来枚举可能的答案，一旦你擅自给出提示，用户将失败。
- 不得输出奇术名称、效果原文、数据库字段值，不能用“该奇术其实……”交底。
- 只输出结构化字段，不输出分析过程。"""

GUESS_PAIR_TEMPLATE = ChatPromptTemplate.from_messages([("user", GUESS_PAIR_PROMPT)])
GUESS_VERIFY_TEMPLATE = ChatPromptTemplate.from_messages([("user", GUESS_VERIFY_PROMPT)])


class PairMatch(BaseModel):
    """当前配对节点：单个原子猜测对单门奇术的四态判定。"""

    text: str = Field(default="", description="用户原子猜测原文")
    verdict: Literal["是", "否", "部分是", "不能确定"] = Field(default="不能确定", description="四态判定")
    reason: str = Field(default="", description="内部判定理由，仅调试用")


class Verification(BaseModel):
    """环节二输出：对单门能力是否已看破的布尔检定。"""

    cracked: bool = Field(description="是否已看破该能力")
    missing: str = Field(default="", description="未看破时指出还缺什么；已看破时为空")


SPEC_PAIR = NodeSpec(id="guess_pair", template=GUESS_PAIR_TEMPLATE, schema=PairMatch, pipes_template=False)
SPEC_VERIFY = NodeSpec(id="guess_verify", template=GUESS_VERIFY_TEMPLATE, schema=Verification, pipes_template=False)


def build_guess_pair_llm(llm_config: dict | None = None) -> Runnable:
    return build_node(SPEC_PAIR, llm_config=llm_config)


def build_guess_verify_llm(llm_config: dict | None = None) -> Runnable:
    """检定 LLM：结构化输出 Verification。"""
    return build_node(SPEC_VERIFY, llm_config=llm_config)
