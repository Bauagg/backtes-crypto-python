# Crypto Strategy — API Sinyal Trading untuk Backend Rust

**FastAPI** yang memberi backend Rust **sinyal trading harian** (`POST /signal`): strategi dipilih
dari besar modal, target porsi tiap coin, dan daftar order yang harus dijalankan. Fitur aplikasi
lain (login, chart, portofolio, log trade, eksekusi order) diurus backend Rust.

| Modal | Strategi (hasil riset notebook 13–20) |
|---|---|
| < Rp1.500.000 | **BTC-60**: BTC saja, 60% modal, filter pasar BTC/Fear & Greed |
| ≥ Rp1.500.000 | **V2-60**: 8 coin porsi inverse-volatilitas, 60% modal, filter pasar, rebalance bulanan |

Endpoint `GET /recommendations` (strategi lama V5) tetap ada sebagai informasi indikator coin.

Proyek dibagi dua:

- **`src/`** — backend (FastAPI). Data pasar dibaca dari **PostgreSQL** (DB milik backend Rust).
- **`notebooks/`** — analisis & training model. Data dibaca dari **CSV** histori panjang.

## Strategi V5 (ringkas)

Entry kandidat: **bottoming ekstrem** (RSI < 30 + Fear&Greed < 25). Lalu disaring 3 gate:

1. **Reversal confirmation** — tunggu bukti pembalikan (bukan menangkap pisau jatuh)
2. **Regime filter** — jangan trade saat market crash / harga belum stabil
3. **ML gate** — RandomForest (dilatih di semua coin) confidence ≥ 0.55

Exit: stop-loss −1.5×ATR, take-profit +2.0×ATR, horizon 5 hari.
Hanya trade coin dengan korelasi ke BTC < 0.7.

Hasil training & backtest terbaru ada di [models/strategy_v5_meta.json](models/strategy_v5_meta.json)
(dihasilkan ulang tiap `notebooks/train_v5_model.py` dijalankan).

## Struktur Proyek

```
backtes-crypto/
├── main.py                              # ★ entry point FastAPI (python main.py)
├── src/                                 # ===== BACKEND =====
│   ├── config/
│   │   ├── settings.py                  # baca .env (host, port, DATABASE_URL, dll)
│   │   └── logger.py                    # format log
│   ├── databases/
│   │   └── connection.py                # koneksi PostgreSQL + ping
│   ├── router/
│   │   └── __init__.py                  # agregasi semua route service
│   ├── utils/
│   │   ├── app_error.py                 # NotFoundError, UnprocessableError + handler
│   │   └── api_response.py              # bersihkan nilai untuk JSON
│   ├── strategy/                        # logika inti strategi (murni, tanpa HTTP/DB)
│   │   ├── allocation.py                # ★ filter pasar H8b, porsi inverse-vol (BTC-60 / V2-60)
│   │   ├── v5.py                        # strategi V5 (gate, scoring, training, backtest)
│   │   ├── backtest_engine.py           # simulasi SL/TP day-by-day
│   │   ├── indicators/                  # MA, RSI, Volume, ATR, Relative Strength, FGI
│   │   └── scoring/                     # score.py + reversal.py (gate)
│   └── services/                        # satu folder per fitur
│       ├── health/                      # GET /health
│       ├── signal_trading/              # ★ POST /signal (sinyal portofolio + order untuk bot Rust)
│       └── recommendation/              # GET /recommendations (top-10 coin)
│                                        #   repository: SQL market_candles & FNG + model ML
├── notebooks/                           # ===== ANALISIS =====
│   ├── research_signal_trading/         # ★ riset strategi sinyal trading, notebook 03 → 20
│   │   ├── 03_… 06_…                    #   strategi V5 (bottoming + ML) & uji exit
│   │   ├── 07_… 12_…                    #   rotasi momentum, audit overfitting, universe 40 coin
│   │   ├── 13_… 16_…                    #   filter Fear & Greed, kelompok coin, portofolio, validasi data
│   │   └── 17_… 20_…                    #   modal kecil, ketahanan modal, V2-60 & statistiknya
│   ├── research/                        # mesin backtest bersama (dipakai notebook 08–20)
│   ├── train_v5_model.py                # latih & simpan model V5 (dikunci ke 10 coin)
│   ├── data_source/                     # loader CSV, downloader Binance Vision, Fear & Greed
│   └── data/raw/                        # data OHLCV: {SYMBOL}_1d_full.csv & {SYMBOL}_1d_since2018.csv
├── models/                              # model ML terlatih (dipakai backend)
│   ├── strategy_v5_rf.pkl
│   ├── strategy_v5_scaler.pkl
│   └── strategy_v5_meta.json
├── docs/
└── requirements.txt
```

