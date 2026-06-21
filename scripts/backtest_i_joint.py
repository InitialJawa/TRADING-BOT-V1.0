import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from strategies.shared.stage_analysis import prep_stage, detect_stage, signal_stage_enhanced, confidence_score

MODAL = 12_000_000
FEE = 0
N_TICKERS = 3
ALLOC = 1.0 / N_TICKERS

TICKERS = [
    {"name": "XAGUSDm", "spread": 30, "point": 0.001, "target_harian": 200000},
    {"name": "XAUUSDm", "spread": 25, "point": 0.01, "target_harian": 200000},
    {"name": "JP225m", "spread": 64, "point": 0.1, "target_harian": 150000},
]

I_PARAMS = {
    "XAGUSDm": {"sl": 1.2, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
    "XAUUSDm": {"sl": 1.5, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
    "JP225m": {"sl": 1.0, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
}

CONF_FACTORS = {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1}
CONF_SIZING = [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)]

def fetch(sym):
    mt5.symbol_select(sym, True)
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5000)
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 1250)
    if h1 is None or len(h1) < 200:
        return None, None
    df = pd.DataFrame(h1)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    dh4 = None
    if h4 is not None and len(h4) > 50:
        dh4 = pd.DataFrame(h4)
        dh4["time"] = pd.to_datetime(dh4["time"], unit="s")
        dh4.set_index("time", inplace=True)
    return df, dh4

