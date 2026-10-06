from fastapi import APIRouter, Depends

from src.services.recommendation_momentum import controller
from src.utils.security import require_api_key

router = APIRouter(tags=["recommendation_momentum"], dependencies=[Depends(require_api_key)])

router.add_api_route("/recommendations/momentum", controller.get_recommendations, methods=["GET"])
router.add_api_route("/recommendations/momentum/history", controller.get_history, methods=["GET"])
