import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

SYMBOL = "XAUUSDm"
MODAL = 5_000_000


def init_mt5():
    if not mt5.initialize():
        return False
    mt5.symbol_select(SYMBOL, True)
    return True


def get_data(bars=1000):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, bars)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def ema(series, p):
    return series.ewm(span=p, adjust=False).mean()


def atr(df, p=14):
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1)))
    )
    return tr.rolling(p).mean()


def rsi(series, p=14):
    d = series.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    rs = g / l
    return 100 - (100 / (1 + rs))


def adx(df, p=14):
    plus = df["high"].diff()
    minus = df["low"].diff()
    plus[plus < 0] = 0
    minus[minus > 0] = 0
    minus = abs(minus)
    a = atr(df, p)
    pdi = 100 * plus.ewm(alpha=1/p).mean() / a
    ndi = 100 * minus.ewm(alpha=1/p).mean() / a
    dx = 100 * abs(pdi - ndi) / (pdi + ndi)
    return dx.ewm(alpha=1/p).mean(), pdi, ndi


# ============================================================
# STRATEGY A — Trend Momentum (Hull MA + ADX filter)
# ============================================================
def strat_a(df, i):
    close = df["close"].iloc[i]
    ema9 = df["ema9"].iloc[i]
    ema21 = df["ema21"].iloc[i]
    ema50 = df["ema50"].iloc[i]
    adx_val = df["adx"].iloc[i]
    pdi = df["pdi"].iloc[i]
    ndi = df["ndi"].iloc[i]

    if adx_val > 22 and pdi > ndi and ema9 > ema21 > ema50 and close > ema9:
        return "BUY"
    if adx_val > 22 and ndi > pdi and ema9 < ema21 < ema50 and close < ema9:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY B — Mean Reversion (RSI + Stochastic + BB)
# ============================================================
def strat_b(df, i):
    rsi_val = df["rsi"].iloc[i]
    close = df["close"].iloc[i]
    bb_low = df["bb_lower"].iloc[i]
    bb_high = df["bb_upper"].iloc[i]
    stoch_k = df["stoch_k"].iloc[i]

    if rsi_val < 30 and close < bb_low and stoch_k < 20:
        return "BUY"
    if rsi_val > 70 and close > bb_high and stoch_k > 80:
        return "SELL"
    return "HOLD"


# ============================================================
# STRATEGY C — Breakout Momentum (Donchian + Volume + ATR)
# ============================================================
def strat_c(df, i):
    close = df["close"].iloc[i]
    atr_val = df["atr"].iloc[i]
    vol = df["tick_volume"].iloc[i]
    vol_avg = df["vol_ma"].iloc[i]
    dc_high = df["dc_high"].iloc[i]
    dc_low = df["dc_low"].iloc[i]

    bb_w = (df["bb_upper"].iloc[i] - df["bb_lower"].iloc[i]) / df["bb_mid"].iloc[i] * 100
    ema20 = df["ema20"].iloc[i]

    if close > dc_high and vol > vol_avg * 1.3 and bb_w > 2.5 and close > ema20:
        return "BUY"
    if close < dc_low and vol > vol_avg * 1.3 and bb_w > 2.5 and close < ema20:
        return "SELL"
    return "HOLD"


# ============================================================
# BACKTEST ENGINE
# ============================================================
def run_backtest(df, modal_awal, signal_fn, name):
    modal = float(modal_awal)
    posisi = None
    harga_masuk = 0.0
    dd_puncak = modal
    dd_max = 0.0
    trades = []
    equity = []
    lot_base = 0.1

    for i in range(60, len(df) - 1):
        tgl = df.index[i]
        close = df["close"].iloc[i]
        close_next = df["close"].iloc[i + 1]
        atr_val = df["atr"].iloc[i]

        if modal > dd_puncak:
            dd_puncak = modal
        dd = (dd_puncak - modal) / dd_puncak * 100
        dd_max = max(dd_max, dd)

        equity.append({"tgl": tgl, "modal": round(modal), "dd": round(dd, 1)})

        if dd > 25:
            posisi = None
            continue

        sig = signal_fn(df, i)

        if posisi is None:
            if sig in ("BUY", "SELL"):
                posisi = sig
                harga_masuk = close
                modal -= 20000
        else:
            profit = 0.0
            sl = atr_val * 2.0
            tp = atr_val * 4.0
            risk_pct = 0.02
            exit_now = False

            if posisi == "BUY":
                if close_next <= close - sl:
                    profit = -(sl / close) * modal * risk_pct
                    exit_now = True
                elif close_next >= close + tp:
                    profit = (tp / close) * modal * risk_pct
                    exit_now = True
                elif sig == "SELL":
                    profit = (close_next - harga_masuk) / harga_masuk * modal * risk_pct
                    exit_now = True
            else:
                if close_next >= close + sl:
                    profit = -(sl / close) * modal * risk_pct
                    exit_now = True
                elif close_next <= close - tp:
                    profit = (tp / close) * modal * risk_pct
                    exit_now = True
                elif sig == "BUY":
                    profit = (harga_masuk - close_next) / harga_masuk * modal * risk_pct
                    exit_now = True

            if not exit_now:
                if posisi == "BUY":
                    profit = (close_next - close) / close * modal * risk_pct * 0.3
                else:
                    profit = (close - close_next) / close * modal * risk_pct * 0.3

            modal += profit
            trades.append({
                "tgl": tgl, "side": posisi,
                "entry": round(harga_masuk, 1), "exit": round(close_next, 1),
                "profit": round(profit), "modal": round(modal)
            })
            posisi = None
            if exit_now:
                pass

    roi = (modal - modal_awal) / modal_awal * 100
    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    avg_w = np.mean([t["profit"] for t in win]) if win else 0
    avg_l = abs(np.mean([t["profit"] for t in loss])) if loss else 1
    pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999
    net = sum(t["profit"] for t in trades)

    return {
        "name": name,
        "modal_akhir": round(modal),
        "roi": round(roi, 2),
        "trades": len(trades),
        "win": len(win),
        "loss": len(loss),
        "win_rate": round(len(win) / max(len(trades), 1) * 100, 1),
        "max_dd": round(dd_max, 1),
        "avg_win": round(avg_w),
        "avg_loss": round(avg_l),
        "profit_factor": round(pf, 2),
        "net_profit": round(net),
        "trade_list": trades[-15:],
        "equity": equity
    }


