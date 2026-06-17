import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
TARGET_HARIAN = 100_000

# ── E VARIANTS ──────────────────────────────────────────────────────

VARIANTS = {}

# E1: M15 EMA5/13, RSI medium, fast MACD
VARIANTS["E1 M15 Turbo"] = {
    "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "tf_minutes": 15,
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 40, "rsi_long_max": 78,
    "rsi_short_min": 22, "rsi_short_max": 60,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 14, "atr_sl_mult": 0.8, "atr_tp_mult": 2.0, "atr_trail_mult": 0.5,
    "volume_ma_period": 20, "volume_mult": 0.9,
    "max_hold_bars": 16, "lot_pct": 500, "running_pct": 0.08
}

# E2: M15 EMA8/21, wider RSI, standard MACD
VARIANTS["E2 M15 Wide"] = {
    "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "tf_minutes": 15,
    "ema_fast": 8, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 35, "rsi_long_max": 80,
    "rsi_short_min": 20, "rsi_short_max": 65,
    "macd_fast": 6, "macd_slow": 14, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 1.0, "atr_tp_mult": 2.4, "atr_trail_mult": 0.6,
    "volume_ma_period": 15, "volume_mult": 0.8,
    "max_hold_bars": 12, "lot_pct": 500, "running_pct": 0.08
}

# E3: M5 super fast scalper
VARIANTS["E3 M5 Scalper"] = {
    "tf": mt5.TIMEFRAME_M5, "tf_name": "M5", "tf_minutes": 5,
    "ema_fast": 3, "ema_medium": 8, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 10,
    "rsi_long_min": 40, "rsi_long_max": 80,
    "rsi_short_min": 20, "rsi_short_max": 60,
    "macd_fast": 3, "macd_slow": 10, "macd_signal": 3,
    "atr_period": 10, "atr_sl_mult": 0.6, "atr_tp_mult": 1.5, "atr_trail_mult": 0.4,
    "volume_ma_period": 10, "volume_mult": 0.8,
    "max_hold_bars": 12, "lot_pct": 600, "running_pct": 0.10,
    "no_ema200_filter": True
}

# E4: M15 pure momentum (no EMA200 filter)
VARIANTS["E4 M15 NoFilter"] = {
    "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "tf_minutes": 15,
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 35, "rsi_long_max": 82,
    "rsi_short_min": 18, "rsi_short_max": 65,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 0.7, "atr_tp_mult": 1.8, "atr_trail_mult": 0.4,
    "volume_ma_period": 15, "volume_mult": 0.7,
    "max_hold_bars": 16, "lot_pct": 600, "running_pct": 0.08,
    "no_ema200_filter": True
}

# E5: M15 session-only (trade 07:00-16:00 UTC = siang WIB)
VARIANTS["E5 M15 Session"] = {
    "tf": mt5.TIMEFRAME_M15, "tf_name": "M15", "tf_minutes": 15,
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 40, "rsi_long_max": 75,
    "rsi_short_min": 25, "rsi_short_max": 60,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 0.9, "atr_tp_mult": 2.2, "atr_trail_mult": 0.5,
    "volume_ma_period": 15, "volume_mult": 0.9,
    "max_hold_bars": 12, "lot_pct": 500, "running_pct": 0.08,
    "session_start": 7, "session_end": 16  # UTC
}

# ── HELPERS ─────────────────────────────────────────────────────────

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def calc_atr(df, p):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()

def calc_rsi(s, p):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def calc_macd(s, f, sl, sg):
    e1 = ema(s, f); e2 = ema(s, sl); m = e1 - e2; return m, ema(m, sg)

def prep_df(df, p):
    df["ema_fast"] = ema(df["close"], p["ema_fast"])
    df["ema_med"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr"] = calc_atr(df, p["atr_period"])
    df["rsi"] = calc_rsi(df["close"], p["rsi_period"])
    df["macd"], df["macd_sig"] = calc_macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True); return df

