"""聚合所有 API 子路由。"""
from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    creator,
    health,
    llm_profiles,
    scenario_domain,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(creator.router)
api_router.include_router(scenario_domain.admin_router)
api_router.include_router(scenario_domain.creator_router)
api_router.include_router(scenario_domain.creator_roster_router)
api_router.include_router(scenario_domain.public_router)
api_router.include_router(scenario_domain.public_roster_router)
api_router.include_router(scenario_domain.challenge_router)
api_router.include_router(llm_profiles.router)
api_router.include_router(admin.router)
