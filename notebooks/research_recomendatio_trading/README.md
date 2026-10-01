# RESEARCH RECOMENDATIO TRADING

Riset fitur rekomendasi coin: shortlist (min 5, maks 10) coin "berpeluang" dari universe Large+Mid
(`flex_params`) buat user filter & analisis sendiri — **bukan** auto-trading, beda dari riset
portofolio di `research_signal_trading/`. Setiap notebook punya sel **Kesimpulan** di bagian akhir.

Terakhir diperbarui: 1 Oktober 2026 (notebook 06 + endpoint).

---

## 1. Keputusan yang berlaku sekarang

**Endpoint produksi**: `GET /recommendations/momentum` (daftar harian) dan
`GET /recommendations/momentum/history` (paper trading, dihitung ulang dari candle) —
`src/services/recommendation_momentum/` + `src/strategy/momentum.py` (paritas dicek di notebook 06).
Endpoint V5 lama `GET /recommendations` sudah dihapus.

Kegunaan (kata user): trader minta rekomendasi → bot sudah menyaring universe jadi 5–10 coin → trader analisis
lagi sendiri. Urutan dihitung ulang **harian** (candle 1d tutup), jadi bisa berubah tiap hari.

| Komponen produksi (notebook 06) | Nilai |
|---|---|
| Universe | `flex_params` Large/Mid aktif saat request (sekarang 23 → 21 coin setelah buang USDC, PAXG); **BTC ikut diranking** |
| Rencana per coin | beli open besok, pegang 14 hari, stop −25% |
| Statistik yang ditampilkan (uji 2024–26) | UTAMA risk-on 45,3% / +1,30%; PELENGKAP risk-on 45,6% / +1,07%; UTAMA risk-off 41,8% / −2,59% |

Tabel di bawah ini adalah hasil riset universe 40 coin (notebook 02–05), sebagai riwayat.

| Komponen | Keputusan |
|---|---|
| Sinyal masuk | Rata-rata rank-percentile **RSI(14) + RSI(7)**, top-5, filter market H8b aktif |
| **Exit** (notebook 02, 05) | Skor jatuh di bawah **persentil 30%** ATAU **14 hari** terlewati ATAU **stop keras −25%** — mana duluan. Setara (notebook 05): **hold tetap 14 hari + stop −25%** — lebih sederhana untuk user, hasil praktis sama |
| Universe | Large+Mid `flex_params`, minus stablecoin, token emas (PAXG/XAUT), WBETH (duplikat ETH) — 40 coin |
| Output (notebook 03) | **Selalu 10 coin**: peringkat 1–5 "utama", 6–10 "pelengkap"; statistik per **kelompok peringkat** (bukan win rate per coin); label risk-on/off + peringatan saat risk-off |
| Filter tambahan (notebook 03) | Tidak ada — ambang skor, win rate per coin, umur listing, likuiditas, anti-pump semua gagal di dev |

### Hasil per-sinyal (periode uji 2024-01 → 2026-06, out-of-sample, evaluasi independen tiap sinyal)
| | Nilai |
|---|---|
| Win rate | **45,5%** |
| Rata-rata untung | +19,2% |
| Rata-rata rugi | −12,7% |
| Ekspektasi per sinyal | **+1,79%** |

⚠️ **Lemah di tahun bear** (2022: win rate 14,6%, ekspektasi −11%) — lihat notebook 02 bagian 5.
Angka gabungan di atas ditopang tahun-tahun kuat (2021, 2024); jangan dibaca sebagai hasil rata tiap
tahun.

⚠️ **Edge melemah di data terbaru** (notebook 03): risk-on 2025 ekspektasi −1,62%, 2026 (s/d Juni) −1,75%
(win rate 37%). Wajib paper trading sebelum dipakai uang nyata.

⚠️ **Sumber untungnya terutama beta pasar alt** (notebook 04): sejak 2022 alpha (coin pilihan − rata-rata
semua alt di jendela sama) ≈ 0. Rugi 2025 karena alt turun saat BTC naik — H8b (berbasis BTC/FGI) tetap risk-on.

