# Strategy G — Auto Execution ke MT5
# Run: python scripts/jalankan_strat_g.py --auto
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time, json, logging
from datetime import datetime, timezone
from src.state_manager import StateManager

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "g_monitor.log")
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

SYMBOL = "XAUUSDm"
INITIAL_MODAL = 12_000_000
TARGET = 500_000
IDR_USD = 15000

CONF_SIZING = [
    (0, 2, 1.0),
    (3, 4, 1.5),
    (5, 6, 2.0),
]

CONFIG = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 30, "rsi_long_max": 95,
    "rsi_short_min": 5, "rsi_short_max": 70,
    "atr_period": 10, "atr_sl_mult": 0.5, "atr_tp_mult": 2.2, "atr_trail_mult": 0.3,
    "volume_ma_period": 15, "volume_mult": 0.7,
    "max_hold_bars": 20, "running_pct": 0.12,
    "risk_per_trade_pct": 0.5,
    "max_daily_loss_pct": 3.0,
    "max_dd_pct": 15.0,
}

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def fetch_h1(bars=200):
    rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars)
    if rh is None: return None
    dh1 = pd.DataFrame(rh)
    dh1["time"] = pd.to_datetime(dh1["time"], unit="s")
    dh1.set_index("time", inplace=True)
    dh1["ema9"] = ema(dh1["close"], 9)
    dh1["ema21"] = ema(dh1["close"], 21)
    dh1["h1_trend"] = np.where(dh1["ema9"] > dh1["ema21"], "UP", "DOWN")
    dh1.dropna(inplace=True)
    return dh1

def prep(df):
    p = CONFIG
    df["ema5"] = ema(df["close"], p["ema_fast"]); df["ema13"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"]); df["ema200"] = ema(df["close"], p["ema_major"])
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["atr"] = tr.rolling(p["atr_period"]).mean()
    d = df["close"].diff(); g = d.where(d > 0, 0).rolling(p["rsi_period"]).mean()
    l = (-d.where(d < 0, 0)).rolling(p["rsi_period"]).mean()
    df["rsi"] = 100 - (100 / (1 + g / l))
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    m = df["close"].rolling(20).mean(); s = df["close"].rolling(20).std()
    df["bbw"] = (m + 2*s - (m - 2*s)) / m
    df["bbw_ma"] = sma(df["bbw"], 20)
    df["squeeze"] = df["bbw"] < df["bbw_ma"]
    df["hour_utc"] = df.index.hour
    dh1 = fetch_h1()
    if dh1 is not None:
        h1_t = dh1["h1_trend"].resample("15min").ffill()
        df["h1_trend"] = h1_t.reindex(df.index, method="ffill")
    else:
        df["h1_trend"] = "NEUTRAL"
    df.dropna(inplace=True); return df

def calc_confidence(row):
    s = 0; bull = row["ema5"] > row["ema13"]
    if (bull and row["h1_trend"] == "UP") or (not bull and row["h1_trend"] == "DOWN"): s += 2
    if row["squeeze"]: s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2: s += 1
    if bull and row["rsi"] > 65: s += 1
    if not bull and row["rsi"] < 35: s += 1
    if 7 <= row["hour_utc"] < 15: s += 1
    return s

def get_frac(conf):
    for lo, hi, f in CONF_SIZING:
        if lo <= conf <= hi: return f
    return 1.0

def get_signal(df):
    row = df.iloc[-1]
    bull = row["ema5"] > row["ema13"]
    if bull and 30 <= row["rsi"] <= 95 and row["tick_volume"] > row["vol_ma"] * 0.7:
        return "BUY"
    if not bull and 5 <= row["rsi"] <= 70 and row["tick_volume"] > row["vol_ma"] * 0.7:
        return "SELL"
    return "HOLD"

def calc_lots(modal, entry_price, sl_price, conf):
    p = CONFIG
    sl_distance = abs(entry_price - sl_price)
    risk_idr = modal * p["risk_per_trade_pct"] / 100
    # Hitung lots dari risk
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return 0.01
    profit_per_01 = mt5.order_calc_profit(
        mt5.ORDER_TYPE_BUY, SYMBOL, 0.01, entry_price, entry_price + 1)
    if profit_per_01 is None or profit_per_01 == 0: return 0.01
    lots = risk_idr / abs(profit_per_01 * sl_distance) * 0.01
    frac = get_frac(conf)
    lots *= frac
    si = mt5.symbol_info(SYMBOL)
    if si:
        lots = max(si.volume_min, min(lots, si.volume_max))
        lots = round(lots / si.volume_step) * si.volume_step
    return max(0.01, lots)

def get_open_position():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions and len(positions) > 0:
        return positions[0]
    return None

def close_position(pos, price, reason=""):
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 20,
        "magic": 250000,
        "comment": f"G close {reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result

def modify_sl_tp(pos, sl, tp):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": SYMBOL,
        "position": pos.ticket,
        "sl": sl,
        "tp": tp,
        "magic": 250000,
    }
    return mt5.order_send(request)

