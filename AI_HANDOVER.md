# AI Handover — Trading Bot V1.0

> Terakhir diupdate: 2026-06-18 04:20 WIB

## Project Goal
Kembangkan & uji strategi trading multi-ticker (XAUUSDm, US30m, AUDUSDm, plus forex major) dengan AI Risk Manager, menggunakan MT5 akun Exness-MT5Trial6 (login: 413889745). MT5 harus dibuka manual sebelum Python jalan.

## Arsitektur

```
config/
├── tickers/              # Metadata per ticker (spread, point, modal, target)
│   ├── ticker_audusdm.json
│   ├── ticker_eurusdm.json
│   ├── ticker_gbpusdm.json
│   ├── ticker_us30m.json
│   └── ticker_usdjpy.json
├── XAUUSD/               # Strategy configs XAUUSD (pakem, TIDAK diubah)
│   ├── settings_xauusd_m15.json
│   ├── settings_xauusd_h1.json
│   └── strategy_{a,b,c,d,f,g,h}.json
├── US30m/                # Strategy configs US30m (dibuat dari 0)
│   └── strategy_{a,b,c,d,e,f,g}.json
└── AUDUSDm/              # Strategy configs AUDUSDm (dibuat dari 0)
    └── strategy_{a,b,c,d,e,f,g}.json

strategies/
├── xauusd/               # Script backtest XAUUSD original (pakem, TIDAK diubah)
│   └── strategi_{d,e,f,g,h}_*.py
├── shared/
│   └── indicators.py     # Shared: ema, sma, atr, rsi, macd, bb

scripts/
└── backtest_multi_ticker.py  # Engine unified multi-ticker
```

## Status Terkini

### Engine (`backtest_multi_ticker.py`)
- Load ticker config dari `config/tickers/*.json`
- Load strategy config dari `config/{ticker_name}/strategy_*.json`
- Support 2 mode: `trend` (default) dan `meanrev` (mean reversion)
- 7 strategy labels: a, b, c, d, e, f, g (masing-masing punya TF & bars sendiri)
- Signal: EMA cross + RSI + MACD (opsional) + volume + BB (opsional)
- Mean reversion: entry saat harga sentuh BB outer bands + RSI extreme
- Confidence sizing (G): multi-factor scoring buat scale lot
- Risk: ATR-based SL/TP, trailing stop, DD limit

### Ticker: US30m (Indeks, Point=0.1, Spread 23 pts, Target Rp150.000/hr)
**Pendekatan:** Trend following (semua strategi mode=trend)

| Label | Nama | TF | Rp/hr | PF | DD | WR | Status |
|---|---|---|---|---|---|---|---|---|
| d | D H1 Confluence | H1 | **Rp141,565** | 3.17 | 11% | 71% | ✅ Nyaris target (94%) |
| e | E H1 Donchian | H1 | Rp125,719 | 2.13 | 17% | 59% | Potensial |
| a | A D1 Long Bias | D1 | Rp96,219 | 2.49 | 3% | 65% | ✅ DD kecil, PF solid |
| b | B H4 EMA Cross | H4 | Rp86,635 | 2.01 | 7% | 67% | Stabil |
| c | C H4 PSAR | H4 | Rp84,363 | 1.64 | 13% | 56% | Perlu tuning |
| f | F M15 Turbo | M15 | Rp44,132 | 2.29 | 25% | 56% | ❌ Kena DD limit |
| g | G M15 Confidence | M15 | Rp32,350 | 1.76 | 25% | 60% | ❌ Kena DD limit |

### Ticker: AUDUSDm (Forex, Point=0.00001, Spread 11 pts, Target Rp100.000/hr)
**Pendekatan:** Mean reversion (A-D) + trend (E-G)

| Label | Nama | TF | Rp/hr | PF | DD | WR | Status |
|---|---|---|---|---|---|---|---|
| e | E H1 Breakout | H1 | Rp73,361 | 2.27 | 15% | 67% | Terbaik AUD |
| g | G M15 Confidence | M15 | Rp19,357 | 1.68 | 25% | 61% | ❌ Kena DD limit |
| f | F M15 Scalp | M15 | Rp15,980 | 1.83 | 25% | 54% | ❌ Kena DD limit |
| d | D H1 Confluence MR | H1 | Rp13,807 | 2.22 | 5% | 60% | MR terlalu ketat |
| a | A D1 Range MR | D1 | Rp13,783 | 2.13 | 3% | 60% | MR terlalu ketat |
| b | B H4 Mean Rev | H4 | Rp4,542 | 1.55 | 3% | 56% | MR terlalu ketat |
| c | C H4 RSI Extreme | H4 | Rp3,452 | 1.50 | 2% | 59% | MR terlalu ketat |

### XAUUSD (PAKEM — TIDAK DIUBAH)
Semua strategi dan config XAUUSD tetap original. Folder `strategies/xauusd/` dan `config/XAUUSD/` tidak tersentuh.

## Perubahan Terakhir (Session Ini)

- **Mean reversion mode**: Tambah mode `meanrev` di `signal_any()` + BB columns di `prep_simple()`
- **Label E**: Tambah `"e"` ke STRATEGY_MAP buat strategi ke-7
- **Display name**: Config sekarang override nama strategi via `display_name`
- **Normalisasi key**: `no_macd_filter` → `no_macd`, `no_ema200_filter` → `no_ema200`, `conf_sizing` dari `confidence_sizing.thresholds`
- **Config key fix**: G config sebelumnya pake `no_macd_filter` tapi code cek `no_macd` — bikin sinyal ke-block total
- **prep_confidence fix**: Ganti hardcode parameter (`rsi_period`, `atr_period`, dll) jadi `.get()` dengan default
- **Tuning US30m**: Update SL/TP/lot/running_pct di A, B, D, E:
  - D H1 Confluence: Rp134k → **Rp141k** (SL 1.0 TP 3.0, PF 3.17)
  - A D1 Long Bias: Rp74k → **Rp96k** (lot 500→600, SL 2.0→1.5)
  - E H1 Donchian: Rp113k → **Rp126k**
- **Commit `297dd6c`**: 36 files berubah, push ke main

## Issues / Blockers

1. **H1 data terbatas**: MT5 trial cuma ngasih 2-3 hari H1 untuk symbol mini — hasil backtest H1 belum representatif.
2. **AUDUSDm mean reversion**: Entry criteria terlalu ketat (BB + RSI + EMA triple filter) — perlu dilonggarkan.
3. **M15 strategies kena 25% DD limit**: Semua parameter F M15 kena DD limit — M15 terlalu noise untuk US30m. Focus ke H1/H4.
4. **EURUSDm, GBPUSDm, USDJPYm**: Belum punya config strategi.

## Cara Run

```powershell
# Buka MT5 dulu, login, pastikan Market Watch aktif
python scripts/backtest_multi_ticker.py
```

## Next Steps (Rekomendasi)

1. **Fine-tune AUDUSDm**: Loosening mean reversion atau ganti approach
2. **Testing D H1 Confluence**: Parameter optimal SL=1.0 TP=3.0 PF 3.17 — Rp141k dari target Rp150k
3. **Buat config EURUSDm, GBPUSDm, USDJPYm** — pake template US30m/AUDUSDm
4. **Debug H1 data** — coba cache data MT5 atau pake symbol lain
5. **Live forward test** untuk H1 strategies (D, E) di US30m
