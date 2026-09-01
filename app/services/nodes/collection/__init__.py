"""小天下集 LLM 节点入口。"""

from app.services.nodes.collection.challenger_view import (
    CHALLENGER_VIEW_TEMPLATE,
    CollectionChallengerView,
    build_collection_challenger_view_llm,
    build_collection_challenger_view_stream_llm,
)
from app.services.nodes.collection.god import (
    GOD_TEMPLATE,
    CollectionGodReply,
    build_collection_god_llm,
    parse_collection_god_reply,
)
from app.services.nodes.collection.guardian_view import (
    GUARDIAN_VIEW_TEMPLATE,
    CollectionGuardianView,
    build_collection_guardian_view_llm,
    build_collection_guardian_view_stream_llm,
)
from app.services.nodes.collection.judge import (
    JUDGE_TEMPLATE,
    CollectionJudgement,
    build_collection_judge_llm,
)
from app.services.nodes.collection.reply import (
    REPLY_TEMPLATE,
    CollectionReply,
    build_collection_reply_llm,
    parse_collection_reply,
)

__all__ = [
    "CHALLENGER_VIEW_TEMPLATE",
    "GOD_TEMPLATE",
    "GUARDIAN_VIEW_TEMPLATE",
    "JUDGE_TEMPLATE",
    "REPLY_TEMPLATE",
    "CollectionChallengerView",
    "CollectionGodReply",
    "CollectionGuardianView",
    "CollectionJudgement",
    "CollectionReply",
    "build_collection_challenger_view_llm",
    "build_collection_challenger_view_stream_llm",
    "build_collection_god_llm",
    "build_collection_guardian_view_llm",
    "build_collection_guardian_view_stream_llm",
    "build_collection_judge_llm",
    "build_collection_reply_llm",
    "parse_collection_god_reply",
    "parse_collection_reply",
]