⚠️ **Risiko portofolio sangat tinggi** (notebook 05): kalau semua rekomendasi diikuti, max drawdown −57% s/d
−62% (bahkan di 2024 yang untung). Fitur ini = **daftar pantauan**, bukan tempat seluruh modal; modal utama
tetap V2-60 (`research_signal_trading`).

### Per kelompok peringkat & status pasar (uji 2024-01 → 2026-06, notebook 03)
| | Win rate | Ekspektasi |
|---|---|---|
| Peringkat 1–5, risk-on | 45,5% | +1,79% |
| Peringkat 6–10, risk-on | 41,2% | +1,58% |
| Peringkat 1–5, **risk-off** | 42,8% | **−1,40%** |

**Catatan penting (notebook 01, masih berlaku buat versi ranking murni tanpa exit)**: edge ranking
forward-return murni kecil dan berasal dari besaran untung/rugi, bukan frekuensi menang. ❌
**`volume_ratio` jangan dipakai** sebagai komponen skor meski korelasi keseluruhannya tinggi — spread
top-vs-bottom-nya negatif (lonjakan volume muncul di breakout naik MAUPUN crash turun).

---

## 2. Kenapa bukan pakai strategi V5 yang sudah ada

Endpoint `GET /recommendations` (`src/services/recommendation/`) saat ini 100% berbasis strategi V5
(bottoming + reversal + regime + model ML). V5 **sudah ditolak** di riset lain
(`research_signal_trading/06_portfolio_single_position.ipynb`): win rate 61,8% yang diklaim ternyata
diuji di data latihnya sendiri — out-of-sample rugi −21%, sinyal terlalu jarang (±8 hari/tahun), dan
membeli coin yang sedang jatuh (bottoming) tidak terbukti punya keunggulan.

Riset di folder ini dibangun **dari nol** — indikator momentum sederhana (RSI, jarak dari puncak,
rasio MA, momentum harga), bukan gate V5 — dan setiap klaim divalidasi dev/test sebelum dipercaya,
supaya tidak mengulang kesalahan yang sama (klaim performa yang ternyata overfit).

---

## 3. Riwayat riset per notebook

