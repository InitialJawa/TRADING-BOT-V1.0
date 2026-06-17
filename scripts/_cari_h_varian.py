import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
SPREAD_POINTS = 280
POINT_VALUE = 0.01

def try_mt5(bars, tf, tf_h4=False, tf_h1=False):
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(): return None, None, None
        mt5.symbol_select(SYMBOL, True)
        rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
        rh4 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, bars//4) if tf_h4 else None
        rh1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars) if tf_h1 else None
        mt5.shutdown()
        if rates is None or len(rates) < 200: return None, None, None
        df = pd.DataFrame(rates); df["time"] = pd.to_datetime(df["time"], unit="s"); df.set_index("time", inplace=True)
        dh4 = None
        if rh4 is not None:
            dh4 = pd.DataFrame(rh4); dh4["time"] = pd.to_datetime(dh4["time"], unit="s"); dh4.set_index("time", inplace=True)
        dh1 = None
        if rh1 is not None:
            dh1 = pd.DataFrame(rh1); dh1["time"] = pd.to_datetime(dh1["time"], unit="s"); dh1.set_index("time", inplace=True)
        return df, dh4, dh1
    except: return None, None, None

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def prep_h1(df, dh4):
    for p in [5, 8, 9, 13, 21, 50, 200]:
        df[f"ema{p}"] = ema(df["close"], p)
    df["atr"] = atr(df, 14)
    df["rsi"] = rsi(df["close"], 14)
    df["vol_ma"] = sma(df["tick_volume"], 20)
    bbu, bbm, bbl = (df["close"].rolling(20).mean() + 2*df["close"].rolling(20).std(),
                     df["close"].rolling(20).mean(),
                     df["close"].rolling(20).mean() - 2*df["close"].rolling(20).std())
    df["bbw"] = (bbu - bbl) / bbm; df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour
    if dh4 is not None and len(dh4) > 50:
        dh4["ema9"] = ema(dh4["close"], 9); dh4["ema21"] = ema(dh4["close"], 21)
        dh4["h4_trend"] = np.where(dh4["ema9"] > dh4["ema21"], "UP", "DOWN")
        dh4.dropna(inplace=True)
        df["h4_trend"] = dh4["h4_trend"].resample("1h").ffill().reindex(df.index, method="ffill")
    else: df["h4_trend"] = "NEUTRAL"
    df.dropna(inplace=True); return df

def prep_h4(df, dh1):
    df["ema9"] = ema(df["close"], 9); df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50); df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, 14)
    df["rsi"] = rsi(df["close"], 14)
    df["vol_ma"] = sma(df["tick_volume"], 20)
    bbu, bbm, bbl = (df["close"].rolling(20).mean() + 2*df["close"].rolling(20).std(),
                     df["close"].rolling(20).mean(),
                     df["close"].rolling(20).mean() - 2*df["close"].rolling(20).std())
    df["bbw"] = (bbu - bbl) / bbm; df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour
    if dh1 is not None and len(dh1) > 50:
        dh1["ema9"] = ema(dh1["close"], 9); dh1["ema21"] = ema(dh1["close"], 21)
        dh1["d1_trend_day"] = np.where(dh1["ema9"] > dh1["ema21"], "UP", "DOWN")
        dh1.dropna(inplace=True)
        df["d1_trend"] = dh1["d1_trend_day"].resample("4h").ffill().reindex(df.index, method="ffill")
    else: df["d1_trend"] = "NEUTRAL"
    df.dropna(inplace=True); return df

