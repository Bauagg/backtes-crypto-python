# Crypto Strategy — API Sinyal Trading untuk Backend Rust

**FastAPI** yang memberi backend Rust **sinyal trading harian** (`POST /signal`): strategi dipilih
dari besar modal, target porsi tiap coin, dan daftar order yang harus dijalankan. Fitur aplikasi
lain (login, chart, portofolio, log trade, eksekusi order) diurus backend Rust.

| Modal | Strategi (hasil riset notebook 13–25) |
|---|---|
| < Rp1.500.000 | **BTC-60**: BTC saja, 60% modal, filter pasar BTC/Fear & Greed |
| ≥ Rp1.500.000 | **V23** (dulu V2-60): 8 coin porsi inverse-volatilitas, filter pasar, eksposur dinamis via volatility targeting (bukan 60% tetap), rebalance bulanan |

Endpoint `GET /recommendations/momentum` memberi **daftar pantauan harian 5–10 coin** (momentum RSI, riset
`notebooks/research_recomendatio_trading/` 01–06) untuk trader yang mau menganalisis sendiri — bukan sinyal bot.
Endpoint V5 lama (`GET /recommendations`) sudah dihapus.

Proyek dibagi dua:

- **`src/`** — backend (FastAPI). Data pasar dibaca dari **PostgreSQL** (DB milik backend Rust).
- **`notebooks/`** — analisis & training model. Data dibaca dari **CSV** histori panjang.

## Rekomendasi Momentum (ringkas)

- Universe: `flex_params` Large/Mid aktif (minus stablecoin, token emas, WBETH); BTC ikut diranking.
- Skor: rata-rata rank-percentile RSI(14) + RSI(7) antar coin → peringkat 1–5 **UTAMA**, 6–10 **PELENGKAP**.
- Dihitung ulang tiap candle harian tutup → urutan bisa berubah tiap hari.
- Rencana per coin: beli open besok, pegang 14 hari, stop keras −25%.
- Status pasar H8b (risk-on/off) + peringatan; risk-off historis rata-rata rugi.
- ⚠️ Performa 2025–2026 melemah (notebook 04–06) → dipantau lewat `/recommendations/momentum/history`.

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
│   │   ├── allocation.py                # ★ filter pasar H8b, porsi inverse-vol, vol targeting (BTC-60 / V23)
│   │   └── momentum.py                  # ★ skor RSI14+RSI7, ranking, simulasi hold 14 hari (rekomendasi)
│   └── services/                        # satu folder per fitur
│       ├── health/                      # GET /health
│       ├── signal_trading/              # ★ POST /signal (sinyal portofolio + order untuk bot Rust)
│       └── recommendation_momentum/     # GET /recommendations/momentum (+ /history paper trading)
├── docs/API_RUST.md                     # ★ panduan integrasi untuk backend Rust
├── notebooks/                           # ===== ANALISIS =====
│   ├── research_signal_trading/         # ★ riset strategi sinyal trading, notebook 03 → 25
│   │   ├── 03_… 06_…                    #   strategi V5 (arsip — kode V5 sudah dihapus, tidak bisa dijalankan ulang)
│   │   ├── 07_… 12_…                    #   rotasi momentum, audit overfitting, universe 40 coin
│   │   ├── 13_… 16_…                    #   filter Fear & Greed, kelompok coin, portofolio, validasi data
│   │   └── 17_… 20_…                    #   modal kecil, ketahanan modal, V2-60 & statistiknya
│   ├── research_recomendatio_trading/   # ★ riset rekomendasi coin momentum, notebook 01 → 06
│   ├── research/                        # mesin backtest bersama (dipakai notebook 08–25)
│   ├── data_source/                     # loader CSV, downloader Binance Vision, Fear & Greed
│   └── data/raw/                        # data OHLCV: {SYMBOL}_1d_full.csv & {SYMBOL}_1d_since2018.csv
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
| `DATABASE_URL` | PostgreSQL tempat backend membaca `candle_ohlcv` & `fear_greed_index` |
| `DB_CONNECT_TIMEOUT` | batas waktu koneksi DB (detik, default 5) |
| `USDT_IDR_RATE` | kurs default Rp per USDT untuk `/signal` kalau request tidak mengirim kurs (default 16300) |
| `FNG_API_URL`, `BINANCE_VISION_URL` | sumber data untuk notebooks |
| `API_KEY` | kalau diisi, semua endpoint kecuali `/health` wajib header `X-API-Key`. **Wajib diisi di produksi** |
| `CORS_ORIGINS` | origin browser yang boleh memanggil API (dipisah koma). Kosong = CORS mati (normal untuk server-ke-server) |
| `ENABLE_DOCS` | `false` di produksi untuk mematikan `/docs` & `/openapi.json` (default `true`) |

## Jalankan Backend

Dari root project (venv aktif):

```powershell
python main.py
# atau, dengan auto-reload saat development:
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Saat start, backend cek koneksi DB dulu. **Kalau DB tidak bisa dihubungi, server tidak jalan**
(sama seperti template Express). Sesi DB dibuka **read-only** dengan batas waktu query 15 detik, jadi Python
tidak bisa menulis ke DB Rust walaupun ada bug. Dokumentasi interaktif: `http://localhost:<API_PORT>/docs`.

## Analisis (notebooks)

```powershell
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
| GET | `/recommendations/momentum` | Daftar pantauan 5–10 coin (`limit` 5–10, `date` opsional): peringkat, UTAMA/PELENGKAP, perubahan peringkat vs kemarin, RSI, rencana beli/jual, status pasar, peringatan |
| GET | `/recommendations/momentum/history` | Paper trading: rekomendasi `days` hari terakhir (maks 120) + hasilnya, dihitung ulang dari candle (tidak menulis ke DB) |

Contoh:

```bash
curl "http://localhost:8080/recommendations/momentum?limit=10"
curl "http://localhost:8080/recommendations/momentum/history?days=30"
```

Panduan integrasi backend Rust (alur harian, body, response, eksekusi order, skenario tes):
**[docs/API_RUST.md](docs/API_RUST.md)**. Skema interaktif: `http://localhost:<API_PORT>/docs`.

## Menambah Coin Baru

- **Backend:** otomatis — coin yang aktif di `flex_params` (Large/Mid) dan punya candle di `candle_ohlcv`
  ikut diranking di request berikutnya. Kalau jumlah universe berubah jauh dari 21 coin, statistik historis
  rekomendasi perlu diukur ulang (notebook 06).
- **Riset:** download CSV-nya ke `notebooks/data/raw/`.
