# RESEARCH SIGNAL TRADING

Catatan riset strategi sinyal trading crypto untuk bot backend Rust. Folder ini berisi notebook
03 → 25; setiap notebook punya sel **Kesimpulan** di bagian akhir. README ini merangkum semuanya
dan mencatat **keputusan yang berlaku sekarang**.

Terakhir diperbarui: 1 Oktober 2026 (notebook 25).

---

## 1. Keputusan yang berlaku sekarang

Strategi dipilih otomatis dari besar modal. Sudah diimplementasikan di backend Python sebagai
`POST /signal` (`src/services/signal_trading/`, rumus inti di `src/strategy/allocation.py`); backend Rust
yang menjalankan order.

| Modal | Strategi | Asal riset |
|---|---|---|
| **< Rp1.500.000** | **BTC-60**: BTC saja, 60% modal di BTC, 40% USDT | notebook 13, 17, 18 |
| **≥ Rp1.500.000** | **V2-60**: 8 coin, 60% modal di coin, 40% USDT | notebook 15, 19, 20 |

### Aturan (berlaku untuk keduanya)

1. **Filter pasar H8b**, dicek sekali sehari setelah candle harian close (00:00 UTC = 07:00 WIB):
   *risk-on* kalau **close BTC > SMA100 BTC** **atau** **rata-rata Fear & Greed 14 hari > 50**.
   Selain itu *risk-off*: semua coin dijual ke USDT.
2. **Aset V2-60**: BTC, ETH, BNB, XRP, ADA, LINK, TRX, DOGE (DOGE maks 10% dari bagian coin).
   Porsi tiap coin berbanding terbalik dengan volatilitas harian 60 hari (coin yang lebih liar dapat
   porsi lebih kecil). LTC & BCH sengaja **dikeluarkan** (notebook 14).
3. **Rebalance**: kalau besok tanggal 1, filter pasar berubah, atau isi akun tidak sesuai target.
   Eksekusi di harga open hari berikutnya.
4. **Order < 5 USDT dilewati** (order minimum Binance spot).
5. **Kill switch**: modal ≤ 70% modal awal → jual semua ke USDT dan bot berhenti untuk dievaluasi.
6. **Spot tanpa leverage** → tidak ada margin call / likuidasi (notebook 18).
7. **Trailing-stop per-coin — BELUM diputuskan, belum diimplementasikan** (notebook 22): di periode
   dev (sampel besar) konsisten unggul (profit≥20%, ambang 2× ATR-14 dari puncak). Tapi di periode uji,
   hasilnya (menang/kalah vs V2-60 polos) **berganti-ganti hanya dengan menggeser modal ±Rp100rb atau
   ambang order ±$1** — tanda sampel kejadian stop di periode uji (±30-40×, 3.5 tahun) terlalu kecil
   buat diukur presisi lewat backtest historis saja. Bukan "terbukti gagal" (beda dari filter per-coin,
   notebook 21, yang memang konsisten gagal) — masuk kategori "belum terbukti ke arah manapun". Kalau
   mau dicoba, perlu paper trading/testnet buat validasi, bukan cuma backtest tambahan.
8. **Volatility targeting — DIREKOMENDASIKAN, belum diimplementasikan** (notebook 23): eksposur ke
   coin tidak lagi tetap 60% (dikali filter H8b biner), tapi **terus menyesuaikan diri** ke volatilitas
   portofolio yang sedang terjadi — target **20%/tahun**, lookback realized-vol **20 hari**, eksposur
   maks **100%** (bukan leverage — batas atas porsi coin), filter H8b tetap dipakai sebagai pengali,
   bukan diganti. Terbukti unggul di **semua** metrik sekaligus vs V2-60 murni (profit, max drawdown,
   Sharpe, rugi harian) — konsisten di dev, uji, modal nyata Rp1,5 juta, sensitivitas modal, buang satu
   coin, lookback, dan biaya 2×. Paling solid dari semua ide yang sudah dites di sesi ini. Laporan
   portofolio lengkap (gaya notebook 20) ada di **notebook 25**: Rp1,5jt → Rp3,95jt (+163,6%),
   DD −15,6%, 47,6% bulan untung — menang di semua metrik yang sebanding vs V2-60 murni.