def prep_m15_with_h1(df, dh1):
    df["ema5"] = ema(df["close"], 5); df["ema13"] = ema(df["close"], 13)
    df["ema50"] = ema(df["close"], 50); df["ema200"] = ema(df["close"], 200)
    df["atr"] = atr(df, 10)
    df["rsi"] = rsi(df["close"], 14)
    df["vol_ma"] = sma(df["tick_volume"], 15)
    bbu, bbm, bbl = (df["close"].rolling(20).mean() + 2*df["close"].rolling(20).std(),
                     df["close"].rolling(20).mean(),
                     df["close"].rolling(20).mean() - 2*df["close"].rolling(20).std())
    df["bbw"] = (bbu - bbl) / bbm; df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour
    if dh1 is not None and len(dh1) > 50:
        dh1["ema9"] = ema(dh1["close"], 9); dh1["ema21"] = ema(dh1["close"], 21)
        dh1["h1_trend"] = np.where(dh1["ema9"] > dh1["ema21"], "UP", "DOWN")
        dh1.dropna(inplace=True)
        df["h1_trend"] = dh1["h1_trend"].resample("15min").ffill().reindex(df.index, method="ffill")
    else: df["h1_trend"] = "NEUTRAL"
    df.dropna(inplace=True); return df

# ---- confidence functions ----
def conf_h1(row, conf_factors, ema_fast="ema9", ema_medium="ema21"):
    s = 0; bull = row[ema_fast] > row[ema_medium]
    ef = row.get("h4_trend", "NEUTRAL")
    if (bull and ef == "UP") or (not bull and ef == "DOWN"): s += 2
    if row.get("squeeze", False): s += 1
    if row.get("tick_volume", 0) > row.get("vol_ma", 1) * 1.2: s += 1
    if bull and row.get("rsi", 50) > conf_factors.get("rsi_extreme_bull", 999): s += 1
    if not bull and row.get("rsi", 50) < conf_factors.get("rsi_extreme_bear", -1): s += 1
    if 7 <= row.get("hour_utc", 0) < 14: s += 1
    c = row.get("close", 0)
    if (bull and c > row.get("ema200", 0)) or (not bull and c < row.get("ema200", 0)): s += 1
    return s

def conf_h4(row):
    s = 0; bull = row["ema9"] > row["ema21"]
    ef = row.get("d1_trend", "NEUTRAL")
    if (bull and ef == "UP") or (not bull and ef == "DOWN"): s += 2
    if row.get("squeeze", False): s += 1
    if row.get("tick_volume", 0) > row.get("vol_ma", 1) * 1.2: s += 1
    if bull and row.get("rsi", 50) > 70: s += 1
    if not bull and row.get("rsi", 50) < 30: s += 1
    return s

# ---- backtest engine ----
def backtest(df, params, conf_func, get_frac_func):
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0; modal_at_entry = 0.0

    ema_fast_col = params["ema_fast"]; ema_med_col = params["ema_medium"]
    # Calculate if ema_fast uses non-standard name
    if ema_fast_col not in df.columns:
        ema(df["close"], int(ema_fast_col.replace("ema",""))).iloc[-1]  # trigger compute
        # Dynamically compute needed EMAs
        for col in [ema_fast_col, ema_med_col]:
            if col not in df.columns:
                p = int(col.replace("ema",""))
                df[col] = ema(df["close"], p)
        df.dropna(inplace=True)

    for i in range(100, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef = df[ema_fast_col].iloc[i]; em = df[ema_med_col].iloc[i]
        day = df.index[i].date()
        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl; current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > params.get("max_dd_pause", 25): in_trade = False; posisi = None; continue

        row = df.iloc[i]
        sig = "HOLD"
        if params.get("signal_func"):
            sig = params["signal_func"](df, i, params)
        else:
            bull = row[params["ema_fast"]] > row[params["ema_medium"]]
            rsi_lo, rsi_hi = params["rsi_long"]
            if bull and rsi_lo <= row["rsi"] <= rsi_hi and row["tick_volume"] > row["vol_ma"] * 0.8:
                sig = "BUY"
            rsi_slo, rsi_shi = params["rsi_short"]
            if not bull and rsi_slo <= row["rsi"] <= rsi_shi and row["tick_volume"] > row["vol_ma"] * 0.8:
                sig = "SELL"

        # M15+H1 hybrid filter
        if params.get("hybrid_h1_trend") and sig != "HOLD":
            h1 = row.get(params["hybrid_h1_field"], "NEUTRAL")
            if (sig == "BUY" and h1 != "UP") or (sig == "SELL" and h1 != "DOWN"):
                sig = "HOLD"

        conf = conf_func(row) if params.get("use_conf", False) else 1
        frac = get_frac_func(conf) if params.get("use_conf", False) else 1.0

        # Skip low conf
        if params.get("min_conf", 0) > conf:
            sig = "HOLD"

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * params["sl_mult"] if sig == "BUY" else c + a * params["sl_mult"]
                tp_price = c + a * params["tp_mult"] if sig == "BUY" else c - a * params["tp_mult"]
                trail = False
                base_cost = params.get("base_cost", 5000)
                base_mult = params.get("base_mult", 1.0)
                trade_frac = frac * base_mult
                modal -= base_cost * trade_frac
                spread_cost = (SPREAD_POINTS * POINT_VALUE / entry_price) * modal
                modal -= spread_cost * trade_frac
                modal_at_entry = modal
                in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif bars >= params["max_hold"]: profit = (c - entry_price) / entry_price * modal_at_entry * trade_frac; exit = True
                else:
                    td = a * params["trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * params["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal_at_entry * trade_frac; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                elif bars >= params["max_hold"]: profit = (entry_price - c) / entry_price * modal_at_entry * trade_frac; exit = True
                else:
                    td = a * params["trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal_at_entry * trade_frac * params["running_pct"]
            if exit:
                modal += profit; day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal), "conf": conf, "frac": trade_frac})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl

