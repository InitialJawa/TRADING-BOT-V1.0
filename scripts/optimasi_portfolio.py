import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from strategies.shared.stage_analysis import prep_stage, detect_stage, signal_stage_enhanced, confidence_score

MODAL = 12_000_000
FEE = 0
TICKER_MAP = {
    "XAGUSDm": {"spread": 30, "point": 0.001},
    "ETHUSDm": {"spread": 100, "point": 0.01},
    "BTCUSDTm": {"spread": 1000, "point": 0.01},
    "JP225m": {"spread": 64, "point": 0.1},
}
CONF_FACTORS = {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1}

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

def run_portfolio(tickers, params, conf_sizing, label):
    n = len(tickers)
    alloc = 1.0 / n
    balance = float(MODAL)
    equity_peak = MODAL
    max_dd = 0.0
    ts = {}
    for tn in tickers:
        ts[tn] = {
            "in_trade": False, "posisi": None, "entry_price": 0.0,
            "entry_time": None, "sl_price": 0.0, "trail": False,
            "modal_at_entry": 0.0, "trade_frac": 1.0, "entry_idx": -1,
            "trail_sl_new": None,
        }
    all_exits = []
    daily_pnl = {}

    all_dates = sorted(set().union(*[
        set(dfs[tn].index.date) for tn in tickers
    ]))
    if not all_dates:
        return None, None, [], {}

    for day in all_dates:
        day_realized = 0.0
        for tn in tickers:
            df = dfs[tn]
            day_mask = df.index.date == day
            if not day_mask.any():
                continue
            day_df = df[day_mask]
            if len(day_df) < 2:
                continue
            p = params[tn]
            pset = {
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
                sig = signal_stage_enhanced(df, i, pset)
                conf = confidence_score(row, CONF_FACTORS)
                frac = 1.0
                for lo2, hi2, fv in conf_sizing:
                    if lo2 <= conf <= hi2:
                        frac = fv; break

                if not st["in_trade"]:
                    if sig != "HOLD" and frac > 0:
                        st["posisi"] = sig
                        st["entry_price"] = c
                        st["entry_time"] = df.index[i]
                        st["entry_idx"] = i
                        base = balance * alloc
                        st["modal_at_entry"] = base
                        st["trade_frac"] = frac
                        if sig == "BUY":
                            st["sl_price"] = c - a * p["sl"]
                        else:
                            st["sl_price"] = c + a * p["sl"]
                        st["trail"] = False
                        balance -= FEE * frac
                        sc = (TICKER_MAP[tn]["spread"] * TICKER_MAP[tn]["point"] / c) * base
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

                    if st["trail_sl_new"] is not None:
                        st["sl_price"] = st["trail_sl_new"]
                        st["trail_sl_new"] = None

                    if st["posisi"] == "BUY":
                        sl_hit = lo <= st["sl_price"] and not st["trail"]
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
                                st["trail_sl_new"] = entry + td * p["trail_sl_init"]
                            if st["trail"]:
                                new_sl = c - td * p["trail_sl_mul"]
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
                                st["trail_sl_new"] = entry - td * p["trail_sl_init"]
                            if st["trail"]:
                                new_sl = c + td * p["trail_sl_mul"]
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
            for tn in tickers:
                ts[tn]["in_trade"] = False
                ts[tn]["posisi"] = None

    return balance, max_dd, all_exits, daily_pnl


# ======================== CONFIG TEST ========================
configs = [
    {
        "label": "4 Ticker (baseline)",
        "tickers": ["XAGUSDm", "ETHUSDm", "BTCUSDTm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.2, "trail": 0.6, "trail_sl_init": 0.5, "trail_sl_mul": 1.0, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "ETHUSDm": {"sl": 1.5, "trail": 0.8, "trail_sl_init": 0.5, "trail_sl_mul": 1.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 1.0},
            "BTCUSDTm": {"sl": 2.0, "trail": 1.2, "trail_sl_init": 0.5, "trail_sl_mul": 1.0, "pct": 0.1, "threshold": 0.0006, "vol_mult": 1.0},
            "JP225m": {"sl": 1.0, "trail": 0.6, "trail_sl_init": 0.5, "trail_sl_mul": 1.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "2 Ticker XAG+JP225 wider trail",
        "tickers": ["XAGUSDm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.2, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "JP225m": {"sl": 1.0, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "4 Ticker trail 2x wider",
        "tickers": ["XAGUSDm", "ETHUSDm", "BTCUSDTm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.2, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "ETHUSDm": {"sl": 1.5, "trail": 1.0, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 1.0},
            "BTCUSDTm": {"sl": 2.0, "trail": 1.5, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0006, "vol_mult": 1.0},
            "JP225m": {"sl": 1.0, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "3 Ticker XAG+ETH+JP225 wider",
        "tickers": ["XAGUSDm", "ETHUSDm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.2, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "ETHUSDm": {"sl": 1.5, "trail": 1.0, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 1.0},
            "JP225m": {"sl": 1.0, "trail": 0.8, "trail_sl_init": 0.7, "trail_sl_mul": 1.5, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "2 Ticker XAG+JP225 trail super wide",
        "tickers": ["XAGUSDm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.5, "trail": 1.0, "trail_sl_init": 0.8, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "JP225m": {"sl": 1.2, "trail": 1.0, "trail_sl_init": 0.8, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "4 Ticker trail super wide",
        "tickers": ["XAGUSDm", "ETHUSDm", "BTCUSDTm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.5, "trail": 1.0, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "ETHUSDm": {"sl": 1.8, "trail": 1.2, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 1.0},
            "BTCUSDTm": {"sl": 2.5, "trail": 1.8, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0006, "vol_mult": 1.0},
            "JP225m": {"sl": 1.2, "trail": 1.0, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
    },
    {
        "label": "4 Ticker super wide + conf>=3 only",
        "tickers": ["XAGUSDm", "ETHUSDm", "BTCUSDTm", "JP225m"],
        "params": {
            "XAGUSDm": {"sl": 1.5, "trail": 1.0, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0004, "vol_mult": 0.8},
            "ETHUSDm": {"sl": 1.8, "trail": 1.2, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 1.0},
            "BTCUSDTm": {"sl": 2.5, "trail": 1.8, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0006, "vol_mult": 1.0},
            "JP225m": {"sl": 1.2, "trail": 1.0, "trail_sl_init": 1.0, "trail_sl_mul": 2.0, "pct": 0.1, "threshold": 0.0005, "vol_mult": 0.8},
        },
        "sizing": [(3, 7, 1.0)],
    },
]


# ======================== RUN ========================
print("=" * 120)
print("  OPTIMASI PORTFOLIO — High/Low SL | FEE=0 | Modal Rp12jt")
print("  Multi-konfigurasi | " + datetime.now().strftime("%Y-%m-%d %H:%M") + " WIB")
print("=" * 120)

if not mt5.initialize():
    print("[ERROR] MT5 gagal"); exit()

print("\n  Fetching data...")
dfs = {}
all_tickers = list(set(sum([c["tickers"] for c in configs], [])))

for tn in all_tickers:
    print(f"  [{tn}] fetching...", end=" ")
    df, dh4 = fetch(tn)
    if df is None:
        print("FAIL"); continue
    print(f"{len(df)} bars")
    p0 = next((c["params"][tn] for c in configs if tn in c["params"]), None)
    if p0:
        pset = {
            "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
            "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
            "atr_sl_mult": p0["sl"], "atr_trail_mult": p0["trail"],
            "running_pct": p0["pct"], "volume_mult": p0["vol_mult"],
            "stage_slope_threshold": p0["threshold"],
            "confidence_factors": CONF_FACTORS,
        }
        df = prep_stage(df, dh4, pset)
        dfs[tn] = df

mt5.shutdown()

results = []
for cfg in configs:
    label = cfg["label"]
    tickers = cfg["tickers"]
    params = cfg["params"]
    sizing = cfg["sizing"]

    valid = all(tn in dfs for tn in tickers)
    if not valid:
        results.append((label, None))
        continue

    bal, mdd, trades, dailies = run_portfolio(tickers, params, sizing, label)

    if bal is None:
        results.append((label, None))
        continue

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1) if loss else 999
    roi = (bal - MODAL) / MODAL * 100
    avg_daily = np.mean(list(dailies.values())) if dailies else 0
    n_days = len(dailies)
    daily_ret = np.array(list(dailies.values()))
    sharpe = (np.mean(daily_ret) / max(np.std(daily_ret), 1e-9)) * np.sqrt(252) if len(daily_ret) > 1 else 0
    ann = (1 + roi / 100) ** (252 / max(n_days, 1)) - 1 if n_days > 0 else 0

    results.append((label, {
        "bal": bal, "roi": roi, "mdd": mdd, "avg_daily": avg_daily,
        "pf": pf, "trades": len(trades), "wr": len(win) / max(len(trades), 1) * 100,
        "n_days": n_days, "ann": ann * 100, "sharpe": sharpe,
    }))

print("\n" + "=" * 120)
print("  HASIL OPTIMASI")
print("=" * 120)
print(f"  {'Konfigurasi':<42} {'Akhir':>12} {'ROI':>8} {'DD':>6} {'PF':>5} {'WR':>5} {'Trades':>7} {'Rp/hari':>10} {'Ann':>7} {'Sharpe':>7}")
print("  " + "-" * 110)
for label, r in results:
    if r is None:
        print(f"  {label:<42} {'DATA ERROR':>12}")
        continue
    pm = "+" if r["roi"] >= 0 else ""
    print(f"  {label:<42} Rp{r['bal']:>10,.0f} {pm}{r['roi']:>6.1f}% {r['mdd']:>5.1f}% {r['pf']:>4.2f} {r['wr']:>3.0f}% {r['trades']:>6d} Rp{r['avg_daily']:>8,.0f} {pm}{r['ann']:>5.1f}% {r['sharpe']:>5.2f}")

print("=" * 120)
print("  SELESAI")
