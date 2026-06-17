import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np

MODAL=12_000_000; SYMBOL="XAUUSDm"; PCT=10_000

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()

def prep(df):
    for p in [3,5,7,8,9,10,12,13,14,15,18,20,21,26,30,34,50]: df[f"e{p}"]=ema(df["close"],p)
    df["a14"]=atr(df,14)
    r=df["close"].diff(); g=r.where(r>0,0).rolling(14).mean(); l=(-r.where(r<0,0)).rolling(14).mean()
    df["r14"]=100-(100/(1+g/l))
    df["vm"]=df["tick_volume"].rolling(10).mean()
    df.dropna(inplace=True); return df

def run(df, m, ef, es, sl, mh, ri, vf, rp):
    m=float(m); e=0; pk=m; dd=0; tr=[]; trd=False; h=0; pn=None
    for i in range(5,len(df)-1):
        c=df["close"].iloc[i]; cn=df["close"].iloc[i+1]; a=df["a14"].iloc[i]
        if m>pk: pk=m
        ddx=(pk-m)/pk*100; dd=max(dd,ddx)
        if ddx>30: trd=False; pn=None; continue
        f=df[f"e{ef}"].iloc[i]; s=df[f"e{es}"].iloc[i]
        f1=df[f"e{ef}"].iloc[i-1]; s1=df[f"e{es}"].iloc[i-1]
        r=df["r14"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vm"].iloc[i]
        cu=f1<=s1 and f>s; cd=f1>=s1 and f<s; hv=v>=vm*vf
        if not trd:
            if cu and hv and r>=ri: pn="L"; e=c; m-=PCT; trd=True; h=0
            elif cd and hv and r<=100-ri: pn="S"; e=c; m-=PCT; trd=True; h=0
        else:
            h+=1; pr=0; ex=False
            if pn=="L":
                if cn<=e-a*sl: pr=-(a*sl/e)*m; ex=True
                elif cd: pr=(c-e)/e*m; ex=True
                elif h>mh: pr=(c-e)/e*m*0.5; ex=True
                else: pr=(cn-c)/c*m*rp
            else:
                if cn>=e+a*sl: pr=-(a*sl/e)*m; ex=True
                elif cu: pr=(e-c)/e*m; ex=True
                elif h>mh: pr=(e-c)/e*m*0.5; ex=True
                else: pr=(c-cn)/c*m*rp
            if ex: m+=pr; tr.append(pr); trd=False; pn=None
    roi=(m-MODAL)/MODAL*100
    w=sum(1 for x in tr if x>0); l=sum(1 for x in tr if x<0)
    pf=sum(x for x in tr if x>0)/abs(sum(x for x in tr if x<0)) if l else 999
    return {"p":round(m-MODAL),"r":round(roi,2),"t":len(tr),"w":round(w/max(len(tr),1)*100,1),
            "pf":round(pf,2),"dd":round(dd,1)}

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,1500)
mt5.shutdown()
dh=pd.DataFrame(rh); dh["time"]=pd.to_datetime(dh["time"],unit="s"); dh.set_index("time",inplace=True)
dh=prep(dh); d4=dh.iloc[-480:]

print(f"H4: {d4.index[0].date()} — {d4.index[-1].date()} ({len(d4)} bar)\n")

# PHASE 1: Find best EMA pair (fix sl=2.0, mh=40, ri=30, vf=1.2, rp=0.08)
print("PHASE 1: Cari EMA pair terbaik...")
pairs=[(3,13),(3,14),(5,13),(5,14),(5,20),(7,14),(7,20),(7,21),(8,13),(8,20),(8,21),
       (9,13),(9,18),(9,20),(10,20),(10,26),(10,30),(12,20),(12,26),(12,30)]
best_pair=None; best_p=-999999
for ef,es in pairs:
    if ef>=es: continue
    r=run(d4,MODAL,ef,es,2.0,40,30,1.2,0.08)
    pm="+" if r["p"]>0 else ""
    print(f"  {ef}/{es:<3}: Rp{r['p']:>9,} ({pm}{r['r']:>6.2f}%) WR {r['w']}% PF {r['pf']} DD {r['dd']}% {r['t']}tr")
    if r["p"]>best_p: best_p=r["p"]; best_pair=(ef,es)

print(f"\n  BEST: {best_pair[0]}/{best_pair[1]}\n")

# PHASE 2: Optimize around best pair
ef0,es0=best_pair
print("PHASE 2: Optimasi SL / max_hold / RSI / volume...")
best=None; best_p=-999999
for sl in [1.2,1.5,1.8,2.0,2.5]:
    for mh in [20,30,40,50,60]:
        for ri in [20,30,40,50]:
            for vf in [0.8,1.0,1.2,1.5,1.8]:
                for rp in [0.05,0.08,0.10,0.12,0.15]:
                    r=run(d4,MODAL,ef0,es0,sl,mh,ri,vf,rp)
                    if r["p"]>best_p: best_p=r["p"]; best={"p":r,"sl":sl,"mh":mh,"ri":ri,"vf":vf,"rp":rp}

if best:
    b=best; pm="+" if b["p"]["p"]>0 else ""
    print(f"\n  BEST: {ef0}/{es0} SL={b['sl']} MH={b['mh']} RSI={b['ri']} VF={b['vf']} RP={b['rp']}")
    print(f"  4bln: Rp{b['p']['p']:,} ({pm}{b['p']['r']}%) WR {b['p']['w']}% PF {b['p']['pf']} DD {b['p']['dd']}% {b['p']['t']}tr\n")

# PHASE 3: Validate
print("PHASE 3: Validasi full data vs D1...")
r4=run(d4,MODAL,ef0,es0,b["sl"],b["mh"],b["ri"],b["vf"],b["rp"])

# D1 — fetch before MT5 shutdown
if not mt5.initialize(): print("[ERROR] MT5 re-init"); exit()
mt5.symbol_select(SYMBOL, True)
rf2=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_D1,0,800)
mt5.shutdown()
d1f=pd.DataFrame(rf2); d1f["time"]=pd.to_datetime(d1f["time"],unit="s"); d1f.set_index("time",inplace=True)
d1f=prep(d1f); d1_4=d1f.iloc[-120:]
rd1=run(d1_4,MODAL,ef0,es0,b["sl"],b["mh"],b["ri"],b["vf"],b["rp"])

r_full = run(dh, MODAL, ef0, es0, b["sl"], b["mh"], b["ri"], b["vf"], b["rp"])
for label,r in [("4bln H4",r4),("4bln D1",rd1),("Full H4",r_full)]:
    pm="+" if r["p"]>0 else ""
    print(f"  {label:<10} Rp{r['p']:>10,} ({pm}{r['r']:>6.2f}%) WR {r['w']:>4}% PF {r['pf']:<5} DD {r['dd']:>4}% | {r['t']} trades")

# PHASE 4: Compare with original Strategy B (10/30/2.0/40/none/1.2/0.08)
print("\nPHASE 4: vs original Strategy B (10/30)...")
orig=run(d4,MODAL,10,30,2.0,40,0,1.2,0.08)  # ri=0 means no RSI filter
pm="+" if orig["p"]>0 else ""
print(f"  Original: Rp{orig['p']:,} ({pm}{orig['r']}%) WR {orig['w']}% | {orig['t']} trades")
