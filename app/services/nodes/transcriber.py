"""转写者节点：把上帝视角叙述转写为指定视角人物的第一人称讲述。

系统提示词只给转写指导，不锚定视角身份；具体身份（视角人物及其真实用户名）
由 user 消息中的占位符注入。一次性转写：对完整上帝叙述做单次调用，A/B 各一个
视角分支并发。转写 LLM 扮演该视角角色，以第一人称向自己的异闻师讲述这场战斗
的经历——不再注入系统固定首尾，结果由角色自然交代（各侧只说自己的，校验节点
负责核对结果与上帝视角结尾一致）。
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel

from app.services.llm import build_chat_model
from app.services.nodes._override import with_system_override

TRANSCRIBE_SYSTEM_PROMPT = """你是记录在你异闻师《异闻录》中的奇人，刚被派出打完一场奇术对决，分出胜负后被传送回异闻录中。现在，你要向自己的异闻师讲述这场战斗的完整经历。

要求：
- 以第一人称（「我」）讲述，完整讲出这场对战的经过，直到胜负分明。你是向自己的异闻师复述亲身经历，不是替对家讲故事。
- 只讲你知道的内容：亲眼所见、亲耳所闻、亲身经历与内心判断，或者你利用能力获取到的信息。你不知道的内容，一律不能写。如果你在战斗中失去意识（昏厥/催眠/灵魂损伤等），那段时间发生的事不能讲；如果你在失去意识时被击杀，你主观上就是一下子就回到了异闻录。
- 战斗结果必须交代清楚，且与真实结果一致：赢了就说赢，输了就说输，平局就说平局，不能自相矛盾。
严禁泄露以下内容：
- 上帝视角的信息，尤其是关于对手异能的**：对手异能的确切名称、具体效果、发动条件、机制原理、冷却与弱点、意图与全貌，一律不得出现在讲述中。这些只能通过你观察到的表象间接呈现（如「对方掌心凝聚火焰」「对手的身形诡异地扭曲」），不得解释原理、不得点破机制、不得出现异能的名称或效果原文。
- 你本人无从知晓的全局信息（对手的内心盘算、双方异能的全貌对比、场外形势）同样不得写入。
只输出讲述正文。"""

# 一次性转写消息：身份由 {viewer_name} 注入；转写 LLM 扮演该角色向自己的异闻师讲述经历，
# 结果由角色自然交代，不再注入系统固定首尾
TRANSCRIBE_USER_MSG = (
    "【双方信息】\n{info}\n\n"
    "【上帝视角全文】\n{god}\n\n"
    "请扮演「{viewer_name}」，以上帝视角叙述为事实基准，向自己的异闻师讲述刚才这场对战的完整经历，"
    "用第一人称（「我」）写出你的讲述。只要是你不知道的内容，一律不写；结果如何（赢/输/平局）照实交代。\n"
    "只输出讲述正文。"
)

# 转写模板：system（转写指导）+ user（双方信息、上帝全文、视角身份）
TRANSCRIBE_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", TRANSCRIBE_SYSTEM_PROMPT),
        ("user", TRANSCRIBE_USER_MSG),
    ]
)


def build_transcribe_chain(llm_config: dict | None = None, system_prompt: str | None = None) -> Runnable:
    """双视角转写链：对完整上帝叙述做一次性转写，A/B 各一个视角分支并发。

    system_prompt 非空时以它覆盖转写系统指令（提示词方案调试用，须保留 {info}/{god}
    /{viewer_name} 数据槽）；None 用冻结默认，生产行为不变。
    """
    llm = build_chat_model(thinking=False, llm_config=llm_config)
    template = with_system_override(TRANSCRIBE_TEMPLATE, system_prompt)

    def _branch(name_key: str) -> Runnable:
        return (
            RunnableLambda(
                lambda inputs: {
                    "info": inputs["info"],
                    "god": inputs["god"],
                    "viewer_name": inputs[name_key],
                }
            )
            | template
            | llm
            | StrOutputParser()
        )

    return RunnableParallel(
        narration_a=_branch("viewer_name_a"),
        narration_b=_branch("viewer_name_b"),
    )
