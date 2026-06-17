import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
TARGET_HARIAN = 150_000
SPREAD_POINTS = 280
POINT_VALUE = 0.01

CONF_SIZING = [
    (0, 2, 1.0),
    (3, 4, 1.5),
    (5, 7, 2.0),
]

def try_mt5_data(bars=3000):
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(): return None, None
        mt5.symbol_select(SYMBOL, True)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars)
        rates_h4 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, bars // 4)
        mt5.shutdown()
        if rates is None or len(rates) < 200: return None, None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        if rates_h4 is not None:
            dh4 = pd.DataFrame(rates_h4)
            dh4["time"] = pd.to_datetime(dh4["time"], unit="s")
            dh4.set_index("time", inplace=True)
        else: dh4 = None
        return df, dh4
    except: return None, None

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))
def bb(df, p=20, std=2):
    m = df["close"].rolling(p).mean(); s = df["close"].rolling(p).std()
    return m + std * s, m, m - std * s

def prep(df, dh4):
    p = {
        "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
        "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
    }
    df["ema9"] = ema(df["close"], p["ema_fast"])
    df["ema21"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr"] = atr(df, p["atr_period"])
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    bbu, bbm, bbl = bb(df, 20, 2)
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour

    if dh4 is not None and len(dh4) > 50:
        dh4["ema9"] = ema(dh4["close"], 9)
        dh4["ema21"] = ema(dh4["close"], 21)
        dh4["h4_trend"] = np.where(dh4["ema9"] > dh4["ema21"], "UP", "DOWN")
        dh4.dropna(inplace=True)
        h4_trend_series = dh4["h4_trend"].resample("1h").ffill()
        df["h4_trend"] = h4_trend_series.reindex(df.index, method="ffill")
    else:
        df["h4_trend"] = "NEUTRAL"

    df.dropna(inplace=True)
    return df

def confidence(row):
    s = 0
    bull = row["ema9"] > row["ema21"]
    h4 = row["h4_trend"]
    if (bull and h4 == "UP") or (not bull and h4 == "DOWN"):
        s += 2
    if row["squeeze"]:
        s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2:
        s += 1
    if bull and row["rsi"] > 75:
        s += 1
    if not bull and row["rsi"] < 25:
        s += 1
    if 7 <= row["hour_utc"] < 14:
        s += 1
    c = row["close"]
    if (bull and c > row["ema200"]) or (not bull and c < row["ema200"]):
        s += 1
    return s

def get_fraction(conf):
    for lo, hi, frac in CONF_SIZING:
        if lo <= conf <= hi:
            return frac
    return 1.0

def signal_h(df, i):
    row = df.iloc[i]
    ema_bull = row["ema9"] > row["ema21"]
    rsi_long = 40 <= row["rsi"] <= 80
    vol_ok = row["tick_volume"] > row["vol_ma"] * 0.8
    if ema_bull and rsi_long and vol_ok:
        return "BUY"
    ema_bear = row["ema9"] < row["ema21"]
    rsi_short = 20 <= row["rsi"] <= 60
    if ema_bear and rsi_short and vol_ok:
        return "SELL"
    return "HOLD"

def backtest(df):
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0; modal_at_entry = 0.0

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef = df["ema9"].iloc[i]; em = df["ema21"].iloc[i]
        sig = signal_h(df, i); day = df.index[i].date()

        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 15: in_trade = False; posisi = None; continue

        conf = confidence(df.iloc[i])
        frac = get_fraction(conf)

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * 1.5 if sig == "BUY" else c + a * 1.5
                tp_price = c + a * 3.0 if sig == "BUY" else c - a * 3.0
                trail = False
                modal -= 5000 * frac
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost * frac
                modal_at_entry = modal
                trade_frac = frac
                in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif bars >= 24: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                else:
                    td = a * 0.5
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * 0.05
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                elif bars >= 24: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                else:
                    td = a * 0.5
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * 0.05

            if exit:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal), "conf": conf, "frac": trade_frac})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl

