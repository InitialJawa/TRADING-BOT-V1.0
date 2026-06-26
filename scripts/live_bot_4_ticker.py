import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json, time
from datetime import datetime
from strategies.shared.indicators import ema, sma, atr, rsi

TICKERS = ["ETHUSDm", "XAGUSDm", "BTCUSDTm", "JP225m"]
TIMEFRAME = mt5.TIMEFRAME_M15
BARS = 500
SPREAD_PTS = 0

def load_params(symbol):
    path = os.path.join("config", symbol, "strategy_f.json")
    with open(path) as f:
        return json.load(f)["params"]

def prep(df, p):
    ef = p["ema_fast"]; em = p["ema_medium"]
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 15))
    df.dropna(inplace=True)
    return df

def signal_f(df, p):
    row = df.iloc[-1]
    ef = f"ema{p['ema_fast']}"; em = f"ema{p['ema_medium']}"
    ema_bull = row[ef] > row[em]
    ema_bear = row[ef] < row[em]
    rsi_long = p.get("rsi_long_min", 30) <= row["rsi"] <= p.get("rsi_long_max", 95)
    rsi_short = p.get("rsi_short_min", 5) <= row["rsi"] <= p.get("rsi_short_max", 70)
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("volume_mult", 1.0)
    if ema_bull and rsi_long and vol_ok:
        return "BUY"
    if ema_bear and rsi_short and vol_ok:
        return "SELL"
    return "HOLD"

def open_trade(symbol, direction, params):
    mt5.symbol_select(symbol, True)
    s = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    a = mt5.account_info()

    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
    if rates is None:
        return False
    df = pd.DataFrame(rates)
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    curr_atr = tr.rolling(params.get("atr_period", 14)).mean().iloc[-1]

    price = tick.ask if direction == "BUY" else tick.bid
    sl = price - curr_atr * params["atr_sl_mult"] if direction == "BUY" else price + curr_atr * params["atr_sl_mult"]

    risk_amount = a.balance * 0.005
    sl_dist = abs(price - sl)
    sl_ticks = sl_dist / max(s.trade_tick_size, 1e-9)
    risk_per_lot = sl_ticks * s.trade_tick_value
    vol = max(s.volume_min, min(s.volume_max, risk_amount / max(risk_per_lot, 1e-9)))
    vol = round(vol / s.volume_step) * s.volume_step

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": vol,
           "type": order_type, "price": price, "sl": sl, "tp": 0,
           "deviation": 10, "magic": 123457, "comment": "F_M15",
           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
    r = mt5.order_send(req)
    print(f"  OPEN {symbol} {direction} {vol} lots @ {price:.2f} SL:{sl:.2f} risk:{risk_amount:.0f}")
    return r.retcode == 10009

def manage_position(symbol, params):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return None
    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)
        current = tick.bid if pos.type == 0 else tick.ask
        entry = pos.price_open

        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, BARS)
        if rates is None:
            return pos
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df = prep(df, params)
        if len(df) < 2:
            return pos

        last = df.iloc[-1]
        ef = f"ema{params['ema_fast']}"; em = f"ema{params['ema_medium']}"
        ema_bull = last[ef] > last[em]
        ema_bear = last[ef] < last[em]

        open_dt = datetime.fromtimestamp(pos.time)
        bars_held = (datetime.now() - open_dt).total_seconds() / 900

        should_close = False
        if pos.type == 0:
            if ema_bear:
                should_close = True
        else:
            if ema_bull:
                should_close = True

        if bars_held >= params.get("max_hold_bars", 20):
            should_close = True

        a = last["atr"]
        trail_dist = a * params.get("atr_trail_mult", 0.3)
        trailing_sl = False
        if pos.type == 0:
            if current - entry >= trail_dist:
                trailing_sl = True
                new_sl = current - trail_dist * 0.5
                if new_sl > pos.sl:
                    req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": pos.ticket,
                           "sl": new_sl, "tp": pos.tp, "deviation": 10, "magic": 123457,
                           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                    r = mt5.order_send(req)
        else:
            if entry - current >= trail_dist:
                trailing_sl = True
                new_sl = current + trail_dist * 0.5
                if new_sl < pos.sl or pos.sl == 0:
                    req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": pos.ticket,
                           "sl": new_sl, "tp": pos.tp, "deviation": 10, "magic": 123457,
                           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                    r = mt5.order_send(req)

        if should_close:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == 0 else tick.ask
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": pos.volume,
                   "type": close_type, "position": pos.ticket, "price": close_price,
                   "deviation": 10, "magic": 123457, "comment": "F_exit",
                   "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
            r = mt5.order_send(req)
            reason = "EMA" if bars_held < params.get("max_hold_bars", 20) else "MAXBAR"
            print(f"  CLOSE {symbol} ({reason}) retcode={r.retcode} PnL:{pos.profit:+.0f}")
            return None

        trail_str = "(T)" if trailing_sl else ""
        print(f"  POS: {'BUY' if pos.type==0 else 'SELL'} {pos.volume}l {trail_str} SL:{pos.sl:.2f} PnL:{pos.profit:+.0f} bars:{bars_held:.0f}")
        return pos
    return None

def main():
    params_cache = {s: load_params(s) for s in TICKERS}

    print(f"\n{'='*70}")
    print(f"  LIVE BOT — STRATEGY F M15 TURBO (ZERO SPREAD)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print(f"  Tickers: {', '.join(TICKERS)}")
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

        for symbol in TICKERS:
            params = params_cache[symbol]
            print(f"\n  --- {symbol} (F) ---")

            pos = manage_position(symbol, params)
            if pos:
                continue

            rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, BARS)
            if rates is None or len(rates) < 100:
                print(f"  DATA FAIL")
                continue

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)
            df = prep(df, params)
            if len(df) < 2:
                continue

            last = df.iloc[-1]
            ef = f"ema{params['ema_fast']}"; em = f"ema{params['ema_medium']}"
            trend = "UP" if last[ef] > last[em] else "DOWN"
            sig = signal_f(df, params)
            print(f"  Close: {last['close']:.2f} | Trend: {trend} | RSI: {last['rsi']:.0f} | Signal: {sig}")

            if sig != "HOLD":
                ok = open_trade(symbol, sig, params)
                if ok:
                    print(f"  >> {symbol} {sig} OPENED!")

        now = datetime.now()
        wait = 900 - (now.minute % 15 * 60 + now.second) + 2
        if wait <= 0:
            wait = 900
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Next cycle in {wait}s...")
        print(f"{'='*70}")
        time.sleep(wait)

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
