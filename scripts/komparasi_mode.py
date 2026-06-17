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


def sma(s, p): return s.rolling(p).mean()
def ema(s, p): return s.ewm(span=p, adjust=False).mean()


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


# SIGNAL FUNCTIONS
def sig_a(df, i):
    c = df["close"].iloc[i]
    sma50 = df["sma50"].iloc[i]; sma100 = df["sma100"].iloc[i]; sma200 = df["sma200"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]; ema20 = df["ema20"].iloc[i]
    uptrend = sma50 > sma100 > sma200 and df["sma50"].iloc[max(i-10,0)] < sma50
    pullback = c <= sma50 + a * 0.5 and c >= sma50 - a * 2
    if uptrend and pullback and r < 45 and c > ema20 * 0.97:
        return "BUY"
    if c < sma100: return "SELL"
    return "HOLD"


def sig_c(df, i):
    c = df["close"].iloc[i]; sma20 = df["sma20"].iloc[i]; sma50 = df["sma50"].iloc[i]
    sma100 = df["sma100"].iloc[i]; sma200 = df["sma200"].iloc[i]
    ema10 = df["ema10"].iloc[i]; v = df["tick_volume"].iloc[i]; vm = df["vol_ma"].iloc[i]
    chg = df["chg5"].iloc[i]; r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]
    uptrend = sma50 > sma100 > sma200
    momentum = c > ema10 and r > 55 and chg > 1.5 and v > vm * 1.2
    if uptrend and momentum: return "BUY"
    if c < sma20 - a * 0.5: return "SELL"
    return "HOLD"


