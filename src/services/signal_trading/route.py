from fastapi import APIRouter

from src.services.signal_trading import controller

router = APIRouter(tags=["signal_trading"])

router.add_api_route("/signal", controller.get_signal, methods=["POST"])
