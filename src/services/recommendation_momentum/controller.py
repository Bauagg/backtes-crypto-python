from datetime import date as Date

from fastapi import Query

from src.services.recommendation_momentum import service
from src.strategy import momentum as mo


def get_recommendations(
    limit: int = Query(mo.MAX_RECOMMENDATIONS, ge=mo.TOP_MAIN, le=mo.MAX_RECOMMENDATIONS,
                       description="Jumlah coin (5-10): 1-5 UTAMA, 6-10 PELENGKAP"),
    date: Date | None = Query(None, examples=["2026-07-17"],
                              description="YYYY-MM-DD; default = candle harian terbaru"),
):
    """Daftar pantauan harian 5-10 coin momentum terkuat + status pasar + perubahan peringkat."""
    return service.get_recommendations(limit, date.isoformat() if date else None)


def get_history(
    days: int = Query(30, ge=1, le=120, description="Jumlah hari riwayat"),
    date: Date | None = Query(None, description="YYYY-MM-DD hari terakhir; default = candle terbaru"),
):
    """Paper trading: rekomendasi hari-hari sebelumnya dan hasilnya (hold 14 hari, stop -25%)."""
    return service.get_history(days, date.isoformat() if date else None)