9. **De-risking berbasis drawdown portofolio & universe >8 coin — DITOLAK** (notebook 24): de-risking
   halus (bukan kill-switch biner) terlalu lambat bereaksi (rugi harian terburuk tidak berubah sama
   sekali di semua ambang yang dicoba) dan menurunkan Sharpe kalau digabung dengan volatility
   targeting. Universe lebih luas (20 coin) terbukti lebih buruk di uji out-of-sample — korelasi
   pairwise rata-rata tetap tinggi (0.72) pas crash 2022, diversifikasi dari nambah coin crypto
   large/mid-cap itu ilusi.

### Ekspektasi realistis (simulasi, bukan jaminan)

| | BTC-60, modal Rp400rb | V2-60, modal Rp1,5 jt |
|---|---|---|
| Profit per tahun | ±+36% (2019–2026) | **±+30%** (periode uji 2023–2026) |
| Penurunan terbesar | ±−25% | ±−19% s/d −24% |
| Rata-rata profit per bulan | ±Rp12rb | ±Rp37rb (±Rp1.200/hari) |
| Bulan untung | ±42% | ±44% |
| Modal ≥ modal awal setelah 12 bulan | ±84% kemungkinan | ±91% kemungkinan |

Pola strategi ini: **lebih sering rugi kecil, sesekali untung besar** (win rate ±38%, rata-rata untung
per trade ±5× rata-rata rugi). Sekitar setengah bulan hasilnya datar (USDT) atau minus. Nilai hasil
per 6–12 bulan, bukan per hari.

---

## 2. Riwayat riset per notebook

