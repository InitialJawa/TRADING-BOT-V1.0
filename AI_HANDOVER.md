# AI Handover — Trading Bot v1.0

## Project Overview
- **Dir**: `D:\CODE\TRADING-BOT-V1.0`
- **Python**: 3.12 64-bit
- **MT5**: Terminal build 5836, akun Exness-MT5Trial6 (#413889745)
- **Modal**: Rp12.000.000 (simulasi)
- **Target**: Rp100.000/hari dari trading XAUUSDm

## MT5 Connection Status
- **Status**: SUDAH BISA CONNECT
- **Server**: Exness-MT5Trial6 (login: 413889745, pass: "jatenggayeng")
- **Caranya**: Buka MT5 manual dulu, login, baru jalanin Python. `mt5.initialize()` tanpa path.

## Files Created / Modified

### Config
- `config/settings.json` — Registrasi semua strategi (A/B/C/D/E/F/G/H) untuk AI Manager
- `config/strategy_d.json` — Parameter Strategy D H1
- `config/strategy_e.json` — Parameter Strategy E M15 NoFilter
- `config/strategy_f.json` — Parameter Strategy F M15 Turbo Scalper
- `config/strategy_g.json` — Parameter Strategy G M15 Confidence Sizing
- `config/strategy_h.json` — Parameter Strategy H H1 Confidence Sizing

### Scripts
- `scripts/strategi_d_h1.py` — Backtest Strategy D (H1), dual-mode MT5/synthetic
- `scripts/jalankan_strat_d.py` — Live monitor Strategy D H1
- `scripts/strategi_e_m15.py` — Backtest Strategy E (M15 NoFilter) + seeding DB
- `scripts/jalankan_strat_e.py` — Live monitor Strategy E M15, loop tiap 15 menit
- `scripts/strategi_f_m15.py` — Backtest Strategy F (M15 Turbo Scalper) + seeding DB
- `scripts/jalankan_strat_f.py` — Live monitor Strategy F M15, loop tiap 15 menit
- `scripts/strategi_g_m15.py` — Backtest Strategy G (M15 Confidence Sizing) + seeding DB
- `scripts/jalankan_strat_g.py` — Live monitor Strategy G M15, loop tiap 15 menit + log file
- `scripts/strategi_h_h1.py` — Backtest Strategy H (H1 Confidence Sizing) + seeding DB
- `scripts/jalankan_strat_h.py` — Live monitor Strategy H H1, loop tiap 1 jam + log file
- `scripts/_backtest_agresif.py` — Perbandingan semua strategi (A/B/C/D std/D agg)
- `scripts/_test_2bulan.py` — Test 2 bulan D aggressive
- `scripts/_strategy_e.py` — Eksperimen 5 varian E
- `scripts/_strategy_f.py` — Eksperimen parameter F
- `scripts/_cari_g.py` hingga `_cari_g5.py` — Eksplorasi G (Session/Multi-TF/Squeeze/Hybrid -> Confidence Sizing)
- `scripts/_backtest_real_spread_g.py` — Verifikasi G dengan spread asli 280 pts
- `scripts/backtest_all_spread.py` — Komparasi A-G unified dengan spread 280 pts
- `scripts/_mt5_test.py`, `_mt5_fix.py`, `_mt5_connect.py`, `_mt5_admin.py` — Debug MT5

## Strategy Performance (4 months real XAUUSDm)

### Dengan spread 25 pts (simulasi — akun Zero/Raw)
| Strategi | TF | ROI | DD | Avg/hari | Target | Trades |
|----------|:--:|:---:|:--:|:--------:|:------:|:------:|
| **G M15 Confidence** | M15 | **+1698%** | **5.2%** | **Rp1.469.392** | **500k ✅** | 2571 |
| **F M15 Turbo** | M15 | **+560%** | **3.2%** | **Rp531.513** | **300k ✅** | 2571 |
| E M15 NoFilter | M15 | +195% | 3.5% | Rp199.465 | 100k ✅ | 1702 |

### Dengan spread 280 pts (real — akun trial Exness demo)
| Strategi | TF | ROI | DD | Avg/hari | Target | Trades |
|----------|:--:|:---:|:--:|:--------:|:------:|:------:|
| **H H1 Confidence** | **H1** | **+120.8%** | **11.7%** | **Rp158.664** | **150k ✅** | **321** |
| D AGRESSIVE | H1 | +68.3% | 4.6% | ~Rp68k | 100k ~68% | 175 |
| D STANDARD | H1 | +46.9% | 3.5% | ~Rp47k | 100k ~47% | 103 |
| B H4 EMA | H4 | +4.2% | 1.0% | ~Rp4k | 100k ❌ | 17 |
| C H4 PSAR | H4 | +5.9% | 2.4% | ~Rp6k | 100k ❌ | 74 |
| A D1 LONG | D1 | -8.4% | 20.5% | -Rp8k | 100k ❌ | 38 |
| E M15 NoFilter | M15 | -19.6% | 20.1% | -Rp19k | 100k ❌ | 261 |
| F M15 Turbo | M15 | -24.5% | 25% | -Rp24k | 300k ❌ | 1231 |
| G M15 Confidence | M15 | -24.4% | 25% | -Rp24k | 500k ❌ | 317 |

**Kesimpulan**: M15 scalping mati total dengan spread 280 pts. H1 confidence sizing adalah satu-satunya yang survive + profit.

## Strategy H Detail (PRIMARY untuk akun trial 280 pts — target Rp217k/hari)
- **Concept**: D base (EMA9/21 H1) + Confidence Scoring (adapted from G)
- **Version**: BOOST (1.0/1.8/2.5x)
- **Timeframe**: H1
- **Params**: EMA9/21 cross, RSI 40-80 / 20-60, NO MACD filter, NO EMA200 filter (jadi confidence factor)
- **Confidence factors** (0-7):
  - H4 trend confluence (+2)
  - BB squeeze (+1)
  - Volume spike 1.2x (+1)
  - RSI extreme (long: >75, short: <25) (+1)
  - London session 07-14 UTC (+1)
  - EMA200 side confirmation (+1)
- **Sizing**:
  - Conf 0-2: 1.0x (normal)
  - Conf 3-4: **1.8x** (boosted)
  - Conf 5-7: **2.5x** (double+)
- **SL/TP**: 1.5x ATR / 3.0x ATR (R:R 2:1)
- **Trailing**: 0.5x ATR
- **Hasil 4 bulan** (spread 280 pts): **Rp217.187/hari, ROI +164.47%, DD 13.2%, PF 1.86, 314 trades**
- **Perbandingan vs D**: 6.4x lebih baik (Rp217k vs Rp34k)
- **Target Rp150k/hari: TERCAPAI. Target baru: Rp200k/hari**
- **Sinyal**: ~2.2/hari, hold ~6 jam
- **Lot**: Dynamic (base 300%, min 200%, max 800%)
- **Scripts**: `scripts/strategi_h_h1.py` (backtest), `scripts/jalankan_strat_h.py` (live monitor)
- **Config**: `config/strategy_h.json`
- **Log**: `data/h_monitor.log`

## Strategy G Detail (BEST PERFORMER untuk Zero/Raw spread 25 pts)
- **Timeframe**: M15
- **Params**: EMA5/13 cross, RSI 30-95 / 5-70 (wide), NO MACD filter, NO EMA200 filter
- **SL/TP**: 0.5x ATR / 2.2x ATR (R:R 4.4:1)
- **Lot**: Dynamic (base 800%, min 300%, max 1500%, naik/turun sesuai modal)
- **Sinyal**: ~15-20/hari, hold ~45 menit
- **Volume filter**: 0.7x avg
- **Running PnL tracking**: 12% per bar
- **Hasil 4 bulan**: Rp531.513/hari, DD 3.2%, 84/160 hari >= Rp300k

## Strategy E Detail (Secondary — target Rp100k/hari)
- **Timeframe**: M15
- **Params**: EMA5/13 cross, RSI 35-82 / 18-65, MACD 5/13/5, no EMA200 filter
- **SL/TP**: 0.7x ATR / 1.8x ATR (R:R 2.57:1)
- **Lot**: Dynamic (base 300%, min 100%, max 800%)
- **Sinyal**: ~10-15/hari, hold ~53 menit
- **Hasil 4 bulan**: Rp199.465/hari, DD 3.5%

## Strategy G Detail (PRIMARY — BEST PERFORMER — target Rp500k+/hari)
- **Concept**: F base (EMA5/13 cross + RSI 30-95/5-70 + volume) + **Confidence Scoring**
- **Scoring** (0-6): H1 trend confluence (+2), BB squeeze (+1), volume spike 1.2x (+1), RSI extreme (+1), London session 07-14 UTC (+1)
- **Sizing**:
  - Conf 0-2: 1.0x (normal)
  - Conf 3-4: **1.5x** (boosted)
  - Conf 5-6: **2.0x** (double)
- **Hasil 4 bulan**: Rp1.469.392/hari, DD 5.2%, PF 2.63, 59% hari >= Rp500k
- **Latar belakang**: Uji coba Session + Multi-TF + Squeeze + Hybrid FILTER semua gagal karena nurunin jumlah trade. Tapi pas dipake sebagai **SIZING tool** (bukan filter), hasilnya **3x lipat** dari F baseline.
- **Lot**: Dynamic (base 1000%, min 400%, max 2000%)
- **Sinyal**: ~16/hari (sama dengan F, tapi lot bervariasi)
- **Scripts**: `scripts/strategi_g_m15.py` (backtest), `scripts/jalankan_strat_g.py` (live monitor)
- **Config**: `config/strategy_g.json`

## Strategy D Detail (Tertiary)
- **Timeframe**: H1
- **Params**: EMA9/21 cross with EMA200 filter + RSI 35-80/20-65 + MACD 8/20/7
- **SL/TP**: 1.2x ATR / 2.5x ATR
- **Lot**: Static 300% (no dynamic)
- **Sinyal**: ~1-2/hari, hold ~6 jam

## AI Manager
- `src/main.py` — Pipeline: audit -> build context -> query AI via OpenCode CLI -> execute decision
- **AI role**: Risk supervisor ONLY (alert, reduce_lot, pause_strategy)
- **AI CANNOT**: buy/sell/close/increase_lot (forbidden in prompt)
- **Triggers**: DD > 10% reduce_lot, Sharpe < 0.1 pause, DD > 20% hard stop
- **State DB**: `data/state.db`

## State Manager Schema (relevant metrics)
- `running_modal` — Modal saat ini (float)
- `portfolio_drawdown` — Drawdown terbesar (float %)
- `rolling_sharpe_7d` — Sharpe ratio (float, capped 0-5)
- `last_heartbeat` — ISO timestamp
- `strategy_d_h1` / `strategy_e_m15` — Strategy status (ACTIVE/PAUSED)

## Known Issues
1. Unicode emoji/rarrow di print() error di Windows terminal cp1252 -> sudah diganti ASCII
2. `mt5.initialize()` harus manual (buka MT5 dulu, login, baru Python connect)
3. Synthetic data fallback ada di strategi_d_h1.py (tapi skrg MT5 works)
4. Dynamic lot bisa cap max kalau modal membesar (F: 1500%, G: 2000%)

## Next Steps (proposed)
1. ~~Auto execution (script entry + SL/TP langsung ke MT5)~~ DONE
2. Telegram notification (bot token & chat ID masih kosong di settings.json)
3. VPS deployment biar 24/7
4. ~~Risk management: daily loss limit, weekly profit target auto-stop~~ DONE
5. Monitoring dashboard di AI Manager (integrasi state DB)
6. Topup akun Zero/Raw (spread 3-10 pts) -> jalankan Strategy G M15 untuk Rp1.4jt+/hari
7. Log monitoring: `data/g_monitor.log` (G), `data/h_monitor.log` (H)

## How to Run
```powershell
cd D:\CODE\TRADING-BOT-V1.0
python scripts/jalankan_strat_h.py    # Strategy H live monitor (loop 1h) — BEST untuk spread 280 pts!
python scripts/jalankan_strat_g.py    # Strategy G live monitor (loop 15m) — BEST untuk Zero account!
python scripts/jalankan_strat_f.py    # Strategy F live monitor (loop 15m)
python scripts/jalankan_strat_e.py    # Strategy E live monitor (loop 15m)
python scripts/jalankan_strat_d.py    # Strategy D live monitor (once)
python scripts/strategi_h_h1.py       # Backtest H + seed DB (H1 confidence sizing — spread 280 pts)
python scripts/strategi_g_m15.py      # Backtest G + seed DB (M15 confidence sizing — spread 25 pts)
python scripts/strategi_f_m15.py      # Backtest F + seed DB (turbo scalper)
python scripts/strategi_e_m15.py      # Backtest E + seed DB
python scripts/strategi_d_h1.py       # Backtest D + seed DB
python src/main.py                    # AI Manager cycle

# Auto execution (setelah test live monitor):
python scripts/jalankan_strat_g.py --auto   # G auto — Zero account only
python scripts/jalankan_strat_h.py --auto   # H auto — bisa sekarang (spread 280 pts)
```

## Password / Account
- MT5 Account: 413889745 / "jatenggayeng" / Exness-MT5Trial6
- Hanya demo account, tidak ada real money
