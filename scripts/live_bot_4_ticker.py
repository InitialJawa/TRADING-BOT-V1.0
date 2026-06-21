import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json, time
from datetime import datetime
from strategies.shared.stage_analysis import prep_stage, detect_stage, signal_stage_enhanced, confidence_score

TICKER_CFG = [
    {
        "name": "XAGUSDm", "strategy": "i", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {
            "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
            "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
            "atr_sl_mult": 1.2, "atr_trail_mult": 0.8, "trail_sl_mul": 1.5,
            "running_pct": 0.1, "volume_mult": 0.8,
            "stage_slope_threshold": 0.0004, "lot_pct": 100, "fee": 0,
            "conf_sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
            "confidence_factors": {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1},
        }
    },
    {
        "name": "XAUUSDm", "strategy": "i", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {
            "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
            "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
            "atr_sl_mult": 1.5, "atr_trail_mult": 0.8, "trail_sl_mul": 1.5,
            "running_pct": 0.1, "volume_mult": 0.8,
            "stage_slope_threshold": 0.0004, "lot_pct": 100, "fee": 0,
            "conf_sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
            "confidence_factors": {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1},
        }
    },
    {
        "name": "JP225m", "strategy": "i", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {
            "ema_fast": 9, "ema_medium": 21, "ema_trend": 50, "ema_major": 200,
            "rsi_period": 14, "atr_period": 14, "volume_ma_period": 20,
            "atr_sl_mult": 1.0, "atr_trail_mult": 0.8, "trail_sl_mul": 1.5,
            "running_pct": 0.1, "volume_mult": 0.8,
            "stage_slope_threshold": 0.0005, "lot_pct": 100, "fee": 0,
            "conf_sizing": [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)],
            "confidence_factors": {"h4": 2, "session": 1, "volume": 1, "rsi": 1, "squeeze": 1, "ema200": 1},
        }
    },
]

CONF_SIZING = [(0, 2, 1.0), (3, 4, 1.5), (5, 7, 2.0)]

def manage_position(ticker, params):
    positions = mt5.positions_get(symbol=ticker)
    if not positions:
        return None
    for pos in positions:
        tick = mt5.symbol_info_tick(ticker)
        current = tick.bid if pos.type == 0 else tick.ask
        entry = pos.price_open

        rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_H1, 0, 300)
        if rates is None:
            return pos
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)

        dh4 = None
        h4_rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_H4, 0, 80)
        if h4_rates is not None and len(h4_rates) > 50:
            dh4 = pd.DataFrame(h4_rates)
            dh4["time"] = pd.to_datetime(dh4["time"], unit="s")
            dh4.set_index("time", inplace=True)

        df = prep_stage(df, dh4, params)
        if len(df) < 5:
            return pos

        last = df.iloc[-1]
        stage = detect_stage(last, params.get("stage_slope_threshold", 0.0004))
        ema_bull = last["ema9"] > last["ema21"]

        should_close = False
        if pos.type == 0:
            if stage == 3 or not ema_bull:
                should_close = True
        elif pos.type == 1:
            if stage == 3 or ema_bull:
                should_close = True

        if should_close:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == 0 else tick.ask
            req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":ticker,"volume":pos.volume,
                   "type":close_type,"position":pos.ticket,"price":close_price,
                   "deviation":10,"magic":pos.magic,"comment":"Stage_exit",
                   "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
            r = mt5.order_send(req)
            print(f"  CLOSE {ticker} (Stage {stage}, EMA flip): retcode={r.retcode}")
            return None

        tsm = params.get("trail_sl_mul", 1.5)
        if pos.type == 0:
            new_sl = current - df["atr"].iloc[-1] * params["atr_trail_mult"] * tsm
            if new_sl > pos.sl:
                req = {"action":mt5.TRADE_ACTION_SLTP,"symbol":ticker,"position":pos.ticket,
                       "sl":new_sl,"tp":pos.tp,"deviation":10,"magic":pos.magic,
                       "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
                r = mt5.order_send(req)
                if r.retcode == 10009:
                    print(f"  TRAIL {ticker}: SL {pos.sl:.2f} -> {new_sl:.2f}")
        else:
            new_sl = current + df["atr"].iloc[-1] * params["atr_trail_mult"] * tsm
            if new_sl < pos.sl or pos.sl == 0:
                req = {"action":mt5.TRADE_ACTION_SLTP,"symbol":ticker,"position":pos.ticket,
                       "sl":new_sl,"tp":pos.tp,"deviation":10,"magic":pos.magic,
                       "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
                r = mt5.order_send(req)
                if r.retcode == 10009:
                    print(f"  TRAIL {ticker}: SL {pos.sl:.2f} -> {new_sl:.2f}")
        return pos
    return None

def open_trade(ticker, cfg, signal_dir, fraction=1.0):
    params = cfg["params"]
    mt5.symbol_select(ticker, True)
    s = mt5.symbol_info(ticker)
    tick = mt5.symbol_info_tick(ticker)
    a = mt5.account_info()

    rates = mt5.copy_rates_from_pos(ticker, cfg["timeframe"], 0, 100)
    df = pd.DataFrame(rates)
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1))))
    curr_atr = tr.rolling(14).mean().iloc[-1]

    price = tick.ask if signal_dir == "BUY" else tick.bid
    if signal_dir == "BUY":
        sl = price - curr_atr * params["atr_sl_mult"]
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl = price + curr_atr * params["atr_sl_mult"]
        order_type = mt5.ORDER_TYPE_SELL

    # Risk-based sizing: 0.5% of balance per trade (matches backtest ALLOC=50%)
    risk_amount = a.balance * 0.005
    sl_dist = abs(price - sl)
    sl_ticks = sl_dist / max(s.trade_tick_size, 1e-9)
    risk_per_lot = sl_ticks * s.trade_tick_value
    vol = max(s.volume_min, min(s.volume_max, risk_amount / max(risk_per_lot, 1e-9)))
    vol = round(vol / s.volume_step) * s.volume_step
    vol *= fraction
    vol = max(s.volume_min, min(s.volume_max, round(vol / s.volume_step) * s.volume_step))

    req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":ticker,"volume":vol,"type":order_type,
           "price":price,"sl":sl,"tp":0,"deviation":10,"magic":123456,"comment":"I_auto",
           "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
    r = mt5.order_send(req)
    amt = risk_per_lot * vol
    frac_str = f"x{fraction:.1f}" if fraction != 1.0 else ""
    print(f"  OPEN {ticker} {signal_dir} {vol} lots{frac_str} @ {price:.2f} "
          f"SL:{sl:.2f} (risk 2%={amt:.0f} {a.currency})")
    return r.retcode == 10009

