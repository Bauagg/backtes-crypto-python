from fastapi import APIRouter

from src.services.recommendation import controller

router = APIRouter(tags=["recommendation"])

router.add_api_route("/recommendations", controller.get_recommendations, methods=["GET"])
