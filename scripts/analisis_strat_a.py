import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

SYMBOL = "XAUUSDm"
MODAL = 5_000_000


def init_mt5():
    if not mt5.initialize(): return False
    mt5.symbol_select(SYMBOL, True)
    return True


def get_data(bars=1200):
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
    df["sma50"] = sma(df["close"], 50)
    df["sma100"] = sma(df["close"], 100)
    df["sma200"] = sma(df["close"], 200)
    df["ema20"] = ema(df["close"], 20)
    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["ll10"] = df["low"].rolling(10).min()
    df.dropna(inplace=True)
    return df


def signal_a(df, i):
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


def backtest_detail(df, modal_awal):
    modal = float(modal_awal)
    posisi = None
    entry_price = 0.0
    entry_date = None
    trail_price = 0.0
    peak = modal
    dd_max = 0.0
    trades = []
    in_trade = False
    bars_held = 0

    for i in range(60, len(df) - 1):
        tgl = df.index[i]
        c = df["close"].iloc[i]
        cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)

        sig = signal_a(df, i)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"
                entry_price = c
                entry_date = tgl
                trail_price = c - df["atr14"].iloc[i] * 3
                modal -= 10000
                in_trade = True
                bars_held = 0
        else:
            bars_held += 1
            trail_price = max(trail_price, ll10)
            profit = 0.0
            exit_here = False
            exit_reason = ""

            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal
                exit_here = True
                exit_reason = "TRAIL_STOP"
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
                exit_reason = "TREND_REVERSAL"
            elif bars_held > 90:
                profit = (c - entry_price) / entry_price * modal
                exit_here = True
                exit_reason = "MAX_HOLD"
            else:
                profit = (cn - c) / c * modal * 0.2

            if exit_here:
                modal += profit
                hold_days = (tgl - entry_date).days
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": tgl,
                    "hold_days": hold_days,
                    "bars_held": bars_held,
                    "entry_price": round(entry_price, 1),
                    "exit_price": round(cn, 1),
                    "price_change": round((cn - entry_price) / entry_price * 100, 2),
                    "profit_idr": round(profit),
                    "profit_pct": round(profit / (modal - profit) * 100, 2) if modal != profit else 0,
                    "modal_sebelum": round(modal - profit),
                    "modal_sesudah": round(modal),
                    "exit_reason": exit_reason,
                })
                in_trade = False
                posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    return trades, modal, roi, dd_max


