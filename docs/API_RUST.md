# Integrasi Backend Rust ↔ API Python (Crypto Signal Trading)

Dokumen ini untuk developer **backend Rust** (`backend-crypto-rust`): apa yang harus disiapkan Rust,
endpoint apa yang dipanggil, kapan, body-nya apa, dan apa yang harus dilakukan dengan response-nya.

Terakhir diperbarui: 1 Oktober 2026.

---

## 1. Pembagian tugas

| Rust | Python (repo ini) |
|---|---|
| Login, user, saldo, eksekusi order ke Binance, log trade | Membaca data pasar dari DB, menghitung sinyal & rekomendasi |
| **Mengisi DB**: `candle_ohlcv`, `fear_greed_index`, `flex_params` | **Hanya membaca DB** — tidak pernah menulis |
| Memutuskan *kapan* memanggil API & mengeksekusi hasilnya | Memutuskan *apa* yang harus dibeli/dijual |

Python tidak menyimpan state apa pun. Semua jawaban dihitung ulang dari DB setiap request.

---

## 2. Koneksi

| | |
|---|---|
| Base URL | lokal: `http://localhost:8080` · **Docker/VPS: `http://treding-api:8080`** (nama container di network `data-net`; prod: `http://treding-prod-api:8080`) |
| Env di Rust (saran) | `PYTHON_API_URL` = base URL di atas, `PYTHON_API_KEY` = `API_KEY` di `.env.docker` Python |
| Format | JSON, UTF-8 |
| Auth | header **`X-API-Key: <API_KEY>`** di semua request kecuali `/health` (aktif kalau `API_KEY` diisi di `.env` Python). Salah/tidak ada → **401** |
| Dokumentasi interaktif | `http://<host>:8080/docs` (Swagger, bisa coba langsung) |
| Menjalankan | `python main.py` atau `uvicorn main:app --host 0.0.0.0 --port 8080` |

Server Python **tidak mau start** kalau DB tidak bisa dihubungi.

### Endpoint

| Method | Path | Dipanggil oleh | Kapan |
|---|---|---|---|
| GET | `/health` | Rust (monitoring) | kapan saja |
| **POST** | **`/signal`** | **bot trading** | **1× sehari**, setelah candle harian tutup |
| GET | `/recommendations/momentum` | halaman rekomendasi di aplikasi | saat user membuka halaman |
| GET | `/recommendations/momentum/history` | halaman riwayat rekomendasi | saat user membuka halaman |

---

## 3. Data yang WAJIB diisi Rust ke DB

Tanpa ini, semua jawaban API salah atau basi.

| Tabel | Isi | Frekuensi |
|---|---|---|
| `candle_ohlcv` | candle `interval = '1d'` untuk **semua simbol aktif Large/Mid di `flex_params`** + `BTCUSDT`. `open_time` dalam **milidetik** (00:00 UTC). Hanya candle yang **sudah tutup** | tiap hari setelah 00:00 UTC (07:00 WIB) |
| `fear_greed_index` | `date`, `fng_value` (0–100) | tiap hari |
| `flex_params` | `type_param = 'SIMBOL_CRYPTO'`, `value_param` = simbol, `description` = `Large`/`Mid`/`Small`, `is_active` | saat daftar coin diubah |

Kebutuhan histori minimal: **±260 hari** candle harian (untuk SMA100 BTC & volatilitas 60 hari).

> **Status per 2 Okt 2026**: semua coin V23 & Large/Mid terisi s/d 2026-09-30 (worker sempat mengejar
> ketertinggalan sejak 11 Juli setelah server Rust dinyalakan ulang). Masih 0 candle: `HYPEUSDT`, `ZECUSDT`
> (lihat bagian 10, poin 3). Fear & Greed terisi s/d 2026-10-01.
>
> Python hanya membaca candle yang **sudah tutup** (`close_time < now`), jadi aman kalau collector juga
> menyimpan candle yang masih berjalan.
>
> Cara Rust mengisi data ini sekarang dan apa yang perlu diubah: **bagian 10**.

---

## 4. `POST /signal` — sinyal harian bot trading

### 4.1 Alur harian di Rust

Jadwalkan **sekali sehari pukul ±07:05 WIB** (00:05 UTC), setelah collector selesai mengisi candle:

```
1. Pastikan candle 1d kemarin sudah masuk DB
2. Ambil saldo akun user dari Binance  (GET /api/v3/account)
3. Hitung modal (Rupiah) = (Σ qty_coin × harga + saldo USDT) × kurs
4. POST /signal dengan body template (bagian 4.2), diisi data asli
5. Ikuti response (bagian 4.4)
6. Simpan log: request, response, order yang dieksekusi & hasilnya
```

### 4.2 Body = satu template tetap

**Bentuk body selalu sama.** Rust tidak memilih "skenario" — Rust hanya mengisi data akun apa adanya;
Python yang memutuskan (strategi, beli/jual, kill switch).

```json
{
  "modal": 2000000,
  "modal_awal": 2000000,
  "kurs_usdt_idr": 16300,
  "posisi": { "BTCUSDT": 0.0005, "ETHUSDT": 0.01 },
  "cash_usdt": 60
}
```

