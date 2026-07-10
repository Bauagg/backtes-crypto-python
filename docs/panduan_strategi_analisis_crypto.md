# Panduan Strategi Analisis Crypto – backend-tredin-rust

**Tujuan dokumen:** referensi belajar & aturan resmi strategi analisis, supaya bisa dibaca ulang kapan saja tanpa perlu mengingat seluruh konteks diskusi sebelumnya.

**Cakupan koin:** BTCIDR, ADAIDR, AVAXIDR, BNBIDR, DOGEIDR, ETHIDR, HBARIDR, SOLIDR, SUIIDR, XRPIDR
**Timeframe target:** 1 hari – 1 minggu (bukan scalping)
**Filosofi:** tool riset untuk analis – kasih data & skor transparan, eksekusi tetap manual oleh analis.

---

## Bagian 1 – Konsep Dasar Tiap Indikator

### 1.1 Moving Average (MA) – Golden Cross & Death Cross

**Apa itu:** rata-rata harga penutupan (*close*) selama N hari terakhir. MA50 = rata-rata 50 hari terakhir, MA200 = rata-rata 200 hari terakhir.

**Formula sederhana (Simple Moving Average / SMA):**
```
MA50 = (close hari ke-1 + close hari ke-2 + ... + close hari ke-50) / 50
```

**Cara baca:**
- **Golden Cross** – MA50 memotong ke atas MA200 – sinyal tren naik jangka panjang
- **Death Cross** – MA50 memotong ke bawah MA200 – sinyal tren turun jangka panjang

**Sifat penting – LAGGING (telat):** karena dihitung dari rata-rata harga masa lalu, sinyal Golden/Death Cross baru muncul **setelah** harga sudah bergerak signifikan. Ini bukan cacat, tapi trade-off: MA jarang kasih sinyal palsu, tapi selalu telat masuk.

**Kenapa tetap dipakai:** bukan sebagai "tombol beli/jual", tapi sebagai **filter arah tren besar** – supaya analis tidak melawan arus utama pasar.

---

### 1.2 RSI (Relative Strength Index)

**Apa itu:** indikator momentum yang mengukur kecepatan & besaran perubahan harga, dalam skala 0–100.

**Cara baca:**
- RSI di atas 70 – area *overbought* (harga naik terlalu cepat, potensi koreksi)
- RSI di bawah 30 – area *oversold* (harga turun terlalu cepat, potensi rebound)
- RSI 40–60 – netral

**Sifat:** lebih cepat bereaksi dibanding MA (leading-ish), karena berbasis perubahan harga jangka pendek, bukan rata-rata jangka panjang.

**Peran dalam strategi:** sinyal *trigger* – menangkap momentum yang mulai melemah/menguat sebelum tren besar (MA) sempat berubah arah.

---

### 1.3 Volume

**Apa itu:** jumlah unit koin yang diperdagangkan dalam periode tertentu.

**Kenapa penting:** pergerakan harga **tanpa** kenaikan volume sering dianggap "kurang meyakinkan" (rawan berbalik arah). Pergerakan harga **dengan** volume tinggi lebih dipercaya mencerminkan minat pasar yang riil, bukan sekadar noise.

**Cara baca sederhana:** bandingkan volume beberapa hari terakhir dengan rata-rata volume 20–30 hari – lonjakan volume signifikan sering muncul di titik-titik penting (breakout, reversal).

---

### 1.4 Fear & Greed Index

**Apa itu:** indeks sentimen pasar crypto skala 0–100 (0 = Extreme Fear, 100 = Extreme Greed), dihitung dari 5 komponen data kuantitatif – **bukan** dari membaca berita secara tekstual.

**5 komponen penyusun (sumber: Alternative.me):**

| Komponen | Bobot | Yang diukur |
|---|---|---|
| Volatilitas | 25% | Volatilitas & max drawdown BTC dibanding rata-rata 30/90 hari |
| Momentum/Volume | 25% | Volume & momentum trading dibanding rata-rata historis |
| Media Sosial | 15% | Interaksi hashtag terkait Bitcoin di media sosial |
| Dominasi BTC | 10% | Naik = tanda fear (lari ke aset "aman"); turun = tanda greed (spekulasi altcoin) |
| Google Trends | 10% | Volume pencarian terkait Bitcoin |

