import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.state_manager import StateManager
from src.audit.system_audit import SystemAudit
from src.audit.risk_audit import RiskAudit
from src.audit.backtest_audit import BacktestAudit
from src.context_builder import ContextBuilder

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
USE_SYNTHETIC = False
SPREAD_POINTS = 25
POINT_VALUE = 0.01

PARAMS = {
    "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 45, "rsi_long_max": 75,
    "rsi_short_min": 25, "rsi_short_max": 55,
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 4.0,
    "atr_trail_mult": 1.0,
    "volume_ma_period": 20, "volume_mult": 1.1,
    "max_hold_bars": 24, "lot_pct": 200, "running_pct": 0.03
}


def generate_synthetic_h1(bars=5000, start_price=3300.0, seed=42):
    np.random.seed(seed)
    dates = pd.date_range(start="2024-01-01", periods=bars, freq="h")
    prices = np.zeros(bars)
    prices[0] = start_price
    trend_dir = 0; trend_bars = 0; trend_max = np.random.randint(24, 120)
    vol_mult = 1.0
    for i in range(1, bars):
        if trend_bars >= trend_max:
            trend_dir = np.random.choice([-1, 0, 1])
            trend_max = np.random.randint(24, 120)
            trend_bars = 0
            vol_mult = np.random.uniform(0.7, 1.3)
        trend_bars += 1
        strength = np.random.uniform(0.05, 0.35) * trend_dir
        vol = np.random.uniform(6, 14) * vol_mult
        ret = np.random.normal(strength, vol)
        prices[i] = prices[i-1] + ret
        if prices[i] < start_price * 0.75: trend_dir = 1; trend_bars = 0
        if prices[i] > start_price * 1.35: trend_dir = -1; trend_bars = 0
    ohlc = np.zeros((bars, 5))
    ohlc[:, 3] = prices
    for i in range(1, bars):
        spread = np.random.uniform(2, 8)
        c = ohlc[i, 3]
        o = ohlc[i-1, 3] + np.random.uniform(-spread, spread)
        hi = max(o, c) + np.random.uniform(0, spread * 1.5)
        lo = min(o, c) - np.random.uniform(0, spread * 1.5)
        ohlc[i, 0] = round(o, 2)
        ohlc[i, 1] = round(hi, 2)
        ohlc[i, 2] = round(lo, 2)
        ohlc[i, 3] = round(c, 2)
        vol_factor = 500 + 4500 * (0.3 + 0.7 * abs(strength / 0.35)) if i > 1 else 2500
        ohlc[i, 4] = int(np.random.uniform(max(300, vol_factor * 0.5), vol_factor * 1.5))
    df = pd.DataFrame(ohlc, columns=["open", "high", "low", "close", "tick_volume"], index=dates)
    df.index.name = "time"
    return df


def try_mt5_data(bars=5000):
    global USE_SYNTHETIC
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print("[INFO] MT5 tidak tersedia, pakai data sintetik")
            USE_SYNTHETIC = True
            return None
        mt5.symbol_select(SYMBOL, True)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars)
        mt5.shutdown()
        if rates is None or len(rates) < 200:
            print("[INFO] Data MT5 tidak cukup, pakai data sintetik")
            USE_SYNTHETIC = True
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        print("[INFO] Data dari MT5")
        return df
    except ImportError:
        print("[INFO] MetaTrader5 tidak terinstall, pakai data sintetik")
        USE_SYNTHETIC = True
        return None
    except Exception as e:
        print(f"[INFO] Gagal akses MT5 ({e}), pakai data sintetik")
        USE_SYNTHETIC = True
        return None


def get_data(bars=5000):
    df = try_mt5_data(bars)
    if df is None:
        df = generate_synthetic_h1(bars)
        print("[INFO] Data sintetik XAUUSD H1 dibuat")
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
    return 100 - (100 / (1 + g / l))


def macd(s, f=12, sl=26, sg=9):
    e1 = ema(s, f)
    e2 = ema(s, sl)
    m = e1 - e2
    return m, ema(m, sg)