def main():
    print("=" * 70)
    print(f"  STRATEGY H — H1 Confidence Sizing (spread {SPREAD_POINTS} pts)")
    print(f"  Target Rp{TARGET_HARIAN:,}/hari | Modal Rp{MODAL:,}")
    print(f"  Sizing: conf 0-2=1.0x, 3-4=1.5x, 5-7=2.0x")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    print("\n[INFO] Mengambil data H1 + H4 XAUUSDm (max 4 bulan)...")
    df, dh4 = try_mt5_data(3000)
    if df is None or len(df) < 200:
        print("[ERROR] Data tidak cukup"); return

    t0, t1 = df.index[0].date(), df.index[-1].date()
    days = len(df) // 24
    print(f"[INFO] Periode: {t0} — {t1} ({len(df)} bars = {days} hari)")

    df = prep(df, dh4)
    modal_akhir, dd_max, trades, daily_pnl = backtest(df)

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    roi = (modal_akhir - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    days_above = sum(1 for p in daily_pnl.values() if p >= TARGET_HARIAN)
    avg_conf = np.mean([t["conf"] for t in trades]) if trades else 0
    avg_frac = np.mean([t["frac"] for t in trades]) if trades else 0

    conf_dist = {}
    for t in trades:
        conf_dist[t["conf"]] = conf_dist.get(t["conf"], 0) + 1

    print(f"\n  {'='*70}")
    print(f"  HASIL STRATEGY H (spread {SPREAD_POINTS} pts)")
    print(f"  {'='*70}")
    print(f"  Modal Awal:     Rp{MODAL:,.0f}")
    print(f"  Modal Akhir:    Rp{modal_akhir:,.0f}")
    print(f"  Profit:         Rp{modal_akhir - MODAL:+,.0f}")
    print(f"  ROI:            {roi:+.2f}%")
    print(f"  Max DD:         {dd_max:.1f}%")
    print(f"  Trades:         {len(trades)} ({len(win)}W / {len(loss)}L)")
    print(f"  Win Rate:       {len(win)/max(len(trades),1)*100:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  Avg Hold:       {avg_hold:.0f} bar ({avg_hold:.0f} jam)")
    print(f"  Trades/hari:    {len(trades)/max(len(daily_pnl),1):.1f}")
    print(f"  Avg Conf:       {avg_conf:.1f}")
    print(f"  Avg Frac:       {avg_frac:.2f}x")
    print(f"  Conf Dist:      {dict(sorted(conf_dist.items()))}")

    print(f"\n  {'='*70}")
    print(f"  TARGET Rp{TARGET_HARIAN:,}/hari")
    print(f"  {'='*70}")
    print(f"  Rata-rata/hari: Rp{avg_daily:,.0f}")
    print(f"  Hari >= Rp150k: {days_above}/{len(daily_pnl)} ({days_above/max(len(daily_pnl),1)*100:.0f}%)")
    total_profit = modal_akhir - MODAL
    print(f"  Proyeksi/bulan (22hr): Rp{avg_daily * 22:,.0f}")
    status = "TERCAPAI" if avg_daily >= TARGET_HARIAN else f"{(avg_daily/TARGET_HARIAN)*100:.0f}%"
    print(f"  >>> TARGET: {status}")

    print(f"\n  {'='*70}")
    print(f"  PERBANDINGAN D vs H")
    print(f"  {'='*70}")
    print(f"  {'Metric':<20} {'H (Confidence)':<17} {'D (baseline)':<17}")
    print(f"  {'-'*54}")
    print(f"  {'ROI':<20} {f'+{roi:.1f}%':<17} {'+35.8%':<17}")
    print(f"  {'Max DD':<20} {f'{dd_max:.1f}%':<17} {'4.1%':<17}")
    print(f"  {'Avg/hari':<20} {'Rp'+f'{avg_daily:,.0f}':<17} {'Rp34,000':<17}")
    print(f"  {'Trades':<20} {f'{len(trades)}':<17} {'82':<17}")

    print(f"\n  {'='*70}")
    print(f"  SEEDING AI MANAGER")
    print(f"  {'='*70}")
    state = StateManager("data/state.db")
    state.upsert_metric("running_modal", round(modal_akhir, 2))
    state.upsert_metric("strategy_h_avg_daily", round(avg_daily, 0))
    state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
    state.upsert_strategy("strategy_h_h1", "ACTIVE")
    state.log_backtest("strategy_h_h1", "PASS" if dd_max < 12 and pf > 1.5 else "FAILED", {
        "roi": round(roi, 2), "dd": round(dd_max, 2), "pf": round(pf, 2),
        "trades": len(trades), "avg_daily_rupiah": round(avg_daily, 0),
        "days_above_150k": days_above, "total_days": len(daily_pnl),
        "avg_conf": round(avg_conf, 1), "avg_frac": round(avg_frac, 2)
    })
    print(f"  [OK] Strategy H saved")

    print(f"\n  {'='*70}")
    print(f"  Jalankan live: python scripts/jalankan_strat_h.py")
    print(f"  {'='*70}")

if __name__ == "__main__":
    main()