# ---- variant configurations ----
def make_variants():
    v = []
    base_ema_fast = "ema9"; base_ema_medium = "ema21"

    # ---- VARIAN 1: Optimasi Lot H ----
    def conf_h_standard(row):
        return conf_h1(row, {"rsi_extreme_bull": 75, "rsi_extreme_bear": 25})

    def get_frac(conf, thresholds):
        for lo, hi, f in thresholds:
            if lo <= conf <= hi: return f
        return 1.0

    # H baseline (existing)
    v.append({
        "name": "H_BASELINE", "tf": "H1", "bars": 3000,
        "prep": lambda df, aux: prep_h1(df, aux[0]), "aux_tf": "H4", "aux_bars": 750,
        "params": {
            "ema_fast": base_ema_fast, "ema_medium": base_ema_medium,
            "rsi_long": (40, 80), "rsi_short": (20, 60),
            "sl_mult": 1.5, "tp_mult": 3.0, "trail_mult": 0.5,
            "max_hold": 24, "running_pct": 0.05, "max_dd_pause": 15,
            "use_conf": True, "signal_func": None,
        },
        "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.5),(5,7,2.0)]),
    })

    # H_LOT400: base mult 1.33 (400/300)
    p = dict(v[0]["params"]); p["base_mult"] = 1.33; p["running_pct"] = 0.07
    v.append({"name": "H_LOT400", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.5),(5,7,2.0)]),
    })

    # H_LOT500: base mult 1.67 (500/300)
    p = dict(v[0]["params"]); p["base_mult"] = 1.67; p["running_pct"] = 0.08
    v.append({"name": "H_LOT500", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.5),(5,7,2.0)]),
    })

    # H_BOOST_TINGGI: conf 1.0/1.8/2.5x
    v.append({"name": "H_BOOST_TINGGI", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": dict(v[0]["params"]),
        "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # H_MINCONF3: conf 3+ only, frac 1.3/1.8
    p = dict(v[0]["params"]); p["min_conf"] = 3
    v.append({"name": "H_MINCONF3", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(3,4,1.3),(5,7,1.8)]),
    })

    # ---- VARIAN 2: H4 Confidence ----
    def conf_h4_std(row):
        return conf_h4(row)

    def frac_h4(c):
        return get_frac(c, [(0,2,1.0),(3,4,1.5),(5,6,2.0)])

    def prep_h4_wrapper(df, aux):
        return prep_h4(df, aux[0])

    v.append({
        "name": "I_H4_CONF", "tf": "H4", "bars": 750,
        "prep": prep_h4_wrapper, "aux_tf": "H1", "aux_bars": 3000,
        "params": {
            "ema_fast": base_ema_fast, "ema_medium": base_ema_medium,
            "rsi_long": (40, 80), "rsi_short": (20, 60),
            "sl_mult": 1.0, "tp_mult": 2.0, "trail_mult": 0.3,
            "max_hold": 12, "running_pct": 0.03, "max_dd_pause": 15,
            "use_conf": True, "signal_func": None,
        },
        "conf_func": conf_h4_std,
        "frac_func": frac_h4,
    })

    # H4 with wider RSI
    p = dict(v[-1]["params"]); p["rsi_long"] = (30, 85); p["rsi_short"] = (15, 70)
    p["running_pct"] = 0.05
    v.append({
        "name": "I_H4_AGRESIF", "tf": "H4", "bars": 750,
        "prep": prep_h4_wrapper, "aux_tf": "H1", "aux_bars": 3000,
        "params": p, "conf_func": conf_h4_std, "frac_func": frac_h4,
    })

    # ---- VARIAN 3: M15 + H1 hybrid ----
    def conf_m15_hybrid(row):
        s = 0; bull = row["ema5"] > row["ema13"]
        h1 = row.get("h1_trend", "NEUTRAL")
        if (bull and h1 == "UP") or (not bull and h1 == "DOWN"): s += 2
        if row.get("squeeze", False): s += 1
        if row.get("tick_volume", 0) > row.get("vol_ma", 1) * 1.2: s += 1
        if bull and row.get("rsi", 50) > 65: s += 1
        if not bull and row.get("rsi", 50) < 35: s += 1
        if 7 <= row.get("hour_utc", 0) < 15: s += 1
        return s

    def prep_m15_hybrid(df, aux):
        return prep_m15_with_h1(df, aux[0])

    def sig_m15_hybrid(df, i, params):
        row = df.iloc[i]
        bull = row["ema5"] > row["ema13"]
        if bull and 30 <= row["rsi"] <= 95 and row["tick_volume"] > row["vol_ma"] * 0.7:
            return "BUY"
        if not bull and 5 <= row["rsi"] <= 70 and row["tick_volume"] > row["vol_ma"] * 0.7:
            return "SELL"
        return "HOLD"

    def frac_m15_hybrid(c):
        return get_frac(c, [(0,2,1.0),(3,4,1.5),(5,6,2.0)])

    v.append({
        "name": "J_M15_HYBRID", "tf": "M15", "bars": 12000,
        "prep": prep_m15_hybrid, "aux_tf": "H1", "aux_bars": 3000,
        "params": {
            "ema_fast": "ema5", "ema_medium": "ema13",
            "rsi_long": (30, 95), "rsi_short": (5, 70),
            "sl_mult": 0.5, "tp_mult": 2.2, "trail_mult": 0.3,
            "max_hold": 20, "running_pct": 0.12, "max_dd_pause": 15,
            "use_conf": True, "signal_func": sig_m15_hybrid,
            "hybrid_h1_trend": True, "hybrid_h1_field": "h1_trend",
        },
        "conf_func": conf_m15_hybrid,
        "frac_func": frac_m15_hybrid,
    })

    # J2: M15 hybrid min conf 2 (skip low conf)
    p = dict(v[-1]["params"]); p["min_conf"] = 2
    v.append({
        "name": "J_M15_CONF2+", "tf": "M15", "bars": 12000,
        "prep": prep_m15_hybrid, "aux_tf": "H1", "aux_bars": 3000,
        "params": p, "conf_func": conf_m15_hybrid, "frac_func": frac_m15_hybrid,
    })

    # ---- VARIAN 4: Parameter sweep H1 ----
    def make_h_variant(name, overrides):
        base_frac = lambda c: get_frac(c, [(0,2,1.0),(3,4,1.5),(5,7,2.0)])
        p = dict(v[0]["params"])
        p.update(overrides)
        return {
            "name": name, "tf": "H1", "bars": 3000,
            "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
            "params": p, "conf_func": conf_h_standard,
            "frac_func": base_frac,
        }

    v.append(make_h_variant("H_EMA5_13", {"ema_fast": "ema5", "ema_medium": "ema13"}))
    v.append(make_h_variant("H_EMA8_21", {"ema_fast": "ema8", "ema_medium": "ema21"}))

    # RSI varian
    v.append(make_h_variant("H_RSI_LEBAR", {"rsi_long": (35, 85), "rsi_short": (15, 65)}))
    v.append(make_h_variant("H_RSI_SEMPIT", {"rsi_long": (45, 75), "rsi_short": (25, 55)}))

    # SL/TP varian
    v.append(make_h_variant("H_SLTP12_25", {"sl_mult": 1.2, "tp_mult": 2.5}))
    v.append(make_h_variant("H_SLTP20_40", {"sl_mult": 2.0, "tp_mult": 4.0}))

    # Running pct varian
    v.append(make_h_variant("H_RUN008", {"running_pct": 0.08}))
    v.append(make_h_variant("H_RUN003", {"running_pct": 0.03}))

    # ---- FINAL KOMBINASI ----
    # BOOST500: boost frac + base_mult 1.67
    p = dict(v[0]["params"]); p["base_mult"] = 1.67
    v.append({"name": "H_BOOST500", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # EMA5 + BOOST
    p = dict(v[0]["params"]); p["ema_fast"] = "ema5"; p["ema_medium"] = "ema13"
    v.append({"name": "H_EMA5_BOOST", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p,
        "conf_func": lambda row: conf_h1(row, {"rsi_extreme_bull": 75, "rsi_extreme_bear": 25}, ema_fast="ema5", ema_medium="ema13"),
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # RSI45 + BOOST
    p = dict(v[0]["params"]); p["rsi_long"] = (45, 75); p["rsi_short"] = (25, 55)
    v.append({"name": "H_RSI45_BOOST", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # BOOST120: base_mult 1.2 + BOOST frac
    p = dict(v[0]["params"]); p["base_mult"] = 1.2
    v.append({"name": "H_BOOST120", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p, "conf_func": conf_h_standard,
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # CUSTOM1: ema5/13, RSI 42-78/22-58, base_mult 1.15, BOOST
    p = dict(v[0]["params"]); p["ema_fast"] = "ema5"; p["ema_medium"] = "ema13"
    p["rsi_long"] = (42, 78); p["rsi_short"] = (22, 58); p["base_mult"] = 1.15
    v.append({"name": "H_CUSTOM1", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p,
        "conf_func": lambda row: conf_h1(row, {"rsi_extreme_bull": 75, "rsi_extreme_bear": 25}, ema_fast="ema5", ema_medium="ema13"),
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    # E5_LOT130: ema5/13, base_mult 1.3, running 0.07, BOOST
    p = dict(v[0]["params"]); p["ema_fast"] = "ema5"; p["ema_medium"] = "ema13"
    p["base_mult"] = 1.3; p["running_pct"] = 0.07
    v.append({"name": "H_E5_LOT130", "tf": "H1", "bars": 3000,
        "prep": v[0]["prep"], "aux_tf": "H4", "aux_bars": 750,
        "params": p,
        "conf_func": lambda row: conf_h1(row, {"rsi_extreme_bull": 75, "rsi_extreme_bear": 25}, ema_fast="ema5", ema_medium="ema13"),
        "frac_func": lambda c: get_frac(c, [(0,2,1.0),(3,4,1.8),(5,7,2.5)]),
    })

    return v

# ---- main runner ----
def run_variant(var):
    name = var["name"]; print(f"\n{'='*60}\n  >>> {name}\n{'='*60}")

    df, dh4, dh1 = try_mt5(var["bars"], 
        {"H1": 16385, "M15": 16385, "H4": 16385}.get(var["tf"], 16385),
        var.get("aux_tf") in ("H4", "H1"), var.get("aux_tf") == "H1")

    if var["aux_tf"] == "H4": aux = (dh4,)
    elif var["aux_tf"] == "H1": aux = (dh1,)
    else: aux = ()

    if df is None or len(df) < 200:
        print(f"  [SKIP] Data tidak cukup"); return None

    t0, t1 = df.index[0].date(), df.index[-1].date()
    days = max((df.index[-1] - df.index[0]).days, 1)
    df = var["prep"](df, aux)
    if df is None or len(df) < 100:
        print(f"  [SKIP] Prep gagal"); return None

    modal_akhir, dd_max, trades, daily_pnl = backtest(df, var["params"], var["conf_func"], var["frac_func"])

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    roi = (modal_akhir - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    avg_conf = np.mean([t["conf"] for t in trades]) if trades else 0

    result = {
        "name": name, "roi": round(roi, 2), "dd": round(dd_max, 2),
        "avg_daily": round(avg_daily, 0), "trades": len(trades),
        "wr": round(len(win)/max(len(trades),1)*100, 1),
        "pf": round(pf, 2), "avg_hold": round(avg_hold, 1),
        "avg_conf": round(avg_conf, 1), "days": days,
    }
    print(f"  ROI: +{roi:.2f}% | DD: {dd_max:.1f}% | Rp{avg_daily:,.0f}/hari | {len(trades)} trades | WR {result['wr']}% | PF {pf:.2f}")
    return result

def main():
    print("=" * 70)
    print(f"  OPTIMASI STRATEGI H — Cari varian terbaik (spread {SPREAD_POINTS} pts)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  Modal: Rp{MODAL:,} | Target: > Rp150k/hari, DD < 15%, PF > 1.5")
    print("=" * 70)

    variants = make_variants()
    results = []
    for v in variants:
        r = run_variant(v)
        if r: results.append(r)

    print(f"\n{'='*70}")
    print(f"  RANGKUMAN SEMUA VARIAN")
    print(f"  Diurutkan dari avg_daily tertinggi")
    print(f"{'='*70}")
    results.sort(key=lambda x: x["avg_daily"], reverse=True)
    
    print(f"\n  {'Nama':<18} {'ROI':>8} {'DD':>5} {'Rp/hari':>12} {'Trades':>7} {'WR':>5} {'PF':>5} {'Hold':>5}")
    print(f"  {'-'*65}")
    for r in results:
        arrows = ""
        if r["avg_daily"] > 150000: arrows = " ***"
        elif r["avg_daily"] > 100000: arrows = " **"
        elif r["avg_daily"] > 50000: arrows = " *"
        print(f"  {r['name']:<18} {r['roi']:>7.1f}% {r['dd']:>4.1f}% Rp{r['avg_daily']:>9,.0f} {r['trades']:>5}  {r['wr']:>4.1f} {r['pf']:>4.2f} {r['avg_hold']:>4.0f}h{arrows}")

    # Best in class
    print(f"\n{'='*70}")
    print(f"  REKOMENDASI")
    print(f"{'='*70}")
    best = results[0] if results else None
    if best:
        print(f"  TERBAIK UMUM: {best['name']} — Rp{best['avg_daily']:,.0f}/hari, DD {best['dd']}%, PF {best['pf']}")
    
    safe = [r for r in results if r["dd"] < 12 and r["pf"] > 1.5]
    if safe:
        safe.sort(key=lambda x: x["avg_daily"], reverse=True)
        print(f"  TERBAIK AMAN (DD<12%, PF>1.5): {safe[0]['name']} — Rp{safe[0]['avg_daily']:,.0f}/hari, DD {safe[0]['dd']}%, PF {safe[0]['pf']}")

    high_pf = [r for r in results if r["pf"] > 2.0 and r["dd"] < 15]
    if high_pf:
        high_pf.sort(key=lambda x: x["pf"], reverse=True)
        print(f"  PF TERTINGGI: {high_pf[0]['name']} — PF {high_pf[0]['pf']}, Rp{high_pf[0]['avg_daily']:,.0f}/hari, DD {high_pf[0]['dd']}%")

    print(f"\n  *** = target Rp150k tercapai | ** = >Rp100k | * = >Rp50k")

if __name__ == "__main__":
    main()
