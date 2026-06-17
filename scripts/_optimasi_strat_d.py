import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime

MODAL = 12_000_000
BARS = 2900

BASE_PARAMS = {
    "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 45, "rsi_long_max": 75,
    "rsi_short_min": 25, "rsi_short_max": 55,
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 4.0,
    "atr_trail_mult": 1.0,
    "volume_ma_period": 20, "volume_mult": 1.1,
    "max_hold_bars": 24, "lot_pct": 200, "running_pct": 0.03
}


def generate_synthetic_h1(bars=BARS, start_price=3300.0, seed=42):
    np.random.seed(seed)
    dates = pd.date_range(start="2024-01-01", periods=bars, freq="h")
    prices = np.zeros(bars)
    prices[0] = start_price
    trend = 0
    for i in range(1, bars):
        if np.random.random() < 0.015:
            trend = np.random.choice([-1, 0, 1])
        trend_str = np.random.uniform(0.1, 0.6) * trend
        vol = np.random.uniform(6, 16)
        ret = np.random.normal(trend_str, vol)
        prices[i] = prices[i-1] + ret
        if prices[i] < start_price * 0.75: prices[i] = prices[i-1] + abs(ret) * 0.5
        if prices[i] > start_price * 1.35: prices[i] = prices[i-1] - abs(ret) * 0.5
    ohlc = np.zeros((bars, 5))
    ohlc[:, 3] = prices
    for i in range(1, bars):
        spread = np.random.uniform(2, 8)
        c = ohlc[i, 3]
        o = ohlc[i-1, 3] + np.random.uniform(-spread, spread)
        hi = max(o, c) + np.random.uniform(0, spread * 1.5)
        lo = min(o, c) - np.random.uniform(0, spread * 1.5)
        ohlc[i, 0] = round(o, 2)
        ohlc[i, 1] = round(hi, 2)
        ohlc[i, 2] = round(lo, 2)
        ohlc[i, 3] = round(c, 2)
        ohlc[i, 4] = int(np.random.uniform(500, 5000))
    return pd.DataFrame(ohlc, columns=["open", "high", "low", "close", "tick_volume"], index=dates)


def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()


def prep(df, p):
    df["ema9"] = ema(df["close"], p["ema_fast"])
    df["ema21"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["atr14"] = tr.rolling(14).mean()
    d = df["close"].diff(); g = d.where(d > 0, 0).rolling(14).mean()
    l = (-d.where(d < 0, 0)).rolling(14).mean()
    df["rsi14"] = 100 - (100 / (1 + g / l))
    e1 = ema(df["close"], 12); e2 = ema(df["close"], 26)
    df["macd"] = e1 - e2; df["macd_signal"] = ema(df["macd"], 9)
    df["vol_ma"] = sma(df["tick_volume"], 20)
    df.dropna(inplace=True)
    return df


def backtest(df, p):
    modal = float(MODAL)
    peak = modal; dd_max = 0.0; trades = []
    in_trade = False; posisi = None; entry_price = 0.0
    entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail_activated = False

    for i in range(250, len(df)):
        c = df["close"].iloc[i]; a = df["atr14"].iloc[i]
        ema9 = df["ema9"].iloc[i]; ema21 = df["ema21"].iloc[i]
        row = df.iloc[i]
        above200 = c > row["ema200"]; ema_bull = ema9 > ema21
        ema_bear = ema9 < ema21; macd_bull = row["macd"] > row["macd_signal"]
        macd_bear = row["macd"] < row["macd_signal"]
        vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
        sig = "HOLD"
        if above200 and ema_bull and p["rsi_long_min"] <= row["rsi14"] <= p["rsi_long_max"] and macd_bull and vol_ok:
            sig = "BUY"
        elif not above200 and ema_bear and p["rsi_short_min"] <= row["rsi14"] <= p["rsi_short_max"] and macd_bear and vol_ok:
            sig = "SELL"
        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 20: in_trade = False; posisi = None; continue
        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail_activated = False; modal -= 5000; in_trade = True
        else:
            bars_held = i - entry_idx; exit_here = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit_here = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal; exit_here = True
                elif ema9 < ema21: profit = (c - entry_price) / entry_price * modal; exit_here = True
                elif bars_held >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit_here = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail_activated and (c - entry_price) >= td:
                        trail_activated = True; sl_price = entry_price + td * 0.3
                    if trail_activated: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit_here = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit_here = True
                elif ema9 > ema21: profit = (entry_price - c) / entry_price * modal; exit_here = True
                elif bars_held >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit_here = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail_activated and (entry_price - c) >= td:
                        trail_activated = True; sl_price = entry_price - td * 0.3
                    if trail_activated: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]
            if exit_here:
                modal += profit; trades.append({"profit": round(profit), "held": bars_held})
                in_trade = False; posisi = None
    return modal, dd_max, trades


