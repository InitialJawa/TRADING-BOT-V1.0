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


def prep(df):
    df["sma100"] = sma(df["close"], 100)
    df["sma200"] = sma(df["close"], 200)
    df["sma50"] = sma(df["close"], 50)
    df["ema20"] = ema(df["close"], 20)
    df["atr20"] = atr(df, 20)
    df["hh50"] = df["high"].rolling(50).max()
    df["ll50"] = df["low"].rolling(50).min()
    df["hh20"] = df["high"].rolling(20).max()
    df["ll20"] = df["low"].rolling(20).min()
    df["chg_pct"] = df["close"].pct_change(periods=5) * 100
    df.dropna(inplace=True)
    return df


# ============================================================
# STRATEGY A — Big Picture Trend (sma200 filter, 50-bar breakout)
# Hanya LONG. Entry: harga > hh50 + sma200 naik. Exit: < ll50
# ============================================================
def s_a(df, i):
    c = df["close"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    sma100 = df["sma100"].iloc[i]
    hh50 = df["hh50"].iloc[i]
    ll50 = df["ll50"].iloc[i]
    chg = df["chg_pct"].iloc[i]

    trend_up = sma100 > sma200 and sma200 > df["sma200"].iloc[max(i-20, 0)]

    if trend_up and c >= hh50 and chg > 0.5:
        return "BUY"
    if c <= ll50:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY B — Multi-Timeframe Confluence
# Weekly uptrend + daily pullback to sma50 + bounce
# ============================================================
def s_b(df, i):
    c = df["close"].iloc[i]
    sma50 = df["sma50"].iloc[i]
    sma100 = df["sma100"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    ema20 = df["ema20"].iloc[i]
    chg = df["chg_pct"].iloc[i]
    atr20 = df["atr20"].iloc[i]
    ll20 = df["ll20"].iloc[i]

    uptrend = sma50 > sma100 > sma200
    pullback_to_support = c <= sma50 * 1.02 and c >= sma50 * 0.97
    bounce_signal = c > ema20 and chg > -2

    if uptrend and pullback_to_support and bounce_signal:
        return "BUY"
    if c < sma100 and c < ema20:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY C — Momentum Breakout with Volatility Filter
# ============================================================
def s_c(df, i):
    c = df["close"].iloc[i]
    hh20 = df["hh20"].iloc[i]
    ll20 = df["ll20"].iloc[i]
    sma200 = df["sma200"].iloc[i]
    atr20 = df["atr20"].iloc[i]
    chg = df["chg_pct"].iloc[i]

    vol_spike = df["tick_volume"].iloc[i] > df["tick_volume"].rolling(20).mean().iloc[i] * 1.3

    if c > sma200 and c > hh20 and vol_spike and chg > 1:
        return "BUY"
    if c < sma200 and c < ll20 and vol_spike and chg < -1:
        return "SELL"
    return "HOLD"


# ============================================================
# BACKTEST — trailing stop, big picture
# ============================================================
def run(df, modal_awal, fn, name):
    modal = float(modal_awal)
    posisi = None
    entry_price = 0.0
    trail_stop = 0.0
    peak = modal
    dd_max = 0.0
    trades = []
    in_trade = False
    bar_hold = 0

    for i in range(30, len(df) - 1):
        tgl = df.index[i]
        c = df["close"].iloc[i]
        cn = df["close"].iloc[i + 1]
        a = df["atr20"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 35:
            posisi = None
            in_trade = False
            continue

        sig = fn(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"
                entry_price = c
                trail_stop = c - a * 4
                modal -= 10000
                in_trade = True
                bar_hold = 0
            elif sig == "SELL":
                posisi = "SHORT"
                entry_price = c
                trail_stop = c + a * 4
                modal -= 10000
                in_trade = True
                bar_hold = 0
        else:
            bar_hold += 1
            profit = 0.0
            exit_here = False

            if posisi == "LONG":
                trail_stop = max(trail_stop, c - a * 3)
                if cn <= trail_stop:
                    profit = (trail_stop - entry_price) / entry_price * modal * 0.5
                    exit_here = True
                elif bar_hold > 60:
                    profit = (cn - entry_price) / entry_price * modal * 0.5
                    exit_here = True
                elif sig == "SELL":
                    profit = (c - entry_price) / entry_price * modal * 0.5
                    exit_here = True
                else:
                    profit = (cn - c) / c * modal * 0.15
            else:
                trail_stop = min(trail_stop, c + a * 3)
                if cn >= trail_stop:
                    profit = (entry_price - trail_stop) / entry_price * modal * 0.5
                    exit_here = True
                elif bar_hold > 60:
                    profit = (entry_price - cn) / entry_price * modal * 0.5
                    exit_here = True
                elif sig == "BUY":
                    profit = (entry_price - c) / entry_price * modal * 0.5
                    exit_here = True
                else:
                    profit = (c - cn) / c * modal * 0.15

            if exit_here:
                modal += profit
                trades.append({
                    "tgl": tgl, "side": posisi, "hold": bar_hold,
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
    print(f"\n{'='*90}")
    print(f"  STRATEGI V3 — XAUUSDm (Big Picture / Low Frequency)")
    print(f"  Periode: {t0} — {t1} | Modal: Rp{MODAL:,}")
    print(f"{'='*90}")
    print(f"  {'Metric':<25} {'A: Big Trend':<18} {'B: MTF Pullback':<18} {'C: Momo Breakout':<18}")
    print(f"  {'-'*25} {'-'*18} {'-'*18} {'-'*18}")

    fields = [
        ("Modal Akhir", "modal_akhir", "Rp{:,.0f}"),
        ("ROI", "roi", "{:+.2f}%"),
        ("Total Trades", "trades", "{}"),
        ("Win / Loss", None, None),
        ("  Win", "win", "{}"),
        ("  Loss", "loss", "{}"),
        ("Win Rate", "wr", "{}%"),
        ("Max DD", "dd", "{}%"),
        ("Avg Win", "avg_w", "Rp{:,.0f}"),
        ("Avg Loss", "avg_l", "Rp{:,.0f}"),
        ("Profit Factor", "pf", "{}"),
    ]
    for label, key, fmt in fields:
        if key is None:
            print(f"  {label:<25} {'-'*18} {'-'*18} {'-'*18}")
            continue
        vals = []
        for r in results:
            try:
                vals.append(fmt.format(r[key]))
            except:
                vals.append(str(r[key]))
        print(f"  {label:<25} {vals[0]:<18} {vals[1]:<18} {vals[2]:<18}")
    print(f"  {'='*90}")

    s = sorted(results, key=lambda x: x["roi"], reverse=True)
    print(f"\n  RANKING:")
    for i, r in enumerate(s, 1):
        wr = "+" if r["roi"] > 0 else ""
        print(f"  #{i} {r['name']} — ROI {wr}{r['roi']}% | {r['trades']} trades | WR {r['wr']}% | PF {r['pf']} | DD {r['dd']}%")

    for r in results:
        print(f"\n  TRADES {r['name']}:")
        if not r["tlist"]:
            print("    (no trades)")
        for t in r["tlist"]:
            pm = "+" if t["profit"] > 0 else ""
            print(f"    {t['tgl'].date()} | {t['side']} | hold {t.get('hold',0)}d | {t['entry']:.0f} -> {t['exit']:.0f} | {pm}Rp{t['profit']:,}")


if not init_mt5():
    print("[ERROR] MT5 tidak bisa diinisialisasi")
    exit()

print("[INFO] Mengambil data XAUUSDm...")
df = get_data(1000)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()

t0, t1 = df.index[0].date(), df.index[-1].date()
df = prep(df)
print(f"[OK] {len(df)} bars siap trading | {t0} — {t1}")

print("\n[RUN] A: Big Trend (50-bar breakout, sma200 filter)...")
ra = run(df, MODAL, s_a, "A: Big Trend")
print("[RUN] B: MTF Pullback (weekly uptrend + daily pullback)...")
rb = run(df, MODAL, s_b, "B: MTF Pullback")
print("[RUN] C: Momentum Breakout (volume + vol spike)...")
rc = run(df, MODAL, s_c, "C: Momo Breakout")

cetak([ra, rb, rc], t0, t1)
mt5.shutdown()
print("\n[DONE]")
