"""Entry point backend -- FastAPI sinyal trading untuk backend Rust.

Endpoint:
  GET  /health           -> cek API hidup
  POST /signal           -> sinyal trading harian untuk bot (BTC-60 / V2-60 dari modal) + daftar order
  GET  /recommendations  -> top-10 coin rekomendasi V5 (informasi, bukan sinyal bot)

Jalankan dari root project:
  python main.py
  (atau) uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""

import warnings
warnings.filterwarnings("ignore")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.logger import get_logger
from src.config.settings import settings
from src.databases import ping
from src.router import api_router
from src.services.recommendation.service import load_model, load_snapshot
from src.utils.app_error import register_error_handlers

logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Sama seperti template Express: DB wajib konek dulu, kalau gagal server tidak start.
    try:
        ping()
    except Exception as e:
        logger.error("Gagal konek database: %s", e)
        raise
    logger.info("Database connected successfully")

    load_model()
    logger.info("Model V5 dimuat")
    load_snapshot()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crypto Signal Trading API",
        description="Sinyal trading portofolio (BTC-60 / V2-60) dan rekomendasi coin untuk backend Rust",
        version="1.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    logger.info("Menjalankan API di http://%s:%s  (docs: /docs)", settings.api_host, settings.api_port)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