| No | Notebook | Pertanyaan | Hasil | Status |
|---|---|---|---|---|
| 03 | `03_sell_signal_exploration` | Bisakah sinyal topping (RSI>70 & FGI>75) dipakai sebagai sinyal keluar posisi V5? | Kejadian topping yang benar-benar diikuti penurunan hanya 39.9%; tidak lebih baik dari aturan exit yang ada | Ditunda |
| 04 | `04_atr_based_exit` | SL/TP berbasis ATR vs persen tetap (−2% / +5%) | Ditemukan **bug backtest lama** (hanya melihat harga hari ke-5): win rate 58.4% ternyata 22.6% kalau SL dicek harian. ATR (−1.5× / +2×) jauh lebih baik | Diterapkan ke V5 |
| 06 | `06_portfolio_single_position` | Strategi V5 dalam mode 1 posisi + rotasi + hard stop + circuit breaker | Out-of-sample 2024–2026: **−21.0%** vs BTC +32.7%. Tidak satu pun dari 324 kombinasi untung | **V5 ditolak** |
| 07 | `07_strategy_research` | Cari strategi lebih baik (10 coin): tren BTC, rotasi momentum, breakout, buy-the-dip | Rotasi momentum terlihat +204% (Konservatif) / +355% (Agresif) | Belakangan ditolak (lihat 08–11) |
| 08 | `08_overfitting_audit` | Apakah hasil 07 overfit? | PBO 37%, Deflated Sharpe 82%, tanpa SUI hanya +4.6% → **overfit sebagian** | – |
| 09 | `09_dataset_large_mid` | Siapkan data semua coin Large/Mid (kurangi survivorship bias) | 50 simbol, 43 bisa dipakai (7 stablecoin dibuang); GRAM diambil sebagai TONUSDT | Data siap |
| 10 | `10_strategy_research_40coin` | Ulangi 07 dengan 40 coin | Rotasi 07 hanya +28.8% (= BTC); pemilihan ulang parameter −21.7%, DD −78%. Filter tren BTC paling kuat | **Rotasi ditolak** |
| 11 | `11_overfitting_audit_40coin` | Audit ulang di 40 coin + uji data segar 2018–2020 | Rotasi: PBO 61%, pilihan coin tidak lebih baik dari acak (p=43%). Filter tren: konsisten di 3 periode, lebih baik dari timing acak (p=2.8%) | Filter tren dipakai |
| 12 | `12_final_strategy_stats` | Win rate, rugi, drawdown, profit tiap kandidat | Filter tren SMA100 paling konsisten: DD ±35–39% di semua periode | – |
| 13 | `13_fear_greed_strategies` | Manfaatkan Fear & Greed Index (17 hipotesis) | **H8b** (tren ATAU FGI 14h > 50) satu-satunya ≥ SMA100 di 3 periode; FGI lebih baik dari sinyal acak (p=0.4%). Menekan drawdown paling efektif dengan porsi tetap 60% | **H8b dipakai** |
| 14 | `14_coin_grouping` | Kelompokkan 10 coin besar berdasarkan karakter | Utama (BTC, ETH, BNB, XRP, ADA, LINK, TRX), fork lama (LTC, BCH), meme (DOGE). Korelasi naik ke 0.70 saat crash | LTC/BCH dikeluarkan |
| 15 | `15_portfolio_rebalance` | Portofolio multi-coin + rebalance ("seperti saham") | **V2** (inverse-vol, filter H8b, bulanan): uji 2023–2026 +307% vs BTC-only +253%, Sharpe 1.16 vs 1.14. Filter tren per coin justru merugikan | **V2 dipakai** |
| 16 | `16_data_validation` | Apakah data harga & FGI faktual? | Cocok dengan Coinbase (selisih median 0.04–0.06%), FGI 100% identik dengan API; anomali ADA/LINK ternyata kesalahan CoinGecko | Data valid |
| 17 | `17_small_capital_risk` | Modal Rp400rb: target Rp30rb/hari, rugi maks Rp10rb/hari? | Target 7.5%/hari tidak realistis (tercapai 0.1% hari). Stop harian merusak hasil (+36% → +6.6%/tahun). V2 butuh modal ≥ ±Rp1,85 jt | BTC-60 untuk modal kecil |
| 18 | `18_capital_survival` | Bisa margin call? Seberapa sering modal turun? | Spot = tidak ada MC. Porsi 60%: titik terendah historis Rp302rb, tidak pernah sentuh kill switch | – |
| 19 | `19_capital_1_5m_portfolio` | Modal Rp1,5 jt dengan order minimum $5 | V2-60 bisa jalan; uji 2023–2026 +30%/tahun, DD −19%; 91% kemungkinan ≥ modal setelah 12 bulan | **V2-60 dipilih** |
| 20 | `20_v2_60_portfolio_stats` | Statistik lengkap V2-60 (aset, untung/rugi per aset, pertumbuhan modal) | Rp1,5 jt → Rp3,78 jt (2023–2026), semua 8 aset menyumbang untung, 120 trade (win rate 38%). Data dashboard diekspor ke `notebooks/data/processed/v2_60_dashboard.json` | – |
| 21 | `21_percoin_filter_redistribution` | Spek baru (30 Sep 2026) minta filter tren per-coin ditambahkan ke V2-60 (coin tren jelek → porsi dipindah ke coin lain, bukan cash). Apakah ini beda dari V3 notebook 15 yang ditolak? | Indikator terbaik (dicari empiris, bukan diasumsikan): jarak dari puncak 30/60 hari, bukan SMA100. Tapi di engine portofolio penuh, **5 desain** (trigger harian, dikunci bulanan, persisten 2 bulan, mayoritas 3 indikator, scaled bertahap) **semua gagal** mengalahkan V2-60 murni di uji 2023–2026 (Sharpe 1.11–1.17 vs baseline 1.17; trigger harian malah jauh lebih buruk, Sharpe 0.87, karena turnover 5–6×) | **Filter per-coin ditolak lagi** (dengan mekanisme & indikator baru sekalipun) |
| 22 | `22_trailing_stop_percoin` | Spek baru minta trailing-stop per-coin (profit min % + ambang penurunan dari puncak berskala volatilitas, dana diparkir sampai rebalance bulanan berikutnya) — belum pernah diuji. Berapa ambang yang masuk akal? | Di skala modal besar/ideal: ambang terpilih (profit≥20%, penurunan≥2×ATR-14) unggul di uji (Sharpe 1.17→1.27). Di modal nyata Rp1,5jt+$5 (nb 19/20) sedikit kalah — tapi tes sensitivitas (modal ±Rp100rb, order minimum ±$1) menunjukkan pemenangnya **gampang kebalik**, tanda sampel kejadian stop di uji (±30-40×) terlalu kecil buat diukur presisi. Dugaan awal (order ke-skip krn <$5) terbukti salah saat dicek (183 vs 225, trailing justru lebih sedikit skip) | **Belum bisa disimpulkan** — beda dari filter per-coin yang memang konsisten gagal; ini butuh paper trading buat validasi, bukan cuma backtest |
| 23 | `23_volatility_targeting` | User minta ide fundamental baru (bukan tempelan per-coin) dengan tujuan eksplisit: rugi harian kecil/0, profit boleh tapi bukan prioritas. Diagnosis: korelasi 8 coin naik ke 0.70 pas crash (nb 14) — filter/stop per-coin tidak bisa memperbaiki ini. Gimana manajemen level-portofolio? | Ganti eksposur tetap 60%/biner H8b jadi eksposur yang terus menyesuaikan ke volatilitas portofolio yang sedang terjadi (target 20%/th, lookback 20 hari, maks 100%, dikali filter H8b). **Menang di SEMUA metrik sekaligus** vs V2-60 di uji + modal nyata Rp1,5jt: profit +163.6% vs +151.7%, DD −15.6% vs −19.2%, Sharpe 1.38 vs 1.16, rugi harian terburuk −6.4% vs −7.6%. Lolos sensitivitas modal, buang-satu-coin, lookback 15-60 hari, biaya 2× | **Direkomendasikan** — hasil paling solid di seluruh sesi riset ini |
| 24 | `24_derisking_dan_universe_luas` | Dua ide pelengkap dari permintaan user yang sama: (a) de-risking halus berbasis drawdown portofolio (bukan kill-switch biner), (b) universe lebih luas dari 8 coin (data 50 coin ada di `notebooks/data/raw`) | (a) Rugi harian terburuk tidak berubah sama sekali di semua ambang (sinyal drawdown baru muncul setelah rugi terjadi, telat); digabung dengan vol-targeting malah menurunkan Sharpe. (b) 20 coin: korelasi pairwise rata-rata 0.72 pas crash 2022 (vs 0.51 bull 2024); di uji 2023-2026 20 coin lebih buruk dari 8 coin di semua metrik (Sharpe 0.98 vs 1.17, DD −29% vs −21%) | **Keduanya ditolak** — vol-targeting (nb 23) sendirian sudah lebih baik dari kombinasi manapun yang dicoba |
| 25 | `25_voltargeting_portfolio_stats` | Laporan portofolio lengkap (gaya sama seperti notebook 20) buat strategi terpilih notebook 23 — aset, untung/rugi per aset, pertumbuhan modal, modal Rp1,5 juta nyata | Rp1,5 jt → **Rp3,95 jt** (+163,6%, ±+32%/tahun), DD −15,6%, 47,6% bulan untung, semua 8 aset tetap untung, 107 trade (win rate 37%), fee total Rp75.656 (lebih kecil dari nb20 meski transaksi sedikit lebih banyak — ukuran transaksi mengecil saat eksposur diturunkan). Menang di semua metrik yang sebanding vs notebook 20. Dashboard diekspor ke `notebooks/data/processed/v23_voltargeting_dashboard.json` | – |

