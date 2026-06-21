import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json, glob
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timezone
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

# ============================================================
# LOAD TICKER CONFIG DARI FILE JSON
# ============================================================
TICKERS = []
config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "tickers")
for fpath in sorted(glob.glob(os.path.join(config_dir, "ticker_*.json"))):
    with open(fpath) as f:
        cfg = json.load(f)
        TICKERS.append({
            "name": cfg["name"],
            "spread": cfg["spread"],
            "point": cfg["point"],
            "modal": cfg["modal"],
            "target": cfg["target_harian"],
        })
        print(f"  [CONFIG] Loaded {cfg['name']} (spread {cfg['spread']}pts, target Rp{cfg['target_harian']:,})")

# ============================================================
# MAP STRATEGY LABEL -> BACKTEST LOGIC
# ============================================================
# Untuk A/B/C: D1/H4 sederhana (SMA/EMA cross + RSI)
# Untuk D/F/G/H: EMA cross + RSI + MACD (existing logic)
STRATEGY_MAP = {
    "a": {"name": "A D1 Long Bias",   "tf": "D1", "tf_mt5": mt5.TIMEFRAME_D1,  "bars": 1000,  "dd_limit": 20},
    "b": {"name": "B H4 EMA Cross",   "tf": "H4", "tf_mt5": mt5.TIMEFRAME_H4,  "bars": 2000,  "dd_limit": 25},
    "c": {"name": "C H4 PSAR",        "tf": "H4", "tf_mt5": mt5.TIMEFRAME_H4,  "bars": 2000,  "dd_limit": 25},
    "d": {"name": "D H1 Confluence",  "tf": "H1", "tf_mt5": mt5.TIMEFRAME_H1,  "bars": 3000,  "dd_limit": 20},
    "e": {"name": "E H1 Donchian",    "tf": "H1", "tf_mt5": mt5.TIMEFRAME_H1,  "bars": 3000,  "dd_limit": 20},
    "f": {"name": "F M15 Turbo",      "tf": "M15","tf_mt5": mt5.TIMEFRAME_M15, "bars": 10000, "dd_limit": 25},
    "g": {"name": "G M15 Confidence", "tf": "M15","tf_mt5": mt5.TIMEFRAME_M15, "bars": 10000, "dd_limit": 25},
}

