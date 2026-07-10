# Dokumentasi API — Crypto Strategy V5

API strategi trading bottoming (ML + reversal + regime filter) untuk dipanggil
backend Rust. Base URL default: `http://localhost:8000`.

---

## Format Simbol (Tokocrypto)

Semua endpoint menerima simbol format **Tokocrypto/Binance**: `BTCUSDT`, `BNBUSDT`,
`ADAUSDT` (tanpa pemisah). API juga menormalisasi varian secara otomatis, jadi
backend Rust tidak perlu khawatir:

| Kirim | Diproses jadi |
|-------|---------------|
| `BTCUSDT` | `BTCUSDT` |
| `btcusdt` | `BTCUSDT` |
| `BTC_USDT` | `BTCUSDT` |
| `BTC-USDT` | `BTCUSDT` |
| `BTC/USDT` | `BTCUSDT` |

> **Catatan penting:** Model dilatih pada pasangan **USDT**. Jika Tokocrypto memberi
> simbol dalam pasangan lain (mis. IDR), pasangan itu belum didukung — hanya coin
> yang ada di `data/raw/` (lihat `GET /coins`).

---

## Menjalankan API

```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Dokumentasi interaktif (Swagger): `http://localhost:8000/docs`

---

## Ringkasan Endpoint

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/health` | Cek API hidup |
| GET | `/strategy` | Parameter & metadata strategi V5 |
| GET | `/coins` | Daftar coin + korelasi BTC + tradeable |
| POST | `/score` | Skor 1 coin/tanggal → BUY/SKIP |
| POST | `/scan` | Scan semua coin tradeable → sinyal BUY |
| POST | `/backtest` | Backtest pada rentang tanggal |

---

## 1. `GET /health`

Cek API hidup dan model termuat.

**Respons:**
```json
{ "status": "ok", "coins_loaded": 10, "model_loaded": true }
```

---

## 2. `GET /strategy`

Parameter strategi V5 (untuk referensi di sisi Rust).

**Respons:**
```json
{
  "strategy": "V5",
  "feature_cols": ["rsi", "volume_ratio", "fng_value", "relative_strength", "confirm_count", "ma_diff_pct"],
  "bottoming_rsi": 30,
  "bottoming_fgi": 25,
  "ml_threshold": 0.55,
  "forward_horizon_days": 5,
  "stop_loss": -0.02,
  "take_profit": 0.05,
  "correlation_max": 0.7,
  "meta": { "trained_coins": ["..."], "walk_forward": {"gap": 0.057}, "...": "..." }
}
```

---

## 3. `GET /coins`

Daftar coin tersedia + korelasi ke BTC. Coin `tradeable: false` (korelasi ≥ 0.7)
sebaiknya tidak ditrade karena redundan dengan BTC.

**Respons:**
```json
{
  "symbol_format": "BTCUSDT (Tokocrypto/Binance, tanpa pemisah)",
  "coins": [
    { "symbol": "HBARUSDT", "correlation_to_btc": 0.5,   "tradeable": true },
    { "symbol": "ETHUSDT",  "correlation_to_btc": 0.809, "tradeable": false }
  ],
  "tradeable_count": 6,
  "total": 9
}
```

---

## 4. `POST /score`

Skor satu coin pada satu tanggal. Mengembalikan verdict **BUY** atau **SKIP**
beserta alasannya.

**Request:**
```json
{ "symbol": "BNBUSDT", "date": "2025-11-22" }
```

**Respons (BUY):**
```json
{
  "symbol": "BNBUSDT",
  "date": "2025-11-22",
  "verdict": "BUY",
  "ml_confidence": 0.617,
  "reason": "semua gate lolos (bottoming + reversal + regime + ML)",
  "rsi": 21.3,
  "fng": 11,
  "close": 833.78
}
```

**Respons (SKIP):**
```json
{
  "symbol": "BTCUSDT",
  "date": "2026-06-20",
  "verdict": "SKIP",
  "ml_confidence": null,
  "reason": "bukan bottoming (RSI>=30 atau FGI>=25)",
  "rsi": 47.1,
  "fng": 23,
  "close": 64298.0
}
```

**Alasan SKIP yang mungkin:**
- `bukan bottoming (RSI>=30 atau FGI>=25)` — belum oversold
- `belum ada konfirmasi reversal (falling knife?)` — masih jatuh
- `rezim pasar buruk (crash / belum stabil)` — market crash
- `ML confidence X < 0.55` — model tidak yakin

---

## 5. `POST /scan`

Scan semua coin tradeable pada satu tanggal, kembalikan hanya sinyal **BUY**
(diurut confidence tertinggi). Cocok dipanggil harian untuk cari peluang.

**Request:**
```json
{ "date": "2025-11-22", "only_tradeable": true }
```
> `date` opsional — jika kosong, pakai tanggal terbaru yang tersedia.

**Respons:**
```json
{
  "date": "2025-11-22",
  "buy_signals": [
    { "symbol": "BNBUSDT", "verdict": "BUY", "ml_confidence": 0.617, "reason": "...", "close": 833.78 },
    { "symbol": "HBARUSDT", "verdict": "BUY", "ml_confidence": 0.598, "reason": "...", "close": 0.21 }
  ],
  "total_scanned": 6,
  "buy_count": 2
}
```

---

## 6. `POST /backtest`

Jalankan backtest strategi V5 pada rentang tanggal. Kembalikan statistik +
daftar semua trade dengan kurva modal.

**Request:**
```json
{
  "start": "2024-01-01",
  "end": "2026-06-30",
  "initial_capital": 1000,
  "position_fraction": 0.20,
  "only_tradeable": true
}
```

**Respons:**
```json
{
  "period": "2024-01-01 to 2026-06-30",
  "n_trades": 21,
  "win_rate": 0.762,
  "initial_capital": 1000.0,
  "final_capital": 1121.36,
  "return_pct": 0.1214,
  "trades": [
    {
      "symbol": "BNBUSDT", "date": "2024-09-07", "ml_confidence": 0.6,
      "forward_return": 0.08, "realized_return": 0.05, "win": true,
      "pnl": 10.0, "capital": 1010.0
    }
  ]
}
```

**Field trade:**
- `forward_return` — return riil 5 hari (sebelum stop/target)
- `realized_return` — return setelah dibatasi stop -2% / target +5%
- `pnl` — laba/rugi USD pada trade itu
- `capital` — modal kumulatif setelah trade

---

## Kode Error

| Status | Arti |
|--------|------|
| 200 | OK |
| 404 | Simbol tidak ditemukan / tanggal tidak ada |
| 422 | Request tidak valid (field kurang/salah tipe) |

---

## Alur Pemakaian Umum (Backend Rust)

1. **Saat startup:** panggil `GET /coins` sekali, simpan daftar coin tradeable.
2. **Harian:** panggil `POST /scan` untuk dapat sinyal BUY hari ini.
3. **Verifikasi:** untuk tiap sinyal, backend Rust eksekusi order via Tokocrypto,
   pasang stop -2% / target +5% (dari `GET /strategy`).
4. **Evaluasi:** panggil `POST /backtest` berkala untuk cek performa strategi.