def place_order(signal, entry, sl, tp, lots, conf):
    order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lots,
        "type": order_type,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 250000,
        "comment": f"G_{conf}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result

def manage_position(pos, df, daily_pnl, state):
    i = len(df) - 1
    if pos is None: return
    row = df.iloc[-1]; c = row["close"]; a = row["atr"]
    held_bars = None
    # Cari bar entry (posisi created time)
    pos_time = pd.to_datetime(pos.time, unit="s")
    entry_idx = df.index.get_indexer([pos_time], method="nearest")[0]
    held = i - entry_idx

    exit_signal = False; reason = ""
    if pos.type == mt5.ORDER_TYPE_BUY:
        if c <= pos.sl: exit_signal = True; reason = "SL"
        elif c >= pos.tp: exit_signal = True; reason = "TP"
        elif row["ema5"] < row["ema13"]: exit_signal = True; reason = "EMA_FLIP"
        elif held >= CONFIG["max_hold_bars"]: exit_signal = True; reason = "MAX_HOLD"
        else:
            td = a * CONFIG["atr_trail_mult"]
            if not hasattr(manage_position, "trail_active"):
                manage_position.trail_active = {}
            if pos.ticket not in manage_position.trail_active:
                manage_position.trail_active[pos.ticket] = False
            if not manage_position.trail_active[pos.ticket] and (c - pos.price_open) >= td:
                new_sl = pos.price_open + td * 0.3
                if new_sl > pos.sl:
                    modify_sl_tp(pos, new_sl, pos.tp)
                    manage_position.trail_active[pos.ticket] = True
    else:
        if c >= pos.sl: exit_signal = True; reason = "SL"
        elif c <= pos.tp: exit_signal = True; reason = "TP"
        elif row["ema5"] > row["ema13"]: exit_signal = True; reason = "EMA_FLIP"
        elif held >= CONFIG["max_hold_bars"]: exit_signal = True; reason = "MAX_HOLD"
        else:
            td = a * CONFIG["atr_trail_mult"]
            if pos.ticket not in manage_position.trail_active:
                manage_position.trail_active[pos.ticket] = False
            if not manage_position.trail_active[pos.ticket] and (pos.price_open - c) >= td:
                new_sl = pos.price_open - td * 0.3
                if new_sl < pos.sl:
                    modify_sl_tp(pos, pos.sl, pos.tp)
                    new_sl = min(pos.sl, new_sl)
                    if new_sl < pos.sl:
                        modify_sl_tp(pos, new_sl, pos.tp)
                    manage_position.trail_active[pos.ticket] = True

    if exit_signal:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            result = close_position(pos, price, reason)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                profit_idr = result.profit + (result.commission or 0) + (result.swap or 0)
                daily_pnl["today"] += profit_idr
                state.log_backtest("strategy_g_m15", "TRADE_CLOSED", {
                    "pos": "BUY" if pos.type==mt5.ORDER_TYPE_BUY else "SELL",
                    "entry": pos.price_open, "exit": price,
                    "profit": profit_idr, "reason": reason, "held": held,
                })