| No | Notebook | Pertanyaan | Hasil | Status |
|---|---|---|---|---|
| 01 | `01_momentum_screening_indikator` | Indikator jangka pendek apa yang beneran bisa dipercaya buat screening top 5-10 coin (bukan korelasi umum, tapi spread top-K vs bottom-K)? | RSI(14)+RSI(7) menang di dev, lolos uji out-of-sample, lolos per-tahun (positif di semua tahun 2021-2026 termasuk bear 2022), dan bukan cuma proxy BTC naik (spread malah lebih besar pas BTC turun). `volume_ratio` kelihatan bagus di korelasi umum tapi spread top-bottom-nya negatif — dibuang dari komposit | **Metodologi terpilih**, belum ke produksi |
| 02 | `02_simulasi_trading_exit_skor` | User minta simulasi trading beneran (bukan cuma ranking): win rate ≥45%, modal Rp1,5 juta. Mekanisme exit apa yang pas? | ATR stop/target tetap dari entry (gaya V5) kelihatan bagus di simulasi portofolio (win rate 60%+, profit ratusan%) tapi **max drawdown −70% s/d −89%**; begitu dievaluasi per-sinyal independen (bukan bias slot portofolio), ekspektasinya ternyata negatif. **Exit berbasis skor** (keluar kalau skor jatuh di bawah persentil 30%, maks 14 hari, stop keras −25%) terbukti lebih baik: win rate 45,5%, ekspektasi +1,79%/sinyal, stabil di uji — tapi lemah di tahun bear (2022: win rate 14,6%) | **Metodologi exit terpilih**, dengan catatan kelemahan bear-market |
| 03 | `03_kualitas_sinyal_5_sampai_10` | User minta min 5 maks 10 coin, win rate bagus, risk-off tetap tampil + peringatan. Peringkat 6–10 layak? Kapan 5 vs 10? Win rate per coin bisa dipercaya? Filter umur listing/likuiditas/pump? | Peringkat 6–10 ekspektasi +1,58% (≈ 1–5) tapi win rate 41% vs 45,5%. Aturan ambang skor ditolak (tak ada yang lolos dev) → selalu 10 coin, 5 utama + 5 pelengkap. Win rate per coin tidak persisten (ρ dev-uji +0,16, p=0,42) dan filternya merugikan. Ketiga filter kepercayaan gagal di dev. Risk-off ekspektasi negatif (−1,23% dev, −1,40% uji). 2025 & 2026 risk-on negatif. 8 varian diuji, 0 diadopsi | **Desain tampilan ditetapkan**, perlu paper trading |
| 04 | `04_diagnosa_edge_2025_2026` | Kenapa sinyal rugi di 2025–2026? (beta vs alpha, momentum berbalik, coin baru listing, exit) | Utamanya **beta**: alpha vs rata-rata alt ≈ 0 sejak 2022 (2025 −0,54%), alt turun saat BTC naik. Ranking 7 hari masih positif tipis (+1,1%). Coin listing < 6 bulan buruk sejak 2023 (sedikit jumlahnya). **Exit skor kalah dari hold tetap 14 hari** di semua tahun kecuali 2022. Filter F1 breadth/F2 musim alt/F3 BTC>SMA50 gagal di dev (F1 bagus di 2025–26 tapi data itu sudah terlihat) | Diagnosa; 0 diadopsi. Kandidat nb05: exit hold tetap vs skor |
| 05 | `05_exit_hold_tetap_vs_skor` | Exit hold tetap 7/14 hari (stop −25% tetap) atau skor < 0,15 lebih baik dari exit sekarang? | Hold 14 hari lolos aturan dev tapi selisih praktis nol (dev +9,14 vs +8,87%, 2024 +4,33 vs +4,61%, 2025–26 −1,51 vs −1,64%); hold 7 hari lebih buruk. Selisih di nb04 datang dari tidak adanya stop keras. **Max drawdown portofolio −57% s/d −66% di semua varian**, 2025 −20%. 14 varian total diuji (nb03–05) | Hold 14 hari boleh (lebih sederhana, bukan lebih untung); masalah 2025–26 **tidak** terselesaikan |
| 06 | `06_universe_live_dan_btc` | Sebelum endpoint: universe live `flex_params` (21 coin, bukan 40) + BTC ikut ranking — statistik berubah? Kode produksi sama dengan notebook? | Paritas OK (jumlah sinyal identik; selisih ±0,2 poin dari 198 hari dengan skor seri, diputus alfabetis). Live 21 + BTC: UTAMA risk-on uji 45,3% / +1,30%, PELENGKAP 45,6% / +1,07%, risk-off −2,59%. BTC di top-10 68% hari, peringkat 1 7% hari. Peringkat 1 berganti 39% hari. 2026 (s/d Juni) UTAMA risk-on −6,05% | **Dipakai endpoint** (tanpa parameter baru dipilih) |

---

## 4. Pelajaran metodologi (sama seperti `research_signal_trading`, + 1 tambahan khusus di sini)

1. **Korelasi keseluruhan ≠ berguna buat top-K selection.** `volume_ratio` punya Spearman tertinggi
   tapi spread top-10/bottom-10-nya negatif. Validasi harus sesuai cara indikator akan **benar-benar
   dipakai** (di sini: pilih top-K harian), bukan metrik generik.
