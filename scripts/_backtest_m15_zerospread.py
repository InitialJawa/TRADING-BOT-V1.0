import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

TICKERS = [
    {"name": "BTCUSDTm", "spread": 0, "point": 1.0,    "modal": 12000000, "target": 200000},
    {"name": "ETHUSDm",  "spread": 0, "point": 0.1,    "modal": 12000000, "target": 100000},
]

# Test 2 periods: 4 bulan terakhir, dan 4 bulan sebelumnya
PERIODS = [
    ("4 BULAN TERAKHIR", datetime.now() - timedelta(days=125), datetime.now()),
    ("4 BULAN SEBELUMNYA", datetime.now() - timedelta(days=250), datetime.now() - timedelta(days=125)),
]

STRATEGIES = ["e", "f", "g"]
STRAT_NAMES = {"e": "E M15 Momentum", "f": "F M15 Turbo", "g": "G M15 Confidence"}

STRAT_PARAMS = {
    "e": {
        "dd_limit": 25,
        "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
        "rsi_period": 14, "rsi_long_min": 35, "rsi_long_max": 82,
        "rsi_short_min": 18, "rsi_short_max": 65,
        "atr_period": 10, "atr_sl_mult": 0.7, "atr_tp_mult": 1.8, "atr_trail_mult": 0.4,
        "volume_ma_period": 15, "volume_mult": 0.7, "max_hold_bars": 16,
        "running_pct": 0.08, "no_ema200": True, "no_macd": False,
    },
    "f": {
        "dd_limit": 25,
        "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
        "rsi_period": 14, "rsi_long_min": 30, "rsi_long_max": 95,
        "rsi_short_min": 5, "rsi_short_max": 70,
        "atr_period": 10, "atr_sl_mult": 0.5, "atr_tp_mult": 2.2, "atr_trail_mult": 0.3,
        "volume_ma_period": 15, "volume_mult": 0.7, "max_hold_bars": 20,
        "running_pct": 0.12, "no_ema200": True, "no_macd": True,
    },
    "g": {
        "dd_limit": 25,
        "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
        "rsi_period": 14, "rsi_long_min": 30, "rsi_long_max": 95,
        "rsi_short_min": 5, "rsi_short_max": 70,
        "atr_period": 10, "atr_sl_mult": 0.5, "atr_tp_mult": 2.2, "atr_trail_mult": 0.3,
        "volume_ma_period": 15, "volume_mult": 0.7, "max_hold_bars": 20,
        "running_pct": 0.12, "no_ema200": True, "no_macd": True,
        "conf_sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 6, 2.0)],
    },
}

def fetch_data_range(symbol, timeframe, dt_from, dt_to):
    if not mt5.initialize():
        return None, None
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_range(symbol, timeframe, dt_from, dt_to)
    if timeframe == mt5.TIMEFRAME_M15:
        rates_h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, dt_from, dt_to)
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

def prep_simple(df, p):
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
    bbu, bbm, bbl = bb(df)
    df["bbu"] = bbu; df["bbm"] = bbm; df["bbl"] = bbl
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    df.dropna(inplace=True)
    return df

def prep_confidence(df, dh, p):
    ef = p.get("ema_fast", 5); em = p.get("ema_medium", 13)
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], p.get("ema_trend", 50))
    df["ema200"] = ema(df["close"], p.get("ema_major", 200))
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    bbu, bbm, bbl = bb(df)
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
            tr = dh["trend_h"].resample("15min").ffill()
            trr = tr.reindex(df.index, method="ffill")
            df.loc[trr.notna(), "trend_h"] = trr[trr.notna()]
    df.dropna(inplace=True)
    return df

def signal_any(df, i, p):
    row = df.iloc[i]; c = row["close"]
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    ema_bull = row[ef] > row[em]
    ema_bear = row[ef] < row[em]
    use_ema200 = not p.get("no_ema200", False)
    use_macd = not p.get("no_macd", False)
    rsi_long = p.get("rsi_long_min", 30) <= row.get("rsi", 50) <= p.get("rsi_long_max", 80)
    rsi_short = p.get("rsi_short_min", 20) <= row.get("rsi", 50) <= p.get("rsi_short_max", 80)
    macd_bull = (not use_macd) or (row.get("macd", 0) > row.get("macd_sig", 0))
    macd_bear = (not use_macd) or (row.get("macd", 0) < row.get("macd_sig", 0))
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("volume_mult", 1.0)
    above_200 = c > row["ema200"]
    if (above_200 or not use_ema200) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    if (not above_200 or not use_ema200) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def confidence_G(row):
    s = 0
    bull = row["ema5"] > row["ema13"]
    h = row.get("trend_h", "NEUTRAL")
    if (bull and h == "UP") or (not bull and h == "DOWN"): s += 2
    if row["squeeze"]: s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2: s += 1
    if bull and row["rsi"] > 65: s += 1
    if not bull and row["rsi"] < 35: s += 1
    if 7 <= row["hour_utc"] < 15: s += 1
    return s

def get_fraction(conf, sizing):
    for lo, hi, frac in sizing:
        if lo <= conf <= hi: return frac
    return 1.0

