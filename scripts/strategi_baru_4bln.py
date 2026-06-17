import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

MODAL = 12_000_000
SYMBOL = "XAUUSDm"


def sma(s, p): return s.rolling(p).mean()
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g/l))


def prep_d1(df):
    for p in [5, 10, 13, 20, 30, 50, 100, 200]:
        df[f"sma{p}"] = sma(df["close"], p)
        df[f"ema{p}"] = ema(df["close"], p)
    df["atr14"] = atr(df, 14); df["atr7"] = atr(df, 7)
    df["rsi14"] = rsi(df["close"], 14); df["rsi7"] = rsi(df["close"], 7)
    df["hh5"] = df["high"].rolling(5).max(); df["ll5"] = df["low"].rolling(5).min()
    df["hh10"] = df["high"].rolling(10).max(); df["ll10"] = df["low"].rolling(10).min()
    df["hh20"] = df["high"].rolling(20).max(); df["ll20"] = df["low"].rolling(20).min()
    df["vol_ma"] = df["tick_volume"].rolling(10).mean()
    df["body"] = abs(df["close"] - df["open"])
    df["upper_shadow"] = df["high"] - np.maximum(df["close"], df["open"])
    df["lower_shadow"] = np.minimum(df["close"], df["open"]) - df["low"]
    df.dropna(inplace=True); return df


def prep_h4(df):
    return prep_d1(df)


def run(df, modal_awal, signal_fn, name, sl_atr=2.0, max_hold=20, running_pct=0.1):
    modal = float(modal_awal); entry = 0; peak = modal
    dd_max = 0; trades = []; in_trade = False; held = 0; posisi = None

    for i in range(5, len(df) - 1):
        c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]; a = df["atr14"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 30: in_trade = False; posisi = None; continue

        sig = signal_fn(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"; entry = c; modal -= 10000; in_trade = True; held = 0
            elif sig == "SELL":
                posisi = "SHORT"; entry = c; modal -= 10000; in_trade = True; held = 0
        else:
            held += 1; profit = 0; exit_now = False; sl = a * sl_atr

            if posisi == "LONG":
                if cn <= entry - sl: profit = -(sl / entry) * modal; exit_now = True
                elif sig == "SELL": profit = (c - entry) / entry * modal; exit_now = True
                elif held > max_hold: profit = (c - entry) / entry * modal * 0.5; exit_now = True
                else: profit = (cn - c) / c * modal * running_pct
            else:
                if cn >= entry + sl: profit = -(sl / entry) * modal; exit_now = True
                elif sig == "BUY": profit = (entry - c) / entry * modal; exit_now = True
                elif held > max_hold: profit = (entry - c) / entry * modal * 0.5; exit_now = True
                else: profit = (c - cn) / c * modal * running_pct

            if exit_now:
                modal += profit
                trades.append({"tgl": df.index[i], "side": posisi, "held": held, "profit": round(profit)})
                in_trade = False; posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]; loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    days = max((df.index[-1] - df.index[0]).days, 1)
    per_day = (modal - modal_awal) / days

    return {"name": name, "modal": round(modal), "profit": round(modal - modal_awal),
            "roi": round(roi, 2), "trades": len(trades), "win": len(win), "loss": len(loss),
            "wr": round(len(win)/max(len(trades),1)*100, 1), "pf": round(pf, 2),
            "dd": round(dd_max, 1), "per_bln": round(per_day * 30),
            "tlist": trades}


# ===== SIGNAL FUNCTIONS =====

# A1: Pullback SMA30 LONG only (original)
def sig_a1(df, i):
    c = df["close"].iloc[i]; sma30 = df["sma30"].iloc[i]; sma100 = df["sma100"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]; ema20 = df["ema20"].iloc[i]
    uptrend = sma30 > sma100
    pullback = c <= sma30 + a * 0.5 and c >= sma30 - a * 2
    if uptrend and pullback and r < 45 and c > ema20 * 0.97: return "BUY"
    return "HOLD"

# A2: Pullback SMA20 faster
def sig_a2(df, i):
    c = df["close"].iloc[i]; sma20 = df["sma20"].iloc[i]; sma50 = df["sma50"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]; ema10 = df["ema10"].iloc[i]
    if sma20 > sma50 and c <= sma20 + a * 0.3 and c >= sma20 - a * 1.5 and r < 50 and c > ema10 * 0.97:
        return "BUY"
    if not (sma20 > sma50) and r > 70:
        return "SELL"
    return "HOLD"

# A3: Pullback SMA50 (buy dip ke SMA50)
def sig_a3(df, i):
    c = df["close"].iloc[i]; sma50 = df["sma50"].iloc[i]; sma200 = df["sma200"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]
    if sma50 > sma200 and c <= sma50 + a * 0.5 and c >= sma50 - a * 2 and r < 40:
        return "BUY"
    if not (sma50 > sma200):
        return "SELL"
    return "HOLD"

# B1: Momentum Breakout (5/13 EMA)
def sig_b1(df, i):
    c = df["close"].iloc[i]; ema5 = df["ema5"].iloc[i]; ema13 = df["ema13"].iloc[i]; ema20 = df["ema20"].iloc[i]
    r = df["rsi14"].iloc[i]; v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]
    if ema5 > ema13 and ema13 > ema20 and r > 58 and v > vm * 1.3:
        return "BUY"
    if ema5 < ema13 and ema13 < ema20 and r < 42 and v > vm * 1.3:
        return "SELL"
    return "HOLD"