# Load strategies per ticker from config/{ticker_name}/*.json
TICKER_STRATEGIES = {}
ticker_config_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
for ticker in TICKERS:
    name = ticker["name"]
    ticker_dir = os.path.join(ticker_config_base, name)
    strategies = []
    if os.path.isdir(ticker_dir):
        for fpath in sorted(glob.glob(os.path.join(ticker_dir, "strategy_*.json"))):
            fname = os.path.basename(fpath)
            label = fname.replace("strategy_", "").replace(".json", "")
            if label in STRATEGY_MAP:
                with open(fpath) as f:
                    cfg = json.load(f)
                base = dict(STRATEGY_MAP[label])
                base["label"] = label
                base["config"] = cfg.get("params", {})
                base["display_name"] = cfg.get("name", base["name"])
                # Normalisasi parameter A/B/C ke format unified
                params = base["config"]
                if label == "a":
                    params.setdefault("ema_fast", 5)
                    params.setdefault("ema_medium", 13)
                    params.setdefault("rsi_long_min", 30)
                    params.setdefault("rsi_long_max", 80)
                    params.setdefault("rsi_short_min", 0)
                    params.setdefault("rsi_short_max", 0)
                    params.setdefault("atr_sl_mult", params.pop("atr_pullback", 2.0))
                    params.setdefault("atr_tp_mult", params.pop("atr_stop", 3.0))
                    params.setdefault("atr_trail_mult", 0.5)
                    params.setdefault("volume_ma_period", 20)
                    params.setdefault("volume_mult", 1.0)
                    params.setdefault("max_hold_bars", params.pop("max_hold_days", 90) * 24)
                    params.setdefault("lot_pct", 200)
                    params.setdefault("running_pct", params.get("running_pct", 0.05))
                    params["no_ema200"] = True
                    params["no_macd"] = True
                elif label == "b":
                    params.setdefault("ema_fast", params.pop("ema_fast", 10))
                    params.setdefault("ema_medium", params.pop("ema_slow", 30))
                    params.setdefault("rsi_long_min", params.pop("rsi_min", 20))
                    params.setdefault("rsi_long_max", params.pop("rsi_max", 80))
                    params.setdefault("rsi_short_min", 20)
                    params.setdefault("rsi_short_max", 80)
                    params.setdefault("atr_sl_mult", params.pop("sl_atr", 1.5))
                    params.setdefault("atr_tp_mult", params.pop("tp_atr", 3.0))
                    params.setdefault("atr_trail_mult", 0.5)
                    params.setdefault("volume_ma_period", 20)
                    params.setdefault("volume_mult", params.pop("vol_factor", 1.2))
                    params.setdefault("max_hold_bars", params.get("max_hold_bars", 40))
                    params.setdefault("lot_pct", params.get("lot_pct", 350))
                    params.setdefault("running_pct", params.get("running_pct", 0.05))
                    params["no_ema200"] = True
                    params["no_macd"] = False
                elif label == "c":
                    params.setdefault("ema_fast", 10)
                    params.setdefault("ema_medium", 30)
                    params.setdefault("rsi_long_min", 20)
                    params.setdefault("rsi_long_max", 80)
                    params.setdefault("rsi_short_min", 20)
                    params.setdefault("rsi_short_max", 80)
                    params.setdefault("atr_sl_mult", params.pop("sl_atr", 2.5))
                    params.setdefault("atr_tp_mult", 5.0)
                    params.setdefault("atr_trail_mult", 0.5)
                    params.setdefault("volume_ma_period", 20)
                    params.setdefault("volume_mult", 1.0)
                    params.setdefault("max_hold_bars", params.get("max_hold_bars", 50))
                    params.setdefault("lot_pct", params.get("lot_pct", 250))
                    params.setdefault("running_pct", params.get("running_pct", 0.05))
                    params["no_ema200"] = True
                    params["no_macd"] = True
                # Normalisasi key names: no_macd_filter -> no_macd, no_ema200_filter -> no_ema200
                if "no_macd_filter" in params:
                    params["no_macd"] = params.pop("no_macd_filter")
                if "no_ema200_filter" in params:
                    params["no_ema200"] = params.pop("no_ema200_filter")
                # Normalisasi confidence_sizing untuk strategy G
                if label == "g":
                    cs = params.get("confidence_sizing", {})
                    if cs.get("enabled"):
                        raw = cs.get("thresholds", [])
                        params["conf_sizing"] = [(t["min_conf"], t["max_conf"], t["fraction"]) for t in raw]
                    else:
                        params["conf_sizing"] = [(0, 9, 1.0)]
                strategies.append(base)
    TICKER_STRATEGIES[name] = strategies
    print(f"  [CONFIG] {name}: {len(strategies)} strategies loaded ({', '.join(s['label'] for s in strategies)})")

# ============================================================
# DATA FETCHING
# ============================================================
def fetch_data(symbol, timeframe, bars):
    if not mt5.initialize():
        return None, None
    mt5.symbol_select(symbol, True)

    # Main timeframe data
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    # Higher timeframe for confidence strategies
    if timeframe == 1:  # H1 -> need H4
        tf_higher = 3
        rates_h = mt5.copy_rates_from_pos(symbol, tf_higher, 0, max(bars // 4, 200))
    elif timeframe == 2:  # M15 -> need H1
        tf_higher = 1
        rates_h = mt5.copy_rates_from_pos(symbol, tf_higher, 0, max(bars // 4, 200))
    else:
        rates_h = None

    mt5.shutdown()

    if rates is None or len(rates) < 200:
        return None, None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)

    dh = None
    if rates_h is not None:
        dh = pd.DataFrame(rates_h)
        dh["time"] = pd.to_datetime(dh["time"], unit="s")
        dh.set_index("time", inplace=True)

    return df, dh


# ============================================================
# PREP FUNCTIONS (per strategy type)
# ============================================================
def prep_simple(df, p, label):
    """Untuk semua strategi"""
    ef = p["ema_fast"]; em = p["ema_medium"]
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], p.get("ema_trend", 50))
    df["ema200"] = ema(df["close"], p.get("ema_major", 200))
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    if not p.get("no_macd", False):
        df["macd"], df["macd_sig"] = macd(df["close"], p.get("macd_fast", 12), p.get("macd_slow", 26), p.get("macd_signal", 9))
    else:
        df["macd"] = 0; df["macd_sig"] = 0
    # BB untuk mean reversion / range detection
    bbu, bbm, bbl = bb(df, p.get("bb_period", 20), p.get("bb_std", 2))
    df["bbu"] = bbu; df["bbm"] = bbm; df["bbl"] = bbl
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    df.dropna(inplace=True)
    return df

def prep_confidence(df, dh, p, label):
    """Untuk strategi G (M15 + H1)"""
    ef = p.get("ema_fast", 5)
    em = p.get("ema_medium", 13)
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], p.get("ema_trend", 50))
    df["ema200"] = ema(df["close"], p.get("ema_major", 200))
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    bbu, bbm, bbl = bb(df, p.get("bb_period", 20), p.get("bb_std", 2))
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour

    df["trend_h"] = "NEUTRAL"
    if dh is not None and len(dh) > 100:
        dh["ema9"] = ema(dh["close"], 9)
        dh["ema21"] = ema(dh["close"], 21)
        dh["trend_h"] = np.where(dh["ema9"] > dh["ema21"], "UP", "DOWN")
        dh.dropna(inplace=True)
        if len(dh) > 50:
            if label == "G":
                resample = "15min"
            else:
                resample = "1h"
            trend_series = dh["trend_h"].resample(resample).ffill()
            trend_reindexed = trend_series.reindex(df.index, method="ffill")
            df.loc[trend_reindexed.notna(), "trend_h"] = trend_reindexed[trend_reindexed.notna()]

    df.dropna(inplace=True)
    return df