def print_table(results):
    print(f"\n{'='*80}")
    print(f"  KOMPARASI STRATEGI XAUUSDm — Data Real MT5")
    print(f"  Periode: Nov 2023 — Jun 2026 (800 bars daily)")
    print(f"  Modal Awal: Rp{MODAL:,}")
    print(f"{'='*80}")
    print(f"  {'Metric':<20} {'A: Trend':<18} {'B: Mean Rev':<18} {'C: Breakout':<18}")
    print(f"  {'-'*20} {'-'*18} {'-'*18} {'-'*18}")
    for r in results:
        print(f"  {'Modal Akhir':<20} {'Rp' + format(r['modal_akhir'], ',')}")
    print()
    rows = [
        ("Modal Akhir", "modal_akhir", lambda v: f"Rp{v:,}"),
        ("ROI", "roi", lambda v: f"{v:+.2f}%"),
        ("Net Profit", "net_profit", lambda v: f"Rp{v:,}"),
        ("Total Trades", "trades", lambda v: f"{v}"),
        ("Win", "win", lambda v: f"{v}"),
        ("Loss", "loss", lambda v: f"{v}"),
        ("Win Rate", "win_rate", lambda v: f"{v}%"),
        ("Max DD", "max_dd", lambda v: f"{v}%"),
        ("Avg Win", "avg_win", lambda v: f"Rp{v:,}"),
        ("Avg Loss", "avg_loss", lambda v: f"Rp{v:,}"),
        ("Profit Factor", "profit_factor", lambda v: f"{v}"),
    ]
    for label, key, fmt in rows:
        vals = [fmt(r[key]) for r in results]
        print(f"  {label:<20} {vals[0]:<18} {vals[1]:<18} {vals[2]:<18}")
    print(f"  {'='*80}")

    sorted_r = sorted(results, key=lambda x: x["roi"], reverse=True)
    print(f"\n  RANKING:")
    for i, r in enumerate(sorted_r, 1):
        tag = {1: "[1st]", 2: "[2nd]", 3: "[3rd]"}.get(i, f"[{i}th]")
        print(f"  {tag} {r['name']} — ROI {r['roi']:+.2f}% | WR {r['win_rate']}% | PF {r['profit_factor']} | DD {r['max_dd']}%")

    for r in results:
        print(f"\n  TRADES {r['name']} (last 8):")
        for t in r["trade_list"][-8:]:
            pm = "+" if t["profit"] > 0 else ""
            print(f"    {t['tgl'].date()} | {t['side']} | Entry:{t['entry']:.1f} -> Exit:{t['exit']:.1f} | {pm}Rp{t['profit']:,}")


def prepare_data(df):
    df["atr"] = atr(df, 14)
    df["ema9"] = ema(df["close"], 9)
    df["ema20"] = ema(df["close"], 20)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["rsi"] = rsi(df["close"], 14)
    df["adx"], df["pdi"], df["ndi"] = adx(df, 14)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bb(df["close"], 20, 2)
    df["stoch_k"], _ = stochastic(df["high"], df["low"], df["close"], 14, 3)
    df["dc_high"] = df["high"].rolling(20).max()
    df["dc_low"] = df["low"].rolling(20).min()
    df["vol_ma"] = df["tick_volume"].rolling(20).mean()
    df.dropna(inplace=True)
    return df


def bb(close, p=20, std=2):
    m = close.rolling(p).mean()
    s = close.rolling(p).std()
    return m + std * s, m, m - std * s


def stochastic(h, l, c, k=14, d=3):
    low = l.rolling(k).min()
    high = h.rolling(k).max()
    k_line = 100 * (c - low) / (high - low)
    return k_line, k_line.rolling(d).mean()


# =========== MAIN ===========
if not init_mt5():
    print("[ERROR] MT5 tidak bisa diinisialisasi. Pastikan MT5 sudah login.")
    exit()

print("[INFO] Mengambil data XAUUSDm...")
df = get_data(800)
if df is None:
    print("[ERROR] Tidak ada data")
    mt5.shutdown()
    exit()

print(f"[OK] Data: {df.index[0].date()} — {df.index[-1].date()} ({len(df)} bars)")
df = prepare_data(df)
print(f"[OK] Indicators computed. Trading bars: {len(df)}")

print("\n[RUN] Strategy A — Trend Momentum (EMA + ADX)...")
ra = run_backtest(df, MODAL, strat_a, "A: Trend Momentum")

print("[RUN] Strategy B — Mean Reversion (RSI + Stoch + BB)...")
rb = run_backtest(df, MODAL, strat_b, "B: Mean Reversion")

print("[RUN] Strategy C — Breakout Volatility (Donchian + Volume)...")
rc = run_backtest(df, MODAL, strat_c, "C: Breakout Volatility")

print_table([ra, rb, rc])

mt5.shutdown()
print("\n[DONE]")
