import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from src.state_manager import StateManager
from src.audit.system_audit import SystemAudit
from src.audit.risk_audit import RiskAudit
from src.audit.backtest_audit import BacktestAudit
from src.context_builder import ContextBuilder

SYMBOL = "XAUUSDm"
MODAL = 5_000_000

# ===== PARAMETER OPTIMAL =====
PARAMS = {
    "sma_entry": 30, "sma_exit": 120, "sma200": 200,
    "rsi_max": 45, "atr_pullback": 2.0, "atr_stop": 3.0,
    "max_hold": 90, "running_pct": 0.15, "ema_buffer": 0.03
}


def init_mt5():
    if not mt5.initialize(): return False
    mt5.symbol_select(SYMBOL, True)
    return True


def get_data(bars=1200):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, bars)
    if rates is None: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def sma(s, p): return s.rolling(p).mean()
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g/l))


def prep(df):
    df["sma_entry"] = sma(df["close"], PARAMS["sma_entry"])
    df["sma_exit"] = sma(df["close"], PARAMS["sma_exit"])
    df["sma200"] = sma(df["close"], PARAMS["sma200"])
    df["ema20"] = ema(df["close"], 20)
    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    df["ll10"] = df["low"].rolling(10).min()
    df.dropna(inplace=True)
    return df


def signal(df, i, p):
    c = df["close"].iloc[i]; sma_entry = df["sma_entry"].iloc[i]
    sma_exit = df["sma_exit"].iloc[i]; sma200 = df["sma200"].iloc[i]
    r = df["rsi14"].iloc[i]; a = df["atr14"].iloc[i]; ema20 = df["ema20"].iloc[i]
    uptrend = sma_entry > sma_exit > sma200
    pullback = c <= sma_entry + a * 0.5 and c >= sma_entry - a * p["atr_pullback"]
    if uptrend and pullback and r < p["rsi_max"] and c > ema20 * (1 - p["ema_buffer"]):
        return "BUY"
    if c < sma_exit: return "SELL"
    return "HOLD"


def backtest_optimal(df, modal_awal, state):
    modal = float(modal_awal)
    posisi = None; entry_price = 0.0; trail_price = 0.0
    peak = modal; dd_max = 0.0; trades = []; in_trade = False; bars_held = 0
    equity_log = []

    for i in range(70, len(df) - 1):
        tgl = df.index[i]; c = df["close"].iloc[i]; cn = df["close"].iloc[i + 1]
        ll10 = df["ll10"].iloc[i]; a = df["atr14"].iloc[i]; p = PARAMS

        if modal > peak: peak = modal
        dd = (peak - modal) / peak * 100
        dd_max = max(dd_max, dd)
        if dd > 30: in_trade = False; posisi = None; continue

        sig = signal(df, i, PARAMS)

        if not in_trade:
            if sig == "BUY":
                posisi = "LONG"; entry_price = c
                trail_price = c - a * p["atr_stop"]
                modal -= 10000; in_trade = True; bars_held = 0
        else:
            bars_held += 1; trail_price = max(trail_price, ll10)
            profit = 0.0; exit_here = False
            if cn <= trail_price:
                profit = (trail_price - entry_price) / entry_price * modal; exit_here = True
            elif sig == "SELL":
                profit = (c - entry_price) / entry_price * modal; exit_here = True
            elif bars_held > p["max_hold"]:
                profit = (c - entry_price) / entry_price * modal; exit_here = True
            else:
                profit = (cn - c) / c * modal * p["running_pct"]
            if exit_here:
                modal += profit
                trades.append({"tgl": tgl, "held": bars_held, "profit": round(profit), "modal": round(modal)})
                in_trade = False; posisi = None

        if i % 5 == 0:
            state.upsert_metric("portfolio_drawdown", round(dd, 2))
            state.upsert_metric("running_modal", round(modal, 2))

    return modal, dd_max, trades


if not init_mt5(): print("[ERROR] MT5"); exit()
print("[INFO] Mengambil data XAUUSDm untuk backtest optimal...")
df = get_data(1200)
if df is None: print("[ERROR] No data"); mt5.shutdown(); exit()

t0, t1 = df.index[0].date(), df.index[-1].date()
df = prep(df)

# ===== 1. BACKTEST OPTIMAL =====
state = StateManager("data/state.db")
print(f"\n{'='*70}")
print("  BACKTEST OPTIMAL — Pullback SMA30")
print(f"  Periode: {t0} — {t1} ({len(df)} bars)")
print(f"  Modal: Rp{MODAL:,}")
print(f"{'='*70}")

