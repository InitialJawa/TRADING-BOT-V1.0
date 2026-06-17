import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
INITIAL_MODAL = 12_000_000

CONFIG = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 35, "rsi_long_max": 82,
    "rsi_short_min": 18, "rsi_short_max": 65,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 0.7, "atr_tp_mult": 1.8, "atr_trail_mult": 0.4,
    "volume_ma_period": 15, "volume_mult": 0.7,
    "max_hold_bars": 16, "lot_pct": 300, "running_pct": 0.08,
    "no_ema200_filter": True,
    "dynamic_lot": {"enabled": True, "base_lot_pct": 300, "min_lot_pct": 100, "max_lot_pct": 800}
}


def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()


def prep(df):
    p = CONFIG
    df["ema5"] = ema(df["close"], p["ema_fast"])
    df["ema13"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["atr"] = tr.rolling(p["atr_period"]).mean()
    d = df["close"].diff(); g = d.where(d > 0, 0).rolling(p["rsi_period"]).mean()
    l = (-d.where(d < 0, 0)).rolling(p["rsi_period"]).mean()
    df["rsi"] = 100 - (100 / (1 + g / l))
    e1 = ema(df["close"], p["macd_fast"]); e2 = ema(df["close"], p["macd_slow"])
    df["macd"] = e1 - e2; df["macd_sig"] = ema(df["macd"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True); return df


def signal(df, i):
    p = CONFIG; row = df.iloc[i]; c = row["close"]
    no_filter = p.get("no_ema200_filter", False)
    above_200 = c > row["ema200"]
    ema_bull = row["ema5"] > row["ema13"]
    rsi_long = p["rsi_long_min"] <= row["rsi"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_sig"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    if (above_200 or no_filter) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_short = p["rsi_short_min"] <= row["rsi"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_sig"]
    if (not above_200 or no_filter) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"


def calc_dynamic_lot(running_modal):
    dl = CONFIG["dynamic_lot"]
    if not dl["enabled"]:
        return dl["base_lot_pct"]
    ratio = max(running_modal, 1_000_000) / INITIAL_MODAL
    lot = dl["base_lot_pct"] * ratio
    lot = max(lot, dl["min_lot_pct"])
    lot = min(lot, dl["max_lot_pct"])
    return round(lot, 0)


def check_once(a, state, running_modal, prev_sig_info):
    mt5.symbol_select(SYMBOL, True)
    rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 300)

    df = pd.DataFrame(rh)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = prep(df)

    last = df.iloc[-1]; now = df.index[-1]
    current_lot = calc_dynamic_lot(running_modal)
    position_size = running_modal * current_lot / 100

    sig, reason = signal(df, -1), ""
    row = last
    if sig == "BUY":
        reason = f"EMA5({row['ema5']:.1f}) > EMA13({row['ema13']:.1f}) + RSI {row['rsi']:.0f}"
    elif sig == "SELL":
        reason = f"EMA5({row['ema5']:.1f}) < EMA13({row['ema13']:.1f}) + RSI {row['rsi']:.0f}"

    trend = "UP" if last["ema5"] > last["ema13"] else "DOWN"
    sl_val = last["atr"] * CONFIG["atr_sl_mult"]
    tp_val = last["atr"] * CONFIG["atr_tp_mult"]
    target_rp = tp_val / last["close"] * position_size if sig != "HOLD" else 0

    sig_changed = sig != prev_sig_info["sig"]
    prev_sig_info["sig"] = sig

    return {
        "now": now, "close": last["close"], "ema5": last["ema5"], "ema13": last["ema13"],
        "rsi": last["rsi"], "atr": last["atr"], "vol": last["tick_volume"],
        "sig": sig, "reason": reason, "trend": trend,
        "lot": current_lot, "position_size": position_size,
        "sl": sl_val, "tp": tp_val, "target_rp": target_rp, "sig_changed": sig_changed
    }


def main():
    import time
    print("=" * 72)
    print(f"  STRATEGY E -- M15 NoFilter Momentum -- LIVE MONITOR")
    print(f"  Target Rp100.000/hari | Dynamic Lot | Jalan terus")
    print(f"  Tekan Ctrl+C untuk berhenti")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    if not mt5.initialize():
        print("[ERROR] MT5 gagal"); return

    a = mt5.account_info()
    state = StateManager("data/state.db")
    running_modal = state.get_metric("running_modal")
    if running_modal is None or running_modal <= 0:
        running_modal = float(a.balance) * 100
    running_modal = max(running_modal, INITIAL_MODAL)

    prev_sig_info = {"sig": None}
    prev_sig = None
    first_run = True

    try:
        while True:
            info = check_once(a, state, running_modal, prev_sig_info)
            now_str = info["now"].strftime("%H:%M")

            if first_run:
                current_lot = info["lot"]
                position_size = info["position_size"]
                print(f"\n  --- MARKET STATUS ({info['now']}) ---")
                print(f"  Akun: {a.login} ({a.server}) | Balance: ${a.balance:,.2f}")
                print(f"  Running Modal: Rp{running_modal:,.0f}")
                print(f"  Dynamic Lot: {current_lot:.0f}% (position Rp{position_size:,.0f})")
                print(f"  Close: ${info['close']:.2f}")
                print(f"  EMA5: {info['ema5']:.2f} | EMA13: {info['ema13']:.2f}")
                print(f"  Trend: {info['trend']} | RSI14: {info['rsi']:.1f} | ATR14: ${info['atr']:.2f}")
                print(f"\n  --- SIGNAL ---")
                if info["sig"] != "HOLD":
                    print(f"  >>> {info['sig']}! {info['reason']}")
                    print(f"  >>> Entry: ${info['close']:.2f} | SL: ${info['close'] - info['sl']:.2f} | TP: ${info['close'] + info['tp']:.2f}")
                    print(f"  >>> R:R {info['tp']/info['sl']:.1f}:1 | Target: Rp{info['target_rp']:,.0f}")
                else:
                    print(f"  HOLD -- menunggu confluence signal")
                print(f"\n  >>> Running: scan tiap 15 menit. Ctrl+C untuk stop.")
                first_run = False
            else:
                if info["sig_changed"] and info["sig"] != "HOLD":
                    print(f"\n[{now_str}] SINYAL BARU: {info['sig']} {info['reason']}")
                    print(f"  Entry ${info['close']:.2f} | Target Rp{info['target_rp']:,.0f} | R:R {info['tp']/info['sl']:.1f}:1")
                elif info["sig_changed"] and info["sig"] == "HOLD" and prev_sig is not None:
                    print(f"\n[{now_str}] SINYAL HILANG: {prev_sig} -> HOLD")
                elif not info["sig_changed"] and info["sig"] == "HOLD":
                    pass  # no signal, quiet
                else:
                    print(f"[{now_str}] Signal: {info['sig']} | {info['close']:.2f} | RSI {info['rsi']:.0f}")

            prev_sig = info["sig"]
            # Sleep sampai candle M15 nutup (00/15/30/45)
            now = datetime.now()
            next_min = ((now.minute // 15) + 1) * 15
            wait = (next_min - now.minute) * 60 - now.second
            if wait <= 0: wait = 900
            time.sleep(wait)

    except KeyboardInterrupt:
        print(f"\n{'='*72}")
        print(f"  MONITOR BERHENTI ({datetime.now().strftime('%H:%M')} WIB)")
        print(f"{'='*72}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