# ============================================================
# SIGNAL FUNCTIONS — unified untuk semua strategy
# ============================================================
def signal_any(df, i, p):
    row = df.iloc[i]; c = row["close"]
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    ema_bull = row[ef] > row[em]
    ema_bear = row[ef] < row[em]
    above_200 = c > row["ema200"]

    use_ema200 = not p.get("no_ema200", False)
    use_macd = not p.get("no_macd", False)
    mode_mr = p.get("mode", "trend") == "meanrev"

    rsi_long = p.get("rsi_long_min", 30) <= row.get("rsi", 50) <= p.get("rsi_long_max", 80)
    rsi_short = p.get("rsi_short_min", 20) <= row.get("rsi", 50) <= p.get("rsi_short_max", 80)
    rsi_os = row.get("rsi", 50) <= p.get("rsi_oversold", 25)
    rsi_ob = row.get("rsi", 50) >= p.get("rsi_overbought", 75)

    macd_bull = (not use_macd) or (row.get("macd", 0) > row.get("macd_sig", 0))
    macd_bear = (not use_macd) or (row.get("macd", 0) < row.get("macd_sig", 0))
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("volume_mult", 1.0)

    if mode_mr:
        # Mean reversion: touch BB outer bands + RSI extreme + volume
        mr_buf = p.get("mr_atr_buffer", 0.5) * row["atr"]
        near_lower = c <= row["bbl"] + mr_buf
        near_upper = c >= row["bbu"] - mr_buf
        if near_lower and ema_bear and rsi_os and vol_ok:
            return "BUY"
        if near_upper and ema_bull and rsi_ob and vol_ok:
            return "SELL"
    else:
        # Trend following
        if (above_200 or not use_ema200) and ema_bull and rsi_long and macd_bull and vol_ok:
            return "BUY"
        if (not above_200 or not use_ema200) and ema_bear and rsi_short and macd_bear and vol_ok:
            return "SELL"

    return "HOLD"

def confidence_G(row):
    s = 0
    bull = row.get("ema5", row.get("ema9", 0)) > row.get("ema13", row.get("ema21", 1))
    h = row.get("trend_h", "NEUTRAL")
    if (bull and h == "UP") or (not bull and h == "DOWN"):
        s += 2
    if row["squeeze"]: s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2: s += 1
    if bull and row["rsi"] > 65: s += 1
    if not bull and row["rsi"] < 35: s += 1
    if 7 <= row["hour_utc"] < 15: s += 1
    return s

def signal_H(df, i, p):
    row = df.iloc[i]
    ef, emTag = f"ema{p['ema_fast']}", f"ema{p['ema_medium']}"
    ema_bull = row[ef] > row[emTag]
    rsi_ok = 40 <= row["rsi"] <= 80
    vol_ok = row["tick_volume"] > row["vol_ma"] * 0.8
    if ema_bull and rsi_ok and vol_ok:
        return "BUY"
    ema_bear = row[ef] < row[emTag]
    rsi_short = 20 <= row["rsi"] <= 60
    if ema_bear and rsi_short and vol_ok:
        return "SELL"
    return "HOLD"

def confidence_H(row):
    s = 0
    bull = row["ema9"] > row["ema21"]
    h = row.get("trend_h", "NEUTRAL")
    if (bull and h == "UP") or (not bull and h == "DOWN"):
        s += 2
    if row["squeeze"]: s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2: s += 1
    if bull and row["rsi"] > 75: s += 1
    if not bull and row["rsi"] < 25: s += 1
    if 7 <= row["hour_utc"] < 14: s += 1
    if (bull and row["close"] > row["ema200"]) or (not bull and row["close"] < row["ema200"]):
        s += 1
    return s