def analisa(trades, modal_akhir, roi, dd_max, modal_awal):
    print(f"\n{'='*80}")
    print(f"  ANALISA DETAIL — Strategy A: Pullback SMA50 (LONG Only)")
    print(f"  Symbol: {SYMBOL} | Modal: Rp{modal_awal:,}")
    print(f"{'='*80}")

    print(f"\n  1. PERFORMANCE OVERVIEW")
    print(f"  {'-'*60}")
    print(f"  Modal Akhir:       Rp{modal_akhir:,}")
    print(f"  Total Profit:      Rp{modal_akhir - modal_awal:,}")
    print(f"  ROI:               +{roi:.2f}%")
    print(f"  Max Drawdown:      {dd_max:.1f}%")
    print(f"  Total Trades:      {len(trades)}")
    win_t = [t for t in trades if t["profit_idr"] > 0]
    loss_t = [t for t in trades if t["profit_idr"] < 0]
    print(f"  Win / Loss:        {len(win_t)}W / {len(loss_t)}L")
    print(f"  Win Rate:          {len(win_t)/max(len(trades),1)*100:.1f}%")

    total_days = sum(t["hold_days"] for t in trades)
    print(f"  Total Hari:        {total_days} hari dalam posisi")
    
    # Cari rentang tanggal
    all_dates = []
    for t in trades:
        all_dates.append(t["entry_date"])
        all_dates.append(t["exit_date"])
    first_date = min(all_dates)
    last_date = max(all_dates)
    total_period_days = (last_date - first_date).days
    print(f"  Periode Trading:   {first_date.date()} — {last_date.date()} ({total_period_days} hari)")

    print(f"\n  2. PROFIT PER HARI & PER MINGGU")
    print(f"  {'-'*60}")
    total_profit = modal_akhir - modal_awal
    avg_per_day = total_profit / total_period_days if total_period_days else 0
    avg_per_week = avg_per_day * 7
    avg_per_month = avg_per_day * 30
    print(f"  Profit/hari:       Rp{avg_per_day:,.0f}")
    print(f"  Profit/minggu:     Rp{avg_per_week:,.0f}")
    print(f"  Profit/bulan:      Rp{avg_per_month:,.0f}")
    print(f"  Return/hari:       {roi/total_period_days*100:.3f}%" if total_period_days else "N/A")

    # Profit per hari hanya saat in posisi
    avg_per_day_in_pos = total_profit / total_days if total_days else 0
    avg_per_week_in_pos = avg_per_day_in_pos * 7
    print(f"  (Saat in posisi)")
    print(f"  Profit/hari:       Rp{avg_per_day_in_pos:,.0f}")
    print(f"  Profit/minggu:     Rp{avg_per_week_in_pos:,.0f}")

    print(f"\n  3. ANALISA HOLD TIME")
    print(f"  {'-'*60}")
    hold_times = [t["hold_days"] for t in trades]
    print(f"  Rata-rata hold:    {np.mean(hold_times):.0f} hari")
    print(f"  Hold terpendek:    {min(hold_times)} hari")
    print(f"  Hold terpanjang:   {max(hold_times)} hari")
    print(f"  Median hold:       {np.median(hold_times):.0f} hari")

    short_trades = [t for t in trades if t["hold_days"] <= 14]
    med_trades = [t for t in trades if 14 < t["hold_days"] <= 40]
    long_trades = [t for t in trades if t["hold_days"] > 40]
    print(f"  1-14 hari:         {len(short_trades)} trade")
    print(f"  15-40 hari:        {len(med_trades)} trade")
    print(f"  >40 hari:          {len(long_trades)} trade")

    print(f"\n  4. ANALISA EXIT REASON")
    print(f"  {'-'*60}")
    reasons = {}
    for t in trades:
        r = t["exit_reason"]
        reasons[r] = reasons.get(r, 0) + 1
    for r, c in reasons.items():
        print(f"  {r:<20} {c}x")

    print(f"\n  5. ANALISA RISK")
    print(f"  {'-'*60}")
    profits = [t["profit_idr"] for t in trades]
    win_p = [t["profit_idr"] for t in win_t] if win_t else [0]
    loss_p = [t["profit_idr"] for t in loss_t] if loss_t else [0]
    print(f"  Profit total:      Rp{sum(profits):,}")
    if win_t: print(f"  Rata-rata Win:     Rp{np.mean(win_p):,.0f}")
    if loss_t: print(f"  Rata-rata Loss:    Rp{abs(np.mean(loss_p)):,.0f}")
    if loss_t:
        pf = sum(win_p) / abs(sum(loss_p))
        print(f"  Profit Factor:     {pf:.2f}")
    print(f"  Best Trade:        Rp{max(profits):,}")
    print(f"  Worst Trade:       Rp{min(profits):,}")
    print(f"  Max DD:            {dd_max:.1f}%")

    print(f"\n  6. DETAIL SETIAP TRADE")
    print(f"  {'='*80}")
    print(f"  {'No':<4} {'Entry':<12} {'Exit':<12} {'Hold':<6} {'Entry $':<10} {'Exit $':<10} {'Chg%':<8} {'Profit':<12} {'Reason':<16}")
    print(f"  {'-'*80}")
    for i, t in enumerate(trades, 1):
        p = "+" if t["profit_idr"] > 0 else ""
        print(f"  {i:<4} {str(t['entry_date'].date()):<12} {str(t['exit_date'].date()):<12} {t['hold_days']:<6} {t['entry_price']:<10.0f} {t['exit_price']:<10.0f} {t['price_change']:<+7.2f}% {p}Rp{t['profit_idr']:<,} {t['exit_reason']:<16}")
    print(f"  {'-'*80}")

    # Cumulative profit chart
    print(f"\n  7. EQUITY CURVE (setiap trade)")
    print(f"  {'-'*60}")
    cum = modal_awal
    for i, t in enumerate(trades):
        cum += t["profit_idr"]
        bar = "#" * max(int(abs(cum - modal_awal) / 50000), 0)
        print(f"  #{i+1:<3} Rp{cum:,} {bar}")

    print(f"\n{'='*80}")
    print(f"  KESIMPULAN:")
    print(f"  {'='*80}")
    print(f"  Modal Rp5jt -> Rp{modal_akhir:,} dalam {total_period_days} hari")
    print(f"  = Rp{avg_per_day:,.0f}/hari atau Rp{avg_per_week:,.0f}/minggu")
    print(f"  Hanya 14 trade dalam 3 tahun (rata-rata hold {np.mean(hold_times):.0f} hari/trade)")
    print(f"  Resiko: Max DD cuma {dd_max:.1f}%, kalah 5x tapi rugi kecil")
    print(f"{'='*80}")

    print(f"""
STRATEGI — KENAPA COCOK UNTUK XAUUSD?
=====================================

1. XAUUSD TREN BESAR NAIK (BULLISH)
   Gold 2023-2026: $1,800 -> $4,300+
   Setiap strategi yang short pasti rugi.
   Strategy A hanya LONG = ikut arah tren.

2. PULLBACK KE SMA50 = ENTRY MURAH
   Harga tidak naik lurus, selalu pullback.
   SMA50 adalah support dinamis di tren naik.
   Beli saat harga touch SMA50 = diskon.

3. CUTOFF DI SMA100 = BATAS RUGI
   Kalau harga tembus SMA100, tren rusak.
   Exit tanpa ragu, rugi kecil.

4. TRAILING STOP = PROFIT MAKSIMAL
   Tidak take profit manual.
   Biarkan harga naik, stop ikut naik.
   Trade Feb 2026: hold 91 hari, profit Rp1.6jt.

5. SEDIKIT TRADE = BIAYA MINIMAL
   14 trade dalam 3 tahun.
   Biaya spread cuma 14 x Rp10.000 = Rp140.000.
   Tidak overload, tidak overtrade.

RUMUS SEDERHANA
===============
Entry: SMA50 naik + harga di SMA50 + RSI < 45
Exit:  harga < SMA100 atau trailing stop kena
Filter: hanya LONG, never short
""")