def evaluate(p, label, seed=42):
    df = generate_synthetic_h1(BARS, seed=seed)
    df = prep(df, p)
    modal_akhir, dd_max, trades = backtest(df, p)
    roi = (modal_akhir - MODAL) / MODAL * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    wr = len(win) / max(len(trades), 1) * 100
    return {"label": label, "roi": round(roi, 2), "dd": round(dd_max, 2), "pf": round(pf, 2),
            "wr": round(wr, 1), "trades": len(trades), "seed": seed}


print("=" * 70)
print("  OPTIMASI STRATEGY D — Multi Parameter Test (4 bulan)")
print("=" * 70)

variants = [
    (BASE_PARAMS.copy(), "BASE"),
    ({**BASE_PARAMS, "rsi_long_min": 50, "rsi_long_max": 80, "rsi_short_min": 20, "rsi_short_max": 50}, "RSI_TIGHT"),
    ({**BASE_PARAMS, "rsi_long_min": 40, "rsi_long_max": 70, "rsi_short_min": 30, "rsi_short_max": 60}, "RSI_MID"),
    ({**BASE_PARAMS, "atr_sl_mult": 1.5, "atr_tp_mult": 3.0}, "RR_1_2"),
    ({**BASE_PARAMS, "atr_sl_mult": 2.5, "atr_tp_mult": 5.0}, "RR_1_2_WIDE"),
    ({**BASE_PARAMS, "volume_mult": 1.5}, "VOL_HIGH"),
    ({**BASE_PARAMS, "volume_mult": 1.0}, "VOL_ANY"),
    ({**BASE_PARAMS, "ema_fast": 5, "ema_medium": 13}, "EMA_5_13"),
    ({**BASE_PARAMS, "ema_fast": 12, "ema_medium": 26}, "EMA_12_26"),
]

results = []
for params, label in variants:
    r = evaluate(params, label, seed=42)
    results.append(r)
    print(f"  {label:<15} ROI: {r['roi']:+.1f}%  DD: {r['dd']:.1f}%  PF: {r['pf']:.2f}  WR: {r['wr']:.0f}%  Trades: {r['trades']}")

results.sort(key=lambda x: x["roi"], reverse=True)
print(f"\n  --- TOP 3 by ROI ---")
for r in results[:3]:
    print(f"  {r['label']:<15} ROI: {r['roi']:+.1f}%  DD: {r['dd']:.1f}%  PF: {r['pf']:.2f}")

results.sort(key=lambda x: x["pf"], reverse=True)
print(f"\n  --- TOP 3 by PF ---")
for r in results[:3]:
    print(f"  {r['label']:<15} ROI: {r['roi']:+.1f}%  DD: {r['dd']:.1f}%  PF: {r['pf']:.2f}")

print(f"\n  --- MULTI-SEED TEST (best variant) ---")
best = results[0]
for seed in [7, 13, 21, 99, 123]:
    r = evaluate(variants[0][0], f"BASE_s{seed}", seed)
    print(f"  seed={seed:<4} ROI: {r['roi']:+.1f}%  DD: {r['dd']:.1f}%  PF: {r['pf']:.2f}  WR: {r['wr']:.0f}%  Trades: {r['trades']}")

print("\n[DONE]")
