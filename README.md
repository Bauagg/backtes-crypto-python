# Crypto Strategy V5 — API untuk Backend Rust

Strategi trading bottoming crypto (ML + reversal confirmation + regime filter),
diekspos sebagai **FastAPI** agar bisa dipanggil dari backend Rust via HTTP.

## Strategi V5 (ringkas)

Entry kandidat: **bottoming ekstrem** (RSI < 30 + Fear&Greed < 25). Lalu disaring 3 gate:

1. **Reversal confirmation** — tunggu bukti pembalikan (bukan menangkap pisau jatuh)
2. **Regime filter** — jangan trade saat market crash / harga belum stabil
3. **ML gate** — RandomForest (dilatih di semua coin) confidence ≥ 0.55

Exit: stop -2%, target +5%, horizon 5 hari. Hanya trade coin dengan korelasi ke BTC < 0.7.

**Hasil backtest 2024-2026:** 76% win rate, modal $1000 → $1121 (+12%).
**Validasi:** walk-forward gap +5.7%, leave-one-coin-out 56%, 5-fold CV 58% (tidak overfit).

## Struktur Proyek

```
backtes-crypto/
├── api.py                              # FastAPI — endpoint untuk backend Rust
├── train_v5_model.py                   # latih & simpan model produksi (jalankan sekali)
├── docs/
│   └── panduan_strategi_analisis_crypto.md
├── data/raw/                           # data OHLCV: {SYMBOL}_1d_full.csv
├── models/
│   ├── strategy_v5_rf.pkl              # model RandomForest terlatih
│   ├── strategy_v5_scaler.pkl          # scaler fitur
│   └── strategy_v5_meta.json           # metadata & parameter (untuk Rust)
├── src/crypto_backtest/
│   ├── strategy_v5.py                  # ★ strategi V5 terpusat (training + scoring)
│   ├── data/loader.py                  # load klines dari data/raw
│   ├── indicators/                     # MA, RSI, Volume, FGI, Relative Strength
│   ├── scoring/                        # score.py + reversal.py (gate)
│   └── backtest/engine.py              # forward return / labeling
├── tests/
└── requirements.txt
```

## Setup (sekali saja)

Buat virtual environment dan install dependency:

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\pip install -e .
```

## Aktifkan venv

Setiap kali mau kerja di proyek ini, aktifkan dulu venv-nya:

```powershell
# PowerShell / CMD
venv\Scripts\activate

# Git Bash
source venv/Scripts/activate
```

Kalau berhasil, prompt terminal akan berubah jadi diawali `(venv)`.

> Jika PowerShell menolak dengan error "running scripts is disabled", jalankan sekali:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Konfigurasi Port (.env)

Salin `.env.example` jadi `.env`, lalu atur host & port di sana:

```powershell
copy .env.example .env
```

Isi `.env`:
```
API_HOST=0.0.0.0
API_PORT=8001
```

> **Penting:** backend Rust jalan di port **8000**, jadi API Python pakai port
> lain (mis. **8001**) agar tidak bentrok. Mau ganti port? Cukup ubah `API_PORT`
> di `.env` — tidak perlu ubah kode.

## Jalankan Proyek

Setelah venv aktif (prompt ada `(venv)`), cukup panggil `python` biasa:

```powershell
# 1. Latih model (sekali; ulangi kalau tambah coin baru di data/raw/)
python train_v5_model.py

# 2. Jalankan API — ini yang dipanggil backend Rust
#    (otomatis baca host/port dari .env)
python api.py
```

Dokumentasi interaktif API: `http://localhost:8001/docs` (sesuai `API_PORT`)
Hentikan server API: tekan **Ctrl + C** di terminal.

> **Tanpa aktivasi venv?** Bisa juga langsung pakai path lengkap tanpa `activate`:
> `venv\Scripts\python train_v5_model.py`

## Keluar dari venv

Kalau sudah selesai dan mau keluar dari virtual environment:

```powershell
deactivate
```

Prompt `(venv)` akan hilang — tanda sudah keluar. Untuk masuk lagi nanti, ulangi
langkah **Aktifkan venv** di atas.

## Dokumentasi Lengkap

- **[docs/API.md](docs/API.md)** — dokumentasi lengkap semua endpoint + contoh request/respons
- **[docs/rust_client_example.rs](docs/rust_client_example.rs)** — klien Rust siap pakai (reqwest + serde)

## Endpoint (untuk Backend Rust)

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/health` | Cek API hidup |
| GET | `/strategy` | Metadata & parameter strategi V5 |
| GET | `/coins` | Daftar coin + korelasi ke BTC + status tradeable |
| POST | `/score` | Skor 1 coin pada 1 tanggal → verdict BUY/SKIP |
| POST | `/scan` | Scan semua coin tradeable → daftar sinyal BUY |
| POST | `/backtest` | Backtest V5 pada rentang tanggal → statistik + trade |

## Format Simbol (Tokocrypto)

API menerima simbol format Tokocrypto **`BTCUSDT`** (tanpa pemisah). Varian seperti
`BTC_USDT`, `btc-usdt` juga dinormalisasi otomatis — backend Rust kirim apa adanya.
Model dilatih pada pasangan **USDT**; hanya coin di `data/raw/` yang didukung
(cek `GET /coins`).

### Contoh panggilan dari Rust (reqwest)

```rust
// POST /scan — dapatkan sinyal BUY hari ini
let res = client.post("http://localhost:8000/scan")
    .json(&serde_json::json!({ "date": "2026-06-30", "only_tradeable": true }))
    .send().await?;
// Respons: { "date": "...", "buy_signals": [{ "symbol": "BNBUSDT",
//            "ml_confidence": 0.62, "reason": "...", "close": 833.78 }], ... }
```

```rust
// POST /score — cek 1 coin
let res = client.post("http://localhost:8000/score")
    .json(&serde_json::json!({ "symbol": "BNBUSDT", "date": "2025-11-22" }))
    .send().await?;
// Respons: { "verdict": "BUY", "ml_confidence": 0.617, "reason": "...", ... }
```

## Menambah Coin Baru (scalable)

1. Drop `data/raw/{SYMBOL}_1d_full.csv` (kolom: date, open, high, low, close, volume)
2. Latih ulang: `python train_v5_model.py`
3. Restart API — coin baru otomatis terdeteksi (`discover_symbols`)

Tidak perlu ubah kode. Sistem tidak hardcode daftar coin.

## Test

```powershell
venv\Scripts\python -m pytest tests/ -v
```