def run_portfolio_backtest(dfs):
    """
    Shared pool Rp12M — all 4 tickers run simultaneously on the same balance.
    Uses HIGH/LOW of each H1 bar for SL checks (more accurate than close-only).
    """
    balance = float(MODAL)
    equity_peak = MODAL
    max_dd = 0.0

    # Per-ticker state
    ts = {}
    for t in TICKERS:
        ts[t["name"]] = {
            "in_trade": False, "posisi": None, "entry_price": 0.0,
            "entry_time": None, "sl_price": 0.0, "trail": False,
            "modal_at_entry": 0.0, "trade_frac": 1.0, "entry_idx": -1,
            "trail_sl_new": None,  # trail SL to apply starting next bar
        }

    all_trades = []
    all_exits = []
    daily_pnl = {}

    # Find common trading days (union of all tickers)
    all_dates = sorted(set().union(*[
        set(dfs[t["name"]].index.date) for t in TICKERS if t["name"] in dfs
    ]))
    if not all_dates:
        return 0, 0, [], {}, {}

    for day in all_dates:
        day_realized = 0.0

        for t in TICKERS:
            tn = t["name"]
            if tn not in dfs:
                continue
            df = dfs[tn]
            day_mask = df.index.date == day
            if not day_mask.any():
                continue
            day_df = df[day_mask].copy()
            if len(day_df) < 2:
                continue

            p = I_PARAMS[tn]
            params = {
                "ema_fast": 9, "ema_medium": 21, "volume_mult": p["vol_mult"],
                "stage_slope_threshold": p["threshold"],
                "confidence_factors": CONF_FACTORS,
            }
            st = ts[tn]
            day_indices = df.index.isin(day_df.index)
            idx_list = np.where(day_indices)[0]

            for pos_in_day, i in enumerate(idx_list):
                row = df.iloc[i]
                c = row["close"]
                hi = row["high"]
                lo = row["low"]
                a = row["atr"]

                sig = signal_stage_enhanced(df, i, params)
                conf = confidence_score(row, CONF_FACTORS)
                frac = 1.0
                for lo2, hi2, fv in CONF_SIZING:
                    if lo2 <= conf <= hi2:
                        frac = fv; break

                if not st["in_trade"]:
                    if sig != "HOLD":
                        st["posisi"] = sig
                        st["entry_price"] = c
                        st["entry_time"] = df.index[i]
                        st["entry_idx"] = i
                        base = balance * ALLOC
                        st["modal_at_entry"] = base
                        st["trade_frac"] = frac
                        if sig == "BUY":
                            st["sl_price"] = c - a * p["sl"]
                        else:
                            st["sl_price"] = c + a * p["sl"]
                        st["trail"] = False
                        balance -= FEE * frac
                        sc = (t["spread"] * t["point"] / c) * base
                        balance -= sc * frac
                        st["in_trade"] = True
                else:
                    entry = st["entry_price"]
                    me = st["modal_at_entry"]
                    tf = st["trade_frac"]
                    exit_here = False
                    profit = 0.0
                    cs = detect_stage(row, p["threshold"])
                    td = a * p["trail"]

                    # Apply pending trail SL from previous bar
                    if st["trail_sl_new"] is not None:
                        st["sl_price"] = st["trail_sl_new"]
                        st["trail_sl_new"] = None

                    if st["posisi"] == "BUY":
                        # Hard SL: valid immediately (placed at broker on entry)
                        sl_hit = lo <= st["sl_price"] and not st["trail"]
                        # Trail SL: only checked if applied on a previous bar
                        trail_hit = lo <= st["sl_price"] and st["trail"]

                        if sl_hit or trail_hit:
                            profit = (st["sl_price"] - entry) / entry * me * tf
                            exit_here = True
                        elif cs == 3:
                            profit = (c - entry) / entry * me * tf
                            exit_here = True
                        elif row["ema9"] < row["ema21"]:
                            profit = (c - entry) / entry * me * tf
                            exit_here = True
                        else:
                            if not st["trail"] and (c - entry) >= td:
                                st["trail"] = True
                                # Trail SL applies starting NEXT bar (wider offset)
                                st["trail_sl_new"] = entry + td * 0.5
                            if st["trail"]:
                                new_sl = c - td * 1.0
                                if new_sl > st["sl_price"]:
                                    st["trail_sl_new"] = new_sl
                    else:
                        sl_hit = hi >= st["sl_price"] and not st["trail"]
                        trail_hit = hi >= st["sl_price"] and st["trail"]

                        if sl_hit or trail_hit:
                            profit = (entry - st["sl_price"]) / entry * me * tf
                            exit_here = True
                        elif cs == 3:
                            profit = (entry - c) / entry * me * tf
                            exit_here = True
                        elif row["ema9"] > row["ema21"]:
                            profit = (entry - c) / entry * me * tf
                            exit_here = True
                        else:
                            if not st["trail"] and (entry - c) >= td:
                                st["trail"] = True
                                st["trail_sl_new"] = entry - td * 0.5
                            if st["trail"]:
                                new_sl = c + td * 1.0
                                if st["sl_price"] == 0 or new_sl < st["sl_price"]:
                                    st["trail_sl_new"] = new_sl

                    if exit_here:
                        balance += profit
                        day_realized += profit
                        held = (df.index[i] - st["entry_time"]).total_seconds() / 3600
                        all_exits.append({
                            "tgl": df.index[i], "ticker": tn,
                            "posisi": st["posisi"], "held": held,
                            "profit": round(profit),
                            "conf": conf, "frac": tf,
                            "balance": round(balance),
                        })
                        st["in_trade"] = False
                        st["posisi"] = None

        daily_pnl[day] = day_realized
        if balance > equity_peak:
            equity_peak = balance
        dd = (equity_peak - balance) / equity_peak * 100
        if dd > max_dd:
            max_dd = dd
        if dd > 25:
            for tn in ts:
                ts[tn]["in_trade"] = False
                ts[tn]["posisi"] = None

    return balance, max_dd, all_exits, daily_pnl, ts

def calc_metrics(balance_akhir, trades, daily_pnl):
    roi = (balance_akhir - MODAL) / MODAL * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    win_days = sum(1 for p in daily_pnl.values() if p >= 0)
    total_days = len(daily_pnl)
    return {
        "roi": roi, "pf": pf, "trades": len(trades),
        "wr": len(win) / max(len(trades), 1) * 100,
        "avg_daily": avg_daily, "total_days": total_days,
        "win_days": win_days, "win_day_pct": win_days / max(total_days, 1) * 100,
        "avg_hold_hrs": avg_hold,
    }

