# RESEARCH RECOMENDATIO TRADING

Riset fitur rekomendasi coin: shortlist (min 5, maks 10) coin "berpeluang" dari universe Large+Mid
(`flex_params`) buat user filter & analisis sendiri — **bukan** auto-trading, beda dari riset
portofolio di `research_signal_trading/`. Setiap notebook punya sel **Kesimpulan** di bagian akhir.

Terakhir diperbarui: 1 Oktober 2026 (notebook 02).

---

## 1. Keputusan yang berlaku sekarang

**Belum ada endpoint produksi dari riset ini.** `GET /recommendations` yang sedang live tetap
berbasis strategi V5 lama (lihat bagian 2 di bawah — ini sengaja, keputusan user: riset dulu,
terpisah dari endpoint yang sudah ada).

| Komponen | Keputusan |
|---|---|
| Sinyal masuk | Rata-rata rank-percentile **RSI(14) + RSI(7)**, top-5, filter market H8b aktif |
| **Exit** (notebook 02) | Skor jatuh di bawah **persentil 30%** ATAU **14 hari** terlewati ATAU **stop keras −25%** — mana duluan |
| Universe | Large+Mid `flex_params`, minus stablecoin, token emas (PAXG/XAUT), WBETH (duplikat ETH) — 40 coin |
| Output | Ranking harian, ambil 5-10 teratas, tiap rekomendasi disertai win rate tervalidasi |

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

1. Komponen "dapat dipercaya" di luar statistik forward-return — likuiditas minimum, umur listing
   minimum, exclude pump-and-dump ekstrem — belum diriset.
2. Belum didesain cara menyajikan skor ke user (bukan cuma angka mentah RSI/momentum).
3. Belum diputuskan apakah ini nanti gantiin atau dampingi `/recommendations` berbasis V5 — perlu
   didiskusikan setelah metodologi makin matang.
4. Paper trading / validasi langsung sebelum dipakai keputusan nyata — sama seperti prinsip di
   `research_signal_trading`.

---

## 7. Aturan pencatatan

Sama seperti `research_signal_trading`: tiap riset baru jadi notebook bernomor berikutnya (02, 03, …)
di folder ini, dijalankan sampai selesai dengan output tersimpan, diakhiri sel **Kesimpulan**, lalu
README ini diperbarui.
