"""Agregasi semua route service."""

from fastapi import APIRouter

from src.services.health.route import router as health_route
from src.services.recommendation_momentum.route import router as recommendation_momentum_route
from src.services.signal_trading.route import router as signal_trading_route

api_router = APIRouter()

api_router.include_router(health_route)
api_router.include_router(recommendation_momentum_route)
api_router.include_router(signal_trading_route)