def should_stop(modal, daily_pnl):
    p = CONFIG
    dd = max(0, (INITIAL_MODAL - modal) / INITIAL_MODAL * 100)
    if dd > p["max_dd_pct"]: return True, f"DD {dd:.1f}% > {p['max_dd_pct']}%"
    daily_loss = abs(min(0, daily_pnl.get("today", 0)))
    daily_loss_pct = daily_loss / INITIAL_MODAL * 100
    if daily_loss_pct > p["max_daily_loss_pct"]:
        return True, f"Daily loss {daily_loss_pct:.1f}% > {p['max_daily_loss_pct']}%"
    return False, ""

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true", help="Auto execution mode (places real trades)")
    args = parser.parse_args()

    print("=" * 72)
    print(f"  STRATEGY G -- M15 Confidence Sizing")
    mode = "AUTO EXECUTION" if args.auto else "LIVE MONITOR"
    print(f"  Mode: {mode}")
    print(f"  Target Rp{TARGET:,}/hari | Risk {CONFIG['risk_per_trade_pct']}%/trade")
    if args.auto:
        print(f"  *** AKAN ENTRY REAL KE MT5 ***")
        print(f"  Daily loss limit: {CONFIG['max_daily_loss_pct']}% | Max DD: {CONFIG['max_dd_pct']}%")
    print(f"  Tekan Ctrl+C untuk berhenti")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    if not mt5.initialize():
        print("[ERROR] MT5 gagal. Buka MT5 dulu, login.")
        return

    a = mt5.account_info()
    state = StateManager("data/state.db")
    running_modal = state.get_metric("running_modal")
    if running_modal is None or running_modal <= 0:
        running_modal = float(a.balance) * IDR_USD if a.balance < 100000 else float(a.balance)
    running_modal = max(running_modal, INITIAL_MODAL)

    daily_pnl = {"today": 0, "date": datetime.now().date()}
    prev_info = {"sig": None}; first_run = True
    manage_position.trail_active = {}
    day_start_modal = running_modal

    try:
        while True:
            now = datetime.now()
            # Check daily reset
            if now.date() != daily_pnl["date"]:
                profit_today = daily_pnl["today"] if args.auto else 0
                print(f"\n[DAY RESET] Profit hari ini: Rp{profit_today:+,.0f}")
                state.upsert_metric(f"profit_{daily_pnl['date']}", round(profit_today, 2))
                daily_pnl = {"today": 0, "date": now.date()}
                day_start_modal = running_modal

            # Fetch data
            mt5.symbol_select(SYMBOL, True)
            rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 300)
            if rh is None: time.sleep(60); continue
            df = pd.DataFrame(rh)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True); df = prep(df)

            last = df.iloc[-1]; now_t = df.index[-1]
            sig = get_signal(df)
            conf = calc_confidence(last)
            frac = get_frac(conf)
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None: time.sleep(60); continue
            entry_price = tick.ask if sig == "BUY" else tick.bid

            # Check stop conditions
            stop, reason = should_stop(running_modal, daily_pnl)
            if stop and args.auto:
                print(f"\n[STOP] {reason} — menghentikan trading")
                state.upsert_metric("stop_reason", reason)
                state.upsert_strategy("strategy_g_m15", "PAUSED")
                break

            # Manage open position
            pos = get_open_position()
            if pos:
                manage_position(pos, df, daily_pnl, state)

            # Check signal vs position
            pos = get_open_position()
            if args.auto and sig != "HOLD" and pos is None:
                sl = entry_price - last["atr"] * CONFIG["atr_sl_mult"] if sig == "BUY" else entry_price + last["atr"] * CONFIG["atr_sl_mult"]
                tp = entry_price + last["atr"] * CONFIG["atr_tp_mult"] if sig == "BUY" else entry_price - last["atr"] * CONFIG["atr_tp_mult"]
                lots = calc_lots(running_modal, entry_price, sl, conf)
                result = place_order(sig, entry_price, sl, tp, lots, conf)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"\n[ORDER] {sig} {lots:.2f} lot @ {entry_price:.3f} | SL {sl:.3f} TP {tp:.3f} | conf {conf} ({frac}x)")
                    state.log_backtest("strategy_g_m15", "ORDER_PLACED", {
                        "signal": sig, "lots": lots, "entry": entry_price,
                        "sl": sl, "tp": tp, "conf": conf, "frac": frac,
                    })

            # Display
            now_str = now_t.strftime("%H:%M")
            pos_str = ""
            p = get_open_position()
            if p:
                pos_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                pos_str = f" | {pos_type} {p.volume:.2f}lot @ {p.price_open:.3f} PnL ${p.profit:.2f}"

            if first_run:
                print(f"\n  --- STRATEGY G | {mode} ---")
                print(f"  Log: {LOG_FILE}")
                print(f"  Akun: {a.login} ({a.server}) | Balance: ${a.balance:.2f}")
                print(f"  Running Modal: Rp{running_modal:,.0f} | Hari ini: Rp{daily_pnl['today']:+,.0f}")
                print(f"  Close: ${last['close']:.3f} | EMA5: {last['ema5']:.3f} | EMA13: {last['ema13']:.3f}")
                print(f"  Trend: {'UP' if last['ema5']>last['ema13'] else 'DOWN'} | H1: {last['h1_trend']} | RSI: {last['rsi']:.1f}")
                print(f"  ATR: ${last['atr']:.3f} | Squeeze: {'Y' if last['squeeze'] else 'N'}")
                print(f"\n  --- SIGNAL ---")
                if sig != "HOLD":
                    print(f"  >>> {sig} (conf {conf}, {frac}x)")
                    logging.info(f"START | SIGNAL {sig} | conf {conf} | {frac}x")
                else:
                    print(f"  HOLD -- menunggu sinyal")
                print(f"\n  >>> Running: scan tiap 15 menit. Ctrl+C untuk stop.")
                first_run = False
            else:
                if sig != prev_info["sig"]:
                    if sig == "HOLD":
                        msg = f"HOLD -- sinyal ilang (dari {prev_info['sig']}) | conf {conf}"
                        print(f"\n[{now_str}] {msg}{pos_str}")
                        logging.info(msg)
                    else:
                        msg = f"SIGNAL {sig} | conf {conf} | {frac}x"
                        print(f"\n[{now_str}] {msg}{pos_str}")
                        logging.info(msg)
                elif first_run:
                    pass
            # Heartbeat: tiap 15 menit kasih tau masih hidup
            hb_now = datetime.now()
            if hb_now.minute % 15 == 0 and hb_now.second < 5:
                if not hasattr(main, "last_hb_min") or main.last_hb_min != hb_now.minute:
                    main.last_hb_min = hb_now.minute
                    p = get_open_position()
                    if p:
                        pt = "BUY" if p.type==mt5.ORDER_TYPE_BUY else "SELL"
                        hb_pos = f"{pt} {p.volume:.2f}lot @ {p.price_open:.3f} PnL ${p.profit:.2f}"
                    else:
                        hb_pos = "NO POSITION"
                    hb_sig = sig if sig != "HOLD" else "HOLD"
                    hb_msg = f"HEARTBEAT | {hb_sig} | conf {conf} | {hb_pos}"
                    print(f"[{now_str}] {hb_msg}")
                    logging.info(hb_msg)
            prev_info["sig"] = sig

            # Sleep to next candle close
            next_min = ((now.minute // 15) + 1) * 15
            wait = (next_min - now.minute) * 60 - now.second
            if wait <= 0: wait = 900
            time.sleep(wait)

    except KeyboardInterrupt:
        print(f"\n{'='*72}")
        print(f"  BERHENTI ({datetime.now().strftime('%H:%M')} WIB)")
        pnl_str = f" | Profit hari ini: Rp{daily_pnl['today']:+,.0f}" if args.auto else ""
        print(f"{'='*72}{pnl_str}")
    finally:
        mt5.shutdown()
        state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())

if __name__ == "__main__":
    main()
