from fastapi import Query

from src.services.recommendation import service


def get_recommendations(
    limit: int = Query(10, ge=1, le=50, description="Jumlah coin yang dikembalikan"),
    date: str | None = Query(None, examples=["2026-07-11"],
                             description="YYYY-MM-DD; default = tanggal data terbaru"),
):
    """Top-N coin rekomendasi: BUY (lolos semua gate V5) di atas, sisanya WATCH."""
    return service.get_recommendations(limit, date)
