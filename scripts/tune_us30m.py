import sys, os, json, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

mt5.initialize()
TICKER = "US30m"
TC = {"name": "US30m", "spread": 23, "point": 0.1, "modal": 12000000, "target": 150000}
mt5.symbol_select(TICKER, True)
rates = mt5.copy_rates_from_pos(TICKER, 2, 0, 10000)
mt5.shutdown()

df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df.set_index("time", inplace=True)
print(f"Data: {len(df)} bars M15", flush=True)

def prep(p):
    d = df.copy()
    ef = p["ema_fast"]; em = p["ema_medium"]
    d[f"ema{ef}"] = ema(d["close"], ef)
    d[f"ema{em}"] = ema(d["close"], em)
    d["ema50"] = ema(d["close"], 50)
    d["ema200"] = ema(d["close"], 200)
    d["atr"] = atr(d, 14)
    d["rsi"] = rsi(d["close"], 14)
    d["vol_ma"] = sma(d["tick_volume"], 20)
    return d.dropna()

def sig(d, i, p):
    r = d.iloc[i]
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    eb = r[ef] > r[em]; ea = r[ef] < r[em]
    a200 = r["close"] > r["ema200"]
    rl = p.get("rsi_long_min",30) <= r["rsi"] <= p.get("rsi_long_max",80)
    rs = p.get("rsi_short_min",20) <= r["rsi"] <= p.get("rsi_short_max",80)
    ok = r["tick_volume"] > r["vol_ma"] * p.get("volume_mult", 1.0)
    ue = not p.get("no_ema200", False)
    um = not p.get("no_macd", False)
    mb = (not um) or 1; ms = (not um) or 1
    if (a200 or not ue) and eb and rl and mb and ok: return "BUY"
    if (not a200 or not ue) and ea and rs and ms and ok: return "SELL"
    return "HOLD"

def bt(d, p):
    m = float(TC["modal"]); pk = m; dd = 0; tr = 0; it = False; pos = None
    ep = 0; ei = 0; sp = 0; tp = 0; tl = False; me = 0
    dp = {}; cd = None; dpnl = 0; wins = 0; losses = 0; sum_w = 0; sum_l = 0
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    for i in range(50, len(d)):
        c = d["close"].iloc[i]; a = d["atr"].iloc[i]
        ev = d[ef].iloc[i]; e2 = d[em].iloc[i]
        s = sig(d, i, p)
        day = d.index[i].date()
        if cd is None: cd = day
        if day != cd: dp[cd] = dpnl; cd = day; dpnl = 0
        if m > pk: pk = m
        dd = max(dd, (pk - m) / pk * 100)
        if dd > p["dd_limit"]: it = False; pos = None; continue
        if not it:
            if s != "HOLD":
                pos = s; ep = c; ei = i
                sp = c - a * p["atr_sl_mult"] if s == "BUY" else c + a * p["atr_sl_mult"]
                tp = c + a * p["atr_tp_mult"] if s == "BUY" else c - a * p["atr_tp_mult"]
                tl = False; m -= 5000; me = m; it = True
        else:
            bars = i - ei; ex = False; pr = 0
            if pos == "BUY":
                if c <= sp: pr = (sp - ep) / ep * me; ex = True
                elif c >= tp: pr = (c - ep) / ep * me; ex = True
                elif ev < e2: pr = (c - ep) / ep * me; ex = True
                elif bars >= p["max_hold_bars"]: pr = (c - ep) / ep * me; ex = True
            else:
                if c >= sp: pr = (ep - sp) / ep * me; ex = True
                elif c <= tp: pr = (ep - c) / ep * me; ex = True
                elif ev > e2: pr = (ep - c) / ep * me; ex = True
                elif bars >= p["max_hold_bars"]: pr = (ep - c) / ep * me; ex = True
            if ex:
                m += pr; dpnl += pr; tr += 1
                if pr > 0: wins += 1; sum_w += pr
                else: losses += 1; sum_l += abs(pr)
                it = False; pos = None
                if m > pk: pk = m
    if cd: dp[cd] = dpnl
    roi = (m - TC["modal"]) / TC["modal"] * 100
    pf = sum_w / max(sum_l, 1) if sum_l else 999
    wr = wins / max(tr, 1) * 100
    ad = np.mean(list(dp.values())) if dp else 0
    return {"roi": roi, "dd": dd, "pf": pf, "wr": wr, "tr": tr, "ad": ad, "hit_dd": dd >= 24.9}

