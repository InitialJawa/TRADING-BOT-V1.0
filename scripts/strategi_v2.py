import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

SYMBOL = "XAUUSDm"
MODAL = 5_000_000
SPREAD_POINTS = 25
POINT_VALUE = 0.01


def init_mt5():
    if not mt5.initialize():
        return False
    mt5.symbol_select(SYMBOL, True)
    return True


def get_data(bars=1000):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, bars)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()


def sma(s, p):
    return s.rolling(p).mean()


def atr(df, p=14):
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1)))
    )
    return tr.rolling(p).mean()


def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    rs = g / l
    return 100 - (100 / (1 + rs))


def macd(s):
    e12 = ema(s, 12)
    e26 = ema(s, 26)
    m = e12 - e26
    return m, ema(m, 9)


def prep(df):
    df["ema10"] = ema(df["close"], 10)
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema100"] = ema(df["close"], 100)
    df["ema200"] = ema(df["close"], 200)
    df["sma200"] = sma(df["close"], 200)
    df["atr14"] = atr(df, 14)
    df["atr20"] = atr(df, 20)
    df["rsi14"] = rsi(df["close"], 14)
    df["macd"], df["macds"] = macd(df["close"])
    df["highest20"] = df["high"].rolling(20).max()
    df["lowest20"] = df["low"].rolling(20).min()
    df["highest50"] = df["high"].rolling(50).max()
    df["lowest50"] = df["low"].rolling(50).min()
    df.dropna(inplace=True)
    return df


# ============================================================
# STRATEGY A — Long Bias Trend (LONG only, trailing stop)
# ============================================================
def s_a(df, i):
    c = df["close"].iloc[i]
    e10 = df["ema10"].iloc[i]
    e20 = df["ema20"].iloc[i]
    e50 = df["ema50"].iloc[i]
    e200 = df["ema200"].iloc[i]
    r = df["rsi14"].iloc[i]
    macd_line = df["macd"].iloc[i]
    macd_sig = df["macds"].iloc[i]

    if c > e200 and e10 > e20 > e50 and macd_line > macd_sig and r > 50:
        return "BUY"
    if c < e10 and e10 < e20 and macd_line < macd_sig:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY B — Pullback Entry (buy dips in uptrend)
# ============================================================
def s_b(df, i):
    c = df["close"].iloc[i]
    e20 = df["ema20"].iloc[i]
    e50 = df["ema50"].iloc[i]
    e200 = df["ema200"].iloc[i]
    r = df["rsi14"].iloc[i]
    m = df["macd"].iloc[i]
    ms = df["macds"].iloc[i]
    lo20 = df["lowest20"].iloc[i]
    hi20 = df["highest20"].iloc[i]

    in_uptrend = c > e200 and e50 > e200
    pullback_done = m > ms and r > 40
    near_support = c <= e20 * 1.01

    if in_uptrend and pullback_done and near_support:
        return "BUY"
    if c < e50 and m < ms:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY C — Adaptive Trend dengan Trailing Stop
# ============================================================
def s_c(df, i):
    c = df["close"].iloc[i]
    e20 = df["ema20"].iloc[i]
    e50 = df["ema50"].iloc[i]
    e200 = df["ema200"].iloc[i]
    a = df["atr14"].iloc[i]
    r = df["rsi14"].iloc[i]
    hi50 = df["highest50"].iloc[i]
    lo50 = df["lowest50"].iloc[i]

    trend_up = c > e200 and e20 > e50
    trend_dn = c < e200 and e20 < e50
    momentum_up = r > 55 and c > hi50 * 0.98
    momentum_dn = r < 45 and c < lo50 * 1.02

    if trend_up and momentum_up:
        return "BUY"
    if trend_dn and momentum_dn:
        return "SELL"
    return "HOLD"