# B2: Dip buy + RSI oversold
def sig_b2(df, i):
    c = df["close"].iloc[i]; ema20 = df["ema20"].iloc[i]; sma100 = df["sma100"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]; lower = df["lower_shadow"].iloc[i]; body = df["body"].iloc[i]
    if c > sma100 and c < ema20 and r < 35 and lower > body * 1.5:
        return "BUY"
    if c < sma100 and r > 65 and df["upper_shadow"].iloc[i] > body * 1.5:
        return "SELL"
    return "HOLD"

# C1: Supertrend-style (trend following based on ATR)
def sig_c1(df, i):
    c = df["close"].iloc[i]; ema20 = df["ema20"].iloc[i]; a = df["atr14"].iloc[i]
    hh10 = df["hh10"].iloc[i]; ll10 = df["ll10"].iloc[i]
    r = df["rsi14"].iloc[i]; v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]

    upper = ema20 + a * 2; lower = ema20 - a * 2
    if c > upper and r > 60 and v > vm * 1.2:
        return "BUY"
    if c < lower and r < 40 and v > vm * 1.2:
        return "SELL"
    return "HOLD"

# C2: 20-day High/Low breakout
def sig_c2(df, i):
    c = df["close"].iloc[i]; hh20 = df["hh20"].iloc[i]; ll20 = df["ll20"].iloc[i]
    ema20 = df["ema20"].iloc[i]; r = df["rsi14"].iloc[i]; v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]
    if c >= hh20 and v > vm * 1.5 and r > 55 and c > ema20:
        return "BUY"
    if c <= ll20 and v > vm * 1.5 and r < 45 and c < ema20:
        return "SELL"
    return "HOLD"

# D1: Volatility expansion (big body + volume)
def sig_d1(df, i):
    c = df["close"].iloc[i]; o = df["open"].iloc[i]; body = df["body"].iloc[i]; a = df["atr14"].iloc[i]
    v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]; ema20 = df["ema20"].iloc[i]
    r = df["rsi14"].iloc[i]

    big_vol = v > vm * 2.0; big_body = body > a * 0.8
    if big_vol and big_body and c > o and c > ema20 and r > 60:
        return "BUY"
    if big_vol and big_body and c < o and c < ema20 and r < 40:
        return "SELL"
    return "HOLD"

# D2: EMA10/30 crossover with ATR filter
def sig_d2(df, i):
    c = df["close"].iloc[i]; ema10 = df["ema10"].iloc[i]; ema30 = df["ema30"].iloc[i]
    prev_ema10 = df["ema10"].iloc[i-1]; prev_ema30 = df["ema30"].iloc[i-1]
    a = df["atr14"].iloc[i]; v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]

    if prev_ema10 <= prev_ema30 and ema10 > ema30 and v > vm * 1.2:
        return "BUY"
    if prev_ema10 >= prev_ema30 and ema10 < ema30 and v > vm * 1.2:
        return "SELL"
    return "HOLD"

# E1: RSI2 (ultra-short term reversal)
def sig_e1(df, i):
    c = df["close"].iloc[i]; r2 = rsi(df["close"], 2).iloc[i]
    ema20 = df["ema20"].iloc[i]; sma100 = df["sma100"].iloc[i]
    if r2 < 8 and c > sma100:
        return "BUY"
    if r2 > 95 and c < sma100:
        return "SELL"
    return "HOLD"


if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

print(f"{'='*75}")
print(f"  OPTIMASI 4 BULAN — Cari strategi terbaik untuk kondisi sekarang")
print(f"  Modal Rp{MODAL:,} | XAUUSDm")
print(f"{'='*75}")