---

## 3. Strategi yang ditolak dan alasannya

| Strategi | Kenapa ditolak |
|---|---|
| **V5** (beli saat bottoming RSI<30 & FGI<25 + konfirmasi + model ML) | Angka lama 61.8% win rate ternyata diuji di data latihnya sendiri. Out-of-sample rugi (−21%). Sinyal terlalu jarang (±8 hari/tahun) dan membeli coin yang sedang jatuh tidak punya keunggulan |
| **Rotasi momentum 1 coin** (pegang 1 coin terkuat) | Keunggulannya muncul karena universe 10 coin dipilih dari coin yang sudah sukses (SUI). Di 40 coin tidak lebih baik dari memilih acak |
| **Beli saat takut ekstrem** (FGI ≤ 20–25) tanpa filter tren | Rugi di hampir semua variasi (−50% di 2021–2023) |
| **Jual saat euforia** (FGI ≥ 75) | Memotong keuntungan bull market |
| **Porsi berbasis FGI** | Kalah dari porsi tetap dengan rata-rata sama; FGI berkorelasi 0.82 dengan tren harga |
| **Filter tren per coin / strategi khusus per coin** | Menurunkan hasil portofolio (rawan overfit) — dites ulang di notebook 21 dengan indikator empiris (jarak dari puncak, bukan SMA100) + mekanisme redistribusi (bukan cash-out) + 5 variasi desain (harian/bulanan/persisten/mayoritas/scaled): semua tetap gagal mengalahkan baseline di uji |
| **Stop rugi harian** (Rp10rb/hari) | Posisi sering ditutup di titik terburuk: +36% → +6.6%/tahun |
| **De-risking halus berbasis drawdown portofolio** | Reaktif bukan prediktif — rugi harian terburuk tidak berubah sama sekali di semua ambang (nb 24); digabung dengan volatility targeting malah menurunkan Sharpe tanpa perbaikan DD berarti |
| **Universe >8 coin (large/mid-cap crypto)** | Korelasi pairwise rata-rata tetap tinggi (0.72) pas crash — sama seperti alasan LTC/BCH dikeluarkan (nb 14), cuma diperluas ke 20 coin. Lebih buruk di semua metrik saat diuji out-of-sample (nb 24) |
| **Sinyal SELL / short dari topping** | Ditunda (notebook 03), bukan ditolak permanen |