def signal_e(df, i, p):
    row = df.iloc[i]; c = row["close"]
    no_filter = p.get("no_ema200_filter", False)
    above_200 = c > row["ema200"]

    if "session_start" in p:
        hour = df.index[i].hour
        if not (p["session_start"] <= hour < p["session_end"]):
            return "HOLD"

    ema_bull = row["ema_fast"] > row["ema_med"]
    rsi_long = p["rsi_long_min"] <= row["rsi"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_sig"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]

    if (above_200 or no_filter) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"

    ema_bear = row["ema_fast"] < row["ema_med"]
    rsi_short = p["rsi_short_min"] <= row["rsi"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_sig"]

    if (not above_200 or no_filter) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def backtest_e(df, p):
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    # Track daily profit
    daily_profit = {}; current_day = None; day_pnl = 0.0

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef = df["ema_fast"].iloc[i]; em = df["ema_med"].iloc[i]
        sig = signal_e(df, i, p)
        day = df.index[i].date()

        # Day tracking
        if current_day is None: current_day = day
        if day != current_day:
            daily_profit[current_day] = day_pnl
            current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail = False; modal -= 5000; in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit = True
                elif c >= tp_price: profit = (min(c, tp_price) - entry_price) / entry_price * modal; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - min(c, tp_price)) / entry_price * modal; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit:
                modal += profit
                day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    # Last day
    if current_day: daily_profit[current_day] = day_pnl
    return modal, dd_max, trades, daily_profit

# ── MAIN ────────────────────────────────────────────────────────────

def fetch_data(timeframe, bars):
    if not mt5.initialize(): return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)
    mt5.shutdown()
    if rates is None: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df

