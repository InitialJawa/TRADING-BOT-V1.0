import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
LOT = 200

PARAMS = {
    "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 45, "rsi_long_max": 75,
    "rsi_short_min": 25, "rsi_short_max": 55,
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 4.0,
    "volume_ma_period": 20, "volume_mult": 1.1,
}


def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()


def prep(df):
    p = PARAMS
    df["ema9"] = ema(df["close"], p["ema_fast"])
    df["ema21"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["atr14"] = tr.rolling(14).mean()
    d = df["close"].diff(); g = d.where(d > 0, 0).rolling(14).mean()
    l = (-d.where(d < 0, 0)).rolling(14).mean()
    df["rsi14"] = 100 - (100 / (1 + g / l))
    e1 = ema(df["close"], 12); e2 = ema(df["close"], 26)
    df["macd"] = e1 - e2; df["macd_signal"] = ema(df["macd"], 9)
    df["vol_ma"] = sma(df["tick_volume"], 20)
    df.dropna(inplace=True)
    return df


def signal(df, i):
    p = PARAMS; row = df.iloc[i]; prev = df.iloc[i - 1]
    c = row["close"]

    long_cond = (
        c > row["ema200"] and
        row["ema9"] > row["ema21"] and
        p["rsi_long_min"] <= row["rsi14"] <= p["rsi_long_max"] and
        row["macd"] > row["macd_signal"] and
        row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    )
    if long_cond:
        return "BUY", f"EMA9({row['ema9']:.1f}) > EMA21({row['ema21']:.1f}) uptrend + RSI {row['rsi14']:.0f}"

    short_cond = (
        c < row["ema200"] and
        row["ema9"] < row["ema21"] and
        p["rsi_short_min"] <= row["rsi14"] <= p["rsi_short_max"] and
        row["macd"] < row["macd_signal"] and
        row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    )
    if short_cond:
        return "SELL", f"EMA9({row['ema9']:.1f}) < EMA21({row['ema21']:.1f}) downtrend + RSI {row['rsi14']:.0f}"

    trend = "UP" if row["ema9"] > row["ema21"] else "DOWN"
    reason = f"EMA9({row['ema9']:.1f}) / EMA21({row['ema21']:.1f}) trend {trend}"
    if row["tick_volume"] <= row["vol_ma"] * p["volume_mult"]:
        reason += " | volume rendah"
    return "HOLD", reason


def main():
    print("=" * 70)
    print(f"  STRATEGY D — H1 Confluence Momentum — LIVE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 70)

    if not mt5.initialize():
        print("[ERROR] MT5 gagal")
        return
    mt5.symbol_select(SYMBOL, True)

    a = mt5.account_info()
    print(f"\n  Akun: {a.login} | Balance: ${a.balance:,.2f} | Equity: ${a.equity:,.2f}")
    print(f"  Modal simulasi: Rp{MODAL:,} (Lot {LOT}%)")

    rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 500)
    mt5.shutdown()
    df = pd.DataFrame(rh)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = prep(df)

    last = df.iloc[-1]; now = df.index[-1]
    sig, reason = signal(df, -1)
    prev_sig, prev_reason = signal(df, -2)

    trend = "UP" if last["ema9"] > last["ema21"] else "DOWN"
    macd_status = "BULLISH" if last["macd"] > last["macd_signal"] else "BEARISH"

    print(f"\n  --- MARKET STATUS ({now}) ---")
    print(f"  Close:     ${last['close']:.2f}")
    print(f"  EMA9:      {last['ema9']:.2f} | EMA21: {last['ema21']:.2f} | EMA50: {last['ema50']:.2f} | EMA200: {last['ema200']:.2f}")
    print(f"  Trend:     {trend}")
    print(f"  RSI14:     {last['rsi14']:.1f}")
    print(f"  MACD:      {last['macd']:.2f} / Signal: {last['macd_signal']:.2f} ({macd_status})")
    print(f"  ATR14:     ${last['atr14']:.2f}")
    print(f"  Volume:    {last['tick_volume']:,.0f} (avg: {last['vol_ma']:,.0f})")

    print(f"\n  --- SIGNAL ---")
    sl_val = last["atr14"] * PARAMS["atr_sl_mult"]
    tp_val = last["atr14"] * PARAMS["atr_tp_mult"]

    if sig == "BUY":
        ps = MODAL * LOT / 100
        print(f"  >>> BUY signal! {reason}")
        print(f"  >>> Entry: ${last['close']:.2f}")
        print(f"  >>> SL:    ${last['close'] - sl_val:.2f} (-${sl_val:.2f})")
        print(f"  >>> TP:    ${last['close'] + tp_val:.2f} (+${tp_val:.2f})")
        print(f"  >>> R:R    {tp_val/sl_val:.1f}:1")
        print(f"  >>> Risk:  Rp{round(sl_val/last['close']*ps):,}")
    elif sig == "SELL":
        ps = MODAL * LOT / 100
        print(f"  >>> SELL signal! {reason}")
        print(f"  >>> Entry: ${last['close']:.2f}")
        print(f"  >>> SL:    ${last['close'] + sl_val:.2f} (+${sl_val:.2f})")
        print(f"  >>> TP:    ${last['close'] - tp_val:.2f} (-${tp_val:.2f})")
        print(f"  >>> R:R    {tp_val/sl_val:.1f}:1")
        print(f"  >>> Risk:  Rp{round(sl_val/last['close']*ps):,}")
    else:
        print(f"  HOLD. {reason}")
        if prev_sig != "HOLD":
            print(f"  Sinyal sebelumnya: {prev_sig} ({prev_reason})")
        print(f"  Menunggu confluence signal...")

    print(f"\n  --- 20 BAR TERAKHIR ---")
    print(f"  {'Date':<22} {'Close':<10} {'EMA9':<10} {'EMA21':<10} {'RSI':<6} {'Signal':<8} {'Vol':<12}")
    print(f"  {'-'*76}")
    for i in range(-20, 0):
        d = df.iloc[i]; s, _ = signal(df, i)
        low_rsi = "⬇" if d["rsi14"] <= 30 else "⬆" if d["rsi14"] >= 70 else " "
        print(f"  {str(df.index[i]):<22} ${d['close']:<7.2f} {d['ema9']:<9.1f} {d['ema21']:<9.1f} {d['rsi14']:<4.0f}{low_rsi} {s:<8} {d['tick_volume']:<12,.0f}")

    print(f"\n{'='*70}")
    print(f"  STATUS: H1 siap | Lot {LOT}% | Trend {trend} | Signal: {sig}")
    print(f"  Hold ~1-2 hari | Hasil keliatan tiap bar H1")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
