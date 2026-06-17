import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np
import json

MODAL=12_000_000; SYMBOL="XAUUSDm"; LOT=350

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def prep(df):
    for p in [10,20,30]: df[f'e{p}']=ema(df['close'],p)
    tr=np.maximum(df['high']-df['low'],np.maximum(abs(df['high']-df['close'].shift(1)),abs(df['low']-df['close'].shift(1))))
    df['a14']=tr.rolling(14).mean()
    d=df['close'].diff(); g=d.where(d>0,0).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
    df['r14']=100-(100/(1+g/l)); df['vm']=df['tick_volume'].rolling(10).mean()
    df.dropna(inplace=True); return df

def run(df,m,lp,detail=False):
    m=float(m); e=0; pk=m; dd=0; tr=[]; trd=False; h=0; pn=None
    for i in range(5,len(df)-1):
        c=df['close'].iloc[i]; cn=df['close'].iloc[i+1]; a=df['a14'].iloc[i]; t=df.index[i]
        if m>pk: pk=m
        ddx=(pk-m)/pk*100; dd=max(dd,ddx)
        if ddx>30: trd=False; pn=None; continue
        e10=df['e10'].iloc[i]; e30=df['e30'].iloc[i]; e10_1=df['e10'].iloc[i-1]; e30_1=df['e30'].iloc[i-1]
        v=df['tick_volume'].iloc[i]; vm=df['vm'].iloc[i]; r=df['r14'].iloc[i]
        cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
        if not trd:
            if cu and v>=vm*1.2 and r>=20: pn='L'; e=c; trd=True; h=0; et=t
            elif cd and v>=vm*1.2 and r<=80: pn='S'; e=c; trd=True; h=0; et=t
        else:
            h+=1; pr=0; ex=False; ps=m*lp/100; sl=a*1.5
            if pn=='L':
                if cn<=e-sl: pr=-ps; ex=True
                elif cd: pr=(c-e)/e*ps*2; ex=True
                elif h>40: pr=(c-e)/e*ps*0.5; ex=True
                else: pr=(cn-c)/c*ps*0.05
            else:
                if cn>=e+sl: pr=-ps; ex=True
                elif cu: pr=(e-c)/e*ps*2; ex=True
                elif h>40: pr=(e-c)/e*ps*0.5; ex=True
                else: pr=(c-cn)/c*ps*0.05
            if ex:
                m+=pr
                if detail: tr.append({"tgl":str(t.date()),"side":pn,"held":h,"profit":round(pr),"exit_reason":("SL" if (pn=='L' and cn<=e-sl) or (pn=='S' and cn>=e+sl) else ("REVERSAL" if (pn=='L' and cd) or (pn=='S' and cu) else ("MAX_HOLD" if h>40 else "RUNNING")))})
                else: tr.append(pr)
                trd=False; pn=None
    roi=(m-MODAL)/MODAL*100; w=sum(1 for x in tr if (isinstance(x,dict) and x["profit"]>0) or (not isinstance(x,dict) and x>0))
    l_=sum(1 for x in tr if (isinstance(x,dict) and x["profit"]<0) or (not isinstance(x,dict) and x<0))
    pf=sum(x["profit"] if isinstance(x,dict) else x for x in tr if (isinstance(x,dict) and x["profit"]>0) or (not isinstance(x,dict) and x>0))/abs(sum(x["profit"] if isinstance(x,dict) else x for x in tr if (isinstance(x,dict) and x["profit"]<0) or (not isinstance(x,dict) and x<0))) if l_ else 999
    days=max((df.index[-1]-df.index[0]).days,1)
    return {"profit":round(m-MODAL),"roi":round(roi,2),"trades":len(tr),"wr":round(w/max(len(tr),1)*100,1),"pf":round(pf,2),"dd":round(dd,1),"per_bln":round((m-MODAL)/days*30),"modal_akhir":round(m),"tlist":tr if detail else []}

