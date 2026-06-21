import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json, time, glob
from datetime import datetime
from strategies.shared.indicators import ema, sma, atr, rsi, macd, bb

# ============================================================
# KONFIGURASI 4 TICKER UNGGULAN
# ============================================================
TICKER_CFG = [
    {
        "name": "XAGUSDm", "strategy": "d", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,
                   "rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":1.2,
                   "atr_tp_mult":4.0,"atr_trail_mult":0.3,"volume_ma_period":20,"volume_mult":0.8,
                   "max_hold_bars":30,"lot_pct":100,"running_pct":0.1,"no_ema200":False,"no_macd":False}
    },
    {
        "name": "ETHUSDm", "strategy": "d", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,
                   "rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":1.5,
                   "atr_tp_mult":4.0,"atr_trail_mult":0.4,"volume_ma_period":20,"volume_mult":1.0,
                   "max_hold_bars":24,"lot_pct":60,"running_pct":0.1,"no_ema200":False,"no_macd":False}
    },
    {
        "name": "BTCUSDTm", "strategy": "d", "timeframe": mt5.TIMEFRAME_H1, "bars": 500,
        "params": {"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,
                   "rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":2.0,
                   "atr_tp_mult":3.5,"atr_trail_mult":0.4,"volume_ma_period":20,"volume_mult":1.0,
                   "max_hold_bars":24,"lot_pct":50,"running_pct":0.1,"no_ema200":False,"no_macd":False}
    },
    {
        "name": "JP225m", "strategy": "g", "timeframe": mt5.TIMEFRAME_M15, "bars": 2000,
        "params": {"mode":"trend","ema_fast":5,"ema_medium":13,"rsi_period":14,
                   "rsi_long_min":30,"rsi_long_max":95,"rsi_short_min":5,"rsi_short_max":70,
                   "atr_period":10,"atr_sl_mult":0.7,"atr_tp_mult":3.5,"atr_trail_mult":0.3,
                   "volume_ma_period":15,"volume_mult":0.7,"max_hold_bars":20,
                   "lot_pct":120,"running_pct":0.12,"no_ema200":True,"no_macd":True}
    },
]

CONF_SIZING = [(0, 2, 1.0), (3, 4, 1.5), (5, 6, 2.0)]

def prep_data(df, p, dh1=None):
    ef, em = p["ema_fast"], p["ema_medium"]
    df[f"ema{ef}"] = ema(df["close"], ef)
    df[f"ema{em}"] = ema(df["close"], em)
    df["ema50"] = ema(df["close"], p.get("ema_trend", 50))
    df["ema200"] = ema(df["close"], p.get("ema_major", 200))
    df["atr"] = atr(df, p.get("atr_period", 14))
    df["rsi"] = rsi(df["close"], p.get("rsi_period", 14))
    if not p.get("no_macd", False):
        df["macd"], df["macd_sig"] = macd(df["close"], 12, 26, 9)
    else:
        df["macd"] = 0; df["macd_sig"] = 0
    df["vol_ma"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))

    # BB squeeze
    bbu, bbm, bbl = bb(df, 20, 2)
    df["bbw"] = (bbu - bbl) / bbm
    df["bbw_ma"] = sma(df["bbw"], 20)

    # H1 trend alignment
    df["h1_trend"] = 0
    if dh1 is not None and len(dh1) > 100:
        dh1["ema9"] = ema(dh1["close"], 9)
        dh1["ema21"] = ema(dh1["close"], 21)
        dh1["h1_val"] = np.where(dh1["ema9"] > dh1["ema21"], 1, -1)
        dh1.dropna(inplace=True)
        h1_series = dh1["h1_val"].resample("15min").ffill()
        df["h1_trend"] = h1_series.reindex(df.index, method="ffill").fillna(0).astype(int)

    df.dropna(inplace=True)
    return df

