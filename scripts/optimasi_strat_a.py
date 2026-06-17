import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from itertools import product

SYMBOL = "XAUUSDm"
MODAL = 5_000_000


def init_mt5():
    if not mt5.initialize(): return False
    mt5.symbol_select(SYMBOL, True)
    return True


def get_data(bars=1000):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, bars)
    if rates is None: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def sma(s, p): return s.rolling(p).mean()
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g/l))


def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()


def prep(df, params):
    p = params
    df["sma_entry"] = sma(df["close"], p["sma_entry"])
    df["sma_exit"] = sma(df["close"], p["sma_exit"])
    df["sma200"] = sma(df["close"], p["sma200"])
    df["ema20"] = ema(df["close"], 20)
    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["ll10"] = df["low"].rolling(10).min()
    df.dropna(inplace=True)
    return df


def signal(df, i, params):
    p = params
    c = df["close"].iloc[i]
    sma_entry = df["sma_entry"].iloc[i]
    sma_exit = df["sma_exit"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    r = df["rsi14"].iloc[i]
    a = df["atr14"].iloc[i]
    ema20 = df["ema20"].iloc[i]

    uptrend = sma_entry > sma_exit > sma200
    pullback = c <= sma_entry + a * 0.5 and c >= sma_entry - a * p["atr_pullback"]
    exhausted = r < p["rsi_max"] and c > ema20 * (1 - p["ema_buffer"])

    if uptrend and pullback and exhausted:
        return "BUY"
    if c < sma_exit:
        return "SELL"
    return "HOLD"


def run(df, modal_awal, params):
    modal = float(modal_awal)
    posisi = None; entry_price = 0.0; trail_price = 0.0
    peak = modal; dd_max = 0.0; trades = []; in_trade = False; bars_held = 0
    p = params

    for i in range(70, len(df) - 1):
        tgl = df.index[i]; c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]; a = df["atr14"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 30: in_trade = False; posisi = None; continue

        sig = signal(df, i, params)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"; entry_price = c
                trail_price = c - a * p["atr_stop"]
                modal -= 10000; in_trade = True; bars_held = 0
        else:
            bars_held += 1; trail_price = max(trail_price, ll10)
            profit = 0.0; exit_here = False

            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal
                exit_here = True
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            elif bars_held > p["max_hold"]:
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            else:
                profit = (cn - c) / c * modal * p["running_pct"]

            if exit_here:
                modal += profit
                trades.append({"profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999

    return {
        "roi": round(roi, 2),
        "dd": round(dd_max, 1),
        "trades": len(trades),
        "win": len(win),
        "loss": len(loss),
        "wr": round(len(win)/max(len(trades),1)*100, 1),
        "pf": round(pf, 2),
    }


# ============================================================
# PARAMETER GRID
# ============================================================
param_grids = {
    "sma_entry": [30, 40, 50, 60, 70],
    "sma_exit": [80, 100, 120, 150, 200],
    "sma200": [150, 200, 250],
    "rsi_max": [35, 40, 45, 50, 55],
    "atr_pullback": [1.5, 2.0, 2.5, 3.0],
    "atr_stop": [2.0, 3.0, 4.0, 5.0],
    "max_hold": [60, 90, 120],
    "running_pct": [0.1, 0.15, 0.2, 0.3],
    "ema_buffer": [0.02, 0.03, 0.04, 0.05],
}

BASE_PARAMS = {
    "sma_entry": 50, "sma_exit": 100, "sma200": 200,
    "rsi_max": 45, "atr_pullback": 2.0, "atr_stop": 3.0,
    "max_hold": 90, "running_pct": 0.15, "ema_buffer": 0.03
}


def optimize_one(param_name, values, df, modal_awal):
    results = []
    for val in values:
        params = BASE_PARAMS.copy()
        params[param_name] = val
        df2 = prep(df.copy(), params)
        r = run(df2, modal_awal, params)
        r["param"] = val
        results.append(r)
        print(f"    {param_name}={val}: ROI {r['roi']:+.2f}% | DD {r['dd']}% | WR {r['wr']}% | PF {r['pf']} | Trades {r['trades']}")
    return results


if not init_mt5(): print("[ERROR] MT5"); exit()
df = get_data(1200)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()
print(f"[OK] {len(df)} bars | {df.index[0].date()} — {df.index[-1].date()}")

print(f"\n{'='*80}")
print("  PARAMETER OPTIMIZATION — Strategy A")
print(f"{'='*80}")

# Baseline
print(f"\n--- BASELINE (default params) ---")
df_base = prep(df.copy(), BASE_PARAMS)
base = run(df_base, MODAL, BASE_PARAMS)
print(f"  ROI: {base['roi']:+.2f}% | DD: {base['dd']}% | WR: {base['wr']}% | PF: {base['pf']} | Trades: {base['trades']}")

# Optimize each parameter
best_overall = {"roi": -999}
best_params = BASE_PARAMS.copy()

for param, values in param_grids.items():
    print(f"\n--- OPTIMIZE: {param} ---")
    results = optimize_one(param, values, df, MODAL)
    best = max(results, key=lambda x: x["roi"])
    worst = min(results, key=lambda x: x["roi"])
    print(f"  BEST:  {param}={best['param']} -> ROI {best['roi']:+.2f}% | DD {best['dd']}% | PF {best['pf']}")
    print(f"  WORST: {param}={worst['param']} -> ROI {worst['roi']:+.2f}% | DD {worst['dd']}%")

    if best["roi"] > best_overall["roi"]:
        best_overall = best
        best_params[param] = best["param"]

print(f"\n{'='*80}")
print(f"  BEST COMBINATION FOUND:")
print(f"{'='*80}")
for k, v in best_params.items():
    base_v = BASE_PARAMS[k]
    arrow = " -> " if v != base_v else " (same)"
    print(f"  {k:<15}: {base_v}{arrow}{v}")

df_opt = prep(df.copy(), best_params)
opt_result = run(df_opt, MODAL, best_params)
print(f"\n  OPTIMIZED RESULT:")
print(f"  ROI: {base['roi']:+.2f}% -> {opt_result['roi']:+.2f}%")
print(f"  DD:  {base['dd']}% -> {opt_result['dd']}%")
print(f"  PF:  {base['pf']} -> {opt_result['pf']}")
print(f"  WR:  {base['wr']}% -> {opt_result['wr']}%")
print(f"  Trades: {base['trades']} -> {opt_result['trades']}")

profit_improvement = opt_result["roi"] - base["roi"]
print(f"\n  IMPROVEMENT: {profit_improvement:+.2f}%")

if profit_improvement > 5:
    print(f"\n  >>> RECOMMENDED PARAMS UPDATE <<<")
    print(f"  Update config/strategy_a.json with:")
    for k, v in best_params.items():
        print(f"    {k}: {v}")

mt5.shutdown()
print("\n[DONE]")