mt5.initialize(); mt5.symbol_select(SYMBOL,True)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,1500)
mt5.shutdown()
dh=pd.DataFrame(rh); dh['time']=pd.to_datetime(dh['time'],unit='s'); dh.set_index('time',inplace=True); dh=prep(dh)
d4=dh.iloc[-480:]

r4=run(d4,MODAL,LOT,True)
rf=run(dh,MODAL,LOT,True)

print("="*70)
print(f"  STRATEGY B — H4 EMA10/30 Cross | Lot {LOT}%")
print(f"  Modal Rp{MODAL:,} | XAUUSDm")
print("="*70)
print(f"\n  4 BULAN ({d4.index[0].date()} — {d4.index[-1].date()}):")
print(f"  Profit: Rp{r4['profit']:,} ({'+'if r4['profit']>0 else ''}{r4['roi']}%)")
print(f"  /bulan: Rp{r4['per_bln']:,} | DD: {r4['dd']}% | WR: {r4['wr']}% | PF: {r4['pf']}")
print(f"  Trades: {r4['trades']}")
print(f"\n  FULL H4 ({dh.index[0].date()} — {dh.index[-1].date()}):")
print(f"  Profit: Rp{rf['profit']:,} ({'+'if rf['profit']>0 else ''}{rf['roi']}%)")
print(f"  /bulan: Rp{rf['per_bln']:,} | DD: {rf['dd']}% | WR: {rf['wr']}% | PF: {rf['pf']}")
print(f"  Trades: {rf['trades']}")

print(f"\n  DETAIL TRADES — 4 BULAN:")
for t in r4['tlist']:
    pm="+" if t['profit']>0 else ""
    print(f"    {t['tgl']} | {t['side']} | {t['held']} bar | {pm}Rp{t['profit']:,} | [{t['exit_reason']}]")

# Save config
strategy_b = {
    "name": "H4 EMA10/30 Cross",
    "symbol": SYMBOL,
    "timeframe": "H4",
    "direction": "LONG_SHORT",
    "params": {
        "ema_fast": 10,
        "ema_slow": 30,
        "rsi_min": 20,
        "rsi_max": 80,
        "vol_factor": 1.2,
        "sl_atr": 1.5,
        "max_hold_bars": 40,
        "running_pct": 0.05,
        "lot_pct": LOT
    },
    "performance_4mo": {
        "roi_pct": r4['roi'],
        "max_dd_pct": r4['dd'],
        "profit_factor": r4['pf'],
        "win_rate_pct": r4['wr'],
        "total_trades": r4['trades']
    },
    "performance_full": {
        "roi_pct": rf['roi'],
        "max_dd_pct": rf['dd'],
        "profit_factor": rf['pf'],
        "win_rate_pct": rf['wr'],
        "total_trades": rf['trades']
    },
    "risk_rules": [
        "MAX_DD_30%: pause all",
        "REDUCE_LOT_AT_DD_10%",
        "EMA_REVERSAL_CLOSE",
        "SL_1.5_ATR"
    ]
}

os.makedirs('config',exist_ok=True)
with open('config/strategy_b.json','w') as f: json.dump(strategy_b,f,indent=2)
print(f"\n  ✅ Saved: config/strategy_b.json")

# Update settings.json
with open('config/settings.json','r') as f: settings = json.load(f)
settings['ai_manager']['strategies']['ema_cross_h4'] = {
    "active": True,
    "type": "LONG_SHORT",
    "symbol": SYMBOL,
    "timeframe": "H4",
    "params": strategy_b["params"],
    "performance_4mo": strategy_b["performance_4mo"],
    "performance_full": strategy_b["performance_full"]
}
# Deactivate old strategy
settings['ai_manager']['strategies']['pullback_sma30']['active'] = False
with open('config/settings.json','w') as f: json.dump(settings,f,indent=2)
print(f"  ✅ Updated: config/settings.json (Strategy B active, A inactive)")
print("="*70)
