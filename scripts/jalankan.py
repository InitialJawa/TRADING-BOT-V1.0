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

def signal(df,i):
    e10=df['e10'].iloc[i]; e30=df['e30'].iloc[i]; e10_1=df['e10'].iloc[i-1]; e30_1=df['e30'].iloc[i-1]
    v=df['tick_volume'].iloc[i]; vm=df['vm'].iloc[i]; r=df['r14'].iloc[i]
    cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
    hv=v>=vm*1.2; in_rsi=20<=r<=80
    if cu and hv and in_rsi: return "BUY",f"EMA10({e10:.1f}) > EMA30({e30:.1f}) + volume spike"
    if cd and hv and in_rsi: return "SELL",f"EMA10({e10:.1f}) < EMA30({e30:.1f}) + volume spike"
    trend="UP" if e10>e30 else "DOWN"
    return "HOLD",f"EMA10({e10:.1f}) / EMA30({e30:.1f}) trend {trend}"

print("="*65)
print(f"  STRATEGY B — LIVE RUN")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB")
print("="*65)

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

a=mt5.account_info()
print(f"\n  Akun: {a.login} | Balance: ${a.balance:,.2f} | Equity: ${a.equity:,.2f}")
print(f"  Modal simulasi: Rp{MODAL:,} (Lot {LOT}%)")

# Fetch latest H4 data
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,100)
mt5.shutdown()
dh=pd.DataFrame(rh); dh['time']=pd.to_datetime(dh['time'],unit='s'); dh.set_index('time',inplace=True)
dh=prep(dh)

# Current bar
last=dh.iloc[-1]; prev=dh.iloc[-2]
now=dh.index[-1]

sig,reason=signal(dh,-1)
sprev,prev_reason=signal(dh,-2)

print(f"\n  --- MARKET STATUS ---")
print(f"  Last bar: {now}")
print(f"  Close: ${last['close']:.2f}")
print(f"  EMA10: {last['e10']:.2f} | EMA30: {last['e30']:.2f}")
print(f"  ATR14: ${last['a14']:.2f} | RSI14: {last['r14']:.1f}")
print(f"  Volume: {last['tick_volume']:,.0f} (avg: {last['vm']:,.0f})")
print(f"  Trend: {'UP' if last['e10']>last['e30'] else 'DOWN'}")

print(f"\n  --- SIGNAL ---")
if sig=="BUY":
    print(f"  >>> BUY signal aktif! {reason}")
    ps=MODAL*LOT/100; sl=last['a14']*1.5
    print(f"  >>> Entry: ${last['close']:.2f} | SL: ${last['close']-sl:.2f}")
    print(f"  >>> Risk: Rp{round(sl/last['close']*ps):,}")
elif sig=="SELL":
    print(f"  >>> SELL signal aktif! {reason}")
    ps=MODAL*LOT/100; sl=last['a14']*1.5
    print(f"  >>> Entry: ${last['close']:.2f} | SL: ${last['close']+sl:.2f}")
    print(f"  >>> Risk: Rp{round(sl/last['close']*ps):,}")
else:
    print(f"  HOLD. {reason}")
    if sprev!=sig:
        print(f"  Previous: {sprev} ({prev_reason})")
    print(f"  Menunggu crossover + volume spike...")

# Check if any recent crossovers
print(f"\n  --- 10 BAR TERAKHIR ---")
print(f"  {'Date':<22} {'Close':<10} {'EMA10':<10} {'EMA30':<10} {'Signal':<8} {'Vol':<12}")
print(f"  {'-'*72}")
for i in range(-10,0):
    d=dh.iloc[i]; s,_=signal(dh,i)
    print(f"  {str(dh.index[i].date()):<22} ${d['close']:<7.2f} {d['e10']:<9.1f} {d['e30']:<9.1f} {s:<8} {d['tick_volume']:<12,.0f}")

print(f"\n{'='*65}")
print(f"  STATUS: Strategy B siap | Lot {LOT}% | DD max ~10%")
print(f"  Untuk live trading: butuh Gemini CLI + Telegram token")
print(f"{'='*65}")