def get_fraction(conf, sizing):
    for lo, hi, frac in sizing:
        if lo <= conf <= hi:
            return frac
    return 1.0


# ============================================================
# BACKTEST ENGINE
# ============================================================
def backtest(df, strat_cfg, ticker_cfg, strategy_label):
    p = strat_cfg
    modal = float(ticker_cfg["modal"])
    spread_pts = ticker_cfg["spread"]
    point_val = ticker_cfg["point"]
    peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_start_equity = modal; modal_at_entry = 0.0
    unrealized_pnl = 0.0
    is_confidence = strategy_label == "g"
    conf_fn = confidence_G if strategy_label == "g" else confidence_H
    ef_tag = f"ema{p['ema_fast']}"; em_tag = f"ema{p['ema_medium']}"

    start_idx = 50 if not is_confidence else 50
    for i in range(start_idx, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef_val = df[ef_tag].iloc[i]; em_val = df[em_tag].iloc[i]
        sig = signal_any(df, i, p)
        day = df.index[i].date()

        if current_day is None:
            current_day = day
            day_start_equity = modal + unrealized_pnl
        if day != current_day:
            equity = modal + unrealized_pnl
            daily_pnl[current_day] = equity - day_start_equity
            current_day = day
            day_start_equity = equity

        equity = modal + unrealized_pnl
        if equity > peak: peak = equity
        dd = (peak - equity) / peak * 100; dd_max = max(dd_max, dd)
        if dd > p["dd_limit"]: unrealized_pnl = 0.0; in_trade = False; posisi = None; continue

        if is_confidence:
            conf = conf_fn(df.iloc[i])
            frac = get_fraction(conf, p["conf_sizing"])
        else:
            conf = 0; frac = 1.0

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail = False
                unrealized_pnl = 0.0
                modal -= 5000 * frac
                spread_cost = (spread_pts * point_val / entry_price) * modal
                modal -= spread_cost * frac
                modal_at_entry = modal
                trade_frac = frac
                in_trade = True
        else:
            bars = i - entry_idx; exit = False
            position_value = modal_at_entry * trade_frac
            if posisi == "BUY":
                unrealized_pnl = (c - entry_price) / entry_price * position_value
                if c <= sl_price: exit = True
                elif c >= tp_price: exit = True
                elif ef_val < em_val: exit = True
                elif bars >= p["max_hold_bars"]: exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
            else:
                unrealized_pnl = (entry_price - c) / entry_price * position_value
                if c >= sl_price: exit = True
                elif c <= tp_price: exit = True
                elif ef_val > em_val: exit = True
                elif bars >= p["max_hold_bars"]: exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)

            if exit:
                modal += unrealized_pnl
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(unrealized_pnl), "modal": round(modal), "conf": conf, "frac": trade_frac})
                unrealized_pnl = 0.0; in_trade = False; posisi = None

    if current_day:
        daily_pnl[current_day] = (modal + unrealized_pnl) - day_start_equity
    return modal, dd_max, trades, daily_pnl


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 90)
    print("  BACKTEST MULTI-TICKER — SEMUA STRATEGI × SEMUA TICKER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 90)

    all_results = []

    for ticker in TICKERS:
        sym = ticker["name"]
        print(f"\n{'='*90}")
        print(f"  >> TICKER: {sym} (spread {ticker['spread']} pts, modal Rp{ticker['modal']:,})")
        print(f"{'='*90}")

        strategies = TICKER_STRATEGIES.get(sym, [])
        if not strategies:
            print("  (TIDAK ADA STRATEGI TERDAFTAR)")
            continue

        for sc in strategies:
            label = sc["label"]
            name = sc.get("display_name", sc["name"])
            tf = sc["tf"]
            print(f"\n  --- {name} ({tf}) ---", end=" ")

            # Params: merge config file params (if any) with defaults
            p = dict(sc)
            p.update(sc.get("config", {}))

            # Fetch data
            df, dh = fetch_data(sym, sc["tf_mt5"], sc["bars"])
            if df is None or len(df) < 200:
                print("DATA TIDAK CUKUP")
                continue

            t0, t1 = df.index[0].date(), df.index[-1].date()
            days = (t1 - t0).days
            print(f"periode {t0} sd {t1} ({days} hr, {len(df)} bars)", end=" ")

            # Prep
            try:
                if label == "g":
                    df = prep_confidence(df, dh, p, "G")
                else:
                    df = prep_simple(df, p, label)
            except Exception as e:
                print(f"PREP ERROR: {e}")
                continue

            if len(df) < 100:
                print("DATA AFTER PREP TIDAK CUKUP")
                continue


            # Backtest
            try:
                modal_akhir, dd_max, trades, daily_pnl = backtest(df, p, ticker, label)
            except Exception as e:
                print(f"BT ERROR: {e}")
                import traceback; traceback.print_exc()
                continue

            win = [t for t in trades if t["profit"] > 0]
            loss = [t for t in trades if t["profit"] < 0]
            pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
            roi = (modal_akhir - ticker["modal"]) / ticker["modal"] * 100
            avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
            avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
            days_above = sum(1 for p in daily_pnl.values() if p >= ticker["target"])

            all_results.append({
                "ticker": sym, "spread": ticker["spread"],
                "strategy": name, "tf": tf,
                "days": days, "trades": len(trades),
                "roi": roi, "dd": dd_max, "pf": pf,
                "avg_daily": avg_daily, "target": ticker["target"],
                "days_above": days_above, "total_days": len(daily_pnl),
                "win_rate": len(win) / max(len(trades), 1) * 100,
                "avg_hold": avg_hold,
            })

            status = "OK" if avg_daily >= ticker["target"] else "NO"
            print(f"  -> ROI {roi:+.1f}% DD {dd_max:.1f}% PF {pf:.2f} "
                  f"Rp{avg_daily:,.0f}/hari (target Rp{ticker['target']:,}) {status} "
                  f"| {len(trades)} trades WR {len(win)/max(len(trades),1)*100:.0f}%")

    # ============================================================
    # SUMMARY TABLE
    # ============================================================
    print("\n\n")
    print("=" * 90)
    print("  RINGKASAN HASIL BACKTEST")
    print("=" * 90)

    header = f"{'Ticker':<10} {'Strategi':<20} {'TF':<5} {'ROI':>8} {'DD':>6} {'PF':>5} {'Rp/hari':>12} {'Target':>10} {'Status':>8} {'Trades':>7} {'WR':>5} {'Hari':>6}"
    print(header)
    print("-" * 90)

    for r in sorted(all_results, key=lambda x: x["avg_daily"], reverse=True):
        status = "OK" if r["avg_daily"] >= r["target"] else "NO"
        target_str = f"Rp{r['target']:,}"
        avg_str = f"Rp{r['avg_daily']:,.0f}"
        days_str = f"{r['days_above']}/{r['total_days']}"
        print(f"{r['ticker']:<10} {r['strategy']:<20} {r['tf']:<5} "
              f"{r['roi']:>+7.1f}% {r['dd']:>5.1f}% {r['pf']:>4.2f} "
              f"{avg_str:>12} {target_str:>10} {status:>8} {r['trades']:>5d} {r['win_rate']:>4.0f}% {days_str:>6}")

    # Best per ticker
    print("\n\n")
    print("=" * 90)
    print("  BEST STRATEGY PER TICKER")
    print("=" * 90)
    for ticker in TICKERS:
        sym = ticker["name"]
        best = [r for r in all_results if r["ticker"] == sym]
        if not best: continue
        best.sort(key=lambda x: x["avg_daily"], reverse=True)
        b = best[0]
        print(f"  {sym:<10} -> {b['strategy']:<20} Rp{b['avg_daily']:,.0f}/hari | ROI {b['roi']:+.1f}% | DD {b['dd']:.1f}%")

    # Kesimpulan
    print("\n\n")
    print("=" * 90)
    print("  KESIMPULAN & REKOMENDASI")
    print("=" * 90)
    total_best = [r for r in all_results if r["avg_daily"] >= r["target"]]
    if total_best:
        print(f"  Strategi yang mencapai target:")
        for r in sorted(total_best, key=lambda x: x["avg_daily"], reverse=True):
            print(f"    OK {r['ticker']:<10} {r['strategy']:<20} -> Rp{r['avg_daily']:,.0f}/hari "
                  f"(target Rp{r['target']:,}) ROI {r['roi']:+.1f}% DD {r['dd']:.1f}%")
    else:
        print("  NO - BELUM ADA strategi yang mencapai target di periode ini")

    print(f"\n  {'='*90}")
    print(f"  DETAIL LENGKAP ADA DI ATAS — {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  {'='*90}")

if __name__ == "__main__":
    main()
