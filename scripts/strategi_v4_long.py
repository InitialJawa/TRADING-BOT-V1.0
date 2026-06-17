import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

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


def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()


def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()


def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g/l))


def prep(df):
    df["sma20"] = sma(df["close"], 20)
    df["sma50"] = sma(df["close"], 50)
    df["sma100"] = sma(df["close"], 100)
    df["sma200"] = sma(df["close"], 200)
    df["ema10"] = ema(df["close"], 10)
    df["ema20"] = ema(df["close"], 20)
    df["atr14"] = atr(df, 14)
    df["atr20"] = atr(df, 20)
    df["rsi14"] = rsi(df["close"], 14)
    df["hh20"] = df["high"].rolling(20).max()
    df["ll10"] = df["low"].rolling(10).min()
    df["ll20"] = df["low"].rolling(20).min()
    df["vol_ma"] = df["tick_volume"].rolling(20).mean()
    df["chg5"] = df["close"].pct_change(5) * 100
    df.dropna(inplace=True)
    return df


# ============================================================
# A — Pullback to SMA50 (LONG only, no short)
# ============================================================
def s_a(df, i):
    c = df["close"].iloc[i]
    sma50 = df["sma50"].iloc[i]
    sma100 = df["sma100"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    r = df["rsi14"].iloc[i]
    a = df["atr14"].iloc[i]
    ema20 = df["ema20"].iloc[i]

    uptrend = sma50 > sma100 > sma200 and df["sma50"].iloc[max(i-10,0)] < sma50
    pullback = c <= sma50 + a * 0.5 and c >= sma50 - a * 2
    exhausted = r < 45 and c > ema20 * 0.97

    if uptrend and pullback and exhausted:
        return "BUY"
    if c < sma100:
        return "SELL"
    return "HOLD"


# ============================================================
# B — Breakout Pullback (buy dip after new high)
# ============================================================
def s_b(df, i):
    c = df["close"].iloc[i]
    sma50 = df["sma50"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    ema20 = df["ema20"].iloc[i]
    hh20 = df["hh20"].iloc[i]
    a = df["atr14"].iloc[i]
    r = df["rsi14"].iloc[i]

    uptrend = sma50 > sma200 and df["sma50"].iloc[max(i-15,0)] < sma50
    recent_high = df["high"].iloc[max(i-15,0)] > df["high"].iloc[i-15:i].max()
    dip = c <= ema20 * 1.01 and r < 50

    if uptrend and recent_high and dip:
        return "BUY"
    if c < sma50:
        return "SELL"
    return "HOLD"


# ============================================================
# C — Trend Momentum (buy strength, trail with sma20)
# ============================================================
def s_c(df, i):
    c = df["close"].iloc[i]
    sma20 = df["sma20"].iloc[i]
    sma50 = df["sma50"].iloc[i]
    sma100 = df["sma100"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    ema10 = df["ema10"].iloc[i]
    v = df["tick_volume"].iloc[i]
    vm = df["vol_ma"].iloc[i]
    chg = df["chg5"].iloc[i]
    r = df["rsi14"].iloc[i]
    a = df["atr14"].iloc[i]

    uptrend = sma50 > sma100 > sma200
    momentum = c > ema10 and r > 55 and chg > 1.5 and v > vm * 1.2

    if uptrend and momentum:
        return "BUY"
    if c < sma20 - a * 0.5:
        return "SELL"
    return "HOLD"


# ============================================================
# BACKTEST — LONG only, trailing stop
# ============================================================
def run(df, modal_awal, fn, name):
    modal = float(modal_awal)
    posisi = None
    entry_price = 0.0
    trail_price = 0.0
    peak = modal
    dd_max = 0.0
    trades = []
    in_trade = False
    bars_held = 0

    for i in range(50, len(df) - 1):
        tgl = df.index[i]
        c = df["close"].iloc[i]
        cn = df["close"].iloc[i + 1]
        a = df["atr14"].iloc[i]
        ll10 = df["ll10"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 30:
            in_trade = False
            posisi = None
            continue

        sig = fn(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"
                entry_price = c
                trail_price = c - a * 3
                modal -= 10000
                in_trade = True
                bars_held = 0
        else:
            bars_held += 1
            trail_price = max(trail_price, ll10)
            profit = 0.0
            exit_here = False

            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal
                exit_here = True
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            elif bars_held > 90:
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            else:
                profit = (cn - c) / c * modal * 0.2

            if exit_here:
                modal += profit
                trades.append({
                    "tgl": tgl, "side": posisi, "held": bars_held,
                    "entry": round(entry_price, 1), "exit": round(cn, 1),
                    "profit": round(profit), "modal": round(modal)
                })
                in_trade = False
                posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    avg_w = np.mean([t["profit"] for t in win]) if win else 0
    avg_l = abs(np.mean([t["profit"] for t in loss])) if loss else 1
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999

    return {
        "name": name, "modal_akhir": round(modal), "roi": round(roi, 2),
        "trades": len(trades), "win": len(win), "loss": len(loss),
        "wr": round(len(win) / max(len(trades), 1) * 100, 1),
        "dd": round(dd_max, 1), "avg_w": round(avg_w), "avg_l": round(avg_l),
        "pf": round(pf, 2), "tlist": trades[-15:],
    }


def cetak(results, t0, t1):
    print(f"\n{'='*95}")
    print(f"  STRATEGI V4 — LONG ONLY XAUUSDm")
    print(f"  Periode: {t0} — {t1} | Modal: Rp{MODAL:,}")
    print(f"{'='*95}")
    print(f"  {'Metric':<28} {'A: Pullback SMA50':<20} {'B: Breakout Dip':<20} {'C: Momo Trail':<20}")
    print(f"  {'-'*28} {'-'*20} {'-'*20} {'-'*20}")

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
            try: vals.append(fmt.format(r[key]))
            except: vals.append(str(r[key]))
        print(f"  {label:<28} {vals[0]:<20} {vals[1]:<20} {vals[2]:<20}")
    print(f"  {'='*95}")

    s = sorted(results, key=lambda x: x["roi"], reverse=True)
    print(f"\n  RANKING:")
    for i, r in enumerate(s, 1):
        w = "+" if r["roi"] > 0 else ""
        print(f"  #{i} {r['name']} — ROI {w}{r['roi']}% | {r['trades']} trades | WR {r['wr']}% | PF {r['pf']} | DD {r['dd']}%")

    for r in results:
        print(f"\n  OPEN TRADES {r['name']}:")
        if not r["tlist"]:
            print("    (no trades)")
        for t in r["tlist"]:
            p = "+" if t["profit"] > 0 else ""
            print(f"    {t['tgl'].date()} | held {t.get('held',0)}d | {t['entry']:.0f} -> {t['exit']:.0f} | {p}Rp{t['profit']:,}")


if not init_mt5():
    print("[ERROR] MT5 tidak bisa diinisialisasi")
    exit()

print("[INFO] Mengambil data XAUUSDm...")
df = get_data(1000)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()

t0, t1 = df.index[0].date(), df.index[-1].date()
df = prep(df)
print(f"[OK] {len(df)} bars | {t0} — {t1}")

print("\n[RUN] A: Pullback SMA50 (buy dip in uptrend, LONG only)...")
ra = run(df, MODAL, s_a, "A: Pullback SMA50")
print("[RUN] B: Breakout Dip (buy dip after new high, LONG only)...")
rb = run(df, MODAL, s_b, "B: Breakout Dip")
print("[RUN] C: Trend Momentum (buy strength, trail sma20, LONG only)...")
rc = run(df, MODAL, s_c, "C: Trend Momentum")

cetak([ra, rb, rc], t0, t1)
mt5.shutdown()
print("\n[DONE]")
