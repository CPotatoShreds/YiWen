"""聚合所有 API 子路由。"""
from fastapi import APIRouter

from app.api.routes import (
    abilities,
    admin,
    auth,
    battles,
    friends,
    health,
    leaderboard,
    loadouts,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(abilities.router)
api_router.include_router(loadouts.router)
api_router.include_router(battles.router)
api_router.include_router(friends.router)
api_router.include_router(leaderboard.router)
api_router.include_router(admin.router)