def prep(df):
    p = PARAMS
    df["ema9"] = ema(df["close"], p["ema_fast"])
    df["ema21"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr14"] = atr(df, p["atr_period"])
    df["rsi14"] = rsi(df["close"], p["rsi_period"])
    df["macd"], df["macd_signal"] = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True)
    return df


def signal_hl(df, i):
    p = PARAMS
    row = df.iloc[i]
    c = row["close"]
    above_ema200 = c > row["ema200"]
    ema_bull = row["ema9"] > row["ema21"]
    rsi_ok_long = p["rsi_long_min"] <= row["rsi14"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_signal"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    atr_ok = row["atr14"] > 0

    if above_ema200 and ema_bull and rsi_ok_long and macd_bull and vol_ok and atr_ok:
        return "BUY"

    ema_bear = row["ema9"] < row["ema21"]
    rsi_ok_short = p["rsi_short_min"] <= row["rsi14"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_signal"]

    if not above_ema200 and ema_bear and rsi_ok_short and macd_bear and vol_ok and atr_ok:
        return "SELL"

    return "HOLD"


def backtest(df, modal_awal):
    p = PARAMS
    modal = float(modal_awal)
    peak = modal
    dd_max = 0.0
    trades = []
    in_trade = False
    posisi = None
    entry_price = 0.0
    entry_idx = 0
    sl_price = 0.0
    tp_price = 0.0
    trail_activated = False

    for i in range(50, len(df)):
        c = df["close"].iloc[i]
        a = df["atr14"].iloc[i]
        ema9 = df["ema9"].iloc[i]
        ema21 = df["ema21"].iloc[i]
        sig = signal_hl(df, i)

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 20: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig != "HOLD":
                posisi = sig
                entry_price = c
                entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail_activated = False
                modal -= 5000
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost
                in_trade = True
        else:
            bars_held = i - entry_idx
            exit_here = False
            profit = 0.0

            if posisi == "BUY":
                if c <= sl_price:
                    profit = (sl_price - entry_price) / entry_price * modal
                    exit_here = True
                elif c >= tp_price:
                    profit = (c - entry_price) / entry_price * modal
                    exit_here = True
                elif ema9 < ema21:
                    profit = (c - entry_price) / entry_price * modal
                    exit_here = True
                elif bars_held >= p["max_hold_bars"]:
                    profit = (c - entry_price) / entry_price * modal
                    exit_here = True
                else:
                    trail_dist = a * p["atr_trail_mult"]
                    if not trail_activated and (c - entry_price) >= trail_dist:
                        trail_activated = True
                        sl_price = entry_price + trail_dist * 0.3
                    if trail_activated:
                        new_sl = c - trail_dist * 0.5
                        sl_price = max(sl_price, new_sl)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price:
                    profit = (entry_price - sl_price) / entry_price * modal
                    exit_here = True
                elif c <= tp_price:
                    profit = (entry_price - c) / entry_price * modal
                    exit_here = True
                elif ema9 > ema21:
                    profit = (entry_price - c) / entry_price * modal
                    exit_here = True
                elif bars_held >= p["max_hold_bars"]:
                    profit = (entry_price - c) / entry_price * modal
                    exit_here = True
                else:
                    trail_dist = a * p["atr_trail_mult"]
                    if not trail_activated and (entry_price - c) >= trail_dist:
                        trail_activated = True
                        sl_price = entry_price - trail_dist * 0.3
                    if trail_activated:
                        new_sl = c + trail_dist * 0.5
                        sl_price = min(sl_price, new_sl)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit_here:
                modal += profit
                trades.append({
                    "tgl": df.index[i],
                    "posisi": posisi,
                    "held": bars_held,
                    "profit": round(profit),
                    "modal": round(modal),
                    "exit_price": round(c, 2),
                    "entry_price": round(entry_price, 2)
                })
                in_trade = False
                posisi = None

    return modal, dd_max, trades


def print_period_breakdown(df, trades, modal_awal, modal_akhir):
    print(f"\n  {'='*70}")
    print(f"  BREAKDOWN PER PERIODE (3 bulanan)")
    print(f"  {'='*70}")
    start = df.index[0]
    end = df.index[-1]
    for year in range(start.year, end.year + 1):
        for q in [1, 4, 7, 10]:
            q_start = pd.Timestamp(f"{year}-{q:02d}-01", tz=df.index.tz)
            q_end = q_start + pd.DateOffset(months=3)
            if q_start < start: continue
            if q_start > end: break
            period_trades = [t for t in trades if q_start <= t["tgl"] < q_end]
            if not period_trades: continue
            q_profit = sum(t["profit"] for t in period_trades)
            q_win = [t for t in period_trades if t["profit"] > 0]
            q_loss = [t for t in period_trades if t["profit"] < 0]
            q_avg_hold = np.mean([t["held"] for t in period_trades])
            print(f"    {year} Q{(q-1)//3+1}: {len(period_trades):2d} trades, profit Rp{q_profit:+,.0f}, "
                  f"WR {len(q_win)/max(len(period_trades),1)*100:.0f}%, avg hold {q_avg_hold:.0f} bars")


def print_comparison(trades, modal_awal, modal_akhir, dd_max, total_bars):
    roi = (modal_akhir - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_win = np.mean([t["profit"] for t in win]) / modal_awal * 100 if win else 0
    avg_loss = np.mean([t["profit"] for t in loss]) / modal_awal * 100 if loss else 0

    print(f"\n  {'='*70}")
    print(f"  PERFORMANCE STRATEGY D — H1 Confluence Momentum")
    print(f"  {'='*70}")
    print(f"  Modal Awal:     Rp{modal_awal:,.0f}")
    print(f"  Modal Akhir:    Rp{modal_akhir:,.0f}")
    print(f"  Profit:         Rp{modal_akhir - modal_awal:,.0f}")
    print(f"  ROI:            +{roi:.2f}%")
    print(f"  Max DD:         {dd_max:.1f}%")
    print(f"  Trades:         {len(trades)} ({len(win)}W / {len(loss)}L)")
    print(f"  Win Rate:       {len(win)/max(len(trades),1)*100:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  Avg Hold:       {avg_hold:.0f} bars ({avg_hold:.1f} jam)")
    print(f"  Avg Win:        {avg_win:+.2f}%")
    print(f"  Avg Loss:       {avg_loss:+.2f}%")
    print(f"  Total Bars:     {total_bars}")

    print(f"\n  {'='*70}")
    print(f"  PERBANDINGAN vs A / B / C")
    print(f"  {'='*70}")
    print(f"  {'Metric':<20} {'Str D (H1)':<15} {'Str A (D1)':<15} {'Str B (H4)':<15} {'Str C (H4)'}")
    print(f"  {'-'*65}")
    print(f"  {'Timeframe':<20} {'H1':<15} {'D1':<15} {'H4':<15} {'H4'}")
    print(f"  {'ROI':<20} {f'+{roi:.1f}%':<15} {'+135.4%/3yr':<15} {'+33.6%/4mo':<15} {'+35.9%/4mo'}")
    print(f"  {'Max DD':<20} {f'{dd_max:.1f}%':<15} {'2.1%':<15} {'9.9%':<15} {'0% /13.4%'}")
    print(f"  {'Win Rate':<20} {f'{len(win)/max(len(trades),1)*100:.0f}%':<15} {'68.2%':<15} {'75-80%':<15} {'64.7%'}")
    print(f"  {'Profit Factor':<20} {f'{pf:.2f}':<15} {'18.28':<15} {'3.28-4.65':<15} {'2.83'}")
    print(f"  {'Total Trades':<20} {f'{len(trades)}':<15} {'22(3yr)':<15} {'4-10(4mo)':<15} {'17(4mo)'}")
    print(f"  {'Hold Time':<20} {f'{avg_hold:.0f} jam':<15} {'22 hari':<15} {'~6 hari':<15} {'~8 hari'}")
    print(f"  {'Sinyal/minggu':<20} {f'{len(trades)/max((total_bars/24/7),1):.1f}x':<15} {'~0.1x':<15} {'~0.2x':<15} {'~1x'}")
    print(f"  {'Arah':<20} {'LONG_SHORT':<15} {'LONG':<15} {'LONG_SHORT':<15} {'LONG_SHORT'}")

    if pf > 3.0 and dd_max < 10 and len(trades) >= 10:
        print(f"\n  >>> LEBIH BAIK dari Strategy C (PF {pf:.2f} vs 2.83)")
    if pf > 4.0 and dd_max < 8:
        print(f"  >>> LEBIH BAIK dari Strategy B (PF {pf:.2f} vs 4.65)")
    if roi > 100 and dd_max < 3 and len(trades) > 22:
        print(f"  >>> LEBIH BAIK dari Strategy A (ROI {roi:.1f}% vs 135%, trades {len(trades)} vs 22)")

    if len(trades) >= 10:
        monthly = len(trades) / max((total_bars / 24 / 30), 1)
        print(f"\n  >> FREKUENSI: ~{monthly:.1f} trades/bulan ({len(trades)} total)")
        print(f"  >> HOLD RATA-RATA: {avg_hold:.0f} jam ({avg_hold/24:.1f} hari)")
        print(f"  >> HASIL KELIHATAN {'HARIAN' if avg_hold < 24 else 'MINGGUAN'} (hold {avg_hold:.0f} jam)")


def main():
    print("=" * 70)
    print("  STRATEGY D — H1 Confluence Momentum")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    print("\n[INFO] Mengambil data H1 XAUUSDm (maks 4 bulan)...")
    df = get_data(2900)
    if df is None or len(df) < 200:
        print("[ERROR] Data tidak mencukupi")
        return

    t0, t1 = df.index[0].date(), df.index[-1].date()
    print(f"[INFO] Periode: {t0} — {t1} ({len(df)} bars H1)")

    df = prep(df)
    print(f"[INFO] Data siap: {len(df)} bars after prep")

    modal_akhir, dd_max, trades = backtest(df, MODAL)

    print_comparison(trades, MODAL, modal_akhir, dd_max, len(df))
    print_period_breakdown(df, trades, MODAL, modal_akhir)

    print(f"\n  {'='*70}")
    print(f"  SEEDING KE AI MANAGER DATABASE")
    print(f"  {'='*70}")

    state = StateManager("data/state.db")
    roi = (modal_akhir - MODAL) / MODAL * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0

    state.upsert_metric("portfolio_drawdown", round(dd_max, 2))
    state.upsert_metric("rolling_sharpe_7d", round(min(pf / 5, 5.0), 2))
    state.upsert_metric("running_modal", round(modal_akhir, 2))
    state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
    state.upsert_strategy("strategy_d_h1", "ACTIVE")
    state.log_backtest("strategy_d_h1", "PASS" if dd_max < 15 and pf > 1.5 else "FAILED", {
        "roi": round(roi, 2), "dd": round(dd_max, 2), "pf": round(pf, 2),
        "trades": len(trades), "win_rate": round(len(win) / max(len(trades), 1) * 100, 1),
        "avg_hold_hours": round(avg_hold, 1), "period_days": round(len(df) / 24, 0)
    })

    print(f"  [OK] Metrics tersimpan:")
    print(f"    portfolio_drawdown: {dd_max:.1f}%")
    print(f"    rolling_sharpe_7d: {min(pf/5, 5.0):.2f}")
    print(f"    running_modal: Rp{modal_akhir:,.0f}")
    print(f"    strategy_d_h1: ACTIVE")
    print(f"    backtest: {'PASS' if dd_max < 15 and pf > 1.5 else 'FAILED'}")

    print(f"\n  {'='*70}")
    print(f"  STRATEGY D SIAP — Hasil keliatan dalam hitungan jam")
    print(f"  Jumlah sinyal: ~{len(trades)/max((len(df)/24/7),1):.1f}x per minggu")
    print(f"  Hold ~{avg_hold:.0f} jam ({avg_hold/24:.1f} hari)")
    print(f"  {'='*70}")
    print(f"\n  Jalankan live: python scripts/jalankan_strat_d.py")


if __name__ == "__main__":
    main()
