"""推演者节点：以上帝视角（读者视角）一次性推演两名异能者的完整对战。纯文本输出（无结构化）。"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.llm.client import build_chat_model
from app.services.nodes._override import with_system_override
from app.services.nodes.battle.discusser import DISCUSS_SYSTEM_PROMPT

_DISCUSS_RULES_END = DISCUSS_SYSTEM_PROMPT.index("\n\n分析流程：")
_DISCUSS_RULES = DISCUSS_SYSTEM_PROMPT[DISCUSS_SYSTEM_PROMPT.index("设定与背景：") : _DISCUSS_RULES_END]

DEDUCE_SYSTEM_PROMPT = f"""你是一个严谨公正的论战师，以上帝视角推演两名能力者的战斗。你是全知叙述者：直述双方的真实行动、异能机制与意图，不隐藏任何信息，也绝不偏向任何一方。
你应该坚持以角色的能力和战术为核心，禁止使用一些看似合理的文学加工（如意志力硬抗一两秒最后操作一番）影响战局，能力的效果往往是绝对的。“只有能力才能对抗能力”是你推演的信条。
你的任务不是生成一个故事，不是写好看的剧情，而是论战，推演双方谁更强，谁会赢。重点在于展示双方的策略和操作，忽视其他细节。

{_DISCUSS_RULES}

推演流程：
1. 【权威奇术比对结果】只列出存在直接冲突的奇术对。其中每项三相判定都是决定性结论，必须严格遵守。不得根据奇术原始描述重新判断、推翻、削弱或改写结论；奇术原始描述只能用于展现已判定的机制与过程。
2. 对未列入比对结果的奇术，不得臆造直接冲突；结合双方各自的战术行动与已经确定的碰撞结论，推演从试探到胜负分明或同归于尽的完整过程。

生成内容规范：
- 保证双方的行动、异能机制与意图在叙述中清晰可见，避免模糊或笼统的描述。双方笔墨应均衡，避免偏向任何一方。
- 分清楚上帝视角推演与角色表现的区别，全知的信息和比对结论只用于推演战斗走向，绝不能影响角色表现。因为战斗中的角色本身没有全知信息，双方奇人互不相识，对对方的奇术也一无所知；应模拟双方在拥有自己能力下最真实的表现。
- 如果输入信息中有奇人的战术意图，以此作为角色决策与行动的参考。
- 不应有过多的文学性描写，清晰干脆地展现能力的效果即可。
- 能力效果必须全程自洽，没有对应能力，不能豁免某个能力的效果。
- 如果一方因为中了对方能力，陷入失去意识的状态，比如昏厥、催眠、灵魂损伤等，无认知能力，那么就不能出现其视角的内容；如果其在这种状态下被击杀，理论上其主观感受就是一下子回到了异闻录。

绝对禁止：
- 禁止随意揣测能力，拓展出能力设定中没有的能力或效果。
- 禁止让能力之外的因素拥有对抗能力的可能，如没有加速或提高感知能力的人，仅凭身体素质不可能闪避一道瞬发的攻击；没有精神防御能力的人，不可能在中了精神冲击类能力后还能凭借意志力操作一两秒。
- 禁止为了故事性而暗暗削弱能力的效果，或让能力之外的因素影响战局。

只输出续写后的完整战斗叙述正文（含所选的结尾句），不要重复开头。"""

# 服务端随机指定开场白（保证多样性，不靠模型自觉）。每项配对地图名，
# 供结尾模板引用（结尾的地图名必须与开场一致）。
OPENINGS = [
    (
        (
            "白光一闪，两位奇人被送入了地图之中，他们都知道，这是又一场对决开始了，"
            "一个未知的对手正在这个地图的某个地方等着自己，只有一方被彻底击败，这场对决才会结束。"
            "这次的地图是青石古镇，青石板路在雨后泛着湿漉漉的微光，两侧飞檐翘角的木楼鳞次栉比，"
            "窄巷纵横、门扉半掩，处处是可以藏身与伏击的阴影。"
            "随着眼前倒计时归零，战斗正式开始！"
        ),
        "青石古镇",
    ),
    (
        (
            "白光一闪，两位奇人被送入了地图之中，他们都知道，这是又一场对决开始了，"
            "一个未知的对手正在这个地图的某个地方等着自己，只有一方被彻底击败，这场对决才会结束。"
            "这次的地图是深山密林，参天古木遮天蔽日，腐叶铺地、藤蔓垂挂，山雾在林间流动，"
            "视野被层层叠叠的树影切割成碎片。"
            "随着眼前倒计时归零，战斗正式开始！"
        ),
        "深山密林",
    ),
]


def build_endings(map_name: str, name_a: str, name_b: str) -> dict[str, str]:
    """三句固定结尾模板：战斗分出胜负后双方传送回异闻录，几笔墨迹宣布结果。

    以真实用户名参数化，deduce 按推演结果三选一原文收尾；服务端按尾部精确匹配或
    正则解析胜负（见 deduction._parse_winner），不依赖模型自觉。
    """
    base = (
        f"胜负已分，白光一闪，双方脱离了{map_name}，"
        "回到了各自异闻师的异闻录之中，几笔墨迹勾勒出结果："
    )
    return {
        "A": base + f"胜者：{name_a}",
        "B": base + f"胜者：{name_b}",
        "draw": base + "平局",
    }


# 上帝视角推演模板：system（推演指导）+ user（双方信息、权威奇术比对结果、开场白、三选一结尾句）
DEDUCE_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", DEDUCE_SYSTEM_PROMPT),
        (
            "user",
            (
                "【双方信息】\n{info}\n\n"
                "【权威奇术比对结果】\n{discuss_report}\n\n"
                "上述结果仅列出存在直接冲突的奇术对；其中三相判定具有决定性，不能由双方信息中的奇术原始描述推翻。\n"
                "根据对战双方信息与权威奇术比对结果，推演这场战斗从开场到结局的完整过程，直到胜负分明或同归于尽，一气呵成。\n"
                "请以以下内容作为开头：\n{opening}\n\n"
                "推演结束时，必须从以下三句结尾中**原文照抄与结果一致的一句**作为全文最后一句（一字不改）：\n"
                "1. {ending_a}\n"
                "2. {ending_b}\n"
                "3. {ending_draw}"
            ),
        ),
    ]
)


def build_deduce_chain(llm_config: dict | None = None, system_prompt: str | None = None) -> Runnable:
    """上帝视角推演链：一次性输出完整对战（纯文本，无结构化），以结尾句声明胜负/平局。

    max_tokens 调大：一次性长文，输出被截断会导致结尾句缺失、胜负无法解析。
    system_prompt 非空时以它覆盖推演系统指令（提示词方案调试用，须保留 {info}/{discuss_report}
    /{opening}/{ending_*} 数据槽）；None 用冻结默认，生产行为不变。
    """
    template = with_system_override(DEDUCE_TEMPLATE, system_prompt)
    return template | build_chat_model(thinking=False, max_tokens=8192, llm_config=llm_config) | StrOutputParser()