| Field | Tipe | Wajib | Diisi dari | Keterangan |
|---|---|---|---|---|
| `modal` | number > 0 | ✅ | dihitung Rust | total nilai akun dalam **Rupiah** (coin + USDT). < Rp1.500.000 → strategi **BTC-60**, ≥ Rp1.500.000 → **V23** |
| `modal_awal` | number > 0 | disarankan | DB Rust | modal saat user mulai bot — disimpan **sekali**, tidak berubah. Dipakai kill switch |
| `kurs_usdt_idr` | number > 0 | – | kurs hari ini | default `.env` `USDT_IDR_RATE` (16300) |
| `posisi` | object `{simbol: qty}` | disarankan | saldo Binance | **jumlah coin (qty)**, bukan nilai. Saldo 0 tidak perlu dikirim. Kalau field ini dikirim, response berisi `order` |
| `cash_usdt` | number ≥ 0 | disarankan | saldo Binance | USDT bebas (tidak terkunci di order) |
| `tanggal` | `"YYYY-MM-DD"` | – | — | **jangan dikirim di produksi** (default = candle terakhir). Hanya untuk tes/replay |

Batas validasi (di luar ini → 422): `modal`/`modal_awal` 0 < x ≤ 10¹³ · `kurs_usdt_idr` 1.000–1.000.000 ·
`cash_usdt` 0–10¹² · `posisi` maks 100 coin, kunci = huruf/angka 2–20 karakter, qty ≥ 0 · `NaN`/`Infinity` ditolak.

Kirim `posisi: {}` kalau user belum punya coin (misal hari pertama) — tetap dapat daftar order BUY.

### 4.3 Contoh response (data 2026-07-11, pasar risk-off)

```json
{
  "tanggal_candle": "2026-07-11",
  "eksekusi_pada": "2026-07-12 saat open (00:00 UTC)",
  "strategi": "V23",
  "alasan_strategi": "modal Rp2,000,000 >= Rp1,500,000",
  "status": "RISK_OFF",
  "filter_pasar": {
    "risk_on": false,
    "berubah_dari_kemarin": false,
    "btc_close": 64182.87,
    "btc_sma100": 70799.08,
    "btc_di_atas_sma100": false,
    "fgi_hari_ini": 26.0,
    "fgi_rata2_14h": 20.2,
    "fgi_14h_di_atas_50": false,
    "alasan": "BTC di bawah SMA100 dan FGI 14 hari <= 50 -> risk-off (semua USDT)"
  },
  "kill_switch": { "aktif": false, "batas_idr": 1400000.0 },
  "volatility_targeting": {
    "aktif": true,
    "volatilitas_basket_20h": 0.3307,
    "target_volatilitas_tahunan": 0.2,
    "eksposur_maksimum": 1.0,
    "eksposur_dipakai": 0.6048
  },
  "modal": { "modal_idr": 2000000.0, "kurs_usdt_idr": 16300.0, "nilai_akun_usdt": 110.09, "sumber": "posisi + cash_usdt" },
  "alokasi_target": [
    { "symbol": "BTCUSDT", "porsi": 0.0, "nilai_usdt": 0.0, "nilai_idr": 0.0, "harga_terakhir": 64182.87,
      "qty_target": 0.0, "volatilitas_harian_60h": 0.0193, "di_bawah_order_minimum": false }
    // ... ETH, BNB, XRP, ADA, LINK, TRX, DOGE
  ],
  "usdt_target": 110.09,
  "perlu_rebalance": true,
  "alasan_rebalance": ["posisi tidak sesuai target: ['BTCUSDT', 'ETHUSDT']"],
  "order": [
    { "urutan": 1, "symbol": "BTCUSDT", "side": "SELL", "tipe": "MARKET", "nilai_usdt": 32.09,
      "qty_perkiraan": 0.0005, "harga_acuan": 64182.87, "jual_semua": true },
    { "urutan": 2, "symbol": "ETHUSDT", "side": "SELL", "tipe": "MARKET", "nilai_usdt": 18.0,
      "qty_perkiraan": 0.01, "harga_acuan": 1799.59, "jual_semua": true }
  ],
  "order_dilewati": [],
  "catatan": ["Candle terakhir 2026-07-11 sudah 82 hari lalu -- cek collector candle backend Rust sebelum trading."]
}
```

### 4.4 Yang harus dilakukan Rust dengan response

Urutan pengecekan — **selalu sama**, tidak peduli kondisi akun:

```
HTTP 4xx/5xx                 → JANGAN trading. Log error, kabari admin.
catatan berisi "tertinggal"  → JANGAN trading hari ini (data basi). Perbaiki collector.
kill_switch.aktif == true    → eksekusi semua `order` (isinya SELL semua), lalu MATIKAN bot user ini
                               dan kabari user. Jangan panggil /signal lagi sampai user mengaktifkan ulang.
perlu_rebalance == false     → tidak ada yang dilakukan hari ini.
perlu_rebalance == true      → eksekusi `order` sesuai `urutan`.
```

Field penting:

