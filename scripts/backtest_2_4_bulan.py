import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

MODAL = 12_000_000
SYMBOL = "XAUUSDm"
PARAMS = {"sma_entry": 30, "sma_exit": 120, "sma200": 200, "rsi_max": 45,
          "atr_pullback": 2.0, "atr_stop": 3.0, "max_hold": 90, "running_pct": 0.15, "ema_buffer": 0.03}


def sma(s, p): return s.rolling(p).mean()
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g/l))


def prep(df):
    df["sma30"] = sma(df["close"], PARAMS["sma_entry"])
    df["sma120"] = sma(df["close"], PARAMS["sma_exit"])
    df["sma200"] = sma(df["close"], PARAMS["sma200"])
    df["ema20"] = ema(df["close"], 20)
    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["ll10"] = df["low"].rolling(10).min()
    df.dropna(inplace=True)
    return df


def run(df, modal_awal, label):
    modal = float(modal_awal); posisi = None; entry = 0; trail = 0; peak = modal
    dd_max = 0; trades = []; in_trade = False; held = 0
    first_date = df.index[0].date() if len(df) > 0 else "?"
    last_date = df.index[-1].date() if len(df) > 0 else "?"

    for i in range(5, len(df) - 1):
        c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]; ll10 = df["ll10"].iloc[i]
        a = df["atr14"].iloc[i]; sma30 = df["sma30"].iloc[i]; sma120 = df["sma120"].iloc[i]
        sma200 = df["sma200"].iloc[i]; r = df["rsi14"].iloc[i]; ema20 = df["ema20"].iloc[i]

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 30: in_trade = False; posisi = None; continue

        uptrend = sma30 > sma120 > sma200
        pullback_zone = c <= sma30 + a * 0.5 and c >= sma30 - a * PARAMS["atr_pullback"]
        exhausted = r < PARAMS["rsi_max"] and c > ema20 * (1 - PARAMS["ema_buffer"])

        if not in_trade:
            if uptrend and pullback_zone and exhausted:
                posisi = "LONG"; entry = c; trail = c - a * PARAMS["atr_stop"]
                modal -= 10000; in_trade = True; held = 0
        else:
            held += 1; trail = max(trail, ll10); profit = 0; exit_now = False
            if cn <= trail:
                profit = (trail - entry) / entry * modal; exit_now = True
            elif not uptrend:
                profit = (c - entry) / entry * modal; exit_now = True
            elif held > PARAMS["max_hold"]:
                profit = (c - entry) / entry * modal; exit_now = True
            else:
                profit = (cn - c) / c * modal * PARAMS["running_pct"]
            if exit_now:
                modal += profit; trades.append({"profit": round(profit)})
                in_trade = False; posisi = None

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]; loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    days = max((df.index[-1] - df.index[0]).days, 1)
    per_day = (modal - modal_awal) / days
    print(f"  {label}")
    print(f"  {'-'*45}")
    print(f"  Periode: {first_date} — {last_date} ({days} hari, {len(df)} bar)")
    print(f"  Modal: Rp{modal_awal:,} -> Rp{round(modal):,}")
    print(f"  Profit: Rp{round(modal - modal_awal):,} ({roi:+.2f}%)")
    if trades:
        print(f"  Trades: {len(trades)} ({len(win)}W/{len(loss)}L) | WR: {len(win)/max(len(trades),1)*100:.0f}% | PF: {pf:.2f}")
    print(f"  Max DD: {dd_max:.1f}%")
    print(f"  Per hari: Rp{per_day:,.0f} | Per bulan: Rp{per_day * 30:,.0f}")
    if trades:
        print(f"  Avg hold: {np.mean([abs(t['profit']) for t in trades]):,.0f}")
    print()
    return modal


if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

print(f"{'='*55}")
print(f"  BACKTEST SMA30 — Modal Rp{MODAL:,}")
print(f"{'='*55}")

# Fetch large dataset, prep once
rf = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, 1200)
mt5.shutdown()
dff = pd.DataFrame(rf); dff["time"] = pd.to_datetime(dff["time"], unit="s"); dff.set_index("time", inplace=True)
dff = prep(dff)

# Slice from the PREPPED data
df_2 = dff.iloc[-75:]
df_4 = dff.iloc[-130:]
df_full = dff

print(f"  Full data tersedia: {dff.index[0].date()} — {dff.index[-1].date()} ({len(dff)} bars)\n")

akhir_2 = run(df_2, MODAL, "2 BULAN TERAKHIR")
akhir_4 = run(df_4, MODAL, "4 BULAN TERAKHIR")
akhir_full = run(df_full, MODAL, "FULL 4 TAHUN")

print(f"{'='*55}")
print(f"  RINGKASAN MODAL Rp{MODAL:,}")
print(f"{'='*55}")
print(f"  {'Periode':<20} {'Profit':<18} {'/bulan':<15} {'ROI':<10}")
print(f"  {'-'*63}")
proj_monthly = {"2 BULAN": 2, "4 BULAN": 4, "FULL 4THN": 48}
for label, akhir in [("2 BULAN", akhir_2), ("4 BULAN", akhir_4), ("FULL 4THN", akhir_full)]:
    profit = akhir - MODAL
    months = proj_monthly[label]
    per_bln = profit / months
    print(f"  {label:<20} Rp{profit:<15,} Rp{round(per_bln):<12,} {profit/MODAL*100:+>8.2f}%")
print(f"{'='*55}")
print(f"\nKesimpulan: Dengan Rp12jt, rata-rata Rp{round((akhir_full-MODAL)/48):,}/bulan.")
print(f"Tapi 2-4 bulan terakhir bisa lebih kecil karena tergantung sinyal entry.")