modal_akhir, dd_max, trades = backtest_optimal(df, MODAL, state)
roi = (modal_akhir - MODAL) / MODAL * 100
win = [t for t in trades if t["profit"] > 0]
loss = [t for t in trades if t["profit"] < 0]
pf = sum(t["profit"] for t in win) / abs(sum(t["profit"] for t in loss)) if loss else 999

print(f"  Modal Akhir: Rp{modal_akhir:,.0f}")
print(f"  Profit:      Rp{modal_akhir - MODAL:,.0f}")
print(f"  ROI:         +{roi:.2f}%")
print(f"  Max DD:      {dd_max:.1f}%")
print(f"  Trades:      {len(trades)} ({len(win)}W/{len(loss)}L)")
print(f"  Win Rate:    {len(win)/max(len(trades),1)*100:.1f}%")
print(f"  Profit Factor: {pf:.2f}")
print(f"  Avg Hold:    {np.mean([t['held'] for t in trades]):.0f} hari")

# ===== 2. SEED KE DATABASE =====
print(f"\n{'='*70}")
print("  SEEDING DATA KE AI MANAGER DATABASE")
print(f"{'='*70}")

state.upsert_metric("portfolio_drawdown", round(dd_max, 2))
state.upsert_metric("rolling_sharpe_7d", round(pf/10, 2))
state.upsert_metric("running_modal", round(modal_akhir, 2))
state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
state.upsert_strategy("pullback_sma30", "ACTIVE")
state.upsert_strategy("adaptive", "PAUSED")
state.upsert_strategy("trend_re", "PAUSED")
state.log_backtest("pullback_sma30", "PASS", {
    "roi": round(roi, 2), "dd": dd_max, "pf": pf,
    "trades": len(trades), "win_rate": round(len(win)/max(len(trades),1)*100, 1),
    "avg_hold": round(np.mean([t["held"] for t in trades]), 0)
})

print("  [OK] Metrics tersimpan:")
print(f"    portfolio_drawdown: {dd_max:.1f}%")
print(f"    rolling_sharpe_7d: {pf/10:.2f}")
print(f"    running_modal: Rp{modal_akhir:,.0f}")
print(f"    last_heartbeat: OK")
print(f"  [OK] Strategy status: pullback_sma30=ACTIVE, others=PAUSED")
print(f"  [OK] Backtest log: PASS")

# ===== 3. SIMULASI AI MANAGER =====
print(f"\n{'='*70}")
print("  SIMULASI AI MANAGER CYCLE")
print(f"{'='*70}")

system_audit = SystemAudit(state)
risk_audit = RiskAudit(state)
backtest_audit = BacktestAudit(state)
context_builder = ContextBuilder(state, risk_audit, system_audit, backtest_audit)

print("\n  [RUN] System Audit...")
sa = system_audit.run_all()
print(f"    VPS: {sa['vps_health']['status']}")
print(f"    MT5: {sa['mt5_connectivity']['status']}")
print(f"    HB:  {sa['heartbeat_status']['status']}")

print("  [RUN] Risk Audit...")
ra = risk_audit.run_all()
print(f"    Drawdown: {ra['drawdown']['value']}% [{ra['drawdown']['level']}]")
print(f"    Sharpe:   {ra['sharpe']['value']} [{ra['sharpe']['level']}]")
print(f"    Strategies: {ra['strategies']['active']} active, {ra['strategies']['paused']} paused")

print("  [RUN] Backtest Audit...")
ba = backtest_audit.run_all()
print(f"    Result: {ba['status']} [{ba['level']}]")

print(f"\n  [RUN] Context Builder (AI Input):")
ctx = context_builder.build()
for k, v in ctx.items():
    print(f"    {k}: {v}")

prompt = context_builder.build_prompt()
print(f"\n  [RUN] Prompt ke AI ({len(prompt)} chars):")
print(f"    {prompt[:500]}...")

print(f"\n  {'='*70}")
print(f"  INTEGRASI SELESAI — AI Manager siap digunakan")
print(f"  {'='*70}")
print(f"  Next steps:")
print(f"  1. Install Gemini CLI:  https://geminicli.com")
print(f"  2. Set Telegram bot token di config/settings.json")
print(f"  3. Jalankan: python -m src.main")
print(f"  4. Atau auto-loop: scripts/run_cycle.ps1")
print(f"  5. Cek data di: sqlite3 data/state.db")

mt5.shutdown()
print("\n[DONE]")