| Field | Arti |
|---|---|
| `status` | `RISK_ON` (boleh pegang coin) / `RISK_OFF` (semua USDT) / `STOP` (kill switch) |
| `perlu_rebalance` | `true` = ada order yang harus dijalankan |
| `order[]` | daftar order, **sudah diurutkan: semua SELL dulu, baru BUY** (USDT hasil jual dipakai untuk beli) |
| `order[].nilai_usdt` | besar order dalam USDT |
| `order[].jual_semua` | `true` = jual **seluruh saldo** coin itu (target 0), bukan cuma `qty_perkiraan` |
| `order_dilewati[]` | order yang tidak dibuat karena < 5 USDT (minimum Binance) — cukup dicatat |
| `alokasi_target[]` | porsi ideal tiap coin — untuk ditampilkan di dashboard portofolio |
| `catatan[]` | peringatan untuk admin/user — selalu log |

### 4.5 Aturan eksekusi di Binance

1. Jalankan order **berurutan sesuai `urutan`**; tunggu SELL terisi sebelum BUY.
2. **BUY**: market order dengan `quoteOrderQty = nilai_usdt` (beli senilai USDT, bukan qty).
3. **SELL** dengan `jual_semua: true`: jual **seluruh saldo free** coin itu (bulatkan ke `stepSize` LOT_SIZE).
4. **SELL** lain: `quantity = nilai_usdt / harga sekarang`, dibulatkan ke `stepSize`.
5. Kalau BUY gagal karena saldo kurang (harga bergerak), kecilkan sedikit (misal ×0,99) lalu coba sekali lagi.
6. Order < 5 USDT (`MIN_NOTIONAL`) akan ditolak Binance — Python sudah menyaringnya, tapi tetap cek.
7. Simpan `orderId`, harga isi, qty isi, fee ke log trade.

### 4.6 Contoh kode Rust (reqwest + serde)

```rust
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Serialize)]
pub struct SignalRequest {
    pub modal: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub modal_awal: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kurs_usdt_idr: Option<f64>,
    pub posisi: HashMap<String, f64>,
    pub cash_usdt: f64,
}

#[derive(Deserialize, Debug)]
pub struct KillSwitch { pub aktif: bool, pub batas_idr: Option<f64> }

#[derive(Deserialize, Debug)]
pub struct Order {
    pub urutan: u32,
    pub symbol: String,
    pub side: String,            // "BUY" | "SELL"
    pub tipe: String,            // "MARKET"
    pub nilai_usdt: f64,
    pub qty_perkiraan: f64,
    pub harga_acuan: f64,
    pub jual_semua: bool,
}

#[derive(Deserialize, Debug)]
pub struct SignalResponse {
    pub tanggal_candle: String,
    pub strategi: String,        // "BTC-60" | "V23"
    pub status: String,          // "RISK_ON" | "RISK_OFF" | "STOP"
    pub kill_switch: KillSwitch,
    pub perlu_rebalance: bool,
    pub order: Option<Vec<Order>>,
    pub catatan: Vec<String>,
}

pub async fn fetch_signal(base_url: &str, body: &SignalRequest) -> anyhow::Result<SignalResponse> {
    let res = reqwest::Client::new()
        .post(format!("{base_url}/signal"))
        .header("X-API-Key", std::env::var("PYTHON_API_KEY")?)   // sama dengan API_KEY di .env Python
        .json(body)
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await?
        .error_for_status()?          // 4xx/5xx -> Err, jangan trading
        .json::<SignalResponse>()
        .await?;
    Ok(res)
}
```

Field response lain (`filter_pasar`, `alokasi_target`, `volatility_targeting`, `modal`) boleh ditambahkan ke
struct kalau dibutuhkan untuk dashboard — serde mengabaikan field yang tidak dideklarasikan.

### 4.7 Aturan posisi: apakah bot beli lagi setiap hari?

**Tidak.** `/signal` bukan sinyal "beli sekarang" per hari — isinya **target portofolio** (porsi ideal tiap coin).
Setiap hari Python membandingkan **posisi yang sedang dipegang** (`posisi` di body) dengan target:

```
Hari 1  risk-on, user belum punya coin   → order BUY 8 coin sesuai porsi
Hari 2  masih risk-on, posisi = target   → perlu_rebalance: false → TIDAK beli lagi
Hari 3  sama                             → tidak ada order
...     (coin dipegang terus, tidak ada batas hari)
Tgl 1   jadwal rebalance bulanan         → order kecil BUY/SELL supaya porsi kembali ke target
Hari X  pasar berubah jadi risk-off      → order SELL semua → pegang USDT
Hari Y  pasar risk-on lagi               → order BUY lagi
Kapan saja  modal <= 70% modal_awal      → kill switch: SELL semua, bot berhenti
```

Order hanya muncul kalau salah satu terjadi (lihat `alasan_rebalance`):

| Pemicu | Contoh `alasan_rebalance` |
|---|---|
| Jadwal bulanan (eksekusi tanggal 1) | `"jadwal rebalance bulanan (2026-10-01 tanggal 1)"` |
| Filter pasar berubah (risk-on ↔ risk-off) | `"filter pasar berubah mati"` |
| Posisi tidak sesuai target (coin yang harusnya dipegang belum ada, atau sebaliknya) | `"posisi tidak sesuai target: ['BTCUSDT']"` |
| Kill switch | `"kill switch aktif"` |