def main():
    print("=" * 100)
    print("  PORTFOLIO BACKTEST — HIGH/LOW SL CHECK")
    print("  Signal: H1 Stage Analysis | SL check: bar HIGH/LOW (cover all wicks)")
    print(f"  Shared Pool Rp12jt | {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 100)

    if not mt5.initialize():
        print("[ERROR] MT5 gagal initialize"); return

    dfs = {}
    for t in TICKERS:
        sym = t["name"]
        print(f"\n[{sym}] Fetching H1+H4...", end=" ")
        df, dh4 = fetch(sym)
        if df is None:
            print("DATA GAGAL"); continue
        t0, t1 = df.index[0].date(), df.index[-1].date()
        days = (t1 - t0).days
        print(f"{t0} s/d {t1} ({days}hr, {len(df)} bars)")

        p = I_PARAMS[sym]
        params_i = {
            "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
            "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
            "atr_sl_mult": p["sl"], "atr_trail_mult": p["trail"],
            "running_pct": p["pct"], "volume_mult": p["vol_mult"],
            "stage_slope_threshold": p["threshold"],
            "confidence_factors": CONF_FACTORS,
        }
        df = prep_stage(df, dh4, params_i)
        if len(df) < 100:
            print("  PREP FAIL"); continue

        stages = [detect_stage(df.iloc[i], p["threshold"]) for i in range(len(df))]
        sc = {s: int((np.array(stages) == s).sum()) for s in [1, 2, 3, 4]}
        print(f"  S1={sc[1]}({sc[1]/len(stages)*100:.0f}%) S2={sc[2]}({sc[2]/len(stages)*100:.0f}%) "
              f"S3={sc[3]}({sc[3]/len(stages)*100:.0f}%) S4={sc[4]}({sc[4]/len(stages)*100:.0f}%)")
        dfs[sym] = df

    mt5.shutdown()
    if len(dfs) < 2:
        print("[ERROR] Data tidak cukup"); return

    print(f"\n{'='*100}")
    print("  MENJALANKAN PORTFOLIO BACKTEST (HIGH/LOW SL CHECK)...")
    print(f"{'='*100}")

    balance_akhir, max_dd, trades, daily_pnl, _ = run_portfolio_backtest(dfs)
    metrics = calc_metrics(balance_akhir, trades, daily_pnl)

    # Per-ticker analysis
    print(f"\n{'='*100}")
    print("  HASIL PER TICKER (realized P&L via high/low SL)")
    print(f"{'='*100}")
    print(f"  {'Ticker':<12} {'Trades':>7} {'Win%':>6} {'Total PnL':>12} {'Avg PnL':>10} {'PF':>6}")
    print(f"  {'-'*53}")
    for t in TICKERS:
        tn = t["name"]
        tt = [tr for tr in trades if tr["ticker"] == tn]
        if not tt: continue
        wins = [tr for tr in tt if tr["profit"] > 0]
        losses = [tr for tr in tt if tr["profit"] < 0]
        total = sum(tr["profit"] for tr in tt)
        avg = np.mean([tr["profit"] for tr in tt])
        pf = sum(tr["profit"] for tr in wins) / max(abs(sum(tr["profit"] for tr in losses)), 1) if losses else 999
        wr = len(wins) / max(len(tt), 1) * 100
        pm = "+" if total >= 0 else ""
        print(f"  {tn:<12} {len(tt):>7d} {wr:>5.0f}% {pm}Rp{total:>10,.0f}  Rp{avg:>8,.0f}  {pf:.2f}")

    pm = "+" if metrics["roi"] > 0 else ""
    print(f"\n{'='*100}")
    print("  HASIL PORTFOLIO — HIGH/LOW SL CHECK")
    print(f"{'='*100}")
    print(f"  Modal Awal:         Rp{MODAL:>12,}")
    print(f"  Modal Akhir:        Rp{balance_akhir:>12,.0f}  ({pm}{metrics['roi']:.1f}%)")
    print(f"  Total Profit:       Rp{balance_akhir - MODAL:>12,.0f}")
    print(f"  Rata-rata Harian:   Rp{metrics['avg_daily']:>12,.0f}")
    print(f"  Max Drawdown:       {max_dd:.1f}%")
    print(f"  Profit Factor:      {metrics['pf']:.2f}")
    print(f"  Total Trades:       {metrics['trades']}")
    print(f"  Win Rate:           {metrics['wr']:.0f}%")
    print(f"  Hari Profit:        {metrics['win_days']}/{metrics['total_days']} ({metrics['win_day_pct']:.0f}%)")
    print(f"  Rata-rata Hold:     {metrics['avg_hold_hrs']:.1f} jam")
    print(f"  Proyeksi Bulanan:   Rp{metrics['avg_daily'] * 22:>12,.0f}")
    print(f"  Proyeksi Tahunan:   Rp{metrics['avg_daily'] * 252:>12,.0f}")
    yearly_roi = (1 + metrics["roi"] / 100) ** (252 / max(metrics["total_days"], 1)) - 1
    print(f"  Annualized ROI:     {yearly_roi*100:+.1f}%")
    daily_returns = np.array(list(daily_pnl.values()))
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
        print(f"  Sharpe Ratio:       {sharpe:.2f}")

    print(f"\n{'='*100}")
    print("  BREAKDOWN BULANAN")
    print(f"{'='*100}")
    monthly = {}
    for d, pnl in sorted(daily_pnl.items()):
        m = d.strftime("%Y-%m")
        if m not in monthly:
            monthly[m] = {"pnl": 0, "days": 0, "win_days": 0}
        monthly[m]["pnl"] += pnl
        monthly[m]["days"] += 1
        if pnl >= 0: monthly[m]["win_days"] += 1
    print(f"  {'Bulan':<10} {'Total PnL':>12} {'Hari':>5} {'Win%':>6}")
    print(f"  {'-'*35}")
    for m, v in sorted(monthly.items()):
        pm2 = "+" if v["pnl"] >= 0 else ""
        wp = v["win_days"] / max(v["days"], 1) * 100
        print(f"  {m:<10} {pm2}Rp{v['pnl']:>10,.0f}  {v['days']:>3d}  {wp:>5.0f}%")

    # Comparison table
    m_end = "Rp{:.1f}jt".format(balance_akhir/1e6)
    m_roi = "{}{:.1f}%".format(pm, metrics["roi"])
    m_hari = "Rp{:,.0f}".format(metrics["avg_daily"])
    m_dd = "{:.1f}%".format(max_dd)
    m_pf = "{:.2f}".format(metrics["pf"])
    m_tr = "{:,}".format(metrics["trades"])
    m_wr = "{:.0f}%".format(metrics["wr"])
    print("\n")
    print("=" * 100)
    print("  PERBANDINGAN METODE SL CHECK")
    print("=" * 100)
    print("  {:<25} {:>18} {:>18}".format("Metrik", "Close-only", "High/Low (now)"))
    print("  " + "-" * 61)
    print("  {:<25} {:>18} {:>18}".format("Modal Akhir", "Rp96.4jt", m_end))
    print("  {:<25} {:>18} {:>18}".format("ROI", "+703.2%", m_roi))
    print("  {:<25} {:>18} {:>18}".format("Rp/hari", "Rp383,637", m_hari))
    print("  {:<25} {:>18} {:>18}".format("Max DD", "7.0%", m_dd))
    print("  {:<25} {:>18} {:>18}".format("Profit Factor", "2.23", m_pf))
    print("  {:<25} {:>18} {:>18}".format("Trades", "1,698", m_tr))
    print("  {:<25} {:>18} {:>18}".format("Win Rate", "66%", m_wr))

    print(f"\n{'='*100}")
    print(f"  SELESAI — {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"{'='*100}")

if __name__ == "__main__":
    main()