def backtest(df, p, ticker_cfg, label):
    modal = float(ticker_cfg["modal"])
    spread_pts = ticker_cfg["spread"]
    point_val = ticker_cfg["point"]
    peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0
    is_confidence = label == "g"
    ef_tag = f"ema{p['ema_fast']}"; em_tag = f"ema{p['ema_medium']}"

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef_val = df[ef_tag].iloc[i]; em_val = df[em_tag].iloc[i]
        sig = signal_any(df, i, p)
        day = df.index[i].date()

        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl
            current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > p["dd_limit"]: in_trade = False; posisi = None; continue

        if is_confidence:
            conf = confidence_G(df.iloc[i])
            frac = get_fraction(conf, p["conf_sizing"])
        else:
            conf = 0; frac = 1.0

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail = False
                modal -= 5000 * frac
                spread_cost = (spread_pts * point_val / max(entry_price, 1e-9)) * modal
                modal -= spread_cost * frac
                in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal; exit = True
                elif ef_val < em_val: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit = True
                elif ef_val > em_val: profit = (entry_price - c) / entry_price * modal; exit = True
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
                    "profit": round(profit), "modal": round(modal), "conf": conf, "frac": frac})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl

if not mt5.initialize():
    print("[ERROR] MT5 cannot initialize"); exit()

all_results = []

for period_label, dt_from, dt_to in PERIODS:
    print(f"\n{'='*95}")
    print(f"  PERIODE: {period_label} ({dt_from.strftime('%Y-%m-%d')} sd {dt_to.strftime('%Y-%m-%d')})")
    print(f"{'='*95}")

    for ticker in TICKERS:
        sym = ticker["name"]
        print(f"\n  --- {sym} (modal Rp{ticker['modal']:,}, target Rp{ticker['target']:,}/hari) ---")

        for label in STRATEGIES:
            name = STRAT_NAMES[label]
            p = dict(STRAT_PARAMS[label])
            tf_mt5 = mt5.TIMEFRAME_M15

            df, dh = fetch_data_range(sym, tf_mt5, dt_from, dt_to)
            if df is None or len(df) < 200:
                print(f"    {name:<20} DATA TIDAK CUKUP"); continue

            t0, t1 = df.index[0].date(), df.index[-1].date()
            days = (t1 - t0).days

            try:
                df = prep_confidence(df, dh, p) if label == "g" else prep_simple(df, p)
            except Exception as e:
                print(f"    {name:<20} PREP ERROR: {e}"); continue

            if len(df) < 100:
                print(f"    {name:<20} DATA AFTER PREP KURANG"); continue

            try:
                modal_akhir, dd_max, trades, daily_pnl = backtest(df, p, ticker, label)
            except Exception as e:
                print(f"    {name:<20} BT ERROR: {e}"); continue

            win = [t for t in trades if t["profit"] > 0]
            loss = [t for t in trades if t["profit"] < 0]
            pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
            roi = (modal_akhir - ticker["modal"]) / ticker["modal"] * 100
            avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
            days_above = sum(1 for pnl in daily_pnl.values() if pnl >= ticker["target"])

            all_results.append({
                "period": period_label, "ticker": sym, "strategy": name,
                "days": days, "trades": len(trades),
                "roi": roi, "dd": dd_max, "pf": pf,
                "avg_daily": avg_daily, "target": ticker["target"],
                "days_above": days_above, "total_days": len(daily_pnl),
                "win_rate": len(win) / max(len(trades), 1) * 100,
            })

            status = "OK" if avg_daily >= ticker["target"] else "NO"
            print(f"    {name:<20} ROI {roi:>+7.1f}% DD {dd_max:>5.1f}% PF {pf:>5.2f} Rp{avg_daily:>9,.0f}/hari ({status}) | {len(trades):>4}tr WR {len(win)/max(len(trades),1)*100:.0f}%")

mt5.shutdown()

print("\n\n" + "=" * 95)
print("  RINGKASAN PERBANDINGAN — M15 ZERO SPREAD")
print("=" * 95)

for period_label, _, _ in PERIODS:
    print(f"\n{'-'*95}")
    print(f"  {period_label}")
    print(f"{'-'*95}")
    print(f"{'Ticker':<10} {'Strategi':<20} {'ROI':>8} {'DD':>6} {'PF':>5} {'Rp/hari':>11} {'Status':>6} {'Trade':>5} {'WR':>5}")
    print(f"{'-'*95}")
    per_res = [r for r in all_results if r["period"] == period_label]
    for r in sorted(per_res, key=lambda x: x["avg_daily"], reverse=True):
        st = "OK" if r["avg_daily"] >= r["target"] else "NO"
        print(f"{r['ticker']:<10} {r['strategy']:<20} {r['roi']:>+7.1f}% {r['dd']:>5.1f}% {r['pf']:>4.2f} Rp{r['avg_daily']:>8,.0f} {st:>6} {r['trades']:>4} {r['win_rate']:>4.0f}%")

print(f"\n{'='*95}")
print("  TOP 10 KOMBINASI TERBAIK (ZERO SPREAD)")
print(f"{'='*95}")
top = sorted(all_results, key=lambda x: x["avg_daily"], reverse=True)[:10]
print(f"{'Periode':<25} {'Ticker':<10} {'Strategi':<20} {'ROI':>8} {'DD':>6} {'PF':>5} {'Rp/hari':>11}")
print(f"{'-'*95}")
for r in top:
    print(f"{r['period']:<25} {r['ticker']:<10} {r['strategy']:<20} {r['roi']:>+7.1f}% {r['dd']:>5.1f}% {r['pf']:>4.2f} Rp{r['avg_daily']:>8,.0f}")