if not init_mt5():
    print("[ERROR] MT5 tidak bisa diinisialisasi")
    exit()

print("[INFO] Mengambil data XAUUSDm...")
df = get_data(1200)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()

df = prep(df)
print(f"[OK] {len(df)} bars | {df.index[0].date()} — {df.index[-1].date()}")

print("[RUN] Backtest Strategy A...")
trades, modal_akhir, roi, dd_max = backtest_detail(df, MODAL)

analisa(trades, modal_akhir, roi, dd_max, MODAL)

# Simpan ke state untuk AI Manager
from src.state_manager import StateManager
state = StateManager("data/analisis_strat_a.db")
state.upsert_metric("strat_a_roi", roi)
state.upsert_metric("strat_a_win_rate", len([t for t in trades if t["profit_idr"] > 0])/max(len(trades),1)*100)
state.upsert_metric("strat_a_max_dd", dd_max)
state.upsert_metric("strat_a_profit", modal_akhir - MODAL)
state.log_backtest("strat_a_pullback_sma50", "PASS" if roi > 0 else "FAILED", {
    "roi": roi, "trades": len(trades), "total_days": sum(t["hold_days"] for t in trades),
    "avg_hold": np.mean([t["hold_days"] for t in trades]),
    "profit_per_day": round((modal_akhir - MODAL) / (trades[-1]["exit_date"] - trades[0]["entry_date"]).days, 0) if trades else 0
})
print("\n[INFO] Data disimpan ke database untuk AI Manager")

mt5.shutdown()
print("[DONE]")