# ============================================================
# BACKTEST
# ============================================================
def run(df, modal_awal, fn, name):
    modal = float(modal_awal)
    posisi = None
    entry_price = 0.0
    peak = modal
    dd_max = 0.0
    trades = []

    for i in range(5, len(df) - 1):
        tgl = df.index[i]
        c = df["close"].iloc[i]
        cn = df["close"].iloc[i + 1]
        a = df["atr14"].iloc[i]

        if modal > peak:
            peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 30:
            posisi = None
            continue

        sig = fn(df, i)

        if posisi is None:
            if sig == "BUY":
                posisi = "LONG"
                entry_price = c
                modal -= 10000
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost
            elif sig == "SELL":
                posisi = "SHORT"
                entry_price = c
                modal -= 10000
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost
        else:
            sl_dist = a * 2.5
            tp_dist = a * 5.0
            risk_rp = modal * 0.015
            pct_move = risk_rp / modal

            profit = 0.0
            exit_here = False

            if posisi == "LONG":
                if cn <= c - sl_dist:
                    profit = -(sl_dist / c) * modal
                    exit_here = True
                elif cn >= c + tp_dist:
                    profit = (tp_dist / c) * modal
                    exit_here = True
                elif sig == "SELL" or (cn < entry_price and cn < df["ema20"].iloc[i]):
                    profit = (cn - entry_price) / entry_price * modal * 0.5
                    exit_here = True
                else:
                    profit = (cn - c) / c * modal * 0.3
            else:
                if cn >= c + sl_dist:
                    profit = -(sl_dist / c) * modal
                    exit_here = True
                elif cn <= c - tp_dist:
                    profit = (tp_dist / c) * modal
                    exit_here = True
                elif sig == "BUY" or (cn > entry_price and cn > df["ema20"].iloc[i]):
                    profit = (entry_price - cn) / entry_price * modal * 0.5
                    exit_here = True
                else:
                    profit = (c - cn) / c * modal * 0.3

            modal += profit
            trades.append({
                "tgl": tgl, "side": posisi,
                "entry": round(entry_price, 1), "exit": round(cn, 1),
                "profit": round(profit), "modal": round(modal)
            })
            posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    avg_w = np.mean([t["profit"] for t in win]) if win else 0
    avg_l = abs(np.mean([t["profit"] for t in loss])) if loss else 1
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999

    return {
        "name": name,
        "modal_akhir": round(modal),
        "roi": round(roi, 2),
        "trades": len(trades),
        "win": len(win),
        "loss": len(loss),
        "wr": round(len(win) / max(len(trades), 1) * 100, 1),
        "dd": round(dd_max, 1),
        "avg_w": round(avg_w),
        "avg_l": round(avg_l),
        "pf": round(pf, 2),
        "tlist": trades[-12:],
    }


def cetak(results):
    print(f"\n{'='*85}")
    print(f"  KOMPARASI STRATEGI V2 — XAUUSDm Real MT5 Data")
    print(f"  Periode: {t0} — {t1} | Modal: Rp{MODAL:,}")
    print(f"{'='*85}")
    print(f"  {'Metric':<22} {'A: Long Bias':<18} {'B: Pullback':<18} {'C: Adaptive':<18}")
    print(f"  {'-'*22} {'-'*18} {'-'*18} {'-'*18}")

    fields = [
        ("Modal Akhir", "modal_akhir", "Rp{:,.0f}"),
        ("ROI", "roi", "{:+.2f}%"),
        ("Total Trades", "trades", "{}"),
        ("Win", "win", "{}"),
        ("Loss", "loss", "{}"),
        ("Win Rate", "wr", "{}%"),
        ("Max DD", "dd", "{}%"),
        ("Avg Win", "avg_w", "Rp{:,.0f}"),
        ("Avg Loss", "avg_l", "Rp{:,.0f}"),
        ("Profit Factor", "pf", "{}"),
    ]
    for label, key, fmt in fields:
        vals = []
        for r in results:
            try:
                vals.append(fmt.format(r[key]))
            except:
                vals.append(str(r[key]))
        print(f"  {label:<22} {vals[0]:<18} {vals[1]:<18} {vals[2]:<18}")
    print(f"  {'='*85}")

    s = sorted(results, key=lambda x: x["roi"], reverse=True)
    print(f"\n  RANKING:")
    for i, r in enumerate(s, 1):
        wr = "+" if r["roi"] > 0 else ""
        print(f"  #{i} {r['name']} — ROI {wr}{r['roi']}% | WR {r['wr']}% | PF {r['pf']} | DD {r['dd']}%")

    for r in results:
        print(f"\n  TRADES {r['name']}:")
        if not r["tlist"]:
            print("    (no trades)")
        for t in r["tlist"]:
            pm = "+" if t["profit"] > 0 else ""
            print(f"    {t['tgl'].date()} | {t['side']} | {t['entry']:.0f} -> {t['exit']:.0f} | {pm}Rp{t['profit']:,} | Modal: Rp{t['modal']:,}")


if not init_mt5():
    print("[ERROR] MT5 tidak bisa diinisialisasi")
    exit()

print("[INFO] Mengambil data XAUUSDm...")
df = get_data(900)
if df is None:
    print("[ERROR] Tidak ada data")
    mt5.shutdown()
    exit()

t0, t1 = df.index[0].date(), df.index[-1].date()
df = prep(df)
print(f"[OK] {len(df)} bars siap trading")

print("\n[RUN] A: Long Bias Trend...")
ra = run(df, MODAL, s_a, "A: Long Bias Trend")
print("[RUN] B: Pullback Entry...")
rb = run(df, MODAL, s_b, "B: Pullback Entry")
print("[RUN] C: Adaptive Trend...")
rc = run(df, MODAL, s_c, "C: Adaptive Trend")

cetak([ra, rb, rc])
mt5.shutdown()
print("\n[DONE]")
