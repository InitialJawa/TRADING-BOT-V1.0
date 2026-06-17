import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
MODAL = 12_000_000

# ── PARAMETER SETS ──────────────────────────────────────────────────

BASE = {
    "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 45, "rsi_long_max": 75,
    "rsi_short_min": 25, "rsi_short_max": 55,
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 4.0, "atr_trail_mult": 1.0,
    "volume_ma_period": 20, "volume_mult": 1.1,
    "max_hold_bars": 24, "lot_pct": 200, "running_pct": 0.03
}

AGGRESSIVE = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 35, "rsi_long_max": 80,
    "rsi_short_min": 20, "rsi_short_max": 65,
    "macd_fast": 8, "macd_slow": 20, "macd_signal": 7,
    "atr_period": 10, "atr_sl_mult": 1.2, "atr_tp_mult": 2.5, "atr_trail_mult": 0.8,
    "volume_ma_period": 15, "volume_mult": 0.9,
    "max_hold_bars": 36, "lot_pct": 300, "running_pct": 0.05
}

# ── STRATEGY A (D1 LONG) ────────────────────────────────────────────

def strat_a_signals(df):
    p = {"ema_fast": 9, "ema_medium": 21, "ema_slow": 50}
    df["ema9"] = df["close"].ewm(span=p["ema_fast"], adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=p["ema_medium"], adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=p["ema_slow"], adjust=False).mean()
    df["signal"] = 0
    df.loc[(df["ema9"] > df["ema21"]) & (df["close"] > df["ema50"]), "signal"] = 1
    return df

# ── STRATEGY B (H4 EMA Cross) ──────────────────────────────────────

def strat_b_signals(df4):
    p = {"ema_fast": 20, "ema_slow": 50}
    df4["ema20"] = df4["close"].ewm(span=p["ema_fast"], adjust=False).mean()
    df4["ema50"] = df4["close"].ewm(span=p["ema_slow"], adjust=False).mean()
    df4["signal"] = 0
    df4.loc[(df4["ema20"] > df4["ema50"]) & (df4["ema20"].shift(1) <= df4["ema50"].shift(1)), "signal"] = 1
    df4.loc[(df4["ema20"] < df4["ema50"]) & (df4["ema20"].shift(1) >= df4["ema50"].shift(1)), "signal"] = -1
    return df4

# ── STRATEGY C (H4 PSAR) ───────────────────────────────────────────

def strat_c_signals(df4):
    psar = 0.02
    step = 0.02
    max_step = 0.2
    high, low, close = df4["high"].values, df4["low"].values, df4["close"].values
    n = len(df4)
    af = psar
    ep = low[0]
    trend = 1
    sar = [0.0] * n; sar[0] = high[0]
    for i in range(1, n):
        if trend == 1:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            if sar[i] > low[i]: sar[i] = ep; trend = -1; af = psar; ep = high[i]
            elif sar[i] > low[i-1]: sar[i] = low[i-1]
            if high[i] > ep: ep = high[i]; af = min(af + step, max_step)
        else:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            if sar[i] < high[i]: sar[i] = ep; trend = 1; af = psar; ep = low[i]
            elif sar[i] < high[i-1]: sar[i] = high[i-1]
            if low[i] < ep: ep = low[i]; af = min(af + step, max_step)
    df4["psar"] = sar
    df4["signal"] = 0
    df4.loc[(df4["close"] > df4["psar"]) & (df4["close"].shift(1) <= df4["psar"].shift(1)), "signal"] = 1
    df4.loc[(df4["close"] < df4["psar"]) & (df4["close"].shift(1) >= df4["psar"].shift(1)), "signal"] = -1
    return df4

# ── STRATEGY D SIGNALS ─────────────────────────────────────────────

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()

def rsi_s(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def macd(s, f=12, sl=26, sg=9):
    e1 = ema(s, f); e2 = ema(s, sl)
    m = e1 - e2; return m, ema(m, sg)

def prep_df(df, p):
    df["ema9"] = ema(df["close"], p["ema_fast"])
    df["ema21"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr14"] = atr(df, p["atr_period"])
    df["rsi14"] = rsi_s(df["close"], p["rsi_period"])
    df["macd"], df["macd_signal"] = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True)
    return df

def signal_d(df, i, p):
    row = df.iloc[i]; c = row["close"]
    above_ema200 = c > row["ema200"]
    ema_bull = row["ema9"] > row["ema21"]
    rsi_ok_long = p["rsi_long_min"] <= row["rsi14"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_signal"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    if above_ema200 and ema_bull and rsi_ok_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema9"] < row["ema21"]
    rsi_ok_short = p["rsi_short_min"] <= row["rsi14"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_signal"]
    if not above_ema200 and ema_bear and rsi_ok_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def backtest_d(df, p):
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail_activated = False

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr14"].iloc[i]
        ema9 = df["ema9"].iloc[i]; ema21 = df["ema21"].iloc[i]
        sig = signal_d(df, i, p)

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
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
                    trail_dist = a * p["atr_trail_mult"]
                    if not trail_activated and (c - entry_price) >= trail_dist:
                        trail_activated = True; sl_price = entry_price + trail_dist * 0.3
                    if trail_activated:
                        new_sl = c - trail_dist * 0.5; sl_price = max(sl_price, new_sl)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit_here = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit_here = True
                elif ema9 > ema21: profit = (entry_price - c) / entry_price * modal; exit_here = True
                elif bars_held >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit_here = True
                else:
                    trail_dist = a * p["atr_trail_mult"]
                    if not trail_activated and (entry_price - c) >= trail_dist:
                        trail_activated = True; sl_price = entry_price - trail_dist * 0.3
                    if trail_activated:
                        new_sl = c + trail_dist * 0.5; sl_price = min(sl_price, new_sl)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit_here:
                modal += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars_held,
                    "profit": round(profit), "modal": round(modal),
                    "exit_price": round(c, 2), "entry_price": round(entry_price, 2)})
                in_trade = False; posisi = None

    return modal, dd_max, trades

