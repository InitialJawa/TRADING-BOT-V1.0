import numpy as np
import pandas as pd
from strategies.shared.indicators import ema, sma, atr, rsi, bb

def prep_stage(df, dh4, params):
    ef = params.get("ema_fast", 9)
    em = params.get("ema_medium", 21)
    df["ema9"] = ema(df["close"], ef)
    df["ema21"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], params.get("ema_trend", 50))
    df["ema200"] = ema(df["close"], params.get("ema_major", 200))
    df["atr"] = atr(df, params.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], params.get("rsi_period", 14))
    df["vol_ma"] = sma(df["tick_volume"], params.get("volume_ma_period", 20))
    df["ema9_slope"] = (df["ema9"] - df["ema9"].shift(5)) / df["ema9"].shift(5) * 100
    df["ema21_slope"] = (df["ema21"] - df["ema21"].shift(5)) / df["ema21"].shift(5) * 100
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
        h4_t = dh4["h4_trend"].resample("1h").ffill()
        df["h4_trend"] = h4_t.reindex(df.index, method="ffill")
    else:
        df["h4_trend"] = "NEUTRAL"
    df.dropna(inplace=True)
    return df

def detect_stage(row, threshold=0.0004):
    ema_bull = row["ema9"] > row["ema21"]
    price_above = row["close"] > row["ema21"]
    ema_up = row["ema21_slope"] > threshold
    ema_bear = row["ema9"] < row["ema21"]
    price_below = row["close"] < row["ema21"]
    ema_down = row["ema21_slope"] < -threshold
    if ema_bull and price_above and ema_up: return 2
    if ema_bear and price_below and ema_down: return 4
    if ema_bull and not ema_up: return 3
    return 1

def confidence_score(row, factors=None):
    if factors is None:
        factors = {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1}
    s = 0
    bull = row["ema9"] > row["ema21"]
    h4 = row.get("h4_trend", "NEUTRAL")
    if (bull and h4 == "UP") or (not bull and h4 == "DOWN"):
        s += factors.get("h4", 2)
    if 7 <= row["hour_utc"] < 15:
        s += factors.get("session", 1)
    if row["tick_volume"] > row["vol_ma"] * 1.2:
        s += factors.get("volume", 1)
    if bull and row["rsi"] > 65:
        s += factors.get("rsi", 1)
    if not bull and row["rsi"] < 35:
        s += factors.get("rsi", 1)
    if row["squeeze"]:
        s += factors.get("squeeze", 1)
    c = row["close"]
    if (bull and c > row["ema200"]) or (not bull and c < row["ema200"]):
        s += factors.get("ema200", 1)
    return s

def get_fraction(conf, sizing):
    for lo, hi, frac in sizing:
        if lo <= conf <= hi:
            return frac
    return 1.0

def signal_stage_enhanced(df, i, params):
    row = df.iloc[i]
    threshold = params.get("stage_slope_threshold", 0.0004)
    stage = detect_stage(row, threshold)
    if stage == 1 or stage == 3:
        return "HOLD"
    vol_ok = row["tick_volume"] > row["vol_ma"] * params.get("volume_mult", 0.8)
    if stage == 2 and row["ema9"] > row["ema21"] and row["close"] > row["ema21"] and vol_ok:
        return "BUY"
    if stage == 4 and row["ema9"] < row["ema21"] and row["close"] < row["ema21"] and vol_ok:
        return "SELL"
    return "HOLD"

def backtest_stage_enhanced(df, params, ticker_cfg):
    modal = float(ticker_cfg["modal"])
    spread_pts = ticker_cfg.get("spread", 25)
    point_val = ticker_cfg.get("point", 0.01)
    fee = params.get("fee", 5000)

    atr_sl = params.get("atr_sl_mult", 1.5)
    atr_trail = params.get("atr_trail_mult", 0.5)
    running_pct = params.get("running_pct", 0.05)
    sizing = params.get("conf_sizing", [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)])

    peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0; modal_at_entry = 0.0

    for i in range(100, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        stage = detect_stage(df.iloc[i], params.get("stage_slope_threshold", 0.0004))
        sig = signal_stage_enhanced(df, i, params)
        conf = confidence_score(df.iloc[i], params.get("confidence_factors", None))
        frac = get_fraction(conf, sizing)
        day = df.index[i].date()
        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0
        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * atr_sl if sig == "BUY" else c + a * atr_sl
                trail = False; modal -= fee * frac
                spread_cost = (spread_pts * point_val / entry_price) * modal
                modal -= spread_cost * frac; modal_at_entry = modal; trade_frac = frac; in_trade = True
        else:
            bars = i - entry_idx; exit_here = False; profit = 0.0
            cs = detect_stage(df.iloc[i], params.get("stage_slope_threshold", 0.0004))

            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal_at_entry * trade_frac; exit_here = True
                elif cs == 3: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit_here = True
                elif df["ema9"].iloc[i] < df["ema21"].iloc[i]: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit_here = True
                else:
                    td = a * atr_trail
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * running_pct
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal_at_entry * trade_frac; exit_here = True
                elif cs == 3: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit_here = True
                elif df["ema9"].iloc[i] > df["ema21"].iloc[i]: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit_here = True
                else:
                    td = a * atr_trail
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * running_pct

            if exit_here:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal), "conf": conf, "frac": trade_frac,
                    "stage_entry": detect_stage(df.iloc[entry_idx], params.get("stage_slope_threshold", 0.0004)),
                    "stage_exit": cs})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl

def calc_metrics(modal_akhir, trades, daily_pnl, ticker_cfg):
    modal = ticker_cfg["modal"]
    roi = (modal_akhir - modal) / modal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    days_above = sum(1 for p in daily_pnl.values() if p >= ticker_cfg.get("target_harian", 100000)) if daily_pnl else 0
    return {"roi": roi, "pf": pf, "trades": len(trades),
            "wr": len(win) / max(len(trades), 1) * 100,
            "avg_daily": avg_daily, "days_above": days_above,
            "total_days": len(daily_pnl), "avg_hold_hrs": avg_hold * 1}
