import sys, os, json, pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
from strategies.shared.indicators import ema, sma, atr, rsi, macd

if not mt5.initialize():
    print("MT5 init failed")
    exit()

# Fetch XAUUSDm H1 data
def fetch_data(tf, start, end):
    if not mt5.initialize():
        print(f"MT5 init failed for {tf}")
        return None
    mt5.symbol_select("XAUUSDm", True)
    rates = mt5.copy_rates_range("XAUUSDm", tf, start.to_pydatetime(), end.to_pydatetime())
    mt5.shutdown()
    return rates

rates = fetch_data(mt5.TIMEFRAME_H1, pd.Timestamp("2023-08-01"), pd.Timestamp("2026-06-18"))
if rates is None or len(rates) < 2000:
    print(f"Not enough H1 data: {len(rates) if rates else 0}")
    exit()

df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df.set_index("time", inplace=True)

# Indicators
df["ema9"] = ema(df["close"], 9)
df["ema21"] = ema(df["close"], 21)
df["ema50"] = ema(df["close"], 50)
df["sma200"] = sma(df["close"], 200)
df["atr14"] = atr(df, 14)
df["rsi"] = rsi(df["close"], 14)
macd_line, macd_sig = macd(df["close"], 12, 26, 9)
df["macd"] = macd_line
df["macd_sig"] = macd_sig
df["vol_ma"] = sma(df["tick_volume"], 20)

# Fetch M15 data
rates_m15 = fetch_data(mt5.TIMEFRAME_M15, pd.Timestamp("2023-08-01"), pd.Timestamp("2026-06-18"))
df_m15 = pd.DataFrame(rates_m15) if rates_m15 is not None else pd.DataFrame()
if not df_m15.empty:
    df_m15["time"] = pd.to_datetime(df_m15["time"], unit="s")
    df_m15.set_index("time", inplace=True)
    df_m15["ema5"] = ema(df_m15["close"], 5)
    df_m15["ema13"] = ema(df_m15["close"], 13)
    df_m15["atr10"] = atr(df_m15, 10)
    df_m15["rsi14"] = rsi(df_m15["close"], 14)
    df_m15["vol_ma15"] = sma(df_m15["tick_volume"], 15)

# Fetch D1 data
rates_d1 = fetch_data(mt5.TIMEFRAME_D1, pd.Timestamp("2020-01-01"), pd.Timestamp("2026-06-18"))
df_d1 = pd.DataFrame(rates_d1) if rates_d1 is not None else pd.DataFrame()
if not df_d1.empty:
    df_d1["time"] = pd.to_datetime(df_d1["time"], unit="s")
    df_d1.set_index("time", inplace=True)
    df_d1["sma30"] = sma(df_d1["close"], 30)
    df_d1["sma120"] = sma(df_d1["close"], 120)
    df_d1["sma200"] = sma(df_d1["close"], 200)
    df_d1["rsi"] = rsi(df_d1["close"], 14)
    df_d1["atr14"] = atr(df_d1, 14)
    df_d1.dropna(inplace=True)
    df_d1 = df_d1[df_d1.index >= "2026-05-01"]

df.dropna(inplace=True)
df = df[df.index >= "2026-05-01"]

if not df_m15.empty:
    df_m15.dropna(inplace=True)
    df_m15 = df_m15[df_m15.index >= "2026-05-01"]

m15_count = len(df_m15) if not df_m15.empty else 0
d1_count = len(df_d1) if not df_d1.empty else 0
print(f"Data: H1={len(df)} bars, M15={m15_count} bars, D1={d1_count} bars")

