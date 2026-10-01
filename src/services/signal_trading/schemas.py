"""Skema request endpoint sinyal entry (padanan types.ts di template Express)."""

from pydantic import BaseModel, Field


class SignalRequest(BaseModel):
    """Dikirim backend Rust sekali sehari (setelah candle harian close, 00:00 UTC)."""
    modal: float = Field(..., gt=0, examples=[1_500_000],
                         description="Total nilai akun saat ini dalam Rupiah (coin + USDT). "
                                     "< Rp1.500.000 -> strategi BTC-60, >= Rp1.500.000 -> V23.")
    modal_awal: float | None = Field(None, gt=0, examples=[1_500_000],
                                     description="Modal awal (Rp) untuk kill switch: kalau modal <= 70% modal_awal, "
                                                 "semua dijual ke USDT dan bot harus berhenti.")
    kurs_usdt_idr: float | None = Field(None, gt=0, examples=[16_300],
                                        description="Kurs Rupiah per 1 USDT. Default dari .env USDT_IDR_RATE.")
    posisi: dict[str, float] | None = Field(None, examples=[{"BTCUSDT": 0.0012, "ETHUSDT": 0.03}],
                                            description="Jumlah coin yang sedang dipegang (qty, bukan nilai). "
                                                        "Kalau diisi, response berisi daftar order.")
    cash_usdt: float | None = Field(None, ge=0, examples=[35.5],
                                    description="Saldo USDT bebas. Dipakai bersama `posisi` untuk menghitung order.")
    tanggal: str | None = Field(None, examples=["2026-07-11"],
                                description="YYYY-MM-DD candle yang dipakai; default = candle harian terakhir di DB.")