def main():
    print(f"\n{'='*70}")
    print(f"  LIVE BOT — STRATEGY I (Stage Analysis Enhanced)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  Cycle setiap 5 menit (300s)")
    print(f"{'='*70}")

    if not mt5.initialize():
        print("[ERROR] MT5 gagal initialize. Buka MT5 dulu!")
        return

    a = mt5.account_info()
    print(f"  Account: {a.login} | Balance: Rp{a.balance:,.0f}")

    cycle = 0
    while True:
        cycle += 1
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === CYCLE {cycle} ===")
        a = mt5.account_info()
        print(f"  Balance: Rp{a.balance:,.0f} | Equity: Rp{a.equity:,.0f} | Floating: Rp{a.profit:+,.0f}")

        for tc in TICKER_CFG:
            sym = tc["name"]
            print(f"\n  --- {sym} (I) ---")

            pos = manage_position(sym, tc["params"])
            if pos:
                stage = "?"
                try:
                    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 300)
                    if rates is not None:
                        df = pd.DataFrame(rates)
                        df["time"] = pd.to_datetime(df["time"], unit="s")
                        df.set_index("time", inplace=True)
                        dh4_r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 80)
                        dh4 = None
                        if dh4_r is not None and len(dh4_r) > 50:
                            dh4 = pd.DataFrame(dh4_r)
                            dh4["time"] = pd.to_datetime(dh4["time"], unit="s")
                            dh4.set_index("time", inplace=True)
                        df = prep_stage(df, dh4, tc["params"])
                        if len(df) > 0:
                            stage = detect_stage(df.iloc[-1], tc["params"].get("stage_slope_threshold", 0.0004))
                except:
                    pass
                print(f"  POSITION: {'BUY' if pos.type==0 else 'SELL'} {pos.volume} lots @ {pos.price_open:.2f} "
                      f"Stage:{stage} SL:{pos.sl:.2f} PnL:{pos.profit:+.0f}")
                continue

            rates = mt5.copy_rates_from_pos(sym, tc["timeframe"], 0, tc["bars"])
            if rates is None or len(rates) < 100:
                print(f"  DATA FAIL")
                continue

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)

            h4_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, tc["bars"] // 4)
            dh4 = None
            if h4_rates is not None and len(h4_rates) > 50:
                dh4 = pd.DataFrame(h4_rates)
                dh4["time"] = pd.to_datetime(dh4["time"], unit="s")
                dh4.set_index("time", inplace=True)

            df = prep_stage(df, dh4, tc["params"])
            if len(df) < 5:
                continue

            last = df.iloc[-1]
            stage = detect_stage(last, tc["params"].get("stage_slope_threshold", 0.0004))
            sig = signal_stage_enhanced(df, -1, tc["params"])
            conf = confidence_score(last, tc["params"].get("confidence_factors", None))
            frac = 1.0
            for lo, hi, fv in tc["params"].get("conf_sizing", CONF_SIZING):
                if lo <= conf <= hi:
                    frac = fv; break

            stage_map = {1: "ACCUMULATION", 2: "TREND UP", 3: "DISTRIBUTION", 4: "TREND DOWN"}
            trend = "UP" if last["ema9"] > last["ema21"] else "DOWN"
            print(f"  Close: {last['close']:.2f} | Trend: {trend} | Stage: {stage}({stage_map.get(stage,'?')}) | "
                  f"Conf: {conf}x{frac:.1f} | RSI: {last['rsi']:.0f} | Signal: {sig}")

            if sig != "HOLD":
                ok = open_trade(sym, tc, sig, frac)
                if ok:
                    print(f"  >> {sym} {sig} OPENED!")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle done. Sleep 300s...")
        print(f"{'='*70}")
        time.sleep(300)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOP] Bot dihentikan user")
        mt5.shutdown()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc()
        mt5.shutdown()