# ========== Backtest engine ==========
def backtest(df, strategy_name, entry_fn, sl_mult, tp_mult, max_bars, lot=0.02):
    modal = 1000.0
    peak = modal
    dd_max = 0
    trades = []
    in_trade = False
    posisi = None
    entry_price = 0
    entry_idx = 0
    sl_price = 0
    tp_price = 0
    last_trade_day = None

    for i in range(len(df)):
        row = df.iloc[i]
        c = float(row["close"])
        today = df.index[i].date()

        if modal > peak:
            peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)

        if in_trade:
            bars = i - entry_idx
            exit_sig = False
            pnl = 0

            # Check exits
            if posisi == 1:
                if c <= sl_price:
                    pnl = (sl_price - entry_price) / entry_price * modal
                    exit_sig = True
                elif c >= tp_price:
                    pnl = (tp_price - entry_price) / entry_price * modal
                    exit_sig = True
                elif bars >= max_bars:
                    pnl = (c - entry_price) / entry_price * modal
                    exit_sig = True
            else:
                if c >= sl_price:
                    pnl = (entry_price - sl_price) / entry_price * modal
                    exit_sig = True
                elif c <= tp_price:
                    pnl = (entry_price - tp_price) / entry_price * modal
                    exit_sig = True
                elif bars >= max_bars:
                    pnl = (entry_price - c) / entry_price * modal
                    exit_sig = True

            if exit_sig:
                modal += pnl
                trades.append({
                    "date": df.index[i], "pos": "BUY" if posisi == 1 else "SELL",
                    "bars": bars, "pnl": round(pnl, 2), "modal": round(modal, 2),
                    "exit": "SL/TP" if bars < max_bars else "MAXHOLD"
                })
                in_trade = False
                posisi = None
        else:
            if today == last_trade_day:
                continue

            sig = entry_fn(row, df, i)
            if sig != 0:
                in_trade = True
                posisi = sig
                entry_price = c
                entry_idx = i
                last_trade_day = today
                atr_val = float(row.get("atr14", row.get("atr10", 10)))
                if sig == 1:
                    sl_price = c - atr_val * sl_mult
                    tp_price = c + atr_val * tp_mult
                else:
                    sl_price = c + atr_val * sl_mult
                    tp_price = c - atr_val * tp_mult

    return modal, dd_max, trades


# ========== Strategy A: D1 SMA30 Pullback LONG ONLY ==========
def strat_a(row, df, i):
    if row["close"] <= row["sma200"]:
        return 0
    if row["rsi"] >= 45:
        return 0
    buf = row["sma30"] * 0.005
    if row["close"] < row["sma30"] - buf:
        return 0
    if row["close"] > row["sma30"] + buf:
        return 0
    return 1

# ========== Strategy B: H4 EMA10/30 Cross ==========
def strat_b(row, df, i):
    if row["tick_volume"] < row["vol_ma"] * 1.2:
        return 0
    if i < 1:
        return 0
    prev = df.iloc[i - 1]
    ema10 = float(row.get("ema10", row.get("ema9", 0)))
    ema30 = float(row.get("ema30", row.get("ema21", 0)))
    ema10_prev = float(prev.get("ema10", prev.get("ema9", 0)))
    ema30_prev = float(prev.get("ema30", prev.get("ema21", 0)))
    if ema10 > ema30 and ema10_prev <= ema30_prev and 20 <= row["rsi"] <= 80:
        return 1
    if ema10 < ema30 and ema10_prev >= ema30_prev and 20 <= row["rsi"] <= 80:
        return -1
    return 0

# ========== Strategy D: H1 Confluence ==========
def strat_d(row, df, i):
    bull = float(row["ema9"]) > float(row["ema21"]) and float(row["macd"]) > float(row["macd_sig"])
    bear = float(row["ema9"]) < float(row["ema21"]) and float(row["macd"]) < float(row["macd_sig"])
    c = float(row["close"])
    vol_ok = float(row["tick_volume"]) > float(row["vol_ma"]) * 1.1
    r = float(row["rsi"])
    if bull and c > float(row["ema50"]) and c > float(row["sma200"]) and 45 <= r <= 75 and vol_ok:
        return 1
    if bear and c < float(row["ema50"]) and c < float(row["sma200"]) and 25 <= r <= 55 and vol_ok:
        return -1
    return 0

# ========== Strategy E: M15 NoFilter ==========
def strat_e(row, df, i):
    if float(row["tick_volume"]) < float(row["vol_ma15"]) * 0.7:
        return 0
    if float(row["ema5"]) > float(row["ema13"]) and 35 <= float(row["rsi14"]) <= 82:
        return 1
    if float(row["ema5"]) < float(row["ema13"]) and 18 <= float(row["rsi14"]) <= 65:
        return -1
    return 0