# D1 data — fetch 800 bars, prep, slice last 120
rf = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, 800)
d1_full = pd.DataFrame(rf); d1_full["time"] = pd.to_datetime(d1_full["time"], unit="s"); d1_full.set_index("time", inplace=True)
d1_full = prep_d1(d1_full)
d1_4 = d1_full.iloc[-120:]
print(f"  D1: {d1_4.index[0].date()} — {d1_4.index[-1].date()} ({len(d1_4)} bars)")

# H4 data — fetch 800 bars, prep, slice
rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, 800)
h4_full = pd.DataFrame(rh); h4_full["time"] = pd.to_datetime(h4_full["time"], unit="s"); h4_full.set_index("time", inplace=True)
h4_full = prep_h4(h4_full)
h4_4 = h4_full.iloc[-480:]
print(f"  H4: {h4_4.index[0].date()} — {h4_4.index[-1].date()} ({len(h4_4)} bars)")

mt5.shutdown()

# Variants: (df, signal_fn, name, sl_atr, max_hold)
strategies = [
    (d1_4, sig_a1, "A1 D1 Pullback SMA30", 2.5, 90),
    (d1_4, sig_a2, "A2 D1 Pullback SMA20", 2.0, 30),
    (d1_4, sig_a3, "A3 D1 Pullback SMA50", 3.0, 120),
    (d1_4, sig_b1, "B1 D1 EMA Crossover", 1.5, 15),
    (d1_4, sig_b2, "B2 D1 Dip Buy RSI<35", 2.0, 20),
    (d1_4, sig_c1, "C1 D1 ATR Channel", 1.5, 10),
    (d1_4, sig_c2, "C2 D1 20d Breakout", 2.0, 15),
    (d1_4, sig_d1, "D1 D1 Vol Expansion", 1.5, 10),
    (d1_4, sig_d2, "D2 D1 EMA10/30 Cross", 2.0, 20),
    (d1_4, sig_e1, "E1 D1 RSI2 Reversal", 2.0, 10),
    (h4_4, sig_a2, "A2 H4 Pullback SMA20", 2.0, 60),
    (h4_4, sig_b1, "B1 H4 EMA Crossover", 1.5, 40),
    (h4_4, sig_c1, "C1 H4 ATR Channel", 1.5, 30),
    (h4_4, sig_c2, "C2 H4 20d Breakout", 2.0, 30),
    (h4_4, sig_d2, "D2 H4 EMA10/30 Cross", 2.0, 40),
    (h4_4, sig_b2, "B2 H4 Dip Buy RSI<35", 2.0, 40),
    (h4_4, sig_e1, "E1 H4 RSI2 Reversal", 2.0, 20),
]

results = []
for df, fn, name, sl, mh in strategies:
    res = run(df, MODAL, fn, name, sl_atr=sl, max_hold=mh)
    results.append(res)

# Print sorted
print(f"\n{'='*75}")
print(f"  RANKING (by profit)")
print(f"{'='*75}")
print(f"  {'#':<3} {'Strategi':<30} {'Profit':<15} {'ROI':<9} {'WR':<8} {'PF':<8} {'DD':<8} {'/bln':<12}")
print(f"  {'-'*90}")
for i, r in enumerate(sorted(results, key=lambda x: x["profit"], reverse=True), 1):
    if r["trades"] == 0: continue
    pm = "+" if r["profit"] > 0 else ""
    print(f"  {i:<3} {r['name']:<30} Rp{r['profit']:<12,} ({pm}{r['roi']:>6.2f}%) "
          f"{r['wr']:>4}%/{r['trades']:<3} {r['pf']:<6} {r['dd']:<5}% Rp{r['per_bln']:<9,}")
# No-trade
no = [r for r in results if r["trades"] == 0]
if no:
    print(f"\n  (0 trade: {', '.join(r['name'] for r in no)})")

print(f"\n{'='*75}")
print(f"  DETAIL TRADES — TOP 5")
print(f"{'='*75}")
for r in sorted(results, key=lambda x: x["profit"], reverse=True)[:5]:
    if not r["tlist"]: continue
    print(f"\n  {r['name']} ({r['trades']} trades, Rp{r['profit']:,}):")
    for t in r["tlist"]:
        pm = "+" if t["profit"] > 0 else ""
        print(f"    {t['tgl'].date()} | {t['side']} | {t['held']}d | {pm}Rp{t['profit']:,}")