with open("config/US30m/strategy_f.json") as f:
    pc = dict(json.load(f)["params"])
pc["dd_limit"] = 25; pc["no_ema200"] = True; pc["no_macd"] = True

# === F M15 — semua kena DD, skip. Tuning D H1 sebagai gantinya ===
# Pake data H1
TICKER_H1 = "US30m"
mt5.initialize()
mt5.symbol_select(TICKER_H1, True)
rh = mt5.copy_rates_from_pos(TICKER_H1, 1, 0, 3000)
mt5.shutdown()
dh = pd.DataFrame(rh)
dh["time"] = pd.to_datetime(dh["time"], unit="s")
dh.set_index("time", inplace=True)
print(f"\nData H1: {len(dh)} bars {dh.index[0]} to {dh.index[-1]}", flush=True)

def prep_h1(p, d=dh):
    d2 = d.copy()
    ef = p["ema_fast"]; em = p["ema_medium"]
    d2[f"ema{ef}"] = ema(d2["close"], ef)
    d2[f"ema{em}"] = ema(d2["close"], em)
    d2["ema50"] = ema(d2["close"], 50)
    d2["ema200"] = ema(d2["close"], 200)
    d2["atr"] = atr(d2, 14)
    d2["rsi"] = rsi(d2["close"], 14)
    d2["macd"], d2["macd_sig"] = macd(d2["close"], 12, 26, 9)
    d2["vol_ma"] = sma(d2["tick_volume"], 20)
    return d2.dropna()

def bt_h1(d, p):
    m = float(TC["modal"]); pk = m; dd = 0; tr = 0; it = False; pos = None
    ep = 0; ei = 0; sp = 0; tp = 0; tl = False; me = 0; dp = {}; cd = None; dpnl = 0
    wins = 0; losses = 0; sum_w = 0; sum_l = 0
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    for i in range(50, len(d)):
        c = d["close"].iloc[i]; a = d["atr"].iloc[i]
        ev = d[ef].iloc[i]; e2 = d[em].iloc[i]; row = d.iloc[i]
        # signal_any
        eb = row[ef] > row[em]; ea = row[ef] < row[em]
        a200 = row["close"] > row["ema200"]
        rl = p.get("rsi_long_min",30) <= row["rsi"] <= p.get("rsi_long_max",80)
        rs = p.get("rsi_short_min",20) <= row["rsi"] <= p.get("rsi_short_max",80)
        ok = row["tick_volume"] > row["vol_ma"] * p.get("volume_mult", 0.7)
        ue = not p.get("no_ema200", False)
        um = not p.get("no_macd", False)
        mb = (not um) or (row.get("macd",0) > row.get("macd_sig",0))
        ms = (not um) or (row.get("macd",0) < row.get("macd_sig",0))
        if (a200 or not ue) and eb and rl and mb and ok: s = "BUY"
        elif (not a200 or not ue) and ea and rs and ms and ok: s = "SELL"
        else: s = "HOLD"
        day = d.index[i].date()
        if cd is None: cd = day
        if day != cd: dp[cd] = dpnl; cd = day; dpnl = 0
        if m > pk: pk = m
        dd = max(dd, (pk - m) / pk * 100)
        if dd > p["dd_limit"]: it = False; pos = None; continue
        if not it:
            if s != "HOLD":
                pos = s; ep = c; ei = i
                sp = c - a * p["atr_sl_mult"] if s == "BUY" else c + a * p["atr_sl_mult"]
                tp = c + a * p["atr_tp_mult"] if s == "BUY" else c - a * p["atr_tp_mult"]
                tl = False; m -= 5000; me = m; it = True
        else:
            bars = i - ei; ex = False; pr = 0
            if pos == "BUY":
                if c <= sp: pr = (sp - ep) / ep * me; ex = True
                elif c >= tp: pr = (c - ep) / ep * me; ex = True
                elif ev < e2: pr = (c - ep) / ep * me; ex = True
                elif bars >= p["max_hold_bars"]: pr = (c - ep) / ep * me; ex = True
            else:
                if c >= sp: pr = (ep - sp) / ep * me; ex = True
                elif c <= tp: pr = (ep - c) / ep * me; ex = True
                elif ev > e2: pr = (ep - c) / ep * me; ex = True
                elif bars >= p["max_hold_bars"]: pr = (ep - c) / ep * me; ex = True
            if ex:
                m += pr; dpnl += pr; tr += 1
                if pr > 0: wins += 1; sum_w += pr
                else: losses += 1; sum_l += abs(pr)
                it = False; pos = None
                if m > pk: pk = m
    if cd: dp[cd] = dpnl
    roi = (m - TC["modal"]) / TC["modal"] * 100
    pf = sum_w / max(sum_l, 1) if sum_l else 999
    wr = wins / max(tr, 1) * 100
    ad = np.mean(list(dp.values())) if dp else 0
    return {"roi": roi, "dd": dd, "pf": pf, "wr": wr, "tr": tr, "ad": ad, "hit_dd": dd >= 19.9}

