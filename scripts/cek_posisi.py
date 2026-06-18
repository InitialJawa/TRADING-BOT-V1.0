import MetaTrader5 as mt5
from datetime import datetime

if not mt5.initialize():
    print("GAGAL konek MT5 — buka MT5 dulu")
    exit()

a = mt5.account_info()
positions = mt5.positions_get()

print(f"\n{'='*60}")
print(f"  MT5 MONITOR — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")
print(f"  Account: {a.login} ({a.server})")
print(f"  Balance: Rp{a.balance:,.0f}")
print(f"  Equity:  Rp{a.equity:,.0f}")
print(f"  Profit:  Rp{a.profit:+,.0f}")
print(f"{'='*60}")

if not positions:
    print("\n  TIDAK ADA POSISI TERBUKA")
    print(f"{'='*60}")
    mt5.shutdown()
    exit()

total_profit = 0
print(f"\n  {'Ticker':<12} {'Type':<6} {'Lots':<6} {'Entry':>10} {'Current':>10} {'SL':>10} {'TP':>10} {'Profit':>12} {'Held':>6}")
print(f"  {'-'*80}")

for p in positions:
    tp = "BUY" if p.type == 0 else "SELL"
    tick = mt5.symbol_info_tick(p.symbol)
    current = tick.bid if p.type == 0 else tick.ask
    held = (datetime.now() - datetime.fromtimestamp(p.time)).total_seconds() / 3600
    if held < 24:
        held_str = f"{held:.1f}h"
    else:
        held_str = f"{held/24:.1f}d"
    
    print(f"  {p.symbol:<12} {tp:<6} {p.volume:<6.2f} {p.price_open:>10.2f} {current:>10.2f} {p.sl:>10.2f} {p.tp:>10.2f} {p.profit:>+10,.0f} {held_str:>6}")
    total_profit += p.profit

print(f"  {'-'*80}")
print(f"  {'TOTAL':<12} {'':<6} {'':<6} {'':>10} {'':>10} {'':>10} {'':>10} {total_profit:>+10,.0f}")
print(f"{'='*60}")
print(f"  Equity - Balance = Rp{a.equity - a.balance:+,.0f} (floating P&L)")
print(f"{'='*60}\n")

mt5.shutdown()
