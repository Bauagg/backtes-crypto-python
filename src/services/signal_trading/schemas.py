"""Skema request endpoint sinyal entry (padanan types.ts di template Express)."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Simbol pair Binance, mis. BTCUSDT / 1000PEPEUSDT (huruf kecil diterima, di-uppercase di service).
Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{2,20}$")]
Qty = Annotated[float, Field(ge=0, le=1e15)]
MAX_POSITIONS = 100          # akun spot wajar tidak memegang ratusan coin; mencegah body raksasa


class SignalRequest(BaseModel):
    """Dikirim backend Rust sekali sehari (setelah candle harian close, 00:00 UTC)."""
    # NaN / Infinity ditolak (422) -- tanpa ini angka tak hingga lolos validasi gt/ge dan merusak perhitungan.
    model_config = ConfigDict(allow_inf_nan=False)

    modal: float = Field(..., gt=0, le=1e13, examples=[1_500_000],
                         description="Total nilai akun saat ini dalam Rupiah (coin + USDT). "
                                     "< Rp1.500.000 -> strategi BTC-60, >= Rp1.500.000 -> V23.")
    modal_awal: float | None = Field(None, gt=0, le=1e13, examples=[1_500_000],
                                     description="Modal awal (Rp) untuk kill switch: kalau modal <= 70% modal_awal, "
                                                 "semua dijual ke USDT dan bot harus berhenti.")
    kurs_usdt_idr: float | None = Field(None, ge=1_000, le=1_000_000, examples=[16_300],
                                        description="Kurs Rupiah per 1 USDT. Default dari .env USDT_IDR_RATE.")
    posisi: dict[Symbol, Qty] | None = Field(None, max_length=MAX_POSITIONS,
                                             examples=[{"BTCUSDT": 0.0012, "ETHUSDT": 0.03}],
                                             description="Jumlah coin yang sedang dipegang (qty >= 0, bukan nilai). "
                                                         "Kalau diisi, response berisi daftar order.")
    cash_usdt: float | None = Field(None, ge=0, le=1e12, examples=[35.5],
                                    description="Saldo USDT bebas. Dipakai bersama `posisi` untuk menghitung order.")
    tanggal: date | None = Field(None, examples=["2026-07-11"],
                                 description="YYYY-MM-DD candle yang dipakai; default = candle harian terakhir di DB.")