---

## 4. Pelajaran metodologi (wajib diikuti riset berikutnya)

1. **Pisahkan data pemilihan dan data uji.** Parameter dipilih hanya dari periode latih; hasil
   dilaporkan di periode uji tanpa diubah.
2. **Waspadai survivorship bias.** Jangan memilih coin berdasarkan siapa yang sukses *hari ini*.
   Gunakan universe luas (notebook 09) atau coin yang sudah besar sejak lama.
3. **Hitung jumlah percobaan.** Sampai notebook 20 sudah ±560+ konfigurasi dicoba. Makin banyak
   mencari, makin besar peluang menemukan pola palsu. Gunakan PBO, Deflated Sharpe, uji nol (acak),
   walk-forward, dan data segar sebelum percaya pada satu angka.
4. **Simulasi realistis.** Sinyal di close → eksekusi di open besok, biaya 0.15%/sisi, stop dicek
   harian dengan gap, order minimum $5 untuk modal kecil.
5. **Angka terbaik di atas kertas hampir selalu terlalu optimis.** Patokan yang jujur adalah hasil
   periode uji / validasi, bukan periode yang ikut dipakai memilih strategi.

---

## 5. Data

| File | Isi | Dipakai |
|---|---|---|
| `notebooks/data/raw/{SYMBOL}_1d_full.csv` | Candle harian Binance Vision, umumnya sejak 2021 (50 simbol Large/Mid) | 06–12 |
| `notebooks/data/raw/{SYMBOL}_1d_since2018.csv` | 10 coin besar sejak 2018 (file terpisah supaya hasil lama tidak berubah) | 14–20 |
| `notebooks/data/raw/fear_greed_index.csv` | Fear & Greed Index alternative.me sejak 2018-02 | semua |
| Database `treding_rust` (`market_candles`, `fear_greed_index`, `flex_params`) | Data backend Rust (identik dengan Binance) | 09–12, validasi, backend `/signal` |

