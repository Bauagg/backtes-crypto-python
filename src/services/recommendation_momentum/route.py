from fastapi import APIRouter

from src.services.recommendation_momentum import controller

router = APIRouter(tags=["recommendation_momentum"])

router.add_api_route("/recommendations/momentum", controller.get_recommendations, methods=["GET"])
router.add_api_route("/recommendations/momentum/history", controller.get_history, methods=["GET"])
