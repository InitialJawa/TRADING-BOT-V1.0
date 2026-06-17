import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

SYMBOL = "XAUUSDm"
MODAL = 12_000_000

AGGRESSIVE = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 35, "rsi_long_max": 80,
    "rsi_short_min": 20, "rsi_short_max": 65,
    "macd_fast": 8, "macd_slow": 20, "macd_signal": 7,
    "atr_period": 10, "atr_sl_mult": 1.2, "atr_tp_mult": 2.5, "atr_trail_mult": 0.8,
    "volume_ma_period": 15, "volume_mult": 0.9,
    "max_hold_bars": 36, "lot_pct": 300, "running_pct": 0.05
}

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def atr(df, p=10):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()

def rsi(s, p=14):
    d = s.diff(); g = d.where(d > 0, 0).rolling(p).mean(); l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def macd(s, f=8, sl=20, sg=7):
    e1 = ema(s, f); e2 = ema(s, sl); m = e1 - e2; return m, ema(m, sg)

def prep(df):
    p = AGGRESSIVE
    df["ema5"] = ema(df["close"], p["ema_fast"])
    df["ema13"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr"] = atr(df, p["atr_period"])
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    df["macd"], df["macd_signal"] = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True); return df

def signal(df, i):
    p = AGGRESSIVE; row = df.iloc[i]; c = row["close"]
    above_200 = c > row["ema200"]
    ema_bull = row["ema5"] > row["ema13"]
    rsi_ok_long = p["rsi_long_min"] <= row["rsi"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_signal"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    if above_200 and ema_bull and rsi_ok_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_ok_short = p["rsi_short_min"] <= row["rsi"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_signal"]
    if not above_200 and ema_bear and rsi_ok_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def backtest(df):
    p = AGGRESSIVE
    modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ema5 = df["ema5"].iloc[i]; ema13 = df["ema13"].iloc[i]
        sig = signal(df, i)

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 20: in_trade = False; posisi = None; continue

        if not in_trade:
            if sig != "HOLD":
                posisi = sig; entry_price = c; entry_idx = i
                sl_price = c - a * p["atr_sl_mult"] if sig == "BUY" else c + a * p["atr_sl_mult"]
                tp_price = c + a * p["atr_tp_mult"] if sig == "BUY" else c - a * p["atr_tp_mult"]
                trail = False; modal -= 5000; in_trade = True
        else:
            bars = i - entry_idx; exit = False; profit = 0.0
            if posisi == "BUY":
                if c <= sl_price: profit = (sl_price - entry_price) / entry_price * modal; exit = True
                elif c >= tp_price: profit = (min(c, tp_price) - entry_price) / entry_price * modal; exit = True
                elif ema5 < ema13: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - min(c, tp_price)) / entry_price * modal; exit = True
                elif ema5 > ema13: profit = (entry_price - c) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit:
                modal += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal),
                    "entry": entry_price, "exit": c, "rr": round((c-entry_price)/(a*p["atr_sl_mult"])*100)/100 if posisi=="BUY" else round((entry_price-c)/(a*p["atr_sl_mult"])*100)/100})
                in_trade = False; posisi = None

    return modal, dd_max, trades

def print_trades(trades):
    print(f"\n  {'='*72}")
    print(f"  SEMUA TRADE (terakhir 20)")
    print(f"  {'='*72}")
    print(f"  {'Date':<20} {'Side':<5} {'Entry':<10} {'Exit':<10} {'Bars':<5} {'Profit':<12} {'R:R':<6} {'Modal'}")
    print(f"  {'-'*72}")
    for t in trades[-20:]:
        p = t["profit"]
        p_str = f"+{p:,}" if p > 0 else f"{p:,}"
        print(f"  {str(t['tgl'])[:19]:<20} {t['posisi']:<5} ${t['entry']:<7.2f} ${t['exit']:<7.2f} {t['held']:<4} {p_str:>7}  {t.get('rr',0):<5.2f}  Rp{t['modal']:,}")

def main():
    print("=" * 72)
    print(f"  STRATEGY D AGGRESSIVE — BACKTEST 2 BULAN")
    print(f"  Modal Rp12jt di akun Exness — XAUUSDm H1")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    if not mt5.initialize():
        print("[ERROR] MT5 gagal"); return
    mt5.symbol_select(SYMBOL, True)
    a = mt5.account_info()
    print(f"\n  Akun: {a.login} ({a.server}) | Balance: Rp{a.balance:,.0f}")

    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 1460)
    mt5.shutdown()
    if rates is None or len(rates) < 200:
        print("[ERROR] Data tidak cukup"); return
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    t0, t1 = df.index[0].date(), df.index[-1].date()
    print(f"  Periode: {t0} — {t1} ({len(df)} bars = {len(df)//24} hari)")

    df = prep(df)
    modal_akhir, dd_max, trades = backtest(df)

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    pf = sum(t["profit"] for t in win) / max(abs(sum(t["profit"] for t in loss)), 1)
    roi = (modal_akhir - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0

    print(f"\n  {'='*72}")
    print(f"  HASIL 2 BULAN — Strategy D AGGRESSIVE")
    print(f"  {'='*72}")
    print(f"  Modal Awal:     Rp{MODAL:,.0f}")
    print(f"  Modal Akhir:    Rp{modal_akhir:,.0f}")
    print(f"  Profit:         Rp{modal_akhir - MODAL:+,.0f}")
    print(f"  ROI:            {roi:+.2f}%")
    print(f"  Max DD:         {dd_max:.1f}%")
    print(f"  Trades:         {len(trades)} ({len(win)}W / {len(loss)}L)")
    print(f"  Win Rate:       {len(win)/max(len(trades),1)*100:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  Avg Hold:       {avg_hold:.0f} bars ({avg_hold:.1f} jam)")
    print(f"  Sinyal/bulan:   {len(trades)/2:.0f}")
    print(f"  Sinyal/minggu:  {len(trades)/max(len(df)/24/7,1):.1f}")

    print(f"\n  >> Kalau dipakai di akun Rp12jt:")
    print(f"     Profit 2 bulan: Rp{modal_akhir - MODAL:+,.0f}")
    print(f"     Rata-rata/bulan: Rp{(modal_akhir - MODAL)//2:+,.0f}")
    print(f"     Rata-rata/minggu: Rp{(modal_akhir - MODAL)//8:+,.0f}")
    print(f"     Rata-rata/hari: Rp{(modal_akhir - MODAL)//len(trades):+,.0f} per trade")

    print_trades(trades)

    print(f"\n{'='*72}")
    verdict = "LAYAK" if roi > 10 and dd_max < 10 else "HATI-HATI"
    print(f"  KESIMPULAN: Strategy D AGGRESSIVE {verdict} dipakai di akun real")
    print(f"  {'='*72}")


if __name__ == "__main__":
    main()