# ── BACKTEST GENERIC (for A/B/C) ────────────────────────────────────

def backtest_generic(df, strat_func, period_hours, modal_awal, allow_short=False):
    """Simple backtest for any strategy that sets df['signal'] = 1 (long), -1 (short), 0 (hold)"""
    df = strat_func(df.copy())
    modal = float(modal_awal); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None; entry_price = 0.0; entry_idx = 0

    for i in range(1, len(df)):
        c = df["close"].iloc[i]
        sig = df["signal"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig == 1 or (sig == -1 and allow_short):
                posisi = "BUY" if sig == 1 else "SELL"
                entry_price = c; entry_idx = i; modal -= 5000; in_trade = True
        else:
            bars = i - entry_idx
            exit_signal = False
            long_exit = posisi == "BUY" and (sig != 1 or bars >= 50)
            short_exit = posisi == "SELL" and (sig != -1 or bars >= 50)
            if long_exit or short_exit or bars >= period_hours // period_hours:
                profit = (c - entry_price) / entry_price * modal if posisi == "BUY" else (entry_price - c) / entry_price * modal
                modal += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    return modal, dd_max, trades

# ── MAIN ────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  BACKTEST PERBANDINGAN — Strategy D (STANDARD vs AGGRESSIVE) vs A/B/C")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    # ── DATA ────────────────────────────────────────────────────────
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("[ERROR] MT5 gagal")
        return
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 2900)
    mt5.shutdown()
    if rates is None or len(rates) < 200:
        print("[ERROR] Data tidak cukup"); return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    t0, t1 = df.index[0].date(), df.index[-1].date()
    print(f"\n  Periode: {t0} — {t1} ({len(df)} bars H1 = {len(df)//24:.0f} hari)")

    # ── Resample H4 untuk B dan C ──────────────────────────────────
    df4 = df.resample("4h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "tick_volume": "sum", "spread": "mean", "real_volume": "sum"
    }).dropna()

    # ── RUN ─────────────────────────────────────────────────────────
    results = []

    # Str D Standard
    print("\n[1/5] Strategy D STANDARD...")
    d1 = prep_df(df.copy(), BASE)
    m1, dd1, t1_list = backtest_d(d1, BASE)
    results.append(("D STANDARD", BASE["lot_pct"], m1, dd1, t1_list, len(d1)))

    # Str D Aggressive
    print("[2/5] Strategy D AGGRESSIVE...")
    d2 = prep_df(df.copy(), AGGRESSIVE)
    m2, dd2, t2_list = backtest_d(d2, AGGRESSIVE)
    results.append(("D AGGRESSIVE", AGGRESSIVE["lot_pct"], m2, dd2, t2_list, len(d2)))

    # Str A (D1)
    print("[3/5] Strategy A (D1 LONG)...")
    df_daily = df.resample("D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    res_a, dd_a, ta = backtest_generic(df_daily.copy(), strat_a_signals, 1, MODAL, allow_short=False)
    results.append(("A (D1 LONG)", 100, res_a, dd_a, ta, len(df_daily)))

    # Str B (H4)
    print("[4/5] Strategy B (H4 EMA Cross)...")
    res_b, dd_b, tb = backtest_generic(df4.copy(), strat_b_signals, 4*6, MODAL, allow_short=True)
    results.append(("B (H4 EMA)", 100, res_b, dd_b, tb, len(df4)))

    # Str C (H4 PSAR)
    print("[5/5] Strategy C (H4 PSAR)...")
    res_c, dd_c, tc = backtest_generic(df4.copy(), strat_c_signals, 4*6, MODAL, allow_short=True)
    results.append(("C (H4 PSAR)", 100, res_c, dd_c, tc, len(df4)))

    # ── PRINT ───────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  HASIL LENGKAP — {t0} — {t1} ({len(df)//24} hari)")
    print(f"{'='*72}")
    print(f"  {'Strategi':<20} {'Modal Akhir':<15} {'Profit':<12} {'ROI':<10} {'DD':<8} {'Trades':<8} {'WR':<8} {'PF':<8} {'Hold'}")
    print(f"  {'-'*95}")

    rows = []
    for name, lp, m_akhir, dd, trades, total_bars in results:
        win = [t for t in trades if t["profit"] > 0]
        loss = [t for t in trades if t["profit"] < 0]
        pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1)
        roi = (m_akhir - MODAL) / MODAL * 100
        wr = len(win) / max(len(trades), 1) * 100
        avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
        monthly_tr = len(trades) / max((total_bars / 24 / 30), 1)

        hold_label = f"{avg_hold:.0f}h" if avg_hold < 24 else f"{avg_hold/24:.1f}d"
        rows.append((name, m_akhir, m_akhir - MODAL, roi, dd, len(trades), wr, pf, hold_label, monthly_tr, avg_hold))

        profit_str = f"+{m_akhir-MODAL:,.0f}" if m_akhir >= MODAL else f"{m_akhir-MODAL:,.0f}"
        print(f"  {name:<20} Rp{m_akhir:>10,.0f}  {profit_str:>10}  {roi:>+6.1f}%  {dd:>5.1f}%  {len(trades):>3}   {wr:>5.1f}%  {pf:>5.2f}  {hold_label:>8}")

    print(f"\n{'='*72}")
    print(f"  PERBANDINGAN DETAIL")
    print(f"{'='*72}")

    # Find best in each category
    best_roi = max(rows, key=lambda r: r[3])
    best_freq = max(rows, key=lambda r: r[-2])
    best_pf = max(rows, key=lambda r: r[7])
    best_dd = min(rows, key=lambda r: r[4])

    print(f"\n  >> ROI TERTINGGI: {best_roi[0]} ({best_roi[3]:+.1f}%)")
    print(f"  >> FREKUENSI: {best_freq[0]} ({best_freq[-2]:.0f} trades/bulan)")
    print(f"  >> DD TERENDAH: {best_dd[0]} ({best_dd[4]:.1f}%)")
    print(f"  >> PROFIT FACTOR: {best_pf[0]} ({best_pf[7]:.2f})")

    # D Aggressive vs others
    for row in rows:
        if "AGGRESSIVE" in row[0]:
            d_agg = row
    for row in rows:
        if row[0] == d_agg[0]: continue
        roi_diff = d_agg[3] - row[3]
        trade_diff = d_agg[5] - row[5]
        label = "> Unggul" if roi_diff > 0 else "< Kalah"
        print(f"\n  D AGGRESSIVE vs {row[0]}:")
        print(f"    ROI: +{d_agg[3]:.1f}% vs {row[3]:+.1f}% ({label})")
        print(f"    Trades: {d_agg[5]} vs {row[5]} ({'+' if trade_diff>0 else ''}{trade_diff})")
        print(f"    DD: {d_agg[4]:.1f}% vs {row[4]:.1f}% {'(lebih aman)' if d_agg[4] < row[4] else '(lebih riskan)'}")

    print(f"\n{'='*72}")
    print(f"  KESIMPULAN")
    print(f"{'='*72}")

    d_std = [r for r in rows if "STANDARD" in r[0]][0]
    d_agg = [r for r in rows if "AGGRESSIVE" in r[0]][0]

    if d_agg[3] > d_std[3] and d_agg[4] < 12:
        print(f"  >> D AGGRESSIVE LEBIH UNGGUL: ROI {d_agg[3]:+.1f}% vs {d_std[3]:+.1f}%")
        print(f"     dengan DD {d_agg[4]:.1f}% (masih aman)")
    elif d_agg[5] > d_std[5] * 1.5:
        print(f"  >> D AGGRESSIVE LEBIH AGGRESIF: {d_agg[5]} trades vs {d_std[5]} trades")
        print(f"     Tapi ROI {d_agg[3]:+.1f}% vs {d_std[3]:+.1f}%")
    else:
        print(f"  >> D STANDARD masih lebih baik secara risk-adjusted")
        print(f"     Tapi D AGGRESIF punya keunggulan di frekuensi trade")

    best_overall = max(rows, key=lambda r: r[3] / max(r[4], 0.1) * min(r[7], 10))
    print(f"  >> BEST OVERALL (ROI/DD*PF): {best_overall[0]}")

    print(f"\n{'='*72}")
    print(f"  SEEDING KE AI MANAGER")
    print(f"{'='*72}")
    state = StateManager("data/state.db")
    for name, lp, m_akhir, dd, trades, total_bars in results:
        short = name.lower().replace(" ", "_")
        label = f"strategy_d_{short}" if "strategy_d" not in short else short
        win = [t for t in trades if t["profit"] > 0]
        loss = [t for t in trades if t["profit"] < 0]
        pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1)
        roi = (m_akhir - MODAL) / MODAL * 100
        state.log_backtest(label, "PASS" if dd < 15 and pf > 1.5 else "FAILED", {
            "roi": round(roi, 2), "dd": round(dd, 2), "pf": round(pf, 2),
            "trades": len(trades), "win_rate": round(len(win) / max(len(trades), 1) * 100, 1)
        })
    state.upsert_strategy("strategy_d_h1_aggressive", "ACTIVE")
    print("  [OK] All results saved to AI Manager database")

    print(f"\n{'='*72}")
    print(f"  SELESAI — Cek AI Manager untuk dashboard")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()