### Pola tiap fitur di `src/services/`

Mengikuti pola template Express (`template-express-ts-backend`):

| File | Tugas | Padanan di Express |
|------|-------|--------------------|
| `route.py` | daftar endpoint | `route.ts` |
| `controller.py` | terima request → panggil service | `controller.ts` |
| `service.py` | business logic | `service.ts` |
| `repository.py` | query ke DB / file | `repository.ts` |
| `schemas.py` | skema request (Pydantic) | `types.ts` |

Menambah fitur baru: buat folder di `src/services/<fitur>/`, lalu daftarkan
router-nya di `src/router/__init__.py`.

## Setup (sekali saja)

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # lalu isi DATABASE_URL, API_PORT, dll
```

Aktifkan venv setiap kali kerja di proyek ini:

```powershell
venv\Scripts\activate          # PowerShell / CMD
source venv/Scripts/activate   # Git Bash
```

> Jika PowerShell menolak dengan error "running scripts is disabled", jalankan sekali:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Konfigurasi (.env)

| Variabel | Fungsi |
|----------|--------|
| `API_HOST`, `API_PORT` | alamat API. Backend Rust pakai port **8000**, jadi API Python pakai port lain (mis. 8080) |
| `DATABASE_URL` | PostgreSQL tempat backend membaca `market_candles` & `fear_greed_index` |
| `DB_CONNECT_TIMEOUT` | batas waktu koneksi DB (detik, default 5) |
| `MARKET_CACHE_TTL` | data pasar dari DB dimuat ulang tiap N detik (default 3600) |
| `USDT_IDR_RATE` | kurs default Rp per USDT untuk `/signal` kalau request tidak mengirim kurs (default 16300) |
| `FNG_API_URL`, `BINANCE_VISION_URL` | sumber data untuk notebooks |

## Jalankan Backend

Dari root project (venv aktif):

```powershell
python main.py
# atau, dengan auto-reload saat development:
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Saat start, backend cek koneksi DB dulu. **Kalau DB tidak bisa dihubungi, server tidak jalan**
(sama seperti template Express). Dokumentasi interaktif: `http://localhost:<API_PORT>/docs`.

## Analisis & Training (notebooks)

```powershell
# Latih ulang model (hasil disimpan ke models/, dipakai backend setelah restart)
python notebooks/train_v5_model.py

# Download data coin baru dari Binance Vision (jalankan dari folder notebooks/)
cd notebooks
python -m data_source.download_binance_vision LINKUSDT DOTUSDT --start 2018-01
```

Notebook `.ipynb` mengimpor logika strategi langsung dari `src/strategy/`, jadi yang
dianalisis selalu sama dengan yang dijalankan backend.

## Endpoint (untuk Backend Rust)

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/health` | Cek API hidup |
| **POST** | **`/signal`** | **Sinyal harian bot**: body `modal` (+ `posisi`, `cash_usdt`, `modal_awal`) → strategi, target porsi, daftar order |
| GET | `/recommendations` | Top-10 coin + detail semua indikator & alasan: `BUY` di atas, sisanya `WATCH` |

Kandidat `/recommendations` = simbol aktif di `flex_params` dengan `description` **Large/Mid** (kategori
market cap), korelasi ke BTC < 0.7, dan bukan stablecoin. Detail request/respons: **[docs/API.md](docs/API.md)**. Klien Rust
siap pakai: **[docs/rust_client_example.rs](docs/rust_client_example.rs)**.

## Menambah Coin Baru

- **Backend:** otomatis — coin baru yang dimasukkan backend Rust ke `market_candles`
  ikut terbaca (paling lambat setelah `MARKET_CACHE_TTL`).
- **Training:** download CSV-nya ke `notebooks/data/raw/`, lalu jalankan ulang
  `python notebooks/train_v5_model.py` dan restart backend.
