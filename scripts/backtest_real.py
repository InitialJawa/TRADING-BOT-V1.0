import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
LOT_BASE = 0.1
MODAL = 5000000  # IDR ~ $345 (converted from Rp5jt)
BIAYA_VPS = 50000  # IDR per bulan


def init_mt5():
    if not mt5.initialize():
        print(f"[ERROR] MT5 init: {mt5.last_error()}")
        return False
    if not mt5.symbol_select(SYMBOL, True):
        print(f"[ERROR] Cannot select {SYMBOL}")
        return False
    print(f"[OK] MT5 connected | Account: {mt5.account_info().login}")
    return True


def get_data(bars=1000):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, bars)
    if rates is None or len(rates) == 0:
        print(f"[ERROR] No data for {SYMBOL}")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    print(f"[OK] Data: {len(df)} bars ({df.index[0].date()} to {df.index[-1].date()})")
    return df


def calculate_indicators(df):
    # ATR (Average True Range)
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1))
        )
    )
    df["atr"] = df["tr"].rolling(14).mean()

    # EMA cepat & lambat untuk Adaptive
    df["ema_fast"] = df["close"].ewm(span=9).mean()
    df["ema_slow"] = df["close"].ewm(span=21).mean()

    # RSI untuk Trend Reversal
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    # Bollinger Bands
    df["bb_mid"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    return df.dropna()


def signal_adaptive(df, i):
    """Adaptive trend following: EMA cross + MACD confirmation"""
    if df["ema_fast"].iloc[i] > df["ema_slow"].iloc[i] and df["macd"].iloc[i] > df["macd_signal"].iloc[i]:
        return "BUY"
    elif df["ema_fast"].iloc[i] < df["ema_slow"].iloc[i] and df["macd"].iloc[i] < df["macd_signal"].iloc[i]:
        return "SELL"
    return "HOLD"


def signal_trend_re(df, i):
    """Trend reversal: RSI extreme + Bollinger bounce"""
    if df["rsi"].iloc[i] < 30 and df["close"].iloc[i] <= df["bb_lower"].iloc[i]:
        return "BUY"
    elif df["rsi"].iloc[i] > 70 and df["close"].iloc[i] >= df["bb_upper"].iloc[i]:
        return "SELL"
    return "HOLD"


def backtest(df, modal_awal):
    state = StateManager("data/backtest_real.db")
    modal = modal_awal
    posisi = None
    harga_masuk = 0
    lot = LOT_BASE

    trades = []
    equity_curve = []
    bulan_aktif = None
    dd_puncak = modal
    dd_max = 0

    for i in range(50, len(df) - 1):
        tgl = df.index[i]
        harga = df["close"].iloc[i]
        harga_next = df["close"].iloc[i + 1]

        bulan_ini = tgl.month
        if bulan_ini != bulan_aktif:
            bulan_aktif = bulan_ini
            modal -= BIAYA_VPS

        sig_adap = signal_adaptive(df, i)
        sig_trend = signal_trend_re(df, i)

        if posisi is None:
            if sig_adap == "BUY" or sig_trend == "BUY":
                posisi = "LONG"
                harga_masuk = harga
                trades.append({"tgl": tgl, "type": "BUY", "harga": harga, "modal_sebelum": modal})
            elif sig_adap == "SELL" or sig_trend == "SELL":
                posisi = "SHORT"
                harga_masuk = harga
                trades.append({"tgl": tgl, "type": "SELL", "harga": harga, "modal_sebelum": modal})
        else:
            profit = 0
            if posisi == "LONG":
                profit = (harga_next - harga_masuk) / harga_masuk * modal * 0.02
            elif posisi == "SHORT":
                profit = (harga_masuk - harga_next) / harga_masuk * modal * 0.02

            modal += profit

            # Update drawdown
            if modal > dd_puncak:
                dd_puncak = modal
            dd_skrg = (dd_puncak - modal) / dd_puncak * 100
            dd_max = max(dd_max, dd_skrg)

            # Update state
            state.upsert_metric("portfolio_drawdown", round(dd_skrg, 2))
            state.upsert_metric(f"modal_{tgl.date()}", round(modal, 2))

            # Risk management: reduce lot if drawdown > 10%
            if dd_skrg > 10:
                lot = max(0.01, lot - 0.02)
            elif dd_skrg < 5:
                lot = min(LOT_BASE, lot + 0.01)

            posisi = None
            trades[-1]["tgl_close"] = tgl
            trades[-1]["type_close"] = "SELL" if trades[-1]["type"] == "BUY" else "COVER"
            trades[-1]["harga_close"] = harga
            trades[-1]["profit"] = round(profit, 2)
            trades[-1]["modal_sesudah"] = round(modal, 2)

        equity_curve.append({"tgl": tgl, "modal": round(modal, 2)})

    return modal, trades, equity_curve, dd_max


def print_hasil(modal_awal, modal_akhir, trades, equity_curve, dd_max, periode):
    laba_total = sum(t.get("profit", 0) for t in trades if "profit" in t)
    rugi_total = sum(t.get("profit", 0) for t in trades if "profit" in t and t["profit"] < 0)
    win_trades = [t for t in trades if t.get("profit", 0) > 0]
    loss_trades = [t for t in trades if t.get("profit", 0) < 0]
    roi = (modal_akhir - modal_awal) / modal_awal * 100
    sharpe = round(laba_total / abs(rugi_total), 2) if rugi_total != 0 else 0

    print(f"\n{'='*60}")
    print(f" HASIL BACKTEST REAL - {periode}")
    print(f"{'='*60}")
    print(f" Modal Awal:   Rp{modal_awal:,.0f} (${modal_awal/14500:,.2f})")
    print(f" Modal Akhir:  Rp{modal_akhir:,.0f} (${modal_akhir/14500:,.2f})")
    print(f" ROI:          {roi:+.2f}%")
    print(f" Total Trades: {len(trades)}")
    print(f" Win Trades:   {len(win_trades)} ({round(len(win_trades)/max(len(trades),1)*100)}%)")
    print(f" Loss Trades:  {len(loss_trades)} ({round(len(loss_trades)/max(len(trades),1)*100)}%)")
    print(f" Max DD:       {dd_max:.1f}%")
    print(f" Sharpe:       {sharpe}")
    print(f" Profit/bln:   Rp{round(laba_total / max(len(equity_curve)/22, 1)):,.0f}")
    print(f"{'='*60}")

    # Top 5 trades
    print(f"\n  TOP 5 TRADES TERBESAR:")
    sorted_trades = sorted([t for t in trades if "profit" in t], key=lambda x: abs(x.get("profit", 0)), reverse=True)[:5]
    for t in sorted_trades:
        tgl = t.get("tgl", "")
        tip = t.get("type", "")
        prf = t.get("profit", 0)
        print(f"    {tgl.date()} | {tip} | Profit: Rp{prf:+,.0f}")

    # Save to state
    state = StateManager("data/backtest_real.db")
    state.log_backtest("adaptive", "PASS" if roi > 0 else "FAILED",
                       {"roi": roi, "trades": len(trades), "win_rate": round(len(win_trades)/max(len(trades),1)*100, 1),
                        "max_dd": dd_max, "sharpe": sharpe})


# =========== MAIN ===========
if not init_mt5():
    exit()

print("\n[INFO] Mengambil data 3 tahun XAUUSDm...")
df = get_data(800)
if df is None:
    mt5.shutdown()
    exit()

df = calculate_indicators(df)

# Backtest full period
modal_awal = 5_000_000
modal_full, trades_full, eq_full, dd_full = backtest(df.copy(), modal_awal)
print_hasil(modal_awal, modal_full, trades_full, eq_full, dd_full, "FULL PERIOD")

# Backtest 2 bulan terakhir
df2 = df.iloc[-60:]
modal_2, trades_2, eq_2, dd_2 = backtest(df2.copy(), modal_awal)
print_hasil(modal_awal, modal_2, trades_2, eq_2, dd_2, "2 BULAN TERAKHIR")

# Backtest 4 bulan terakhir
df4 = df.iloc[-120:]
modal_4, trades_4, eq_4, dd_4 = backtest(df4.copy(), modal_awal)
print_hasil(modal_awal, modal_4, trades_4, eq_4, dd_4, "4 BULAN TERAKHIR")

# Summary per bulan
print(f"\n{'='*60}")
print(" EQUITY CURVE (per 20 bars)")
print(f"{'='*60}")
for i in range(0, len(eq_full), 60):
    pt = eq_full[i]
    print(f"  {pt['tgl'].date()} | Modal: Rp{pt['modal']:,.0f}")

mt5.shutdown()
print("\n[DONE] Backtest selesai")
