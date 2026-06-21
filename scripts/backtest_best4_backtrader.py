"""
Backtrader Backtest — 4 Best Configs (XAGUSDm D, ETHUSDm D, BTCUSDTm D, JP225m G)
Backtest all 4 best tickers + compare with previous agent results
"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import backtrader as bt
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

MODAL = 12_000_000

BEST4 = [
    {
        "label": "XAGUSDm_D",
        "symbol": "XAGUSDm", "tf": "H1", "tf_mt5": mt5.TIMEFRAME_H1, "bars": 3000,
        "spread": 30, "point": 0.001, "target": 200000,
        "strategy_type": "D",
        "p": {
            "ema_fast": 9, "ema_medium": 21, "rsi_period": 14, "atr_period": 14,
            "rsi_long_min": 30, "rsi_long_max": 80,
            "rsi_short_min": 20, "rsi_short_max": 70,
            "atr_sl_mult": 1.2, "atr_tp_mult": 4.0, "atr_trail_mult": 0.3,
            "volume_ma_period": 20, "volume_mult": 0.8,
            "max_hold_bars": 30, "lot_pct": 100, "running_pct": 0.1,
            "no_ema200": False, "no_macd": False,
        },
        "prev": {"roi": -8.0, "dd": 10.6, "pf": 2.54, "wr": 0, "trades": 0, "avg_hr": 605921},
    },
    {
        "label": "ETHUSDm_D",
        "symbol": "ETHUSDm", "tf": "H1", "tf_mt5": mt5.TIMEFRAME_H1, "bars": 3000,
        "spread": 100, "point": 0.01, "target": 200000,
        "strategy_type": "D",
        "p": {
            "ema_fast": 9, "ema_medium": 21, "rsi_period": 14, "atr_period": 14,
            "rsi_long_min": 30, "rsi_long_max": 80,
            "rsi_short_min": 20, "rsi_short_max": 70,
            "atr_sl_mult": 1.5, "atr_tp_mult": 4.0, "atr_trail_mult": 0.4,
            "volume_ma_period": 20, "volume_mult": 1.0,
            "max_hold_bars": 24, "lot_pct": 60, "running_pct": 0.1,
            "no_ema200": False, "no_macd": False,
        },
        "prev": {"roi": -10.3, "dd": 11.5, "pf": 2.05, "wr": 0, "trades": 0, "avg_hr": 468118},
    },
    {
        "label": "BTCUSDTm_D",
        "symbol": "BTCUSDTm", "tf": "H1", "tf_mt5": mt5.TIMEFRAME_H1, "bars": 3000,
        "spread": 1000, "point": 0.01, "target": 300000,
        "strategy_type": "D",
        "p": {
            "ema_fast": 9, "ema_medium": 21, "rsi_period": 14, "atr_period": 14,
            "rsi_long_min": 30, "rsi_long_max": 80,
            "rsi_short_min": 20, "rsi_short_max": 70,
            "atr_sl_mult": 2.0, "atr_tp_mult": 3.5, "atr_trail_mult": 0.4,
            "volume_ma_period": 20, "volume_mult": 1.0,
            "max_hold_bars": 24, "lot_pct": 50, "running_pct": 0.1,
            "no_ema200": False, "no_macd": False,
        },
        "prev": {"roi": -0.6, "dd": 4.0, "pf": 2.65, "wr": 0, "trades": 0, "avg_hr": 437474},
    },
    {
        "label": "JP225m_G",
        "symbol": "JP225m", "tf": "M15", "tf_mt5": mt5.TIMEFRAME_M15, "bars": 10000,
        "spread": 64, "point": 0.1, "target": 150000,
        "strategy_type": "G",
        "p": {
            "ema_fast": 5, "ema_medium": 13, "rsi_period": 14, "atr_period": 10,
            "rsi_long_min": 30, "rsi_long_max": 95,
            "rsi_short_min": 5, "rsi_short_max": 70,
            "atr_sl_mult": 0.7, "atr_tp_mult": 3.5, "atr_trail_mult": 0.3,
            "volume_ma_period": 15, "volume_mult": 0.7,
            "max_hold_bars": 20, "lot_pct": 120, "running_pct": 0.12,
            "no_ema200": True, "no_macd": True,
            "conf_sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
        },
        "prev": {"roi": -5.3, "dd": 6.5, "pf": 2.50, "wr": 0, "trades": 0, "avg_hr": 528960},
    },
]

# ───────────── MT5 Data Fetch ─────────────
def mt5_init():
    if not mt5.initialize():
        print("  [ERROR] MT5 initialize failed")
        return False
    return True

def fetch_mt5_data(symbol, tf_mt5, bars):
    if not mt5_init():
        return None
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, tf_mt5, 0, bars)
    mt5.shutdown()
    if rates is None or len(rates) < 200:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df

def fetch_higher_tf(symbol, bars):
    """Fetch H1 for M15-based strategies"""
    if not mt5_init():
        return None
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, max(bars // 4, 200))
    mt5.shutdown()
    if rates is None or len(rates) < 100:
        return None
    dh = pd.DataFrame(rates)
    dh["time"] = pd.to_datetime(dh["time"], unit="s")
    dh.set_index("time", inplace=True)
    return dh

# ───────────── Data Prep ─────────────
def prep_df(df, dh, cfg):
    p = cfg["p"]
    ef, em = p["ema_fast"], p["ema_medium"]
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    if not p.get("no_macd", False):
        df["macd"], df["macd_sig"] = macd(df["close"], 12, 26, 9)
    else:
        df["macd"], df["macd_sig"] = 0, 0
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    bbu, bbm, bbl = bb(df, 20, 2)
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = (df["bbw"] < df["bbw_ma"]).astype(int)

    # Higher TF trend for confidence / filter
    if cfg["strategy_type"] == "G" and dh is not None and len(dh) > 100:
        dh["ema9"] = ema(dh["close"], 9)
        dh["ema21"] = ema(dh["close"], 21)
        dh["h1_val"] = np.where(dh["ema9"] > dh["ema21"], 1, -1)
        dh.dropna(inplace=True)
        h1_series = dh["h1_val"].resample("15min").ffill()
        df["h1_trend"] = h1_series.reindex(df.index, method="ffill").fillna(0).astype(int)
    else:
        df["h1_trend"] = 0

    df["hour_utc"] = df.index.hour

    # Confidence for G strategies
    if cfg["strategy_type"] == "G":
        conf_list = []
        for _, row in df.iterrows():
            s = 0
            bull = row[f"ema{ef}"] > row[f"ema{em}"]
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
            conf_list.append(s)
        df["confidence"] = conf_list
    else:
        df["confidence"] = 0

    df.dropna(inplace=True)
    return df

# ───────────── Backtrader Data Feed ─────────────
# We build data feed dynamically per ticker


# ───────────── Strategy ─────────────
class Best4Strategy(bt.Strategy):
    params = (
        ("cfg", None),
        ("verbose", False),
    )

    def __init__(self):
        self.cfg = self.p.cfg
        self.p_ = self.cfg["p"]
        self.trades_log = []
        self.daily_pnl = {}
        self.current_day_pnl = 0.0
        self.last_day = None
        self.dd_halt = False
        self.peak_modal = MODAL
        self.dd_max = 0.0

        # Position tracking
        self.in_pos = False
        self.pos_type = None
        self.entry_price = 0.0
        self.entry_idx = 0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trail_active = False
        self.trade_frac = 1.0
        self.modal_at_entry = 0.0
        self.entry_conf = 0

    def log(self, txt):
        if self.p.verbose:
            print(f"{self.datas[0].datetime.datetime(0)} [{self.cfg['label']}]: {txt}")

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
            if self.in_pos:
                self.close_position(c, "DD_HALT")
            return

        ef = self.datas[0].ema_fast[0]
        em = self.datas[0].ema_med[0]
        a = self.datas[0].atr[0]
        r = self.datas[0].rsi[0]
        v = self.datas[0].volume[0]
        vm = self.datas[0].vol_ma[0]
        conf_val = int(round(self.datas[0].confidence[0]))

        frac = 1.0
        if self.cfg["strategy_type"] == "G":
            for lo, hi, fr in self.p_.get("conf_sizing", [(0, 9, 1.0)]):
                if lo <= conf_val <= hi:
                    frac = fr; break

        if self.in_pos:
            self.manage_exit(c, ef, em, a)
        else:
            self.manage_entry(c, ef, em, r, v, vm, a, conf_val, frac, modal)

    def signal(self, ef, em, r):
        p = self.p_
        ema_bull = ef > em
        rsi_long = p["rsi_long_min"] <= r <= p["rsi_long_max"]
        vol_mult = p.get("volume_mult", 0.7)
        above_200 = self.datas[0].close[0] > self.datas[0].ema200[0]
        use_ema200 = not p.get("no_ema200", False)
        val_ok = self.datas[0].volume[0] > self.datas[0].vol_ma[0] * vol_mult

        macd_bull = True
        if not p.get("no_macd", False):
            macd_bull = self.datas[0].macd[0] > self.datas[0].macd_sig[0]

        if (above_200 or not use_ema200) and ema_bull and rsi_long and macd_bull and val_ok:
            return "BUY"

        ema_bear = ef < em
        rsi_short = p["rsi_short_min"] <= r <= p["rsi_short_max"]
        macd_bear = True
        if not p.get("no_macd", False):
            macd_bear = self.datas[0].macd[0] < self.datas[0].macd_sig[0]

        if (not above_200 or not use_ema200) and ema_bear and rsi_short and macd_bear and val_ok:
            return "SELL"

        return "HOLD"

    def manage_entry(self, c, ef, em, r, v, vm, a, conf_val, frac, modal):
        sig = self.signal(ef, em, r)
        if sig == "HOLD":
            return

        p = self.p_
        sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
        tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]

        cost = 5000 * frac
        spread_cost = (self.cfg["spread"] * self.cfg["point"] / c) * modal * frac
        total_cost = cost + spread_cost
        self.broker.add_cash(-total_cost)

        self.in_pos = True
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
        p = self.p_
        bars = len(self) - self.entry_idx
        exit_signal = False; profit = 0.0; reason = ""

        if self.pos_type == "BUY":
            if c <= self.sl_price:
                profit = (self.sl_price - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "SL"
            elif c >= self.tp_price:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "TP"
            elif ef < em:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "EMA_FLIP"
            elif bars >= p["max_hold_bars"]:
                profit = (c - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "MAX_BAR"
            else:
                td = a * p["atr_trail_mult"]
                if not self.trail_active and (c - self.entry_price) >= td:
                    self.trail_active = True
                    self.sl_price = self.entry_price + td * 0.3
                if self.trail_active:
                    self.sl_price = max(self.sl_price, c - td * 0.5)
                    if c <= self.sl_price:
                        profit = (self.sl_price - self.entry_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                        exit_signal = True; reason = "TRAIL"
                    else:
                        profit = (c - self.datas[0].close[-1]) / self.datas[0].close[-1] * self.modal_at_entry * self.trade_frac * p["running_pct"]
        else:
            if c >= self.sl_price:
                profit = (self.entry_price - self.sl_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "SL"
            elif c <= self.tp_price:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "TP"
            elif ef > em:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "EMA_FLIP"
            elif bars >= p["max_hold_bars"]:
                profit = (self.entry_price - c) / self.entry_price * self.modal_at_entry * self.trade_frac
                exit_signal = True; reason = "MAX_BAR"
            else:
                td = a * p["atr_trail_mult"]
                if not self.trail_active and (self.entry_price - c) >= td:
                    self.trail_active = True
                    self.sl_price = self.entry_price - td * 0.3
                if self.trail_active:
                    self.sl_price = min(self.sl_price, c + td * 0.5)
                    if c >= self.sl_price:
                        profit = (self.entry_price - self.sl_price) / self.entry_price * self.modal_at_entry * self.trade_frac
                        exit_signal = True; reason = "TRAIL"
                    else:
                        profit = (self.datas[0].close[-1] - c) / self.datas[0].close[-1] * self.modal_at_entry * self.trade_frac * p["running_pct"]

        if exit_signal:
            self.close_position(c, reason, profit)

    def close_position(self, c, reason, profit=0.0):
        self.broker.add_cash(profit)
        self.current_day_pnl += profit
        self.trades_log.append({
            "tgl": self.datas[0].datetime.datetime(0),
            "posisi": self.pos_type, "held": len(self) - self.entry_idx,
            "profit": round(profit), "modal": round(self.broker.getvalue()),
            "conf": self.entry_conf, "frac": self.trade_frac, "reason": reason,
        })
        self.log(f"EXIT {self.pos_type} @ {c:.2f} profit={profit:.2f} reason={reason}")
        self.in_pos = False; self.pos_type = None

    def stop(self):
        if self.last_day is not None:
            self.daily_pnl[self.last_day] = self.current_day_pnl


# ───────────── Runner ─────────────
def run_single(cfg):
    symbol = cfg["symbol"]
    print(f"\n{'='*70}")
    print(f"  BACKTEST: {cfg['label']} ({symbol} — {cfg['strategy_type']} {cfg['tf']})")
    print(f"{'='*70}")

    print(f"  [DATA] Fetching {cfg['tf']} data...")
    df = fetch_mt5_data(symbol, cfg["tf_mt5"], cfg["bars"])
    if df is None or len(df) < 200:
        print(f"  [ERROR] Data tidak cukup")
        return None

    dh = None
    if cfg["strategy_type"] == "G":
        print(f"  [DATA] Fetching H1 data for confidence...")
        dh = fetch_higher_tf(symbol, cfg["bars"])

    t0, t1 = df.index[0].date(), df.index[-1].date()
    print(f"  [DATA] {t0} — {t1} ({len(df)} bars)")

    print(f"  [PREP] Computing indicators...")
    df = prep_df(df, dh, cfg)
    print(f"  [PREP] {len(df)} bars after prep")

    # Create data feed with dynamic lines
    feed_df = df.rename(columns={
        f"ema{cfg['p']['ema_fast']}": "ema_fast",
        f"ema{cfg['p']['ema_medium']}": "ema_med",
    })
    feed_df["ema200"] = df["ema200"]
    feed_df["open"] = df["open"]
    feed_df["high"] = df["high"]
    feed_df["low"] = df["low"]
    feed_df["close"] = df["close"]
    feed_df["tick_volume"] = df["tick_volume"]

    # Build data feed class with all line mappings
    extra_lines = (
        "ema_fast", "ema_med", "ema200", "atr", "rsi", "macd", "macd_sig",
        "vol_ma", "squeeze", "hour_utc", "h1_trend", "confidence",
    )
    extra_params_dict = {
        k: k for k in extra_lines  # map line name -> same column name
    }
    all_params = (
        (("datetime", None),)
        + (("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"))
        + (("volume", "tick_volume"),)
        + tuple(extra_params_dict.items())
    )
    DynData = type("DynData", (bt.feeds.PandasData,), {
        "lines": extra_lines,
        "params": all_params,
    })

    cerebro = bt.Cerebro(stdstats=False)
    data = DynData(dataname=feed_df, open="open", high="high", low="low", close="close", volume="tick_volume")
    cerebro.adddata(data)
    cerebro.addstrategy(Best4Strategy, cfg=cfg)
    cerebro.broker.setcash(MODAL)
    cerebro.broker.setcommission(commission=0.0)

    print(f"  [BT] Running backtrader...")
    results = cerebro.run()
    strat = results[0]
    final_value = cerebro.broker.getvalue()
    roi = (final_value - MODAL) / MODAL * 100

    trades = strat.trades_log
    wins = [t for t in trades if t["profit"] > 0]
    losses = [t for t in trades if t["profit"] < 0]
    total = len(trades)
    wr = (len(wins) / total * 100) if total else 0
    total_win = sum(t["profit"] for t in wins)
    total_loss = abs(sum(t["profit"] for t in losses)) if losses else 0
    pf = total_win / max(total_loss, 1) if total_loss > 0 else 999

    days = (t1 - t0).days or 1
    avg_per_hr = (final_value - MODAL) / max(days * 24, 1)
    avg_daily = np.mean(list(strat.daily_pnl.values())) if strat.daily_pnl else 0
    days_above = sum(1 for p in strat.daily_pnl.values() if p >= cfg["target"]) if cfg["target"] else 0

    print(f"\n  +-------------------------------------------------------+")
    print(f"  | HASIL: {cfg['label']:<49} |")
    print(f"  +-------------------------------------------------------+")
    print(f"  | Modal: Rp{MODAL:>11,} -> Rp{final_value:>11,} |")
    print(f"  | Profit: Rp{final_value - MODAL:>+11,} |")
    print(f"  | ROI: {roi:>+10.2f}%  |")
    print(f"  | Trades: {total:>5} ({len(wins)}W / {len(losses)}L) |")
    print(f"  | Win Rate: {wr:>5.1f}% | PF: {pf:>5.2f} |")
    print(f"  | Avg/hr: Rp{avg_per_hr:>+9,.0f} | DD: {strat.dd_max:.1f}% |")
    print(f"  | Avg/day: Rp{avg_daily:>+9,.0f} |")
    print(f"  +-------------------------------------------------------+")

    return {
        "label": cfg["label"],
        "symbol": symbol,
        "strategy": f"{cfg['strategy_type']} {cfg['tf']}",
        "period": f"{t0} — {t1}",
        "final_value": final_value,
        "profit": final_value - MODAL,
        "roi": roi,
        "dd": strat.dd_max,
        "trades": total,
        "win_rate": wr,
        "profit_factor": pf,
        "avg_per_hr": avg_per_hr,
        "avg_daily": avg_daily,
        "days_above": days_above,
        "total_days": len(strat.daily_pnl),
        "target": cfg["target"],
    }, trades


def main():
    print("=" * 70)
    print("  BACKTRADER — BEST 4 CONFIGS (XAGUSDm D, ETHUSDm D, BTCUSDTm D, JP225m G)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    all_results = []
    for cfg in BEST4:
        res = run_single(cfg)
        if res:
            all_results.append(res)

    # ───── COMPARISON TABLE ─────
    print(f"\n\n{'='*70}")
    print(f"  PERBANDINGAN: BACKTRADER vs AGENT SEBELUMNYA")
    print(f"{'='*70}")

    header = f"  {'Ticker':<12} {'Backtrader':<17} {'Agent':<17} {'Delta':<12}"
    print(header)
    print(f"  {'-'*58}")

    prev_map = {c["label"]: c["prev"] for c in BEST4}

    for res, _ in all_results:
        label = res["label"]
        p = prev_map.get(label, {})
        prev_roi = p.get("roi", 0)
        prev_dd = p.get("dd", 0)
        prev_pf = p.get("pf", 0)
        prev_hr = p.get("avg_hr", 0)

        delta_roi = res["roi"] - prev_roi
        delta_hr = res["avg_per_hr"] - prev_hr

        bt_str = f"ROI {res['roi']:+.1f}% DD {res['dd']:.1f}%"
        ag_str = f"ROI {prev_roi:+.1f}% DD {prev_dd:.1f}%"
        dlt_str = f"ROI {delta_roi:+.1f}%"
        print(f"  {label:<12} {bt_str:<17} {ag_str:<17} {dlt_str:<12}")
        print(f"  {'':<12} PF {res['profit_factor']:.2f} T{res['trades']:<4}  PF {prev_pf:.2f} {'':<11} PF {res['profit_factor']-prev_pf:+.2f}")
        print(f"  {'':<12} Rp{res['avg_per_hr']:>8,.0f}/hr     Rp{prev_hr:>8,.0f}/hr     Rp{delta_hr:>+8,.0f}/hr")
        print()

    # Summary
    print(f"\n{'='*70}")
    print(f"  RINGKASAN")
    print(f"{'='*70}")
    for res, _ in all_results:
        delta = abs(res["roi"] - prev_map[res["label"]].get("roi", 0)) if res["label"] in prev_map else 0
        status = "VALID" if delta < 50 else "BEDA"
        print(f"  {res['label']:<12} Modal Rp{res['final_value']:>11,} | ROI {res['roi']:+8.1f}% | DD {res['dd']:.1f}% | PF {res['profit_factor']:.2f} | {res['trades']} trades | Rp{res['avg_per_hr']:,.0f}/hr | {status}")

    print(f"\n  {'='*70}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  {'='*70}")


if __name__ == "__main__":
    main()