**Cara baca:**
- Extreme Fear (0–24) – secara historis sering jadi area akumulasi/pembelian (kontrarian)
- Extreme Greed (75–100) – secara historis sering jadi area kewaspadaan/ambil untung

**Catatan penting:** indeks ini berbasis Bitcoin, dipakai sebagai *proxy* sentimen pasar keseluruhan – bukan sentimen spesifik per-altcoin.

---

### 1.5 Relative Strength vs BTC

**Apa itu:** perbandingan performa return suatu koin terhadap performa BTC dalam periode yang sama.

**Cara hitung sederhana:**
```
Relative Strength = Return Koin (%) - Return BTC (%)
```

**Cara baca:**
- Positif – koin *outperform* BTC (kekuatan independen)
- Negatif – koin *underperform* BTC (cuma "numpang" pergerakan BTC)

**Kenapa penting:** banyak altcoin sebenarnya tidak punya pergerakan independen – mereka cuma mengikuti BTC dengan volatilitas lebih tinggi. Faktor ini membantu memisahkan sinyal yang benar-benar berasal dari koin tersebut vs sinyal yang sebenarnya cuma "gema" dari BTC.

---

## Bagian 2 – Strategi Skoring

### 2.1 Definisi Target (harus presisi agar bisa diuji)

> **Pertanyaan yang dijawab sistem:** "Apakah harga penutupan 7 hari dari sekarang akan lebih tinggi dari harga penutupan hari ini?"

### 2.2 Struktur 5 Faktor

| # | Faktor | Peran | Sifat |
|---|---|---|---|
| 1 | MA50 vs MA200 | **Filter arah** (bukan vote setara) | Lagging |
| 2 | RSI mingguan | Trigger momentum | Leading-ish |
| 3 | Volume trend | Konfirmasi kekuatan tren | Leading-ish |
| 4 | Fear & Greed Index | Konteks sentimen pasar | Leading |
| 5 | Relative Strength vs BTC | Konteks kekuatan independen | Netral/konteks |

### 2.3 Kenapa MA Jadi Filter, Bukan Vote Setara

Karena sifatnya lagging, MA diberi peran khusus:

- **MA50 > MA200** – sistem **hanya mencari sinyal BULLISH** dari faktor #2–5; sinyal bearish dari faktor lain dianggap noise yang melawan tren utama
- **MA50 < MA200** – sistem **hanya mencari sinyal BEARISH**
- **MA50 ≈ MA200** (selisih <1%) – status NETRAL, tidak ada bias arah

### 2.4 Formula Skor

Setiap faktor #2–5 menghasilkan vote: `+1` (mendukung arah filter MA), `0` (netral), `-1` (melawan arah filter MA – dicatat tapi tidak membalik verdict).

```
Total Skor = vote(RSI) + vote(Volume) + vote(FearGreed) + vote(RelativeStrength)
Rentang: -4 sampai +4
```

### 2.5 Klasifikasi Confidence

| Total Skor | Verdict | Confidence |
|---|---|---|
| +3 sampai +4 | BULLISH | HIGH |
| +1 sampai +2 | BULLISH | MEDIUM |
| 0 | NETRAL | – |
| -1 sampai -2 | BEARISH | MEDIUM |
| -3 sampai -4 | BEARISH | HIGH |

---

## Bagian 3 – Analisis Korelasi Antar Koin

### 3.1 Konsep

Korelasi mengukur seberapa mirip pergerakan dua koin – dalam skala **-1 sampai +1**:
- **+1** – bergerak identik searah
- **0** – tidak ada hubungan
- **-1** – bergerak berlawanan arah sepenuhnya

**Yang dihitung bukan harga mentah**, tapi ***daily return*** (persentase perubahan harian), karena membandingkan harga mentah antar koin dengan skala berbeda (misal BTC di miliaran rupiah vs DOGE di ratusan rupiah) tidak bermakna secara statistik.

```
Return harian = (close hari ini - close kemarin) / close kemarin
```

### 3.2 Tujuan Analisis Ini

Mengetahui koin mana yang bergerak **independen** vs koin yang sekadar **"mengikuti" BTC** (artinya sinyal analisisnya kemungkinan redundan dengan sinyal BTC).

### 3.3 Cara Interpretasi

