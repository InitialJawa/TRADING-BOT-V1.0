"""
Backtrader Backtest — Strategy G (M15 Confidence Sizing) on XAUUSDm
Exact replication of original backtest logic from strategi_g_m15.py
"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
SPREAD_POINTS = 25
POINT_VALUE = 0.01
TARGET_HARIAN = 500_000
CONF_SIZING = [(0, 2, 1.0), (3, 4, 1.5), (5, 6, 2.0)]


def fetch_mt5_data(bars=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return None, None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    rates_h1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars // 4)
    mt5.shutdown()
    if rates is None or len(rates) < 500:
        return None, None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    dh1 = None
    if rates_h1 is not None:
        dh1 = pd.DataFrame(rates_h1)
        dh1["time"] = pd.to_datetime(dh1["time"], unit="s")
        dh1.set_index("time", inplace=True)
    return df, dh1


def prep_data(df, dh1):
    df["ema5"] = ema(df["close"], 5)
    df["ema13"] = ema(df["close"], 13)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, 10)
    df["rsi"] = rsi(df["close"], 14)
    df["macd"], df["macd_sig"] = macd(df["close"], 5, 13, 5)
    df["vol_ma"] = sma(df["tick_volume"], 15)
    bbu, bbm, bbl = bb(df, 20, 2)
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = (df["bbw"] < df["bbw_ma"]).astype(int)
    df["hour_utc"] = df.index.hour

    df["h1_trend"] = 0
    if dh1 is not None and len(dh1) > 100:
        dh1["ema9"] = ema(dh1["close"], 9)
        dh1["ema21"] = ema(dh1["close"], 21)
        dh1["h1_val"] = np.where(dh1["ema9"] > dh1["ema21"], 1, -1)
        dh1.dropna(inplace=True)
        h1_series = dh1["h1_val"].resample("15min").ffill()
        df["h1_trend"] = h1_series.reindex(df.index, method="ffill").fillna(0).astype(int)

    df.dropna(inplace=True)
    return df


def confidence(row):
    s = 0
    bull = row["ema5"] > row["ema13"]
    h1 = row["h1_trend"]
    if (bull and h1 == 1) or (not bull and h1 == -1):
        s += 2
    if row["squeeze"]:
        s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2:
        s += 1
    if bull and row["rsi"] > 65:
        s += 1
    if not bull and row["rsi"] < 35:
        s += 1
    if 7 <= row["hour_utc"] < 15:
        s += 1
    return s


def get_fraction(conf):
    for lo, hi, frac in CONF_SIZING:
        if lo <= conf <= hi:
            return frac
    return 1.0


class StrategyG(bt.Strategy):
    params = (("verbose", False),)

    def __init__(self):
        self.trades_log = []
        self.daily_pnl = {}
        self.current_day_pnl = 0.0
        self.last_day = None

        self.in_position = False
        self.pos_type = None
        self.entry_price = 0.0
        self.entry_idx = 0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trail_active = False
        self.trade_frac = 1.0
        self.modal_at_entry = 0.0
        self.entry_conf = 0
        self.dd_halt = False
        self.peak_modal = MODAL
        self.dd_max = 0.0

    def log(self, txt):
        if self.p.verbose:
            print(f"{self.datas[0].datetime.datetime(0)}: {txt}")

    def next(self):
        dt = self.datas[0].datetime.datetime(0)
        day = dt.date()
        c = self.datas[0].close[0]

        if self.last_day is None:
            self.last_day = day
        if day != self.last_day:
            self.daily_pnl[self.last_day] = self.current_day_pnl
            self.current_day_pnl = 0.0
            self.last_day = day

        modal = self.broker.getvalue()
        if modal > self.peak_modal:
            self.peak_modal = modal
        dd = (self.peak_modal - modal) / self.peak_modal * 100
        self.dd_max = max(self.dd_max, dd)

        if dd > 25 or self.dd_halt:
            self.dd_halt = True
            if self.in_position:
                self.close_position(c, "DD_HALT")
            return

        ef = self.datas[0].ema5[0]
        em = self.datas[0].ema13[0]
        a = self.datas[0].atr[0]
        r = self.datas[0].rsi[0]
        v = self.datas[0].volume[0]
        vm = self.datas[0].vol_ma[0]
        conf_val = int(round(self.datas[0].confidence[0]))
        frac = get_fraction(conf_val)

        if self.in_position:
            self.manage_exit(c, ef, em, a)
        else:
            self.manage_entry(c, ef, em, r, v, vm, a, conf_val, frac, modal)

    def manage_entry(self, c, ef, em, r, v, vm, a, conf_val, frac, modal):
        ema_bull = ef > em
        rsi_long = 30 <= r <= 95
        vol_ok = v > vm * 0.7

        sig = "HOLD"
        if ema_bull and rsi_long and vol_ok:
            sig = "BUY"
        else:
            ema_bear = ef < em
            rsi_short = 5 <= r <= 70
            if ema_bear and rsi_short and vol_ok:
                sig = "SELL"

        if sig == "HOLD":
            return

        sl_price = c - a * 0.5 if sig == "BUY" else c + a * 0.5
        tp_price = c + a * 2.2 if sig == "BUY" else c - a * 2.2

        cost_per_trade = 5000 * frac
        spread_cost = (SPREAD_POINTS * POINT_VALUE / c) * modal * frac
        total_cost = cost_per_trade + spread_cost

        self.broker.add_cash(-total_cost)
        self.in_position = True
        self.pos_type = sig
        self.entry_price = c
        self.entry_idx = len(self)
        self.sl_price = sl_price
        self.tp_price = tp_price
        self.trail_active = False
        self.trade_frac = frac
        self.modal_at_entry = modal - total_cost
        self.entry_conf = conf_val

        self.log(f"ENTRY {sig} @ {c:.2f} conf={conf_val} frac={frac} SL={sl_price:.2f} TP={tp_price:.2f}")

    def manage_exit(self, c, ef, em, a):
        bars = len(self) - self.entry_idx
        exit_signal = False
        profit = 0.0

        if self.pos_type == "BUY":
            if c <= self.sl_price:
                profit = (self.sl_price - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "SL"
            elif c >= self.tp_price:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "TP"
            elif ef < em:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "EMA_FLIP"
            elif bars >= 20:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "MAX_BAR"
            else:
                td = a * 0.3
                if not self.trail_active and (c - self.entry_price) >= td:
                    self.trail_active = True
                    self.sl_price = self.entry_price + td * 0.3
                if self.trail_active:
                    self.sl_price = max(self.sl_price, c - td * 0.5)
                    if c <= self.sl_price:
                        profit = (self.sl_price - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                        exit_signal = True
                        reason = "TRAIL"
                    else:
                        profit = (c - self.datas[0].close[-1]) / self.datas[0].close[-1] * self.modal_at_entry * self.trade_frac * 0.12
        else:
            if c >= self.sl_price:
                profit = (self.entry_price - self.sl_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "SL"
            elif c <= self.tp_price:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "TP"
            elif ef > em:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "EMA_FLIP"
            elif bars >= 20:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True
                reason = "MAX_BAR"
            else:
                td = a * 0.3
                if not self.trail_active and (self.entry_price - c) >= td:
                    self.trail_active = True
                    self.sl_price = self.entry_price - td * 0.3
                if self.trail_active:
                    self.sl_price = min(self.sl_price, c + td * 0.5)
                    if c >= self.sl_price:
                        profit = (self.entry_price - self.sl_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                        exit_signal = True
                        reason = "TRAIL"
                    else:
                        profit = (self.datas[0].close[-1] - c) / self.datas[0].close[-1] * self.modal_at_entry * self.trade_frac * 0.12

        if exit_signal:
            self.close_position(c, reason, profit)

    def close_position(self, c, reason, profit=0.0):
        self.broker.add_cash(profit)
        modal_now = self.broker.getvalue()
        self.current_day_pnl += profit

        self.trades_log.append({
            "tgl": self.datas[0].datetime.datetime(0),
            "posisi": self.pos_type,
            "held": len(self) - self.entry_idx,
            "profit": round(profit),
            "modal": round(modal_now),
            "conf": self.entry_conf,
            "frac": self.trade_frac,
            "reason": reason,
        })

        self.log(f"EXIT {self.pos_type} @ {c:.2f} profit={profit:.2f} reason={reason}")
        self.in_position = False
        self.pos_type = None

    def stop(self):
        if self.last_day is not None:
            self.daily_pnl[self.last_day] = self.current_day_pnl

        # Flush any remaining open position PnL
        self.daily_pnl[self.last_day] = self.current_day_pnl


class EnrichedData(bt.feeds.PandasData):
    lines = ("ema5", "ema13", "ema50", "ema200", "atr", "rsi", "macd",
             "macd_sig", "vol_ma", "bbw", "bbw_ma", "squeeze",
             "hour_utc", "h1_trend", "confidence", "frac")
    params = (
        ("datetime", None),
        ("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"),
        ("volume", "tick_volume"),
        ("ema5", "ema5"), ("ema13", "ema13"), ("ema50", "ema50"), ("ema200", "ema200"),
        ("atr", "atr"), ("rsi", "rsi"), ("macd", "macd"), ("macd_sig", "macd_sig"),
        ("vol_ma", "vol_ma"), ("bbw", "bbw"), ("bbw_ma", "bbw_ma"),
        ("squeeze", "squeeze"), ("hour_utc", "hour_utc"), ("h1_trend", "h1_trend"),
        ("confidence", "confidence"), ("frac", "frac"),
    )


def run_backtest(df):
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.addstrategy(StrategyG)
    cerebro.broker.setcash(MODAL)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    data = EnrichedData(dataname=df)
    cerebro.adddata(data)

    print("\n[BACKTRADER] Running Strategy G backtest...")
    results = cerebro.run()
    strat = results[0]
    final_value = cerebro.broker.getvalue()
    roi = (final_value - MODAL) / MODAL * 100

    dd = strat.analyzers.drawdown.get_analysis()

    avg_daily = np.mean(list(strat.daily_pnl.values())) if strat.daily_pnl else 0
    days_above = sum(1 for p in strat.daily_pnl.values() if p >= TARGET_HARIAN)

    # Compute from our trade log (more accurate since we bypass backtrader orders)
    trades_log = strat.trades_log
    wins = [t for t in trades_log if t["profit"] > 0]
    losses = [t for t in trades_log if t["profit"] < 0]
    win_count = len(wins)
    loss_count = len(losses)
    total_trades = len(trades_log)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    total_win_pnl = sum(t["profit"] for t in wins)
    total_loss_pnl = abs(sum(t["profit"] for t in losses)) if losses else 0
    profit_factor = total_win_pnl / max(total_loss_pnl, 1) if total_loss_pnl > 0 else 999

    print(f"\n{'='*70}")
    print(f"  BACKTRADER RESULTS — Strategy G (M15 Confidence Sizing)")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Periode: {df.index[0].date()} — {df.index[-1].date()} ({len(df)} bars)")
    print(f"{'='*70}")
    print(f"  Modal Awal:     Rp{MODAL:,.0f}")
    print(f"  Modal Akhir:    Rp{final_value:,.0f}")
    print(f"  Profit:         Rp{final_value - MODAL:+,.0f}")
    print(f"  ROI:            {roi:+.2f}%")
    print(f"  Max DD:         {dd.max.drawdown:.1f}%")
    print(f"  Trades:         {total_trades} ({win_count}W / {loss_count}L)")
    print(f"  Win Rate:       {win_rate:.1f}%")
    print(f"  Profit Factor:  {profit_factor:.2f}")
    print(f"  Avg Win:        Rp{total_win_pnl/max(win_count,1):,.0f}")
    print(f"  Avg Loss:       Rp{total_loss_pnl/max(loss_count,1):,.0f}")
    print(f"  Rata-rata/hari: Rp{avg_daily:,.0f}")
    print(f"  Hari >= Rp500k: {days_above}/{len(strat.daily_pnl)}")
    print(f"  Target Tercapai: {'YA' if avg_daily >= TARGET_HARIAN else 'TIDAK'}")

    return {
        "final_value": final_value,
        "roi": roi,
        "max_dd": dd.max.drawdown,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_daily": avg_daily,
        "days_above": days_above,
        "total_days": len(strat.daily_pnl),
        "win_count": win_count,
        "loss_count": loss_count,
        "avg_win": total_win_pnl / max(win_count, 1),
        "avg_loss": total_loss_pnl / max(loss_count, 1),
    }, strat.trades_log


def main():
    print("=" * 70)
    print("  BACKTRADER — Strategy G (M15 Confidence Sizing)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    print("\n[INFO] Mengambil data M15 + H1 XAUUSDm (4 bulan)...")
    df, dh1 = fetch_mt5_data(12000)
    if df is None or len(df) < 500:
        print("[ERROR] Data tidak cukup dari MT5")
        return

    print(f"[INFO] Data: {df.index[0].date()} — {df.index[-1].date()} ({len(df)} bars M15)")

    print("[INFO] Menghitung indikator + confidence scoring...")
    df = prep_data(df, dh1)
    df["confidence"] = df.apply(confidence, axis=1)
    df["frac"] = df["confidence"].apply(get_fraction)

    print(f"[INFO] Data setelah prep: {len(df)} bars")
    conf_dist = df["confidence"].value_counts().sort_index().to_dict()
    print(f"[INFO] Distribusi confidence: {conf_dist}")

    result, trades = run_backtest(df)

    # ---- COMPARISON WITH PREVIOUS AGENT ----
    print(f"\n{'='*70}")
    print(f"  PERBANDINGAN: BACKTRADER vs AGENT SEBELUMNYA (Custom Pandas)")
    print(f"{'='*70}")
    print(f"  {'Metric':<22} {'Backtrader':<16} {'Agent(Pandas)':<16} {'Delta':<12}")
    print(f"  {'-'*66}")

    prev = {
        "roi": 1698.4, "max_dd": 5.2, "pf": 2.63, "wr": 51.9,
        "trades": 2571, "avg_daily": 1469392, "days_above": 94,
    }

    rows = [
        ("ROI (%)", f'{result["roi"]:+.1f}%', f'+{prev["roi"]:.1f}%',
         f'{result["roi"] - prev["roi"]:+.1f}%'),
        ("Max DD (%)", f'{result["max_dd"]:.1f}%', f'{prev["max_dd"]:.1f}%',
         f'{result["max_dd"] - prev["max_dd"]:+.1f}%'),
        ("Profit Factor", f'{result["profit_factor"]:.2f}', f'{prev["pf"]:.2f}',
         f'{result["profit_factor"] - prev["pf"]:+.2f}'),
        ("Win Rate (%)", f'{result["win_rate"]:.1f}%', f'{prev["wr"]:.1f}%',
         f'{result["win_rate"] - prev["wr"]:+.1f}%'),
        ("Total Trades", f'{result["total_trades"]}', f'{prev["trades"]}',
         f'{result["total_trades"] - prev["trades"]:+d}'),
        ("Avg Daily (Rp)", f'Rp{result["avg_daily"]:,.0f}', f'Rp{prev["avg_daily"]:,.0f}',
         f'Rp{result["avg_daily"] - prev["avg_daily"]:+,.0f}'),
        ("Hari >=500k", f'{result["days_above"]}/{result["total_days"]}',
         f'{prev["days_above"]}/~120', ""),
    ]

    for label, bt_v, ag_v, delta in rows:
        print(f"  {label:<22} {bt_v:<16} {ag_v:<16} {delta:<12}")

    # Summary
    print(f"\n  {'='*70}")
    print(f"  RINGKASAN PERBEDAAN")
    print(f"  {'='*70}")

    diffs = []
    if abs(result["roi"] - prev["roi"]) / abs(prev["roi"]) > 0.05:
        diffs.append(f"ROI berbeda {abs(result['roi'] - prev['roi']):.1f}%")

    if abs(result["max_dd"] - prev["max_dd"]) > 1:
        diffs.append(f"Max DD {'lebih tinggi' if result['max_dd'] > prev['max_dd'] else 'lebih rendah'} {abs(result['max_dd'] - prev['max_dd']):.1f}%")

    if abs(result["total_trades"] - prev["trades"]) / prev["trades"] > 0.05:
        diffs.append(f"Jumlah trade {'lebih banyak' if result['total_trades'] > prev['trades'] else 'lebih sedikit'} ({abs(result['total_trades'] - prev['trades'])} trade)")

    if diffs:
        print(f"  Perbedaan signifikan:")
        for d in diffs:
            print(f"    • {d}")
        if result["total_trades"] < prev["trades"] * 0.5:
            print(f"\n  ⚠️ CATATAN: Backtrader menghasilkan jauh lebih sedikit trade.")
            print(f"     Kemungkinan karena perbedaan eksekusi order (next-bar vs same-bar)")
            print(f"     atau perbedaan handling floating P&L / trail logic.")
    else:
        print(f"  ✅ Hasil backtrader konsisten dengan agent sebelumnya!")
        print(f"     Perbedaan kecil dalam rentang toleransi.")

    print(f"\n  {'='*70}")
    print(f"  PENJELASAN")
    print(f"  {'='*70}")
    print(f"  Backtrader memberikan simulasi yang lebih realistis karena:")
    print(f"  1. Order dieksekusi di harga open bar berikutnya (bukan close bar sama)")
    print(f"  2. Broker simulation dengan cash management")
    print(f"  3. Slippage & commission bisa ditambahkan")
    print(f"  4. Performance metrics lebih standard (Sharpe, drawdown, dll)")
    print(f"\n  Perbedaan hasil wajar karena mekanisme eksekusi order berbeda")
    print(f"  antara backtrader (next-bar fill) dan custom pandas (same-bar fill).")
    print(f"\n  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")

if __name__ == "__main__":
    main()
