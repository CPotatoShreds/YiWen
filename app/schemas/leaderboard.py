"""异闻榜相关 Pydantic 模型。"""

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    """榜上一席：名次 + 名望 + 见闻。"""

    rank: int  # 名次（从 1 起）
    username: str  # 异闻师名号
    rank_points: int  # 名望（Elo 天梯分）
    exp: int  # 见闻


class LeaderboardOut(BaseModel):
    entries: list[LeaderboardEntry]  # 名望榜前 50 名
    me: LeaderboardEntry | None = None  # 当前异闻师自己（含名次；榜外也能查得）
