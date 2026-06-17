import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np
from datetime import datetime

MODAL=12_000_000; SYMBOL="XAUUSDm"; LOT=350

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def prep(df):
    for p in [10,20,30]: df[f'e{p}']=ema(df['close'],p)
    tr=np.maximum(df['high']-df['low'],np.maximum(abs(df['high']-df['close'].shift(1)),abs(df['low']-df['close'].shift(1))))
    df['a14']=tr.rolling(14).mean()
    d=df['close'].diff(); g=d.where(d>0,0).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
    df['r14']=100-(100/(1+g/l)); df['vm']=df['tick_volume'].rolling(10).mean()
    df.dropna(inplace=True); return df

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,100)
mt5.shutdown()
dh=pd.DataFrame(rh); dh['time']=pd.to_datetime(dh['time'],unit='s'); dh.set_index('time',inplace=True)
dh=prep(dh)

print("="*65)
print("  STRATEGY B — TEST ENTRY & CLOSE")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*65)

# Current market status
last_idx=-1; last=dh.iloc[last_idx]
print(f"\n  Market: XAUUSD ${last['close']:.2f}")
print(f"  EMA10: {last['e10']:.2f} | EMA30: {last['e30']:.2f}")
print(f"  ATR14: ${last['a14']:.2f}")
print(f"  Trend: {'UP' if last['e10']>last['e30'] else 'DOWN'}")
print(f"\n  Modal simulasi: Rp{MODAL:,}")

# Test ENTRY: force BUY at current price
entry_price = last['close']
entry_time = dh.index[last_idx]
entry_side = "LONG"
atr = last['a14']
sl_price = entry_price - atr * 1.5  # SL 1.5x ATR
lot_rp = MODAL * LOT / 100  # Rp position size
risk_rp = (atr * 1.5 / entry_price) * lot_rp

print(f"\n{'='*65}")
print(f"  TEST ENTRY")
print(f"{'='*65}")
print(f"  Side: {entry_side}")
print(f"  Entry: ${entry_price:.2f}")
print(f"  SL: ${sl_price:.2f} (1.5x ATR = -${atr*1.5:.2f})")
print(f"  Position size: Rp{lot_rp:,.0f} ({LOT}% of modal)")
print(f"  Risk if SL hit: Rp{risk_rp:,.0f}")

# Simulate 3 price scenarios
print(f"\n{'='*65}")
print(f"  TEST CLOSE — 3 Skenario")
print(f"{'='*65}")

scenarios = [
    ("SL TERSENTUH (rugi)", sl_price - 5, "SL"),
    ("HARGA NAIK 1% (profit)", entry_price * 1.01, "PROFIT"),
    ("REVERSAL (EMA10 < EMA30)", entry_price * 0.995, "REVERSAL"),
]

for name, exit_price, reason in scenarios:
    if reason == "SL":
        profit_pct = (exit_price - entry_price) / entry_price
        profit_rp = profit_pct * lot_rp
    elif reason == "PROFIT":
        profit_pct = (exit_price - entry_price) / entry_price
        profit_rp = profit_pct * lot_rp
    elif reason == "REVERSAL":
        profit_pct = (exit_price - entry_price) / entry_price
        profit_rp = profit_pct * lot_rp * 2  # reversal exit = 2x

    new_modal = MODAL + profit_rp
    pm = "+" if profit_rp >= 0 else ""

    print(f"\n  [{name}]")
    print(f"  Exit: ${exit_price:.2f}")
    print(f"  P&L: {pm}Rp{profit_rp:,.0f} ({profit_pct*100:+.2f}%)")
    print(f"  Modal: Rp{MODAL:,} -> Rp{new_modal:,.0f}")

# Simulate running profit (per H4 bar) — price moves +0.2%
print(f"\n{'='*65}")
print(f"  TEST RUNNING PROFIT (per bar H4)")
print(f"{'='*65}")
running_pct = 0.05  # 5% of daily move captured per bar
bar_move = entry_price * 0.002  # 0.2% per bar
for i in range(1, 6):
    new_price = entry_price + bar_move * i
    profit = (new_price - last['close']) / last['close'] * lot_rp * running_pct
    if i % 2 == 0:  # some down bars too
        old = new_price
        new_price = entry_price + bar_move * (i-1)
        profit = (new_price - old) / old * lot_rp * running_pct
    pm = "+" if profit >= 0 else ""
    print(f"  Bar {i}: ${new_price:.2f} | Running: {pm}Rp{profit:,.0f}")

# Full trade simulation
print(f"\n{'='*65}")
print(f"  FULL SIMULASI 1 TRADE (realistis)")
print(f"{'='*65}")
print(f"  Kalau harga naik 2% dalam 3 hari:")
profit_2pct = 0.02 * lot_rp
new_modal = MODAL + profit_2pct
print(f"    Profit kotor: +Rp{profit_2pct:,.0f}")
print(f"    Modal: Rp{MODAL:,} -> Rp{new_modal:,.0f}")
print(f"    ROI trade ini: {0.02*LOT:.2f}%")
print(f"\n  Kalau kena SL (1.5 ATR ~$36):")
loss = risk_rp
new_modal2 = MODAL - loss
print(f"    Rugi: -Rp{loss:,.0f}")
print(f"    Modal: Rp{MODAL:,} -> Rp{new_modal2:,.0f}")
print(f"    Kerugian: {loss/MODAL*100:.2f}% dari modal")

print(f"\n{'='*65}")
print(f"  KESIMPULAN")
print(f"{'='*65}")
print(f"  Entry: ${entry_price:.2f} | SL: ${sl_price:.2f} | Risk: {risk_rp/MODAL*350/100:.1f}% per trade")
print(f"  Dengan WR 75%, rata-rata 1 trade/bln:")
print(f"  -> Expected value = 0.75*(+Rp{profit_2pct:,.0f}) + 0.25*(-Rp{loss:,.0f}) = Rp{0.75*profit_2pct-0.25*loss:,.0f}/trade")
print(f"{'='*65}")
