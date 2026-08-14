"""聚合所有 API 子路由。"""
from fastapi import APIRouter

from app.api.routes import (
    abilities,
    admin,
    admin_core_guess,
    auth,
    battles,
    board,
    friends,
    health,
    leaderboard,
    llm_profiles,
    loadouts,
    notifications,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(abilities.router)
api_router.include_router(loadouts.router)
api_router.include_router(battles.router)
api_router.include_router(board.router)
api_router.include_router(friends.router)
api_router.include_router(notifications.router)
api_router.include_router(leaderboard.router)
api_router.include_router(llm_profiles.router)
api_router.include_router(admin.router)
api_router.include_router(admin_core_guess.router)  # 临时试验：核心一句话试验（删除时连文件一并移除）
