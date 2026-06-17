import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
TARGET_HARIAN = 300_000
SPREAD_POINTS = 25
POINT_VALUE = 0.01

PARAMS = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 30, "rsi_long_max": 95,
    "rsi_short_min": 5, "rsi_short_max": 70,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 0.5, "atr_tp_mult": 2.2, "atr_trail_mult": 0.3,
    "volume_ma_period": 15, "volume_mult": 0.7,
    "max_hold_bars": 20, "lot_pct": 800, "running_pct": 0.12,
    "no_ema200_filter": True, "no_macd_filter": True
}


def try_mt5_data(bars=12000):
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(): return None
        mt5.symbol_select(SYMBOL, True)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
        mt5.shutdown()
        if rates is None or len(rates) < 500: return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True); return df
    except: return None


def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()
def atr(df, p=10):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))
def macd(s, f=5, sl=13, sg=5):
    e1 = ema(s, f); e2 = ema(s, sl); m = e1 - e2; return m, ema(m, sg)

def prep(df):
    p = PARAMS
    df["ema5"] = ema(df["close"], p["ema_fast"])
    df["ema13"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr"] = atr(df, p["atr_period"])
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    df["macd"], df["macd_sig"] = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True); return df

def signal_f(df, i):
    p = PARAMS; row = df.iloc[i]; c = row["close"]
    no_ema = p["no_ema200_filter"]; no_macd = p["no_macd_filter"]
    ema_bull = row["ema5"] > row["ema13"]
    above_200 = c > row["ema200"]
    rsi_long = p["rsi_long_min"] <= row["rsi"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_sig"] or no_macd
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    if (above_200 or no_ema) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_short = p["rsi_short_min"] <= row["rsi"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_sig"] or no_macd
    if (not above_200 or no_ema) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def backtest(df):
    p = PARAMS; modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef = df["ema5"].iloc[i]; em = df["ema13"].iloc[i]
        sig = signal_f(df, i); day = df.index[i].date()

        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail = False; modal -= 5000
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost; in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl


def main():
    print("=" * 70)
    print(f"  STRATEGY F — M15 Turbo Scalper")
    print(f"  Target Rp{TARGET_HARIAN:,}/hari | Modal Rp{MODAL:,}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    print("\n[INFO] Mengambil data M15 XAUUSDm (4 bulan)...")
    df = try_mt5_data(12000)
    if df is None or len(df) < 500:
        print("[ERROR] Data tidak cukup"); return

    t0, t1 = df.index[0].date(), df.index[-1].date()
    days = len(df) // (24 * 4)
    print(f"[INFO] Periode: {t0} — {t1} ({len(df)} bars = {days} hari)")

    df = prep(df)
    modal_akhir, dd_max, trades, daily_pnl = backtest(df)

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    roi = (modal_akhir - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    days_above = sum(1 for p in daily_pnl.values() if p >= TARGET_HARIAN)

    print(f"\n  {'='*70}")
    print(f"  HASIL STRATEGY F")
    print(f"  {'='*70}")
    print(f"  Modal Awal:     Rp{MODAL:,.0f}")
    print(f"  Modal Akhir:    Rp{modal_akhir:,.0f}")
    print(f"  Profit:         Rp{modal_akhir - MODAL:+,.0f}")
    print(f"  ROI:            {roi:+.2f}%")
    print(f"  Max DD:         {dd_max:.1f}%")
    print(f"  Trades:         {len(trades)} ({len(win)}W / {len(loss)}L)")
    print(f"  Win Rate:       {len(win)/max(len(trades),1)*100:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  Avg Hold:       {avg_hold:.0f} bar ({avg_hold*15:.0f} menit)")
    print(f"  Trades/hari:    {len(trades)/max(len(daily_pnl),1):.1f}")

    print(f"\n  {'='*70}")
    print(f"  TARGET Rp{TARGET_HARIAN:,}/hari")
    print(f"  {'='*70}")
    print(f"  Rata-rata/hari: Rp{avg_daily:,.0f}")
    print(f"  Hari >= Rp300k: {days_above}/{len(daily_pnl)} ({days_above/max(len(daily_pnl),1)*100:.0f}%)")
    status = "TERCAPAI" if avg_daily >= TARGET_HARIAN else f"{(avg_daily/TARGET_HARIAN)*100:.0f}%"
    print(f"  >>> TARGET: {status}")

    print(f"\n  {'='*70}")
    print(f"  PERBANDINGAN D / E / F")
    print(f"  {'='*70}")
    print(f"  {'Metric':<20} {'F (M15)':<15} {'E (M15)':<15} {'D (H1)':<15}")
    print(f"  {'-'*65}")
    print(f"  {'ROI':<20} {f'+{roi:.1f}%':<15} {'+195.0%':<15} {'+46.9%':<15}")
    print(f"  {'Max DD':<20} {f'{dd_max:.1f}%':<15} {'3.5%':<15} {'3.5%':<15}")
    print(f"  {'Avg/hari':<20} {'Rp'+f'{avg_daily:,.0f}':<15} {'Rp199,465':<15} {'~Rp94k':<15}")
    print(f"  {'Target':<20} {'Rp300k':<15} {'Rp100k':<15} {'Rp100k':<15}")
    print(f"  {'Tercapai':<20} {'YA' if avg_daily>=TARGET_HARIAN else 'TIDAK':<15} {'YA':<15} {'~94%':<15}")
    print(f"  {'Trades':<20} {f'{len(trades)}':<15} {'1702':<15} {'103':<15}")
    print(f"  {'Hold':<20} {f'{avg_hold*15:.0f}m':<15} {'53m':<15} {'9 jam':<15}")

    print(f"\n  >>> Rp300k/HARI: {'TERCAPAI' if avg_daily >= TARGET_HARIAN else 'BELUM'}")

    print(f"\n  {'='*70}")
    print(f"  SEEDING AI MANAGER")
    print(f"  {'='*70}")
    state = StateManager("data/state.db")
    state.upsert_metric("running_modal", round(modal_akhir, 2))
    state.upsert_metric("strategy_f_avg_daily", round(avg_daily, 0))
    state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
    state.upsert_strategy("strategy_f_m15", "ACTIVE")
    state.log_backtest("strategy_f_m15", "PASS" if dd_max < 12 and pf > 1.5 else "FAILED", {
        "roi": round(roi, 2), "dd": round(dd_max, 2), "pf": round(pf, 2),
        "trades": len(trades), "avg_daily_rupiah": round(avg_daily, 0),
        "days_above_300k": days_above, "total_days": len(daily_pnl)
    })
    print(f"  [OK] Strategy F saved")

    print(f"\n  Jalankan live: python scripts/jalankan_strat_f.py")


if __name__ == "__main__":
    main()