# ========== Strategy F: M15 Turbo ==========
def strat_f(row, df, i):
    if float(row["tick_volume"]) < float(row["vol_ma15"]) * 0.7:
        return 0
    if float(row["ema5"]) > float(row["ema13"]) and 30 <= float(row["rsi14"]) <= 95:
        return 1
    if float(row["ema5"]) < float(row["ema13"]) and 5 <= float(row["rsi14"]) <= 70:
        return -1
    return 0

# ========== Strategy H: H1 Confidence Sizing ==========
def strat_h(row, df, i):
    bull = float(row["ema9"]) > float(row["ema21"])
    bear = float(row["ema9"]) < float(row["ema21"])
    if not bull and not bear:
        return 0
    c = float(row["close"])
    r = float(row["rsi"])
    if bull and (r < 40 or r > 80):
        return 0
    if bear and (r < 20 or r > 60):
        return 0
    vol_ok = float(row["tick_volume"]) > float(row["vol_ma"]) * 0.8
    if not vol_ok:
        return 0
    return 1 if bull else -1


# ========== Run all ==========
results = []

# --- Strategy A (D1) ---
if len(df_d1) > 100:
    bal, dd, trades = backtest(df_d1, "A D1", strat_a, 2.0, 3.0, 90)
    wins = len([t for t in trades if t["pnl"] > 0])
    results.append(("A D1 SMA30 Pullback", len(trades), bal, dd, wins, f"{((bal-1000)/1000*100):+.2f}%"))
    print(f"\nA D1: {len(trades)} trades, balance=${bal:.2f}, DD={dd:.2f}%")
    for t in trades:
        print(f"  {t['date']} {t['pos']} pnl=${t['pnl']} bal=${t['modal']}")

# --- Strategy D (H1) ---
bal, dd, trades = backtest(df, "D H1", strat_d, 2.0, 4.0, 24)
wins = len([t for t in trades if t["pnl"] > 0])
results.append(("D H1 Confluence", len(trades), bal, dd, wins, f"{((bal-1000)/1000*100):+.2f}%"))
print(f"\nD H1: {len(trades)} trades, balance=${bal:.2f}, DD={dd:.2f}%")
for t in trades:
    print(f"  {t['date']} {t['pos']} pnl=${t['pnl']} bal=${t['modal']}")

# --- Strategy E (M15) ---
bal, dd, trades = backtest(df_m15, "E M15", strat_e, 0.7, 1.8, 16)
wins = len([t for t in trades if t["pnl"] > 0])
results.append(("E M15 NoFilter", len(trades), bal, dd, wins, f"{((bal-1000)/1000*100):+.2f}%"))
print(f"\nE M15: {len(trades)} trades, balance=${bal:.2f}, DD={dd:.2f}%")
for t in trades[:10]:
    print(f"  {t['date']} {t['pos']} pnl=${t['pnl']} bal=${t['modal']}")

# --- Strategy F (M15) ---
bal, dd, trades = backtest(df_m15, "F M15", strat_f, 0.5, 2.2, 20)
wins = len([t for t in trades if t["pnl"] > 0])
results.append(("F M15 Turbo", len(trades), bal, dd, wins, f"{((bal-1000)/1000*100):+.2f}%"))
print(f"\nF M15: {len(trades)} trades, balance=${bal:.2f}, DD={dd:.2f}%")

# --- Strategy H (H1) ---
bal, dd, trades = backtest(df, "H H1", strat_h, 1.5, 3.0, 24)
wins = len([t for t in trades if t["pnl"] > 0])
results.append(("H H1 Confidence", len(trades), bal, dd, wins, f"{((bal-1000)/1000*100):+.2f}%"))
print(f"\nH H1: {len(trades)} trades, balance=${bal:.2f}, DD={dd:.2f}%")
for t in trades[:10]:
    print(f"  {t['date']} {t['pos']} pnl=${t['pnl']} bal=${t['modal']}")

# Summary
print(f"\n{'='*60}")
print(f"{'Strategy':<25} {'Trades':<8} {'Balance':<12} {'DD':<8} {'WR':<8} {'Return':<10}")
print(f"{'-'*60}")
for name, n, bal, dd, wins, ret in results:
    wr = f"{wins/n*100:.0f}%" if n > 0 else "N/A"
    print(f"{name:<25} {n:<8} ${bal:<8.2f} {dd:<7.2f}% {wr:<8} {ret:<10}")