Catatan:
- `notebooks/data/raw` sekarang berisi **50 coin**. Notebook 03, 04, 06, 07, 08 dan
  `train_v5_model.py` **dikunci ke 10 coin aslinya** supaya hasilnya tidak berubah.
- `GRAMUSDT` (Gram, dulu Toncoin) diambil dari arsip `TONUSDT`.
- Validasi faktual data ada di notebook 16.

---

## 6. Cara menjalankan ulang

Dari root project, venv aktif, kernel Jupyter `crypto-backtest`:

```powershell
cd notebooks/research_signal_trading
..\..\venv\Scripts\jupyter nbconvert --to notebook --execute --inplace 13_fear_greed_strategies.ipynb
```

- Notebook mencari folder project otomatis, jadi bisa dijalankan dari lokasi mana pun di dalam project.
- Mesin backtest bersama ada di `notebooks/research/` (`single_position.py`, `portfolio.py`);
  jangan dihapus — notebook 08–20 bergantung padanya.
- **03 & 04**: notebook lama, sebagian sel punya error bawaan (dibuat sebelum restrukturisasi);
  hasil yang tersimpan tetap valid sebagai catatan.
- **16**: mengambil data live CoinGecko & Coinbase — hasil menjalankan ulang akan sedikit berbeda.
- Dashboard visual V2-60 dibuat dari hasil notebook 20 (`v2_60_dashboard.json`); versi
  V2-60+VolTargeting dari notebook 25 (`v23_voltargeting_dashboard.json`), skema JSON sama + field
  tambahan `eksposur` per minggu di `equity[]` dan `target_vol`/`vol_lookback_hari`/`eksposur_maks` di `meta`.

---

## 7. Hal terbuka / langkah berikutnya

1. **Paper trading / testnet 1–3 bulan** sebelum modal riil — satu-satunya uji yang tidak bisa di-overfit.
2. **Collector candle backend Rust**: data `market_candles` terakhir 2026-07-11. `/signal` memberi
   peringatan kalau data tertinggal; jangan trading sebelum ini diperbaiki.
3. **Batas modal Rp1,5 jt**: kalau modal naik-turun di sekitar batas, strategi berganti-ganti
   (BTC-60 ↔ V2-60). Pertimbangkan jeda (mis. kembali ke BTC-60 di bawah Rp1,35 jt).
4. **Sisa kecil coin (< $5)** tidak bisa dijual saat keluar pasar; perlu konversi manual ("convert small balance").
5. Sinyal SELL/short (notebook 03) ditunda sampai ada data bear market lebih banyak.
6. **Desain integrasi trailing-stop per-coin (notebook 22) ke engine produksi** — perlu state per-posisi
   (entry price, puncak, status parkir) yang belum ada di `research/portfolio.py` / backend Rust;
   direview dulu sebelum coding ke engine produksi.
7. Hanya ATR(14) yang dicoba sebagai ukuran volatilitas penskala trailing-stop — belum dicoba lookback
   lain atau ukuran volatilitas lain.

---

## 8. Aturan pencatatan

Setiap riset baru **wajib** dibuat sebagai notebook bernomor berikutnya di folder ini (21, 22, …),
dijalankan sampai selesai dengan output tersimpan, diakhiri sel **Kesimpulan**, lalu **README ini
diperbarui**: tabel riwayat (bagian 2), dan bagian 1 kalau keputusannya berubah.