| Korelasi terhadap BTC | Interpretasi |
|---|---|
| > 0.7 | TINGGI – koin cenderung "ngikut" BTC, sinyal analisisnya kemungkinan besar redundan |
| 0.4 – 0.7 | SEDANG – ada hubungan, tapi koin masih punya pergerakan sendiri |
| < 0.4 | RENDAH – koin bergerak cukup independen, sinyal analisisnya punya nilai tambah tersendiri |

### 3.4 Kenapa Ini Berguna Buat Analis

Kalau dari 10 koin ternyata 6 di antaranya punya korelasi tinggi ke BTC, itu artinya analis **secara efektif tidak sedang menganalisis 10 hal independen** – lebih mendekati 4–5 keputusan independen (karena 6 koin tadi cenderung "ikut arus" yang sama). Ini mencegah ilusi diversifikasi – punya banyak koin di watchlist bukan berarti otomatis dapat sinyal yang beragam.

---

## Bagian 4 – Metodologi Backtesting

Backtest **wajib** dilakukan sebelum sistem skor ini dipercaya untuk riset sungguhan.

### 4.1 Langkah

1. **Split data:** 70% data lama untuk kalibrasi awal, 30% data terbaru untuk validasi (*out-of-sample*) – sistem tidak boleh "melihat" data validasi saat aturan dibuat
2. **Jalankan sistem skor** di sepanjang data historis, catat verdict tiap hari
3. **Bandingkan** verdict dengan apa yang benar-benar terjadi 7 hari kemudian

### 4.2 Metrik yang Dihitung

- **Win rate** – dari semua verdict BULLISH, berapa persen yang harga benar-benar naik dalam 7 hari?
- **Sharpe Ratio** – return rata-rata dibagi standar deviasi return; mengukur return **per unit risiko**, bukan cuma persentase benar semata

### 4.3 Ambang Kelayakan

Win rate perlu **di atas 55%** pada data out-of-sample untuk dianggap punya *edge* nyata di atas tebakan acak (50%). Di bawah itu, revisi bobot faktor atau definisi ulang target sebelum dipakai untuk riset produksi.

---

## Bagian 5 – Keterbatasan (penting disampaikan ke pengguna tool)

- Ini sistem *rule-based* sederhana, bukan setara quant institusional (yang butuh tim puluhan orang & data feed mahal) – tapi mengadopsi prinsip metodologi yang sama secara proporsional
- MA tetap lagging meski diposisikan sebagai filter – tren besar bisa berbalik sebelum filter sempat ter-update
- Data on-chain mendalam (MVRV, SOPR) tidak tersedia gratis untuk koin di luar BTC/ETH, sehingga metodologi ini seragam lintas 10 koin
- Fear & Greed Index berbasis Bitcoin, dipakai sebagai proxy sentimen keseluruhan – bukan sentimen spesifik per-altcoin
- **Bukan saran finansial.** Win rate historis tidak menjamin performa masa depan.

---

## Bagian 6 – Sumber Data

| Data | Endpoint |
|---|---|
| Candle historis (semua koin) | Backend sendiri – `GET /api/market/klines` (proxy dari Tokocrypto) |
| Fear & Greed Index | `GET https://api.alternative.me/fng/` |
| BTC Dominance (opsional) | `GET https://api.coingecko.com/api/v3/global` |

---

## Bagian 7 – Glosarium Singkat

| Istilah | Arti |
|---|---|
| Lagging indicator | Indikator yang bereaksi setelah pergerakan harga terjadi |
| Leading indicator | Indikator yang berpotensi memberi sinyal sebelum pergerakan besar terjadi |
| Overbought | Harga naik terlalu cepat, berpotensi koreksi turun |
| Oversold | Harga turun terlalu cepat, berpotensi rebound naik |
| Backtesting | Menguji strategi terhadap data historis sebelum dipakai di masa depan |
| Out-of-sample | Data yang tidak digunakan saat membuat/kalibrasi aturan, dipakai khusus untuk validasi |
| Sharpe Ratio | Ukuran return yang disesuaikan dengan risiko (return dibagi volatilitas) |
| Korelasi Pearson | Ukuran statistik seberapa mirip pergerakan dua aset (-1 sampai +1) |

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0 | 2026-07-07 | Draf awal lengkap – konsep indikator, strategi skoring, korelasi, backtest, glosarium |