# ============================================================
# MODE 1: COMPOUND + LOT BESAR
# Lot naik setiap modal naik Rp500rb
# ============================================================
def run_mode1(df, modal_awal):
    modal = float(modal_awal)
    posisi = None; entry_price = 0.0; trail_price = 0.0
    peak = modal; dd_max = 0.0; trades = []
    in_trade = False; bars_held = 0
    history = [{"tgl": df.index[0], "modal": round(modal), "dd": 0}]

    for i in range(60, len(df) - 1):
        tgl = df.index[i]; c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]; a = df["atr14"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)

        lot = max(0.1, round(modal / modal_awal * 0.1, 2))
        lot = min(lot, 1.0)
        risk_pct = lot / 0.1 * 0.01

        if dd > 30: in_trade = False; posisi = None; continue

        sig = sig_a(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"; entry_price = c; trail_price = c - a * 3
                modal -= 10000 * lot / 0.1; in_trade = True; bars_held = 0
        else:
            bars_held += 1; trail_price = max(trail_price, ll10)
            profit = 0.0; exit_here = False

            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal * (lot / 0.1) * 0.5
                exit_here = True
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            elif bars_held > 90:
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
            else:
                profit = (cn - c) / c * modal * 0.15 * (lot / 0.1)

            if exit_here:
                modal += profit
                trades.append({"tgl": tgl, "held": bars_held, "lot": round(lot, 2),
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

        if i % 20 == 0:
            history.append({"tgl": tgl, "modal": round(modal), "dd": round(dd, 1)})

    return modal, dd_max, trades, history


# ============================================================
# MODE 2: MULTI STRATEGI (A + C parallel, capital split)
# ============================================================
def run_mode2(df, modal_awal):
    modal_a = modal_awal * 0.5
    modal_c = modal_awal * 0.5

    pos_a = None; entry_a = 0; trail_a = 0; in_a = False; held_a = 0
    pos_c = None; entry_c = 0; trail_c = 0; in_c = False; held_c = 0
    peak = modal_awal; dd_max = 0.0
    trades = []
    history = [{"tgl": df.index[0], "modal": round(modal_a + modal_c), "dd": 0}]

    for i in range(60, len(df) - 1):
        tgl = df.index[i]; c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]; a = df["atr14"].iloc[i]

        total = modal_a + modal_c
        if total > peak: peak = total
        dd = (peak - total) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 30: in_a = False; in_c = False; pos_a = None; pos_c = None; continue

        sig_a_val = sig_a(df, i)
        sig_c_val = sig_c(df, i)

        # Strategy A
        if not in_a:
            if sig_a_val == "BUY":
                pos_a = "LONG"; entry_a = c; trail_a = c - a * 3
                modal_a -= 5000; in_a = True; held_a = 0
        else:
            held_a += 1; trail_a = max(trail_a, ll10)
            profit = 0; exit_a = False
            if cn <= trail_a:
                profit = (trail_a - entry_a) / entry_a * modal_a * 0.5; exit_a = True
            elif sig_a_val == "SELL":
                profit = (c - entry_a) / entry_a * modal_a; exit_a = True
            elif held_a > 90:
                profit = (c - entry_a) / entry_a * modal_a; exit_a = True
            else:
                profit = (cn - c) / c * modal_a * 0.15
            if exit_a:
                modal_a += profit
                trades.append({"tgl": tgl, "strat": "A", "held": held_a, "profit": round(profit), "modal": round(modal_a + modal_c)})
                in_a = False; pos_a = None

        # Strategy C
        if not in_c:
            if sig_c_val == "BUY":
                pos_c = "LONG"; entry_c = c; trail_c = c - a * 3
                modal_c -= 5000; in_c = True; held_c = 0
        else:
            held_c += 1; trail_c = max(trail_c, ll10)
            profit = 0; exit_c = False
            if cn <= trail_c:
                profit = (trail_c - entry_c) / entry_c * modal_c * 0.5; exit_c = True
            elif sig_c_val == "SELL":
                profit = (c - entry_c) / entry_c * modal_c; exit_c = True
            elif held_c > 90:
                profit = (c - entry_c) / entry_c * modal_c; exit_c = True
            else:
                profit = (cn - c) / c * modal_c * 0.15
            if exit_c:
                modal_c += profit
                trades.append({"tgl": tgl, "strat": "C", "held": held_c, "profit": round(profit), "modal": round(modal_c + modal_c)})
                in_c = False; pos_c = None

        if i % 20 == 0:
            history.append({"tgl": tgl, "modal": round(total), "dd": round(dd, 1)})

    total_akhir = modal_a + modal_c
    return total_akhir, dd_max, trades, history


# ============================================================
# MODE 3: HIGH RISK (lot 0.5, stop lebar, risk 3% per trade)
# ============================================================
def run_mode3(df, modal_awal):
    modal = float(modal_awal)
    posisi = None; entry_price = 0.0; trail_price = 0.0
    peak = modal; dd_max = 0.0; trades = []
    in_trade = False; bars_held = 0

    for i in range(60, len(df) - 1):
        tgl = df.index[i]; c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]; a = df["atr14"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 40: in_trade = False; posisi = None; continue

        sig = sig_a(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"; entry_price = c; trail_price = c - a * 4
                modal -= 50000; in_trade = True; bars_held = 0
        else:
            bars_held += 1; trail_price = max(trail_price, ll10)
            profit = 0.0; exit_here = False

            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal * 0.5
                exit_here = True
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal * 0.8
                exit_here = True
            elif bars_held > 120:
                profit = (c - entry_price) / entry_price * modal * 0.8
                exit_here = True
            else:
                profit = (cn - c) / c * modal * 0.5

            if exit_here:
                modal += profit
                trades.append({"tgl": tgl, "held": bars_held,
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    return modal, dd_max, trades, []


# ============================================================
# CETAK HASIL
# ============================================================
def cetak_perbandingan(results, t0, t1):
    print(f"\n{'='*95}")
    print(f"  PERBANDINGAN 3 MODE — XAUUSDm {t0} — {t1}")
    print(f"  Modal Awal: Rp{MODAL:,}")
    print(f"{'='*95}")
    print(f"  {'Metric':<30} {'Mode 1: Compound':<20} {'Mode 2: Multi Strat':<20} {'Mode 3: High Risk':<20}")
    print(f"  {'-'*30} {'-'*20} {'-'*20} {'-'*20}")

    for r in results:
        profit = r["modal_akhir"] - MODAL
        r["profit"] = profit
        r["per_month"] = profit / max(r.get("trades_count", 1), 1) * (30 / max(r.get("avg_hold", 25), 1))

    fields = [
        ("Modal Akhir", "modal_akhir", "Rp{:,.0f}"),
        ("Total Profit", "profit", "Rp{:,.0f}"),
        ("ROI", "roi", "{:+.2f}%"),
        ("Profit Factor", "pf", "{}"),
        ("Total Trades", "trades_count", "{}"),
        ("Win Rate", "wr", "{}%"),
        ("Max DD", "dd", "{}%"),
        ("Rata-rata Hold", "avg_hold", "{} hari"),
    ]

    for label, key, fmt in fields:
        vals = []
        for r in results:
            try: vals.append(fmt.format(r[key]))
            except: vals.append(str(r[key]))
        print(f"  {label:<30} {vals[0]:<20} {vals[1]:<20} {vals[2]:<20}")
    print(f"  {'='*95}")

    # Monthly projection
    print(f"\n  PROYEKSI BULANAN (berdasarkan data 3 tahun):")
    print(f"  {'-'*95}")
    print(f"  {'Mode':<30} {'/bulan':<20} {'/tahun':<20} {'3 tahun':<20}")
    print(f"  {'-'*95}")
    for r in results:
        days = 798  # periode backtest
        per_day = r["profit"] / days
        per_month = per_day * 30
        per_year = per_day * 365
        per_3y = per_day * 1095
        print(f"  {r['name']:<30} Rp{per_month:,.0f}/bln    Rp{per_year:,.0f}/thn    Rp{per_3y:,.0f}/3thn")
    print(f"  {'-'*95}")

    # Ranking
    s = sorted(results, key=lambda x: x["roi"], reverse=True)
    print(f"\n  RANKING:")
    medals = ["#1", "#2", "#3"]
    for i, r in enumerate(s):
        print(f"  {medals[i]} {r['name']} — ROI {r['roi']:+.2f}% | PF {r['pf']} | DD {r['dd']}% | Rp{r['profit']:,}")

    # Detail mode
    for r in results:
        proj_day = r["profit"] / 798
        print(f"\n  TOP TRADES {r['name']}:")
        if r.get("tlist"):
            for t in r["tlist"][-8:]:
                pm = "+" if t["profit"] > 0 else ""
                info = f"  {t['tgl'].date()} | held {t.get('held',0)}d | {pm}Rp{t['profit']:,}"
                if "lot" in t: info += f" | lot {t['lot']}"
                if "strat" in t: info += f" | strat {t['strat']}"
                print(info)
        print(f"  -> Proyeksi: Rp{proj_day:,.0f}/hari = Rp{proj_day*30:,.0f}/bulan")


# ============================================================
if not init_mt5(): print("[ERROR] MT5"); exit()

df = get_data(1000)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()
t0, t1 = df.index[0].date(), df.index[-1].date()
df = prep(df)
print(f"[OK] {len(df)} bars | {t0} — {t1}")

print("\n[MODE 1] Compound + Lot Progresif...")
m1_akhir, m1_dd, m1_trades, m1_hist = run_mode1(df, MODAL)
m1_win = [t for t in m1_trades if t["profit"] > 0]
m1_loss = [t for t in m1_trades if t["profit"] < 0]
m1_pf = sum(t["profit"] for t in m1_win) / abs(sum(t["profit"] for t in m1_loss)) if m1_loss else 999
m1_avg_hold = np.mean([t["held"] for t in m1_trades]) if m1_trades else 0

print("[MODE 2] Multi Strategi (A + C parallel)...")
m2_akhir, m2_dd, m2_trades, m2_hist = run_mode2(df, MODAL)
m2_win = [t for t in m2_trades if t["profit"] > 0]
m2_loss = [t for t in m2_trades if t["profit"] < 0]
m2_pf = sum(t["profit"] for t in m2_win) / abs(sum(t["profit"] for t in m2_loss)) if m2_loss else 999
m2_avg_hold = np.mean([t["held"] for t in m2_trades]) if m2_trades else 0

print("[MODE 3] High Risk (lot 0.5, stop lebar)...")
m3_akhir, m3_dd, m3_trades, m3_hist = run_mode3(df, MODAL)
m3_win = [t for t in m3_trades if t["profit"] > 0]
m3_loss = [t for t in m3_trades if t["profit"] < 0]
m3_pf = sum(t["profit"] for t in m3_win) / abs(sum(t["profit"] for t in m3_loss)) if m3_loss else 999
m3_avg_hold = np.mean([t["held"] for t in m3_trades]) if m3_trades else 0

results = [
    {"name": "Mode 1: Compound", "modal_akhir": round(m1_akhir), "roi": round((m1_akhir-MODAL)/MODAL*100, 2),
     "pf": m1_pf, "trades_count": len(m1_trades), "wr": round(len(m1_win)/max(len(m1_trades),1)*100, 1),
     "dd": round(m1_dd, 1), "avg_hold": round(m1_avg_hold), "tlist": m1_trades},
    {"name": "Mode 2: Multi Strat", "modal_akhir": round(m2_akhir), "roi": round((m2_akhir-MODAL)/MODAL*100, 2),
     "pf": m2_pf, "trades_count": len(m2_trades), "wr": round(len(m2_win)/max(len(m2_trades),1)*100, 1),
     "dd": round(m2_dd, 1), "avg_hold": round(m2_avg_hold), "tlist": m2_trades},
    {"name": "Mode 3: High Risk", "modal_akhir": round(m3_akhir), "roi": round((m3_akhir-MODAL)/MODAL*100, 2),
     "pf": m3_pf, "trades_count": len(m3_trades), "wr": round(len(m3_win)/max(len(m3_trades),1)*100, 1),
     "dd": round(m3_dd, 1), "avg_hold": round(m3_avg_hold), "tlist": m3_trades},
]

cetak_perbandingan(results, t0, t1)
mt5.shutdown()
print("\n[DONE]")