with open("config/US30m/strategy_d.json") as f:
    pcd = dict(json.load(f)["params"])
pcd["dd_limit"] = 20; pcd["no_macd"] = False; pcd["no_ema200"] = False

tests = [
    ("D H1 Confluence", 9,21, 1.2, 3.5, 0.3, 30, 0.7),
    ("D1 SL1.0 TP3.0",  9,21, 1.0, 3.0, 0.3, 25, 0.7),
    ("D2 SL1.5 TP4.0",  9,21, 1.5, 4.0, 0.3, 35, 0.7),
    ("D3 SL0.8 TP2.5",  9,21, 0.8, 2.5, 0.3, 20, 0.7),
    ("D4 EMA5/13",      5,13, 1.2, 3.5, 0.3, 30, 0.7),
    ("D5 EMA12/26",    12,26, 1.2, 3.5, 0.3, 30, 0.7),
    ("D6 vol 1.0",      9,21, 1.2, 3.5, 0.3, 30, 1.0),
    ("D7 vol 0.5",      9,21, 1.2, 3.5, 0.3, 30, 0.5),
    ("D8 trail 0.5",    9,21, 1.2, 3.5, 0.5, 30, 0.7),
    ("D9 no macd",      9,21, 1.2, 3.5, 0.3, 30, 0.7),
]

for name, ef, em, sl, tp, tr, mh, vm in tests:
    p = dict(pcd)
    p.update({"ema_fast":ef,"ema_medium":em,"atr_sl_mult":sl,"atr_tp_mult":tp,"atr_trail_mult":tr,"max_hold_bars":mh,"volume_mult":vm})
    pp = p.copy()
    if "no macd" in name: pp["no_macd"] = True
    d = prep_h1(pp)
    if len(d) < 50:
        print(f"{name:<20} — DATA TIDAK CUKUP", flush=True)
        continue
    r = bt_h1(d, pp)
    flag = "HIT DD" if r["hit_dd"] else "OK"
    extra = ""
    if abs(r["ad"]) > 0:
        cap = (r["ad"] - 150000) / 150000 * 100
        extra = f" {'^' if cap>=0 else 'v'}{cap:.0f}%"
    print(f"{name:<20} SL={sl:.1f} TP={tp:.1f} EMA={ef}/{em:<2} -> "
          f"Rp{r['ad']:>8,.0f}/hr ROI={r['roi']:>+6.1f}% DD={r['dd']:>5.1f}% "
          f"PF={r['pf']:<5.2f} WR={r['wr']:<5.1f}% Trades={r['tr']:<3}{extra}", flush=True)

for name, ef, em, sl, tp, tr, mh, vm in tests:
    p = dict(pc)
    p.update({"ema_fast":ef,"ema_medium":em,"atr_sl_mult":sl,"atr_tp_mult":tp,"atr_trail_mult":tr,"max_hold_bars":mh,"volume_mult":vm})
    d = prep(p)
    if len(d) < 200:
        print(f"{name:<20} — DATA TIDAK CUKUP", flush=True)
        continue
    r = bt(d, p)
    flag = "HIT DD" if r["hit_dd"] else "OK"
    print(f"{name:<20} SL={sl:.1f} TP={tp:.1f} EMA={ef}/{em:<2} -> "
          f"Rp{r['ad']:>8,.0f}/hr ROI={r['roi']:>+6.1f}% DD={r['dd']:>5.1f}% "
          f"PF={r['pf']:<5.2f} WR={r['wr']:<5.1f}% Trades={r['tr']:<4} {flag}", flush=True)