def main():
    print("=" * 72)
    print(f"  STRATEGY E — Mencari target Rp{TARGET_HARIAN:,}/hari dengan modal Rp{MODAL:,}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    # Fetch data for each TF
    data_cache = {}
    v_keys = list(VARIANTS.keys())
    tfs_needed = set()
    for vn in v_keys:
        v = VARIANTS[vn]
        tfs_needed.add((v["tf_name"], v["tf"], v["tf_minutes"]))

    for tf_name, tf, tf_min in tfs_needed:
        # 4 months max
        max_bars = int(120 * 24 * 60 / tf_min)
        print(f"\n[FETCH] {tf_name} x{max_bars}")
        df = fetch_data(tf, max_bars + 200)
        if df is None or len(df) < 200:
            print(f"  GAGAL ambil data {tf_name}")
            continue
        print(f"  {df.index[0].date()} — {df.index[-1].date()} ({len(df)} bars)")
        data_cache[tf_name] = df

    if not data_cache:
        print("\n[ERROR] Tidak ada data"); return

    # Run variants
    print(f"\n{'='*72}")
    print(f"  BACKTEST STRATEGY E")
    print(f"{'='*72}")

    results = []
    for vn in v_keys:
        v = VARIANTS[vn]; tf_name = v["tf_name"]
        if tf_name not in data_cache:
            print(f"\n  [SKIP] {vn} — data {tf_name} tidak tersedia"); continue

        df = data_cache[tf_name].copy()
        df = prep_df(df, v)
        print(f"\n  [{vn}] running {len(df)} bars...")
        modal_akhir, dd_max, trades, daily_pnl = backtest_e(df, v)

        win = [t for t in trades if t["profit"] > 0]
        loss = [t for t in trades if t["profit"] < 0]
        pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1)
        roi = (modal_akhir - MODAL) / MODAL * 100
        avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
        days_traded = len(daily_pnl)
        avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
        days_above_target = sum(1 for p in daily_pnl.values() if p >= TARGET_HARIAN)

        results.append((vn, modal_akhir, dd_max, trades, roi, pf, avg_hold, daily_pnl, avg_daily, days_above_target, days_traded, win, loss))

    # Print comparison
    print(f"\n{'='*72}")
    print(f"  PERBANDINGAN STRATEGY E — target Rp{TARGET_HARIAN:,}/hari")
    print(f"{'='*72}")
    print(f"  {'Variant':<20} {'ROI':<10} {'DD':<8} {'Trades':<8} {'PF':<8} {'Hold':<8} {'Avg/hari':<14} {'>=100k':<10} {'WR':<8}")
    print(f"  {'-'*90}")

    best_for_target = None; best_daily_val = 0
    for r in results:
        vn, modal_akhir, dd_max, trades, roi, pf, avg_hold, daily_pnl, avg_daily, days_above, days_tot, win, loss = r
        wr = len(win) / max(len(trades), 1) * 100
        hold_label = f"{avg_hold:.0f}m" if avg_hold < 60 else f"{avg_hold/60:.1f}h"
        avg_daily_str = f"Rp{avg_daily:>8,.0f}" if avg_daily >= 0 else f"-Rp{abs(avg_daily):>7,.0f}"
        print(f"  {vn:<20} {roi:>+7.1f}%  {dd_max:>5.1f}%  {len(trades):>4}   {pf:>5.2f}  {hold_label:<6} {avg_daily_str}  {days_above:>2}/{days_tot:<4} {wr:>5.1f}%")

        if avg_daily > best_daily_val:
            best_daily_val = avg_daily
            best_for_target = r

    print(f"\n{'='*72}")
    if best_for_target:
        vn, modal_akhir, dd_max, trades, roi, pf, avg_hold, daily_pnl, avg_daily, days_above, days_tot, win, loss = best_for_target
        print(f"  BEST: {vn}")
        print(f"  ROI: {roi:+.2f}% | DD: {dd_max:.1f}% | PF: {pf:.2f} | Trades: {len(trades)}")
        print(f"  Rata-rata/hari: Rp{avg_daily:,.0f}")
        print(f"  Hari >= Rp100k: {days_above}/{days_tot} ({days_above/max(days_tot,1)*100:.0f}%)")

        # Show daily distribution
        print(f"\n  DISTRIBUSI HARIAN (top/bottom days):")
        sorted_days = sorted(daily_pnl.items(), key=lambda x: x[1], reverse=True)
        print(f"  Top 5 hari terbaik:")
        for d, p in sorted_days[:5]:
            mark = " *** " if p >= TARGET_HARIAN else ""
            print(f"    {d}: Rp{p:+,.0f}{mark}")
        print(f"  Bottom 5 hari terburuk:")
        for d, p in sorted_days[-5:]:
            print(f"    {d}: Rp{p:+,.0f}")

        if avg_daily >= TARGET_HARIAN:
            print(f"\n  >>> TERCAPAI! Rata-rata Rp{avg_daily:,.0f}/hari >= target Rp{TARGET_HARIAN:,}/hari")
        else:
            need = TARGET_HARIAN - avg_daily
            mult = TARGET_HARIAN / max(avg_daily, 1)
            print(f"\n  >>> BELUM TERCAPAI. Kurang Rp{need:,.0f}/hari ({mult:.1f}x dari sekarang)")
            print(f"      Butuh lot {(500*mult):.0f}% atau parameter lebih agresif")

    # Also show D Aggressive for comparison
    print(f"\n{'='*72}")
    print(f"  SEEDING KE AI MANAGER")
    print(f"{'='*72}")
    state = StateManager("data/state.db")

    for r in results:
        vn, modal_akhir, dd_max, trades, roi, pf, avg_hold, daily_pnl, avg_daily, days_above, days_tot, win, loss = r
        label = "strategy_e_" + vn.lower().replace(" ", "_")
        state.log_backtest(label, "PASS" if dd_max < 15 and pf > 1.5 else "FAILED", {
            "roi": round(roi, 2), "dd": round(dd_max, 2), "pf": round(pf, 2),
            "trades": len(trades), "avg_daily_rupiah": round(avg_daily, 0),
            "days_above_target": days_above, "total_days": days_tot
        })
    state.upsert_strategy("strategy_e", "ACTIVE")
    print("  [OK] Results saved")

    print(f"\n{'='*72}")
    if best_for_target and best_for_target[8] >= TARGET_HARIAN:
        print(f"  STRATEGY E — TARGET TERCAPAI! Rp{best_for_target[8]:,.0f}/hari")
    else:
        print(f"  STRATEGY E — Perlu optimasi lanjutan")
    print(f"{'='*72}")

if __name__ == "__main__":
    main()