Karena itu **body `posisi` harus selalu saldo asli dari Binance** — itulah yang membuat bot tahu sudah punya
coin dan tidak membeli dobel. Kalau `posisi` tidak dikirim, Python tidak tahu isi akun dan hanya memberi target
(tanpa daftar order).

### 4.8 Frekuensi pengecekan: 1× sehari

Semua riset & simulasi memakai **candle harian (1d)** — tidak ada pengecekan per menit/per jam.

```
00:00 UTC (07:00 WIB)   candle harian tutup
                        → Python menghitung: risk-on/off, porsi target, kill switch
open hari berikutnya    → order dieksekusi (simulasi memakai harga open)
```

- Keputusan **hanya dari harga close harian**; kill switch juga dicek 1× sehari dari nilai modal saat itu.
- Di antara dua pengecekan bot **diam**, walaupun harga naik-turun di siang hari.
- Di Rust cukup **1 jadwal per hari** (±07:45 WIB, lihat bagian 10.2). Memanggil `/signal` lebih sering tidak
  berguna — candle harian belum berubah, jadi jawabannya sama.

---

## 5. `GET /recommendations/momentum` — daftar pantauan coin

Untuk **halaman rekomendasi** di aplikasi: trader minta rekomendasi → bot sudah menyaring universe Large/Mid
jadi 5–10 coin → trader menganalisis lagi sendiri. **Bukan sinyal bot**, tidak dieksekusi otomatis.

Urutan dihitung ulang setiap candle harian tutup, jadi bisa berubah tiap hari
(hari ini BTC peringkat 1, besok ETH). Tidak perlu body.

### Query

| Param | Default | Keterangan |
|---|---|---|
| `limit` | 10 | 5–10 coin. Peringkat 1–5 = `UTAMA`, 6–10 = `PELENGKAP` |
| `date` | candle terakhir | `YYYY-MM-DD`, untuk melihat rekomendasi hari tertentu |

```
GET /recommendations/momentum?limit=10
```

### Contoh response (dipotong ke 1 coin)

```json
{
  "date": "2026-07-11",
  "next_update": "setiap candle harian tutup (07:00 WIB)",
  "market": {
    "status": "RISK_OFF",
    "btc_close": 64182.87,
    "btc_sma100": 70799.08,
    "btc_above_sma100": false,
    "fear_greed": 26.0,
    "fear_greed_avg_14d": 20.2,
    "explanation": "BTC di bawah SMA100 dan rata-rata Fear & Greed 14 hari 20 (<= 50) -> pasar RISK-OFF: ..."
  },
  "warnings": [
    "PASAR RISK-OFF: historis rata-rata sinyal -2,59% (win rate 41,8%). ...",
    "Performa historis melemah: ..."
  ],
  "universe": { "categories": ["Large", "Mid"], "count": 21, "btc_included": true },
  "method": { "score": "...", "groups": "...", "plan": "...", "research": "..." },
  "dropped_from_top": [
    { "id": "....", "symbol": "QNTUSDT", "image_url": "http://192.168.0.109:8000/files/....png" }
  ],
  "recommendations": [
    {
      "rank": 1,
      "id": "8f6c2a1e-....-....-....-............",
      "symbol": "UNIUSDT",
      "image_url": "http://192.168.0.109:8000/files/8a854f46-8ae2-4749-9b6c-7c30ff181954.png",
      "group": "UTAMA",
      "market_cap_category": "Mid",
      "score": 1.0,
      "previous_rank": 1,
      "rank_change": 0,
      "close": 3.616,
      "change_1d": 0.0247,
      "change_7d": 0.1237,
      "rsi14": 74.13,
      "rsi7": 87.59,
      "plan": {
        "entry": "open 2026-07-12 (07:00 WIB)",
        "hold_days": 14,
        "sell_on": "close 2026-07-25",
        "hard_stop_pct": -0.25,
        "stop_loss_price_estimate": 2.712
      },
      "historical_stats": { "win_rate": 0.418, "avg_win": 0.085, "avg_loss": -0.106,
                            "expectancy": -0.026, "hit_stop": 0.096, "n": 1637 },
      "explanations": [
        "[Peringkat] #1 dari 21 coin (UTAMA) -- skor momentum 1.00 (0 = terlemah, 1 = terkuat di antara 21 coin)",
        "[RSI 14 hari] 74.1 -- sudah tinggi (>70), rawan koreksi",
        "[RSI 7 hari] 87.6 -- momentum jangka pendek kuat",
        "[Perubahan] posisi sama dengan kemarin"
      ]
    }
  ]
}
```

| Field | Untuk tampilan |
|---|---|
| `market.status` + `warnings[]` | **wajib ditampilkan** di atas daftar (banner). Risk-off = peringatan merah |
| `recommendations[].id` | UUID baris `flex_params` coin itu (`flex_params.id`) — penghubung ke data coin di Rust/FE. Juga ada di `dropped_from_top[]` dan riwayat |
| `recommendations[].image_url` | logo coin — `flex_params.photo_url` (logo CoinGecko yang disimpan & disajikan Rust di `/files/...`). `null` kalau coin belum punya foto |
| `recommendations[].group` | badge `UTAMA` / `PELENGKAP` |
| `previous_rank`, `rank_change` | panah naik/turun; `previous_rank = null` → label **BARU** |
| `dropped_from_top[]` | `{id, symbol, image_url}` — "keluar dari daftar sejak kemarin" |
| `change_1d`, `change_7d`, `score`, `historical_stats.win_rate` | angka **desimal** (0.1237 = 12,37%) |
| `plan` | rencana: beli open besok, pegang 14 hari, stop −25% (`stop_loss_price_estimate` dari close; hitung ulang dari harga beli asli) |
| `explanations[]` | teks penjelasan siap tampil |
| `historical_stats` | statistik historis kelompok coin ini sesuai status pasar hari ini (bukan per coin) |