def compute_confidence(row):
    s = 0
    ef_col = f"ema5"; em_col = f"ema13"
    bull = row[ef_col] > row[em_col]
    h1 = row.get("h1_trend", 0)
    if (bull and h1 == 1) or (not bull and h1 == -1):
        s += 2
    squeeze = row["bbw"] < row["bbw_ma"]
    if squeeze:
        s += 1
    if row["tick_volume"] > row["vol_ma"] * 1.2:
        s += 1
    if bull and row["rsi"] > 65:
        s += 1
    if not bull and row["rsi"] < 35:
        s += 1
    hour = row.get("hour_utc", 0)
    if 7 <= hour < 15:
        s += 1
    return s

def get_fraction(conf):
    for lo, hi, frac in CONF_SIZING:
        if lo <= conf <= hi:
            return frac
    return 1.0

def get_signal(df, i, p):
    row = df.iloc[i]; c = row["close"]
    ef, em = f"ema{p['ema_fast']}", f"ema{p['ema_medium']}"
    ema_bull = row[ef] > row[em]; ema_bear = row[ef] < row[em]
    above_200 = c > row["ema200"] if not p.get("no_ema200", False) else True
    rsi_long = p.get("rsi_long_min",30) <= row["rsi"] <= p.get("rsi_long_max",80)
    rsi_short = p.get("rsi_short_min",20) <= row["rsi"] <= p.get("rsi_short_max",80)
    macd_bull = p.get("no_macd",False) or row["macd"] > row["macd_sig"]
    macd_bear = p.get("no_macd",False) or row["macd"] < row["macd_sig"]
    vol_ok = row["tick_volume"] > row["vol_ma"] * p.get("volume_mult", 1.0)
    if above_200 and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    if (not above_200) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def manage_position(ticker, params):
    """Check existing positions and update trailing stop if needed"""
    positions = mt5.positions_get(symbol=ticker)
    if not positions:
        return None
    
    for pos in positions:
        bars_held = pos.time
        tick = mt5.symbol_info_tick(ticker)
        current = tick.bid if pos.type == 0 else tick.ask
        entry = pos.price_open
        atr_val = pos.sl  # placeholder

        # Check EMA cross exit
        rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_H1 if params["timeframe"] != mt5.TIMEFRAME_M15 else mt5.TIMEFRAME_M15, 0, 300)
        if rates is None:
            return pos
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df = prep_data(df, params["params"])
        if len(df) < 5:
            return pos
        
        last = df.iloc[-1]
        ef, em = f"ema{params['params']['ema_fast']}", f"ema{params['params']['ema_medium']}"
        ema_bull = last[ef] > last[em]
        
        # If position direction no longer matches trend, close
        should_close = False
        if pos.type == 0 and not ema_bull:  # BUY but trend turned bearish
            should_close = True
        elif pos.type == 1 and ema_bull:  # SELL but trend turned bullish
            should_close = True
        
        if should_close:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == 0 else tick.ask
            req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":ticker,"volume":pos.volume,
                   "type":close_type,"position":pos.ticket,"price":close_price,
                   "deviation":10,"magic":pos.magic,"comment":"EMA_close",
                   "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
            r = mt5.order_send(req)
            print(f"  CLOSE {ticker} (EMA reverse): retcode={r.retcode}")
            return None
        
        # Update trailing stop
        if pos.type == 0:  # BUY
            new_sl = current - df["atr"].iloc[-1] * params["params"]["atr_trail_mult"] * 0.5
            if new_sl > pos.sl:
                req = {"action":mt5.TRADE_ACTION_SLTP,"symbol":ticker,"position":pos.ticket,
                       "sl":new_sl,"tp":pos.tp,"deviation":10,"magic":pos.magic,
                       "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
                r = mt5.order_send(req)
                if r.retcode == 10009:
                    print(f"  TRAIL {ticker}: SL {pos.sl:.2f} -> {new_sl:.2f}")
        else:  # SELL
            new_sl = current + df["atr"].iloc[-1] * params["params"]["atr_trail_mult"] * 0.5
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
    """Open a new position with confidence-based sizing"""
    params = cfg["params"]
    mt5.symbol_select(ticker, True)
    s = mt5.symbol_info(ticker)
    tick = mt5.symbol_info_tick(ticker)
    
    # Calculate lot size with confidence fraction
    vol_min = s.volume_min
    lot_pct = params.get("lot_pct", 100) * fraction
    vol = max(vol_min, round(vol_min * (lot_pct / 100), 2))
    vol = min(vol, s.volume_max)
    vol = round(vol / s.volume_step) * s.volume_step
    
    # Get ATR for SL/TP
    rates = mt5.copy_rates_from_pos(ticker, cfg["timeframe"], 0, 100)
    df = pd.DataFrame(rates)
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    curr_atr = tr.rolling(14).mean().iloc[-1]
    
    price = tick.ask if signal_dir == "BUY" else tick.bid
    
    if signal_dir == "BUY":
        sl = price - curr_atr * params["atr_sl_mult"]
        tp = price + curr_atr * params["atr_tp_mult"]
        order_type = mt5.ORDER_TYPE_BUY
    else:
        sl = price + curr_atr * params["atr_sl_mult"]
        tp = price - curr_atr * params["atr_tp_mult"]
        order_type = mt5.ORDER_TYPE_SELL
    
    req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":ticker,"volume":vol,"type":order_type,
           "price":price,"sl":sl,"tp":tp,"deviation":10,"magic":123456,"comment":f"{cfg['strategy'].upper()}_auto",
           "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
    r = mt5.order_send(req)
    frac_str = f"x{fraction:.1f}" if fraction != 1.0 else ""
    print(f"  OPEN {ticker} {signal_dir} {vol} lots{frac_str} @ {price:.2f} SL:{sl:.2f} TP:{tp:.2f} retcode={r.retcode}")
    return r.retcode == 10009

def main():
    print(f"\n{'='*70}")
    print(f"  LIVE BOT — 4 TICKER UNGGULAN")
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
        
        # Balance
        a = mt5.account_info()
        print(f"  Balance: Rp{a.balance:,.0f} | Equity: Rp{a.equity:,.0f} | Floating: Rp{a.profit:+,.0f}")
        
        for tc in TICKER_CFG:
            sym = tc["name"]
            print(f"\n  --- {sym} ({tc['strategy'].upper()}) ---")
            
            # Check existing position
            pos = manage_position(sym, tc)
            
            if pos:
                print(f"  POSITION: {'BUY' if pos.type==0 else 'SELL'} {pos.volume} lots @ {pos.price_open:.2f} SL:{pos.sl:.2f} TP:{pos.tp:.2f} PnL:{pos.profit:+.0f}")
                continue
            
            # No position — check for signal
            rates = mt5.copy_rates_from_pos(sym, tc["timeframe"], 0, tc["bars"])
            if rates is None or len(rates) < 100:
                print(f"  DATA FAIL")
                continue
            
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)
            
            # Fetch H1 data for confidence scoring (JP225m)
            dh1 = None
            if tc["strategy"] == "g":
                h1_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, tc["bars"] // 4)
                if h1_rates is not None and len(h1_rates) > 100:
                    dh1 = pd.DataFrame(h1_rates)
                    dh1["time"] = pd.to_datetime(dh1["time"], unit="s")
                    dh1.set_index("time", inplace=True)
            
            df = prep_data(df, tc["params"], dh1)
            if len(df) < 5:
                continue
            
            # Compute confidence for G strategies
            fraction = 1.0
            conf = 0
            if tc["strategy"] == "g":
                df["hour_utc"] = df.index.hour
                conf = compute_confidence(df.iloc[-1])
                fraction = get_fraction(conf)
            
            sig = get_signal(df, -1, tc["params"])
            last = df.iloc[-1]
            ef, em = f"ema{tc['params']['ema_fast']}", f"ema{tc['params']['ema_medium']}"
            trend = "UP" if last[ef] > last[em] else "DOWN"
            
            conf_str = f" | Conf: {conf} x{fraction:.1f}" if tc["strategy"] == "g" else ""
            print(f"  Close: {last['close']:.2f} | Trend: {trend} | RSI: {last['rsi']:.0f} | Signal: {sig}{conf_str}")
            
            if sig != "HOLD":
                ok = open_trade(sym, tc, sig, fraction)
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
