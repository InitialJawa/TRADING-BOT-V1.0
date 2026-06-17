import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from src.state_manager import StateManager

SYMBOL = "XAUUSDm"
MODAL = 12_000_000
TARGET = 300_000

F_PARAMS = {
    "ema_fast": 5, "ema_medium": 13, "ema_trend": 50, "ema_major": 200,
    "rsi_period": 14,
    "rsi_long_min": 30, "rsi_long_max": 85,
    "rsi_short_min": 15, "rsi_short_max": 70,
    "macd_fast": 5, "macd_slow": 13, "macd_signal": 5,
    "atr_period": 10, "atr_sl_mult": 0.5, "atr_tp_mult": 2.2, "atr_trail_mult": 0.3,
    "volume_ma_period": 15, "volume_mult": 0.7,
    "max_hold_bars": 20, "lot_pct": 800, "running_pct": 0.12,
    "no_ema200_filter": True,
    "no_macd_filter": True,
    "dynamic_lot_base": 800,
    "dynamic_lot_min": 300,
    "dynamic_lot_max": 1500

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

def macd(s, f=5, sl=13, sg=5):
    e1 = ema(s, f); e2 = ema(s, sl); m = e1 - e2; return m, ema(m, sg)

def prep(df):
    p = F_PARAMS
    df["ema5"] = ema(df["close"], p["ema_fast"])
    df["ema13"] = ema(df["close"], p["ema_medium"])
    df["ema50"] = ema(df["close"], p["ema_trend"])
    df["ema200"] = ema(df["close"], p["ema_major"])
    df["atr"] = atr(df, p["atr_period"])
    df["rsi"] = rsi(df["close"], p["rsi_period"])
    df["macd"], df["macd_sig"] = macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    df["vol_ma"] = sma(df["tick_volume"], p["volume_ma_period"])
    df.dropna(inplace=True); return df

def signal_f(df, i):
    p = F_PARAMS; row = df.iloc[i]; c = row["close"]
    no_ema = p["no_ema200_filter"]
    no_macd = p.get("no_macd_filter", False)
    above_200 = c > row["ema200"]
    ema_bull = row["ema5"] > row["ema13"]
    rsi_long = p["rsi_long_min"] <= row["rsi"] <= p["rsi_long_max"]
    macd_bull = row["macd"] > row["macd_sig"] or no_macd
    vol_ok = row["tick_volume"] > row["vol_ma"] * p["volume_mult"]
    if (above_200 or no_ema) and ema_bull and rsi_long and macd_bull and vol_ok:
        return "BUY"
    ema_bear = row["ema5"] < row["ema13"]
    rsi_short = p["rsi_short_min"] <= row["rsi"] <= p["rsi_short_max"]
    macd_bear = row["macd"] < row["macd_sig"] or no_macd
    if (not above_200 or no_ema) and ema_bear and rsi_short and macd_bear and vol_ok:
        return "SELL"
    return "HOLD"

def calc_lot(running_modal):
    dl = F_PARAMS
    ratio = max(running_modal, 1_000_000) / MODAL
    lot = dl["dynamic_lot_base"] * ratio
    lot = max(lot, dl["dynamic_lot_min"])
    lot = min(lot, dl["dynamic_lot_max"])
    return round(lot, 0)

def backtest(df, modal_awal=None):
    p = F_PARAMS
    if modal_awal is None: modal_awal = MODAL
    modal = float(modal_awal); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price = 0.0; tp_price = 0.0; trail = False
    daily_pnl = {}; current_day = None; day_pnl = 0.0

    for i in range(50, len(df)):
        c = df["close"].iloc[i]; a = df["atr"].iloc[i]
        ef = df["ema5"].iloc[i]; em = df["ema13"].iloc[i]
        sig = signal_f(df, i)
        day = df.index[i].date()

        if current_day is None: current_day = day
        if day != current_day:
            daily_pnl[current_day] = day_pnl
            current_day = day; day_pnl = 0.0

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100; dd_max = max(dd_max, dd)
        if dd > 25: in_trade = False; posisi = None; continue

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
                elif c >= tp_price: profit = (c - entry_price) / entry_price * modal; exit = True
                elif ef < em: profit = (c - entry_price) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (c - entry_price) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (c - entry_price) >= td: trail = True; sl_price = entry_price + td * 0.3
                    if trail: sl_price = max(sl_price, c - td * 0.5)
                    profit = (c - df["close"].iloc[i-1]) / df["close"].iloc[i-1] * modal * p["running_pct"]
            else:
                if c >= sl_price: profit = (entry_price - sl_price) / entry_price * modal; exit = True
                elif c <= tp_price: profit = (entry_price - c) / entry_price * modal; exit = True
                elif ef > em: profit = (entry_price - c) / entry_price * modal; exit = True
                elif bars >= p["max_hold_bars"]: profit = (entry_price - c) / entry_price * modal; exit = True
                else:
                    td = a * p["atr_trail_mult"]
                    if not trail and (entry_price - c) >= td: trail = True; sl_price = entry_price - td * 0.3
                    if trail: sl_price = min(sl_price, c + td * 0.5)
                    profit = (df["close"].iloc[i-1] - c) / df["close"].iloc[i-1] * modal * p["running_pct"]

            if exit:
                modal += profit
                day_pnl += profit
                trades.append({"tgl": df.index[i], "posisi": posisi, "held": bars,
                    "profit": round(profit), "modal": round(modal),
                    "entry": round(entry_price, 2), "exit": round(c, 2)})
                in_trade = False; posisi = None

    if current_day: daily_pnl[current_day] = day_pnl
    return modal, dd_max, trades, daily_pnl


def test_period(label, bars):
    print(f"\n{'='*72}")
    print(f"  {label}")
    print(f"{'='*72}")

    if not mt5.initialize():
        print("[ERROR] MT5 gagal"); return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    mt5.shutdown()
    if rates is None or len(rates) < 500:
        print("[ERROR] Data tidak cukup"); return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)

    t0, t1 = df.index[0].date(), df.index[-1].date()
    days = len(df) // (24 * 4)
    print(f"  Periode: {t0} — {t1} ({len(df)} bars = {days} hari)")
    print(f"  Lot base: {F_PARAMS['dynamic_lot_base']}% (max {F_PARAMS['dynamic_lot_max']}%)")
    print(f"  SL: {F_PARAMS['atr_sl_mult']}x ATR | TP: {F_PARAMS['atr_tp_mult']}x ATR (R:R {F_PARAMS['atr_tp_mult']/F_PARAMS['atr_sl_mult']:.1f}:1)")

    df = prep(df)
    modal_akhir, dd_max, trades, daily_pnl = backtest(df)

    if modal_akhir is None:
        return None

    win = [t for t in trades if t["profit"] > 0]
    loss = [t for t in trades if t["profit"] < 0]
    loss_sum = sum(t["profit"] for t in loss)
    pf = sum(t["profit"] for t in win) / max(abs(loss_sum), 1) if loss else 999
    roi = (modal_akhir - MODAL) / MODAL * 100
    avg_hold = np.mean([t["held"] for t in trades]) if trades else 0
    avg_daily = np.mean(list(daily_pnl.values())) if daily_pnl else 0
    days_above = sum(1 for p in daily_pnl.values() if p >= TARGET)
    max_day = max(daily_pnl.values()) if daily_pnl else 0
    min_day = min(daily_pnl.values()) if daily_pnl else 0

    # Dynamic lot current
    final_lot = calc_lot(modal_akhir)

    print(f"\n  --- HASIL ---")
    print(f"  Modal Awal:     Rp{MODAL:,.0f}")
    print(f"  Modal Akhir:    Rp{modal_akhir:,.0f}")
    print(f"  Profit:         Rp{modal_akhir - MODAL:+,.0f}")
    print(f"  ROI:            {roi:+.2f}%")
    print(f"  Max DD:         {dd_max:.1f}%")
    print(f"  Trades:         {len(trades)} ({len(win)}W / {len(loss)}L)")
    print(f"  Win Rate:       {len(win)/max(len(trades),1)*100:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}")
    print(f"  Avg Hold:       {avg_hold:.0f} bar ({avg_hold*15:.0f} menit)")
    print(f"  Trades/hari:    {len(trades)/max(len(daily_pnl),1):.1f}")
    print(f"  Lot akhir:      {final_lot:.0f}% (position Rp{modal_akhir*final_lot/100:,.0f})")

    print(f"\n  --- TARGET Rp{TARGET:,}/hari ---")
    print(f"  Rata-rata/hari: Rp{avg_daily:,.0f}")
    print(f"  Hari >= Rp300k: {days_above}/{len(daily_pnl)} ({days_above/max(len(daily_pnl),1)*100:.0f}%)")
    print(f"  Hari terbaik:   Rp{max_day:+,.0f}")
    print(f"  Hari terburuk:  Rp{min_day:+,.0f}")
    print(f"  >>> TARGET: {'TERCAPAI' if avg_daily >= TARGET else f'BELUM ({avg_daily/TARGET*100:.0f}%)'}")

    if dd_max < 10:
        print(f"  >>> DD AMAN ({dd_max:.1f}%)")
    else:
        print(f"  >>> DD WARNING ({dd_max:.1f}% > 10%)")

    # Show top/bottom 5 days
    sorted_days = sorted(daily_pnl.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top 5 hari:")
    for d, p in sorted_days[:5]:
        print(f"    {d}: Rp{p:+,.0f} {'###' if p >= TARGET else ''}")
    print(f"  Bottom 5 hari:")
    for d, p in sorted_days[-5:]:
        print(f"    {d}: Rp{p:+,.0f}")

    return {"modal": modal_akhir, "dd": dd_max, "trades": len(trades), "roi": roi,
            "avg_daily": avg_daily, "pf": pf, "days_above": days_above, "total_days": len(daily_pnl),
            "max_day": max_day, "min_day": min_day, "win_rate": len(win)/max(len(trades),1)*100,
            "final_lot": final_lot, "data_bars": len(df), "label": label}


def main():
    print("=" * 72)
    print(f"  STRATEGY F — M15 Big Lot Momentum")
    print(f"  Target Rp{TARGET:,}/hari | Lot base {F_PARAMS['dynamic_lot_base']}% max {F_PARAMS['dynamic_lot_max']}%")
    print(f"  SL {F_PARAMS['atr_sl_mult']}x ATR / TP {F_PARAMS['atr_tp_mult']}x ATR (R:R {F_PARAMS['atr_tp_mult']/F_PARAMS['atr_sl_mult']:.1f}:1)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
    print("=" * 72)

    # Test 2 bulan (~6000 bars M15)
    r2 = test_period("TEST 2 BULAN", 6000)

    # Test 4 bulan (~12000 bars M15)
    r4 = test_period("TEST 4 BULAN", 12000)

    # Comparison
    print(f"\n{'='*72}")
    print(f"  PERBANDINGAN F vs E")
    print(f"{'='*72}")
    print(f"  {'Metric':<20} {'F (2bln)':<18} {'F (4bln)':<18} {'E (4bln)':<18}")
    print(f"  {'-'*72}")
    if r2:
        print(f"  {'ROI':<20} {'+'+str(round(r2['roi'],1))+'%':<18} {'+'+str(round(r4['roi'],1))+'%' if r4 else '-':<18} {'+195.0%':<18}")
        print(f"  {'DD':<20} {str(round(r2['dd'],1))+'%':<18} {str(round(r4['dd'],1))+'%' if r4 else '-':<18} {'3.5%':<18}")
        print(f"  {'Avg/hari':<20} {'Rp'+f'{r2["avg_daily"]:,.0f}':<18} {'Rp'+f'{r4["avg_daily"]:,.0f}' if r4 else '-':<18} {'Rp199,465':<18}")
        print(f"  {'Target 300k':<20} {'YA' if r2['avg_daily']>=TARGET else 'TIDAK':<18} {'YA' if r4 and r4['avg_daily']>=TARGET else 'TIDAK':<18} {'TIDAK':<18}")
        print(f"  {'Days >=300k':<20} {str(r2['days_above'])+'/'+str(r2['total_days']):<18} {str(r4['days_above'])+'/'+str(r4['total_days']) if r4 else '-':<18} {'(target 100k)':<18}")
        print(f"  {'Trades':<20} {str(r2['trades']):<18} {str(r4['trades']) if r4 else '-':<18} {'1702':<18}")
        print(f"  {'Lot akhir':<20} {str(r2['final_lot'])+'%':<18} {str(r4['final_lot'])+'%' if r4 else '-':<18} {'800%':<18}")

    # Seeding
    print(f"\n{'='*72}")
    print(f"  SEEDING AI MANAGER")
    print(f"{'='*72}")
    state = StateManager("data/state.db")
    for r in [r2, r4]:
        if r:
            state.log_backtest(f"strategy_f_{r['label'].lower().replace(' ','_')}", 
                "PASS" if r["dd"] < 12 and r["pf"] > 1.5 else "FAILED", {
                "roi": round(r["roi"], 2), "dd": round(r["dd"], 2), "pf": round(r["pf"], 2),
                "trades": r["trades"], "avg_daily_rupiah": round(r["avg_daily"], 0),
                "days_above_300k": r["days_above"], "total_days": r["total_days"]
            })
    state.upsert_strategy("strategy_f_m15", "TESTING")
    print("  [OK] Saved")

    print(f"\n{'='*72}")
    if r2 and r4:
        if r2["avg_daily"] >= TARGET and r4["avg_daily"] >= TARGET:
            print(f"  HASIL: TARGET Rp{TARGET:,}/hari TERCAPAI di kedua test!")
        elif r2["avg_daily"] >= TARGET:
            print(f"  HASIL: TARGET tercapai di 2 bulan, cek 4 bulan")
        elif r4 and r4["avg_daily"] >= TARGET:
            print(f"  HASIL: TARGET tercapai di 4 bulan")
        else:
            best = max([r for r in [r2, r4] if r], key=lambda x: x["avg_daily"])
            print(f"  HASIL: TERBAIK {best['label']} Rp{best['avg_daily']:,.0f}/hari")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()
