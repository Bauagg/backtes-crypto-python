from fastapi import APIRouter, Depends

from src.services.signal_trading import controller
from src.utils.security import require_api_key

router = APIRouter(tags=["signal_trading"], dependencies=[Depends(require_api_key)])

router.add_api_route("/signal", controller.get_signal, methods=["POST"])