2. **`NaN > 0` di numpy bernilai `False`, bukan di-skip.** Kalau menghitung win rate dari array yang
   ada NaN-nya (misal coin baru listing, indikator belum bisa dihitung), perbandingan `>` langsung
   akan diam-diam menghitung NaN sebagai "kalah" kalau tidak di-mask manual sebelum `.mean()`. Dua
   bug di awal riset ini (data NaN coin baru listing ketarik jadi "bottom" karena `-inf` dipakai di
   kedua sisi sorting; lalu win rate universe anjlok ke 29% karena bug ini) — keduanya kebetulan jadi
   pelajaran berharga, dicek ulang sebelum hasil akhir dipercaya.
3. Pisahkan data pemilihan (dev) dan data uji — dev = 2021-2023, uji = 2024-2026 (dibagi tahun, beda
   dari portofolio yang dibagi per blok dev/uji lebih panjang, karena di sini datanya jauh lebih
   padat: tiap hari × tiap coin, bukan tiap bulan).
4. Angka terbaik di dev hampir selalu lebih optimis dari uji — patokan jujur tetap hasil periode uji.
5. **Simulasi portofolio (slot posisi terbatas) bisa bias seleksi** (notebook 02) — cuma
   mengevaluasi sinyal yang kebetulan dapat modal/slot kosong, bukan representasi jujur tiap sinyal.
   Buat validasi "seberapa bisa dipercaya satu sinyal", evaluasi tiap sinyal **independen**, jangan
   cuma lihat hasil portofolio compounding-nya (yang bisa kelihatan bagus padahal cuma subset
   ter-cherry-pick).
6. **Lookahead bug di exit berbasis indikator**: skor/ATR yang dipakai buat keputusan exit WAJIB
   dari hari **sebelumnya**, bukan hari yang sama dengan eksekusi exit — kesalahan ini sempat bikin
   hasil kelihatan luar biasa bagus sebelum diperbaiki.
7. Max drawdown WAJIB dicek sebelum percaya angka profit/win-rate yang kelihatan bagus — simulasi
   ATR-stop di notebook 02 awalnya kelihatan sangat menguntungkan sebelum ketahuan drawdown-nya
   −70% s/d −89%.

---

## 5. Data

| File | Isi |
|---|---|
| `notebooks/data/raw/{SYMBOL}_1d_full.csv` | Candle harian 50 simbol Large/Mid (sama dengan dataset `research_signal_trading/09`) |

Kategori Large/Mid dipakai dari **snapshot** `research_signal_trading/09_dataset_large_mid.ipynb`
(query `flex_params` saat notebook itu terakhir dijalankan) — bisa beda dari DB live sekarang. Kalau
nanti diarahkan ke produksi, kategori harus diambil langsung dari `flex_params` saat itu juga, bukan
snapshot ini.

---

## 6. Hal terbuka / langkah berikutnya

1. ~~Filter likuiditas/umur listing/pump~~ — diriset di notebook 03, tidak ada yang lolos. Likuiditas
   minimum boleh dipakai sebagai syarat praktis eksekusi, bukan filter skor.
2. Penyajian: 10 coin (5 utama + 5 pelengkap), statistik kelompok, label pasar (notebook 03). Teks
   penjelasan per coin belum didesain.
3. ~~Kenapa edge 2025–2026 negatif~~ — notebook 04: beta pasar alt. ~~Exit hold tetap~~ — notebook 05: setara,
   tidak memperbaiki 2025–26. Sisa: breadth alt sebagai info tampilan / dipantau di paper trading.
4. ~~Gantiin atau dampingi V5~~ — V5 dihapus, endpoint momentum sudah ada. Catatan lama:
   belum diputuskan apakah ini nanti gantiin atau dampingi `/recommendations` berbasis V5 — perlu
   didiskusikan setelah metodologi makin matang.
5. Paper trading / validasi langsung sebelum dipakai keputusan nyata — sama seperti prinsip di
   `research_signal_trading`.

---

## 7. Aturan pencatatan

Sama seperti `research_signal_trading`: tiap riset baru jadi notebook bernomor berikutnya (02, 03, …)
di folder ini, dijalankan sampai selesai dengan output tersimpan, diakhiri sel **Kesimpulan**, lalu
README ini diperbarui.
