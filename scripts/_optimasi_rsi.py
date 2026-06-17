import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
SPREAD_POINTS = 25
POINT_VALUE = 0.01

def fetch(bars=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize(): return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    mt5.shutdown()
    if rates is None: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True); return df

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=10):
    tr = np.maximum(df["high"]-df["low"],
        np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))
def macd(s,f=5,sl=13,sg=5):
    e1=ema(s,f); e2=ema(s,sl); m=e1-e2; return m, ema(m,sg)

def prep(df):
    df["ema5"]=ema(df["close"],5)
    df["ema13"]=ema(df["close"],13)
    df["ema200"]=ema(df["close"],200)
    df["atr"]=atr(df,10)
    df["rsi"]=rsi(df["close"],14)
    df["vol_ma"]=sma(df["tick_volume"],15)
    df.dropna(inplace=True); return df

def backtest(df, rsi_smin, rsi_smax, rsi_lmin, rsi_lmax):
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0
    daily_pnl = {}; current_day = None; day_pnl = 0.0

    for i in range(50, len(df)):
        row = df.iloc[i]; c = row["close"]; a = row["atr"]
        day = df.index[i].date()
        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0
        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

        ema_bull = row["ema5"] > row["ema13"]
        vol_ok = row["tick_volume"] > row["vol_ma"] * 0.7

        sig = "HOLD"
        if ema_bull and rsi_lmin <= row["rsi"] <= rsi_lmax and vol_ok:
            sig = "BUY"
        elif not ema_bull and rsi_smin <= row["rsi"] <= rsi_smax and vol_ok:
            sig = "SELL"

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * 0.5 if sig == "BUY" else c + a * 0.5
                tp_price = c + a * 2.2 if sig == "BUY" else c - a * 2.2
                modal -= 5000
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost
                in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            ef = row["ema5"]; em = row["ema13"]
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= 20: profit = (c - entry_price) / entry_price * modal; exit = True
                else: profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * 0.12
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal; exit = True
                elif bars >= 20: profit = (entry_price - c) / entry_price * modal; exit = True
                else: profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * 0.12
            if exit:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "profit": round(profit)})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    roi = (modal - MODAL) / MODAL * 100
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0

    return {"profit": round(modal-MODAL), "roi": round(roi,1), "dd": round(dd_max,1),
            "trades": len(trades), "wr": round(len(win)/max(len(trades),1)*100,1),
            "pf": round(pf,2), "avg_day": round(avg_daily,0)}

print("=" * 100)
print(f"  OPTIMASI RSI RANGE UNTUK STRATEGY F")
print(f"  Modal Rp{MODAL:,} | Spread 25 pts | M15 XAUUSDm")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 100)

df = fetch()
if df is None:
    print("[ERROR] Data gagal"); exit()

df = prep(df)
t0, t1 = df.index[0].date(), df.index[-1].date()
print(f"  Periode: {t0} — {t1} ({len(df)} bars)")
print()

variants = [
    ("Current F:  RSI Short 15-70 / Long 30-85", 15, 70, 30, 85),
    ("Widened:    RSI Short 10-70 / Long 30-90", 10, 70, 30, 90),
    ("Widened:    RSI Short 5-70  / Long 30-95", 5, 70, 30, 95),
    ("NoRSI Sell: RSI Short 0-100 / Long 30-85", 0, 100, 30, 85),
    ("NoRSI:      RSI Short 0-100 / Long 0-100", 0, 100, 0, 100),
]

results = []
for label, smin, smax, lmin, lmax in variants:
    r = backtest(df, smin, smax, lmin, lmax)
    r["label"] = label
    results.append(r)
    pm = "+" if r["profit"] > 0 else ""
    print(f"  {label:<40}")
    print(f"    Profit: Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) | "
          f"DD {r['dd']:>4}% | {r['trades']:>4} trades | "
          f"WR {r['wr']:>4}% | PF {r['pf']:>5} | Rp{r['avg_day']:>8,}/hari")
    print()

print("=" * 100)
print("  RANKING (by avg daily):")
for i, r in enumerate(sorted(results, key=lambda x: x["avg_day"], reverse=True), 1):
    print(f"  #{i:<2} {r['label']:<40} Rp{r['avg_day']:>8,}/hari | Rp{r['profit']:>10,} | DD {r['dd']}% | {r['trades']}trades")
print()

# Also show additional sells captured
print("  BAR YANG MASUK DENGAN RSI MIN DITURUNKAN:")
for smin_test in [15, 10, 5, 0]:
    sell_mask = (df["ema5"] < df["ema13"]) & (df["tick_volume"] > df["vol_ma"] * 0.7)
    rsi_sell_mask = (df["rsi"] >= smin_test) & (df["rsi"] <= 70)
    total = (sell_mask & rsi_sell_mask).sum()
    print(f"    RSI min {smin_test:>2}: {total:>4} sell bars masuk")
