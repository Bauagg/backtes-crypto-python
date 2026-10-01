from fastapi import APIRouter

from src.services.health import controller

router = APIRouter(tags=["health"])

router.add_api_route("/health", controller.health, methods=["GET"])