Rekomendasi aman di-cache di Rust sampai candle harian berikutnya (isinya hanya berubah sekali sehari).

### Aturan posisi: kalau coin muncul lagi besok, beli lagi?

Rekomendasi **tidak dieksekusi otomatis**; ini aturan yang disarankan untuk trader (dan untuk fitur "ikuti
rekomendasi" kalau nanti dibuat di Rust):

```
Hari 1   NEAR muncul di daftar        → beli di open besok (hari 2), catat tanggal jual = hari 1 + 14
Hari 2   NEAR muncul lagi             → JANGAN beli lagi; tetap pegang posisi lama, tanggal jual TIDAK digeser
Hari 5   NEAR keluar dari daftar      → TETAP pegang (keluar daftar bukan sinyal jual)
Kapan saja  harga <= beli × 0,75      → jual (stop −25%)
Hari 15  close                        → jual (14 hari selesai)
Hari 16  NEAR masih/muncul di daftar  → itu sinyal BARU → boleh beli lagi, hitung 14 hari baru
```

Ringkasnya: **satu posisi per coin, jual hanya karena 14 hari selesai atau stop −25%**. Coin lain yang
muncul di daftar boleh dibeli sebagai posisi terpisah (bagi modal rata; hindari > 5 posisi terbuka sekaligus
kalau modal kecil, karena order minimum Binance 5 USDT).

> ⚠️ **Catatan jujur**: statistik di `historical_stats` dan `/history` menghitung **setiap kemunculan harian
> sebagai sinyal terpisah** (coin yang muncul 5 hari berturut-turut = 5 sinyal yang tumpang tindih). Aturan
> "satu posisi per coin" di atas lebih realistis tapi **belum disimulasikan khusus** — akan diuji di notebook
> riset 07. Hasilnya bisa sedikit berbeda dari angka statistik yang ditampilkan.

### Frekuensi pengecekan rekomendasi

- **Beli**: harga open setelah sinyal · **jual 14 hari**: harga close hari ke-14 → cukup dicek **1× sehari**.
- **Stop −25%** di simulasi dicek dengan **harga low harian**: kalau harga terendah hari itu menyentuh −25%,
  dianggap terjual di harga stop (kalau harga dibuka sudah di bawah stop / gap turun → terjual di harga open).
  Ini **setara dengan order stop-loss di Binance** yang berjaga 24 jam.

Kalau nanti ada fitur "ikuti rekomendasi" di Rust:

- **Disarankan**: begitu beli, langsung pasang order **`STOP_LOSS_LIMIT`** (atau **OCO**) di Binance pada
  `harga_beli × 0,75`. Binance yang berjaga — Rust tidak perlu memantau harga terus.
- Alternatif: Rust cek harga tiap 1–5 menit lalu jual kalau harga ≤ stop — lebih boros request dan bisa terlambat
  kalau harga bergerak cepat.

### Ringkasan frekuensi (bot & rekomendasi)

| | Frekuensi cek | Di simulasi | Di Rust |
|---|---|---|---|
| `/signal` (bot) | 1× sehari | close harian → eksekusi di open besok | jadwal ±07:45 WIB |
| Rekomendasi: beli & jual 14 hari | 1× sehari | open / close harian | jadwal harian |
| Rekomendasi: stop −25% | sepanjang hari | memakai **low** harian | **order stop-loss di Binance** |

---

## 6. `GET /recommendations/momentum/history` — riwayat (paper trading)

Rekomendasi hari-hari sebelumnya beserta hasilnya kalau diikuti (beli open besok, jual close hari ke-14,
stop −25%, biaya 0,15%/sisi). Dihitung ulang dari candle — tidak ada yang disimpan.

| Param | Default | Keterangan |
|---|---|---|
| `days` | 30 | 1–120 hari ke belakang |
| `date` | candle terakhir | hari terakhir riwayat |

```json
{
  "until": "2026-07-11",
  "days": 20,
  "rule": "beli open hari berikutnya, jual close hari ke-14, stop keras -25%, biaya 0.15%/sisi",
  "summary": {
    "UTAMA_risk_on":      { "finished": 0,  "running": 0,  "win_rate": null,  "expectancy": null,   "hit_stop": null },
    "UTAMA_risk_off":     { "finished": 30, "running": 65, "win_rate": 0.6,   "expectancy": 0.0515, "hit_stop": 0.0 }
    // ... PELENGKAP_risk_on, PELENGKAP_risk_off
  },
  "historical_stats": { "...": "angka riset untuk pembanding" },
  "history": [
    { "date": "2026-07-11", "market": "RISK_OFF", "out_of_sample": true,
      "recommendations": [ { "rank": 1, "id": "....", "symbol": "UNIUSDT", "image_url": "http://.../files/....png", "group": "UTAMA", "status": "MENUNGGU_ENTRY" } ] },
    { "date": "2026-06-22", "market": "RISK_OFF", "out_of_sample": false,
      "recommendations": [ { "rank": 1, "symbol": "TRXUSDT", "group": "UTAMA", "status": "SELESAI",
                             "entry_price": 0.334, "exit_or_last_price": 0.3297,
                             "exit_or_last_date": "2026-07-06", "return": -0.0158 } ] }
  ]
}
```

`status` per rekomendasi: `MENUNGGU_ENTRY` (belum ada harga beli) · `BERJALAN` (belum 14 hari, `return` =
sementara) · `SELESAI` · `STOP_KERAS` (kena −25%). `history` urut terbaru di atas.

---

## 7. Error

Body error selalu `{"detail": ...}`.

| HTTP | Kapan | `detail` |
|---|---|---|
| 401 | header `X-API-Key` tidak ada / salah (kalau `API_KEY` aktif) | `"API key tidak valid atau tidak dikirim (header X-API-Key)"` |
| 404 | candle/tanggal tidak ada di DB, BTC tidak ada, flex_params kosong | string, mis. `"Tidak ada candle untuk 2030-01-01 di database"` |
| 422 | validasi body/query gagal (mis. `modal: 0`, `limit: 4`, tanggal bukan `YYYY-MM-DD`, angka `NaN`/`Infinity`, qty negatif, simbol bukan huruf/angka, `posisi` > 100 coin) | **list** objek FastAPI: `[{"loc": ["body","modal"], "msg": "Input should be greater than 0", ...}]` |
| 422 | histori BTC < 101 hari, coin terskor < 5 | string |
| 500 | bug / DB putus di tengah request | `"Terjadi kesalahan di server"` (detail hanya di log Python) |

Di Rust: anggap **semua non-2xx = jangan trading**, log body-nya apa adanya (bisa string atau list).

---

## 8. Skenario tes (Postman / Insomnia)

Ini **kondisi pura-pura** untuk memastikan Python menjawab benar — di produksi kondisi datang sendiri dari akun asli.
Semua `POST http://localhost:8080/signal`, Body → JSON.

| # | Body | Harus keluar |
|---|---|---|
| 1 | `{"modal": 1000000}` | `strategi: "BTC-60"`, `order: null` |
| 2 | `{"modal": 2000000, "modal_awal": 2000000}` | `strategi: "V23"`, `kill_switch.batas_idr: 1400000` |
| 3 | `{"modal": 2000000, "modal_awal": 2000000, "kurs_usdt_idr": 16300, "posisi": {"BTCUSDT": 0.0005, "ETHUSDT": 0.01}, "cash_usdt": 60}` | `order` berisi daftar (SELL semua kalau risk-off) |
| 4 | `{"modal": 1300000, "modal_awal": 2000000}` | `kill_switch.aktif: true`, `status: "STOP"` |
| 5 | `{"modal": 0}` | HTTP **422** |
| 6 | `{"modal": 2000000, "posisi": {}, "cash_usdt": 122}` | user baru: daftar BUY kalau risk-on, kosong kalau risk-off |
| 7 | `{"modal": 2000000, "posisi": {}, "cash_usdt": 122, "tanggal": "2025-07-15"}` | replay hari risk-on: `status: "RISK_ON"`, 8 order BUY (BTC, ETH, BNB, XRP, ADA, LINK, TRX, DOGE) |

GET rekomendasi:
```
GET http://localhost:8080/recommendations/momentum?limit=10      → 200, 10 coin
GET http://localhost:8080/recommendations/momentum?limit=4       → 422
GET http://localhost:8080/recommendations/momentum?date=2030-01-01 → 404
GET http://localhost:8080/recommendations/momentum/history?days=30 → 200
```

### 8.1 Koleksi curl (siap import ke Postman)

Format bash. **Postman → Import → Raw text → tempel satu blok curl** — request langsung jadi, lengkap dengan
header & body. Variabel `{{base_url}}` dan `{{api_key}}` otomatis terbaca sebagai variabel Postman; isi
sekali di **Environment**:

| Variable | Nilai |
|---|---|
| `base_url` | `http://localhost:8080` |
| `api_key` | nilai `API_KEY` di `.env` Python |

Semua endpoint kecuali `/health` wajib header `X-API-Key`; tanpa itu → **401**.

**Health** (tanpa key)
```bash
curl --location '{{base_url}}/health'
```

**Rekomendasi hari ini (10 coin)**
```bash
curl --location '{{base_url}}/recommendations/momentum?limit=10' \
  --header 'X-API-Key: {{api_key}}'
```

**Rekomendasi tanggal tertentu (5 coin)**
```bash
curl --location '{{base_url}}/recommendations/momentum?limit=5&date=2026-09-30' \
  --header 'X-API-Key: {{api_key}}'
```

**Riwayat / paper trading 30 hari**
```bash
curl --location '{{base_url}}/recommendations/momentum/history?days=30' \
  --header 'X-API-Key: {{api_key}}'
```

**Signal — produksi (body yang dikirim Rust tiap hari)**
```bash
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{
    "modal": 2000000,
    "modal_awal": 2000000,
    "kurs_usdt_idr": 16300,
    "posisi": { "BTCUSDT": 0.0005, "ETHUSDT": 0.01 },
    "cash_usdt": 60
  }'
```

**Signal — modal kecil (BTC-60)**
```bash
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{ "modal": 1000000 }'
```

**Signal — user baru, belum punya coin**
```bash
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{ "modal": 2000000, "modal_awal": 2000000, "posisi": {}, "cash_usdt": 122 }'
```

**Signal — kill switch (modal turun > 30%)**
```bash
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{ "modal": 1300000, "modal_awal": 2000000 }'
```

**Signal — replay hari risk-on (khusus tes)**
```bash
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{ "modal": 2000000, "posisi": {}, "cash_usdt": 122, "tanggal": "2025-07-15" }'
```

**Tes error** (harus 422 / 404 / 401)
```bash
# 422 — modal harus > 0
curl --location '{{base_url}}/signal' \
  --header 'Content-Type: application/json' \
  --header 'X-API-Key: {{api_key}}' \
  --data '{ "modal": 0 }'

# 422 — limit minimal 5
curl --location '{{base_url}}/recommendations/momentum?limit=4' \
  --header 'X-API-Key: {{api_key}}'

# 404 — tanggal tidak ada di DB
curl --location '{{base_url}}/recommendations/momentum?date=2030-01-01' \
  --header 'X-API-Key: {{api_key}}'

# 401 — tanpa API key
curl --location '{{base_url}}/recommendations/momentum'
```

Hasil yang diharapkan (dicek 6 Okt 2026, candle terakhir 2026-10-03):

| Request | HTTP | Isi penting |
|---|---|---|
| health | 200 | `"database": "connected"` |
| rekomendasi `limit=10` / `limit=5` | 200 | 10 / 5 coin, tiap coin ada `id`, `image_url`, `group` |
| history `days=30` | 200 | `summary` + `history[]` |
| signal produksi | 200 | `strategi: "V23"`, `order` SELL dulu lalu BUY |
| signal modal kecil | 200 | `strategi: "BTC-60"`, `order: null` (tanpa `posisi`) |
| signal user baru | 200 | daftar BUY (kalau risk-on) |
| signal kill switch | 200 | `status: "STOP"`, `kill_switch.aktif: true` |
| signal replay 2025-07-15 | 200 | `status: "RISK_ON"`, 8 order BUY |
| `modal: 0` / `limit=4` | 422 | `detail` = list error validasi |
| `date=2030-01-01` | 404 | `"Tidak ada candle untuk 2030-01-01 di database"` |
| tanpa key | 401 | `"API key tidak valid atau tidak dikirim (header X-API-Key)"` |

**Di terminal (bukan Postman)**: ganti `{{base_url}}` & `{{api_key}}` dengan nilai asli. Di Windows PowerShell
pakai `curl.exe` (bukan `curl`) dan body JSON lewat file (`-d "@body.json"`) supaya tanda kutip tidak rusak:

```powershell
$KEY = (Select-String -Path .env -Pattern '^API_KEY=(.*)').Matches.Groups[1].Value
curl.exe -H "X-API-Key: $KEY" "http://localhost:8080/recommendations/momentum?limit=10"
```

---

## 9. Checklist sebelum bot jalan dengan uang asli

- [ ] Collector mengisi candle `1d` **semua** simbol aktif Large/Mid + BTC setiap hari (cek: tidak ada catatan "tertinggal")
- [ ] `fear_greed_index` terisi tiap hari
- [ ] `modal_awal` user disimpan di DB Rust saat bot pertama kali diaktifkan
- [ ] Scheduler memanggil `/signal` sekali sehari ±07:05 WIB, **setelah** collector selesai
- [ ] Non-2xx atau data tertinggal → bot tidak trading hari itu
- [ ] Order dijalankan sesuai `urutan` (SELL dulu), BUY pakai `quoteOrderQty`, `jual_semua` jual seluruh saldo
- [ ] Kill switch → bot user berhenti & user dikabari
- [ ] Semua request/response/order dicatat di log trade
- [ ] Uji coba dulu dengan Binance **testnet** atau modal kecil

---

## 10. Perubahan yang dibutuhkan di backend Rust

Python = **otak** (memutuskan beli/jual & rekomendasi), Rust = **badan** (menyediakan data lengkap & tepat waktu,
menjalankan perintah dengan disiplin). Bagian ini menjelaskan apa yang harus dijamin Rust supaya otaknya tidak salah.

### 10.1 Cara kerja Rust sekarang (dibaca dari kode, 2 Okt 2026)

**`src/services/coin_symbols`** — sekali sehari, mengisi `flex_params` (`SIMBOL_CRYPTO`):

1. Ambil pair USDT spot yang `TRADING` di Binance (`/api/v3/exchangeInfo`).
2. Ambil volume 24 jam dalam USDT (`/api/v3/ticker/24hr`).
3. Validasi ke CoinGecko top 250: crypto asli (bukan saham tokenized), bukan stablecoin, bukan token emas.
4. **Coin besar** = lolos validasi **dan volume 24 jam ≥ $5 juta** → tetap/masuk daftar; selain itu di-soft-delete.
   Coin yang dulu dihapus sistem lalu besar lagi → dipulihkan.
5. Kategori (`description`) dari market cap CoinGecko: **Large ≥ $50 miliar, Mid ≥ $5 miliar, sisanya Small**.
6. Kategori 8 coin V23 dikunci (`LOCKED_CATEGORY_SYMBOLS`) — tidak ikut berubah.

**`src/services/candle_ohlcv`** — tiap 30 menit:

- Simbol = semua `flex_params` `SIMBOL_CRYPTO` yang **tidak di-soft-delete** (aktif maupun tidak).
- Simbol baru → histori awal **500 candle** (backfill otomatis).
- Simbol yang tertinggal → dikejar dari candle terakhirnya (maks 1000), jadi lubang data tertambal sendiri.
- Hanya candle yang sudah tutup yang disimpan; `ON CONFLICT DO NOTHING`.

Hubungannya dengan Python: Python membaca universe dari `flex_params` yang tidak di-soft-delete → **semua coin
yang diranking otomatis sudah lolos standar volume $5 juta**. Python tidak mengecek volume lagi.

### 10.2 WAJIB (bot bisa salah/macet kalau tidak)

**1. Kunci 8 coin V23 supaya tidak pernah di-soft-delete.**
Kategorinya sudah dikunci, tapi coinnya masih bisa di-soft-delete kalau volume < $5 juta → candle berhenti →
`/signal` V23 macet (butuh 8 coin lengkap). Di `coin_symbols/service.rs`:

```rust
let is_big_coin = |symbol: &str| {
    LOCKED_CATEGORY_SYMBOLS.contains(&symbol) || ( /* aturan volume + CoinGecko yang sudah ada */ )
};
```

**2. Panggil `/signal` setelah candle kemarin benar-benar masuk, dan cek tanggalnya.**
Candle tutup 00:00 UTC, worker jalan tiap 30 menit → candle baru bisa baru masuk ±00:30 UTC. Kalau `/signal`
dipanggil terlalu cepat, Python memakai candle **kemarin lusa** tanpa peringatan (peringatan baru muncul kalau
tertinggal > 2 hari).

- Jadwal `/signal` **±07:45 WIB** (00:45 UTC).
- Sebelum eksekusi: `tanggal_candle` harus = **kemarin (UTC)**. Kalau tidak → jangan trading, coba lagi 30 menit kemudian.

**3. Selidiki `HYPEUSDT` dan `ZECUSDT`** — aktif di `flex_params` tapi candle-nya 0. Cek log
`Sync candle HYPEUSDT gagal: ...`. Kalau pair-nya memang tidak bisa diambil, `coin_symbols` sebaiknya tidak
mengaktifkannya.

### 10.3 Disarankan (supaya sinyal stabil)

**4. Histeresis volume** — coin yang volumenya mondar-mandir di sekitar $5 juta keluar-masuk daftar tiap hari, jadi
urutan rekomendasi berubah karena **isi universe** berubah, bukan karena momentum. Pilih salah satu:

- masuk kalau volume ≥ **$5 juta**, keluar hanya kalau < **$3 juta**; atau
- pakai **rata-rata volume 7 hari** (dari `candle_ohlcv`: `volume × close`) sebagai ganti volume 24 jam — sekaligus
  menyaring coin yang cuma di-pump sehari.

**5. Tetap kumpulkan candle coin yang di-soft-delete ±30 hari.** Kalau coin yang sudah direkomendasikan keluar
dari daftar, candle-nya berhenti → hasil paper trading `/recommendations/momentum/history` macet di `BERJALAN`.
Cukup ubah query simbol worker candle:

```sql
WHERE type_param = 'SIMBOL_CRYPTO'
  AND (deleted_at IS NULL OR deleted_at > now() - interval '30 days')
```

**6. Simpan state yang sengaja tidak disimpan Python:**

- `modal_awal` per user (sekali, saat bot diaktifkan) — dipakai kill switch;
- status bot per user: aktif / berhenti karena kill switch;
- log tiap request + response `/signal` + order yang dieksekusi (harga isi, qty, fee) — untuk audit & evaluasi.

### 10.4 Opsional

**7. Cache rekomendasi per hari** — isinya hanya berubah sekali sehari setelah candle baru masuk; tidak perlu
memanggil Python setiap user membuka halaman.

**8. Monitoring** — cek `/health` berkala; alert kalau `catatan` (`/signal`) atau `warnings` (rekomendasi) berisi
kata "tertinggal".

### 10.5 Yang dikerjakan di sisi Python

- Universe rekomendasi sekarang hanya Large/Mid = **14 coin** (karena batas kategori naik ke $50 miliar/$5 miliar),
  jadi top-10 = 70% universe — hampir tidak menyaring. Rencana: uji universe **Large + Mid + Small** (±61 coin,
  semua sudah lolos $5 juta) di notebook riset 07, ukur ulang `historical_stats`, lalu ubah endpoint kalau hasilnya
  layak. **Tidak ada perubahan yang dibutuhkan di Rust** untuk ini.
