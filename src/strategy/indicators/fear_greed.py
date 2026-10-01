"""Bagian 1.4 -- Fear & Greed Index (market sentiment context factor).

Hanya ambang batas yang dipakai strategi. Datanya sendiri:
- backend: tabel fear_greed_index di DB (src/services/recommendation/repository.py)
- analisis: API alternative.me + cache CSV (notebooks/data_source/fear_greed.py)
"""

FNG_EXTREME_FEAR = 25
FNG_EXTREME_GREED = 75
