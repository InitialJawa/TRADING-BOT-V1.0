import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
IDR_USD = 15000

SPREAD_POINTS = 280
POINT_VALUE = 0.01

COMMISSION = {"A": 10000, "B": 10000, "C": 10000, "D": 5000, "E": 5000, "F": 5000}
LOT_PCT = {"A": 100, "B": 100, "C": 100, "D": 200, "E": 300, "F": 800, "G": 1000}
TARGETS = {"A": 50000, "B": 50000, "C": 50000, "D": 100000, "E": 100000, "F": 300000, "G": 500000}

# ============== INDICATORS ==============
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))
def macd(s, f=12, sl=26, sg=9):
    e1 = ema(s, f); e2 = ema(s, sl); m = e1 - e2; return m, ema(m, sg)

# ============== DATA ==============
def fetch_data(bars=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("[ERROR] MT5 tidak bisa initialize. Buka MT5 dulu, login, lalu coba lagi.")
        return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    mt5.shutdown()
    if rates is None or len(rates) < 500:
        print("[ERROR] Data tidak cukup")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df

def resample(df, freq):
    ohlc = df.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "tick_volume": "sum", "spread": "mean"
    })
    ohlc.dropna(inplace=True)
    return ohlc

# ============== BACKTEST ENGINE ==============
def backtest_engine(df, params, signal_fn, name, fraction_fn=None):
    p = params
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0
    spread_total = 0.0; commission_total = 0.0; modal_at_entry = 0.0

    for i in range(p.get("warmup", 50), len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        day = df.index[i].date()
        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0
        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > p.get("max_dd", 30): in_trade = False; posisi = None; continue

        frac = 1.0
        if fraction_fn:
            conf = fraction_fn(df, i)
            frac = frac_g(conf)

        sig = signal_fn(df, i, p)
        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["sl"] if sig == "BUY" else c + a * p["sl"]
                tp_price = c + a * p["tp"] if sig == "BUY" else c - a * p["tp"]
                trail = False

                comm = COMMISSION.get(name[:1], 5000) * frac
                modal -= comm; commission_total += comm

                spread_rp = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal * frac
                modal -= spread_rp; spread_total += spread_rp

                modal_at_entry = modal
                trade_frac = frac
                in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            ef = df.get("ema_fast", df.get("ema5", pd.Series(index=df.index))).iloc[i]
            em = df.get("ema_medium", df.get("ema13", pd.Series(index=df.index))).iloc[i]
            close_prev = df["close"].iloc[i-1]

            base_entry = modal_at_entry * trade_frac
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * base_entry; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * base_entry; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * base_entry; exit = True
                elif bars >= p.get("max_hold", 99): profit = (c - entry_price) / entry_price * base_entry; exit = True
                else:
                    td = a * p.get("trail", 0)
                    if td > 0:
                        if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                        if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - close_prev) / close_prev * base_entry * p.get("running", 0.05)
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * base_entry; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * base_entry; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * base_entry; exit = True
                elif bars >= p.get("max_hold", 99): profit = (entry_price - c) / entry_price * base_entry; exit = True
                else:
                    td = a * p.get("trail", 0)
                    if td > 0:
                        if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                        if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (close_prev - c) / close_prev * base_entry * p.get("running", 0.05)

            if exit:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf_num = sum(t["profit"] for t in win)
    pf_den = abs(sum(t["profit"] for t in loss)) if loss else 1
    pf = pf_num / pf_den if pf_den > 0 else 999
    roi = (modal - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    days_above = sum(1 for v in daily_pnl.values() if v >= TARGETS.get(name[:1], 100000))

    return {
        "name": name, "modal_akhir": round(modal),
        "profit": round(modal - MODAL), "roi": round(roi, 1),
        "dd_max": round(dd_max, 1), "trades": len(trades),
        "win": len(win), "loss": len(loss),
        "wr": round(len(win) / max(len(trades), 1) * 100, 1),
        "pf": round(pf, 2), "avg_hold": round(avg_hold),
        "avg_daily": round(avg_daily, 0), "days_above": days_above,
        "total_days": len(daily_pnl),
        "spread_total": round(spread_total), "commission_total": round(commission_total),
        "trades_per_day": round(len(trades) / max(len(daily_pnl), 1), 1)
    }

# G: M15 Confidence Sizing (F base + confidence scoring)
CONF_SIZING_G = [
    (0, 2, 1.0),
    (3, 4, 1.5),
    (5, 6, 2.0),
]

def confidence_g(df, i):
    row = df.iloc[i]
    s = 0; bull = row["ema5"] > row["ema13"]
    h1 = row.get("h1_trend", "NEUTRAL")
    if (bull and h1 == "UP") or (not bull and h1 == "DOWN"): s += 2
    if row.get("squeeze", False): s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2: s += 1
    if bull and row["rsi14"] > 65: s += 1
    if not bull and row["rsi14"] < 35: s += 1
    if 7 <= row.get("hour_utc", 0) < 15: s += 1
    return s

def frac_g(conf):
    for lo, hi, f in CONF_SIZING_G:
        if lo <= conf <= hi: return f
    return 1.0

def sig_g(df, i, p):
    row = df.iloc[i]
    ema_bull = row["ema5"] > row["ema13"]
    rsi_long = 30 <= row["rsi14"] <= 95
    vol_ok = row["tick_volume"] > row["vol_ma"] * 0.7
    sig = "HOLD"
    if ema_bull and rsi_long and vol_ok: sig = "BUY"
    if not ema_bull and 5 <= row["rsi14"] <= 70 and vol_ok: sig = "SELL"
    # G uses the same entry as F — sizing is applied externally in backtest engine
    return sig

# ============== SIGNAL FUNCTIONS ==============

# A: D1 Pullback SMA30 LONG Only
def sig_a(df, i, p):
    row = df.iloc[i]; c = row["close"]
    sma30 = row["sma30"]; sma100 = row["sma100"]; sma200 = row["sma200"]
    r = row["rsi14"]; a = row["atr"]; ema20 = row["ema20"]
    uptrend = sma30 > sma100
    pullback = c <= sma30 + a * 0.5 and c >= sma30 - a * 2.0
    if uptrend and pullback and r < 45 and c > ema20 * 0.97:
        return "BUY"
    return "HOLD"

# B: H4 EMA10/30 Cross
def sig_b(df, i, p):
    row = df.iloc[i]; row1 = df.iloc[i-1]
    e10 = row["ema10"]; e30 = row["ema30"]
    e10_1 = row1["ema10"]; e30_1 = row1["ema30"]
    v = row["tick_volume"]; vm = row["vol_ma"]; r = row["rsi14"]
    if e10_1 <= e30_1 and e10 > e30 and v >= vm * 1.2 and r >= 20: return "BUY"
    if e10_1 >= e30_1 and e10 < e30 and v >= vm * 1.2 and r <= 80: return "SELL"
    return "HOLD"

# C: H4 Adaptive Trend
def sig_c(df, i, p):
    row = df.iloc[i]; c = row["close"]
    e20 = row["ema20"]; e50 = row["ema50"]; e200 = row["ema200"]
    a = row["atr"]; r = row["rsi14"]
    hi50 = row["highest50"]; lo50 = row["lowest50"]
    trend_up = c > e200 and e20 > e50
    trend_dn = c < e200 and e20 < e50
    momentum_up = r > 55 and c > hi50 * 0.98
    momentum_dn = r < 45 and c < lo50 * 1.02
    if trend_up and momentum_up: return "BUY"
    if trend_dn and momentum_dn: return "SELL"
    return "HOLD"

# D: H1 Confluence Momentum
def sig_d(df, i, p):
    row = df.iloc[i]; c = row["close"]
    above_200 = c > row["ema200"]
    ema_bull = row["ema9"] > row["ema21"]
    rsi_long = p["rs_lmin"] <= row["rsi14"] <= p["rs_lmax"]
    macd_bull = row["macd"] > row["macd_sig"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("vol_mult", 1.1)
    if above_200 and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema9"] < row["ema21"]
    rsi_short = p["rs_smin"] <= row["rsi14"] <= p["rs_smax"]
    macd_bear = row["macd"] < row["macd_sig"]
    if not above_200 and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

# E: M15 NoFilter Momentum
def sig_e(df, i, p):
    row = df.iloc[i]; c = row["close"]
    ema_bull = row["ema5"] > row["ema13"]
    above_200 = c > row["ema200"]
    rsi_long = p["rs_lmin"] <= row["rsi14"] <= p["rs_lmax"]
    macd_bull = row["macd"] > row["macd_sig"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("vol_mult", 0.7)
    if (above_200 or True) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_short = p["rs_smin"] <= row["rsi14"] <= p["rs_smax"]
    macd_bear = row["macd"] < row["macd_sig"]
    if (not above_200 or True) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

# F: M15 Turbo Scalper (no MACD, no EMA200)
def sig_f(df, i, p):
    row = df.iloc[i]; c = row["close"]
    ema_bull = row["ema5"] > row["ema13"]
    rsi_long = p["rs_lmin"] <= row["rsi14"] <= p["rs_lmax"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("vol_mult", 0.7)
    if ema_bull and rsi_long and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_short = p["rs_smin"] <= row["rsi14"] <= p["rs_smax"]
    if ema_bear and rsi_short and vol_ok:
        return "SELL"
    return "HOLD"

# ============== INDICATOR PREP FOR EACH TF ==============
def prep_m15(df):
    df["ema5"] = ema(df["close"], 5)
    df["ema13"] = ema(df["close"], 13)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, 10)
    df["rsi14"] = rsi(df["close"], 14)
    df["macd"], df["macd_sig"] = macd(df["close"], 5, 13, 5)
    df["vol_ma"] = sma(df["tick_volume"], 15)
    # BB squeeze untuk G
    bbu = df["close"].rolling(20).mean() + 2 * df["close"].rolling(20).std()
    bbl = df["close"].rolling(20).mean() - 2 * df["close"].rolling(20).std()
    df["bbw"] = (bbu - bbl) / df["close"].rolling(20).mean()
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour
    # H1 trend dari resample M15
    dh1 = df.resample("1h").agg({"close":"last","ema5":"last","ema13":"last"})
    dh1["ema9"] = ema(dh1["close"], 9)
    dh1["ema21"] = ema(dh1["close"], 21)
    dh1["h1_trend"] = np.where(dh1["ema9"] > dh1["ema21"], "UP", "DOWN")
    h1_trend_series = dh1["h1_trend"].resample("15min").ffill()
    df["h1_trend"] = h1_trend_series.reindex(df.index, method="ffill")
    df.dropna(inplace=True); return df

def prep_h1(df):
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["macd"], df["macd_sig"] = macd(df["close"], 12, 26, 9)
    df["vol_ma"] = sma(df["tick_volume"], 20)
    df.dropna(inplace=True); return df

def prep_h4(df):
    for p in [10, 20, 30, 50, 100, 200]:
        df[f"ema{p}"] = ema(df["close"], p)
    df["atr"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["vol_ma"] = sma(df["tick_volume"], 10)
    df["highest50"] = df["high"].rolling(50).max()
    df["lowest50"] = df["low"].rolling(50).min()
    df.dropna(inplace=True); return df

def prep_d1(df):
    for p in [20, 30, 50, 100, 200]:
        df[f"sma{p}"] = sma(df["close"], p)
        df[f"ema{p}"] = ema(df["close"], p)
    df["atr"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df.dropna(inplace=True); return df

# ============== STRATEGY CONFIGS ==============
STRATEGIES = [
    {
        "name": "A: Pullback SMA30 D1",
        "timeframe": "D1", "bars_needed": 800,
        "prep_fn": prep_d1, "signal_fn": sig_a,
        "params": {"sl": 2.5, "tp": 5.0, "max_hold": 90, "running": 0.15, "warmup": 200, "max_dd": 30,
                   "rs_lmin": 0, "rs_lmax": 45, "rs_smin": 0, "rs_smax": 100}
    },
    {
        "name": "B: EMA10/30 Cross H4",
        "timeframe": "H4", "bars_needed": 800,
        "prep_fn": prep_h4, "signal_fn": sig_b,
        "params": {"sl": 1.5, "tp": 3.0, "max_hold": 40, "running": 0.05, "warmup": 50, "max_dd": 30,
                   "rs_lmin": 0, "rs_lmax": 100, "rs_smin": 0, "rs_smax": 100}
    },
    {
        "name": "C: Adaptive Trend H4",
        "timeframe": "H4", "bars_needed": 800,
        "prep_fn": prep_h4, "signal_fn": sig_c,
        "params": {"sl": 2.5, "tp": 5.0, "max_hold": 50, "running": 0.05, "warmup": 50, "max_dd": 30,
                   "rs_lmin": 0, "rs_lmax": 100, "rs_smin": 0, "rs_smax": 100}
    },
    {
        "name": "D: Confluence Momentum H1",
        "timeframe": "H1", "bars_needed": 2500,
        "prep_fn": prep_h1, "signal_fn": sig_d,
        "params": {"sl": 2.0, "tp": 4.0, "max_hold": 24, "running": 0.03, "warmup": 50, "max_dd": 20,
                   "rs_lmin": 45, "rs_lmax": 75, "rs_smin": 25, "rs_smax": 55, "vol_mult": 1.1}
    },
    {
        "name": "E: NoFilter Momentum M15",
        "timeframe": "M15", "bars_needed": 12000,
        "prep_fn": prep_m15, "signal_fn": sig_e,
        "params": {"sl": 0.7, "tp": 1.8, "max_hold": 16, "running": 0.08, "warmup": 50, "max_dd": 20,
                   "rs_lmin": 35, "rs_lmax": 82, "rs_smin": 18, "rs_smax": 65, "vol_mult": 0.7}
    },
    {
        "name": "F: Turbo Scalper M15",
        "timeframe": "M15", "bars_needed": 12000,
        "prep_fn": prep_m15, "signal_fn": sig_f,
        "params": {"sl": 0.5, "tp": 2.2, "max_hold": 20, "running": 0.12, "warmup": 50, "max_dd": 25,
                   "rs_lmin": 30, "rs_lmax": 95, "rs_smin": 5, "rs_smax": 70, "vol_mult": 0.7}
    },
    {
        "name": "G: Confidence Sizing M15",
        "timeframe": "M15", "bars_needed": 12000,
        "prep_fn": prep_m15, "signal_fn": sig_g,
        "fraction_fn": confidence_g,
        "params": {"sl": 0.5, "tp": 2.2, "max_hold": 20, "running": 0.12, "warmup": 50, "max_dd": 25,
                   "vol_mult": 0.7}
    },
]

# ============== REPORT ==============
def print_comparison(results):
    print(f"\n{'='*95}")
    print(f"  KOMPARASI A-G DENGAN SPREAD ({SPREAD_POINTS} pts XAUUSDm)")
    print(f"  Modal Rp{MODAL:,} | 4 bulan | data real MT5")
    print(f"  Spread cost per trade: Rp{SPREAD_POINTS * POINT_VALUE / 4358 * MODAL:,.0f} (avg)")
    print(f"{'='*95}")

    print(f"\n  {'Strategy':<24} {'Profit':<14} {'ROI':<9} {'DD':<7} {'Trades':<8} {'WR':<6} {'PF':<7} {'Avg/hari':<14} {'Biaya Sp':<12}")
    print(f"  {'-'*24} {'-'*14} {'-'*9} {'-'*7} {'-'*8} {'-'*6} {'-'*7} {'-'*14} {'-'*12}")
    for r in sorted(results, key=lambda x: x["profit"], reverse=True):
        pm = "+" if r["profit"] > 0 else ""
        pm_d = "+" if r["avg_daily"] > 0 else ""
        print(f"  {r['name']:<24} Rp{r['profit']:<12,} ({pm}{r['roi']:>6.1f}%) "
              f"{r['dd_max']:<5}% {r['trades']:<5} {r['wr']:<4}% {r['pf']:<5} "
              f"Rp{r['avg_daily']:<10,} Rp{r['spread_total']:<9,}")
    print(f"  {'='*95}")

    print(f"\n  TARGET HARIAN:")
    print(f"  {'-'*60}")
    for r in sorted(results, key=lambda x: x["avg_daily"], reverse=True):
        n = r["name"]
        k = n[:1]
        tgt = TARGETS.get(k, 100000)
        avg = r["avg_daily"]
        pct = avg / tgt * 100
        status = "Tercapai" if avg >= tgt else f"{pct:.0f}%"
        print(f"  {n:<24} Rp{avg:<10,} /hari   target Rp{tgt:<6,}   {status}")

    print(f"\n  IMPAK SPREAD:")
    print(f"  {'-'*60}")
    for r in sorted(results, key=lambda x: x["profit"], reverse=True):
        n = r["name"]
        p = r["profit"]
        s = r["spread_total"]
        c = r["commission_total"]
        total_cost = s + c
        pct_cost = total_cost / (abs(p) + total_cost) * 100 if p != 0 or total_cost > 0 else 0
        print(f"  {n:<24} Spread Rp{s:<9,} + Komisi Rp{c:<9,} = Rp{total_cost:<9,} ({pct_cost:.1f}% dari gross)")

    print(f"\n  RANKING (by Avg Harian / Target):")
    print(f"  {'-'*60}")
    ranked = []
    for r in results:
        k = r["name"][:1]
        tgt = TARGETS.get(k, 100000)
        ratio = r["avg_daily"] / tgt
        ranked.append((r["name"], ratio, r["avg_daily"], tgt))
    ranked.sort(key=lambda x: x[1], reverse=True)
    for i, (n, ratio, avg, tgt) in enumerate(ranked, 1):
        print(f"  #{i:<2} {n:<24} {ratio:.2f}x target ({'Rp'+f'{avg:,.0f}'+'/hari'})")

def main():
    print("=" * 95)
    print(f"  BACKTEST ALL STRATEGIES (A-G) DENGAN SPREAD")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  Spread: {SPREAD_POINTS} pts XAUUSDm = Rp{SPREAD_POINTS*POINT_VALUE/4358*MODAL:,.0f}/trade (avg)")
    print("=" * 95)

    print("\n[INFO] Mengambil data M15 XAUUSDm...")
    m15 = fetch_data()
    if m15 is None:
        return
    t0, t1 = m15.index[0].date(), m15.index[-1].date()
    print(f"[INFO] Periode: {t0} — {t1} ({len(m15)} bars)")

    results = []
    for cfg in STRATEGIES:
        name = cfg["name"]
        tf = cfg["timeframe"]

        print(f"\n  --- {name} ({tf}) ---")

        if tf == "M15":
            df = m15.copy()
        elif tf == "H1":
            df = resample(m15, "1h")
        elif tf == "H4":
            df = resample(m15, "4h")
        elif tf == "D1":
            df = resample(m15, "D")

        print(f"  Data: {df.index[0].date()} — {df.index[-1].date()} ({len(df)} bars)")

        df = cfg["prep_fn"](df)
        fraction_fn = cfg.get("fraction_fn")
        result = backtest_engine(df, cfg["params"], cfg["signal_fn"], name, fraction_fn)
        results.append(result)

        pm = "+" if result["profit"] > 0 else ""
        print(f"  Profit: Rp{result['profit']:,} ({pm}{result['roi']}%) | "
              f"DD {result['dd_max']}% | {result['trades']} trades | "
              f"Rp{result['avg_daily']:,}/hari | "
              f"Spread: Rp{result['spread_total']:,}")

    print_comparison(results)

    print(f"\n{'='*95}")
    print(f"  CATATAN:")
    print(f"  - Semua backtest pake modal Rp{MODAL:,} (100% deployment)")
    print(f"  - Spread: {SPREAD_POINTS} pts XAUUSDm ($0.25 per oz)")
    print(f"  - Komisi: Rp5k/trade (D/E/F/G) dan Rp10k/trade (A/B/C)")
    print(f"  - Untuk REAL P&L: kalikan hasil dengan lot_pct/100%")
    print(f"    Contoh F (800%): profit real = hasil ini x 8")
    print(f"{'='*95}")


if __name__ == "__main__":
    main()
