import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np
from itertools import product
import json, re, subprocess

MODAL=12_000_000; SYMBOL="XAUUSDm"

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))

def prep(df):
    for p in [3,5,7,8,9,10,12,13,14,15,18,20,21,26,30,34,50,100,200]:
        df[f"e{p}"]=ema(df["close"],p)
        df[f"s{p}"]=sma(df["close"],p)
    df["a14"]=atr(df,14); df["a7"]=atr(df,7)
    df["r14"]=rsi(df["close"],14); df["r7"]=rsi(df["close"],7)
    df["vma"]=df["tick_volume"].rolling(10).mean()
    df["vvma"]=df["tick_volume"].rolling(30).mean()
    df["hh5"]=df["high"].rolling(5).max(); df["ll5"]=df["low"].rolling(5).min()
    df["hh10"]=df["high"].rolling(10).max(); df["ll10"]=df["low"].rolling(10).min()
    df["hh14"]=df["high"].rolling(14).max(); df["ll14"]=df["low"].rolling(14).min()
    df["hh20"]=df["high"].rolling(20).max(); df["ll20"]=df["low"].rolling(20).min()
    df["hh50"]=df["high"].rolling(50).max(); df["ll50"]=df["low"].rolling(50).min()
    # Bollinger
    df["bbm"]=sma(df["close"],20); df["bbstd"]=df["close"].rolling(20).std()
    df["bbu"]=df["bbm"]+df["bbstd"]*2; df["bbl"]=df["bbm"]-df["bbstd"]*2
    df["bbw"]=(df["bbu"]-df["bbl"])/df["bbm"]; df["bbw_ma"]=df["bbw"].rolling(20).mean()
    # MACD
    df["macd"]=ema(df["close"],12)-ema(df["close"],26)
    df["macds"]=ema(df["macd"],9); df["macdh"]=df["macd"]-df["macds"]
    # ADX
    tr=atr(df,14); h=df["high"]; l=df["low"]; c=df["close"]
    dm_plus=(h-h.shift(1)).where((h-h.shift(1))>(l.shift(1)-l),0).clip(lower=0)
    dm_minus=(l.shift(1)-l).where((l.shift(1)-l)>(h-h.shift(1)),0).clip(lower=0)
    df["adx"]=100*(dm_plus.rolling(14).mean()-dm_minus.rolling(14).mean()).abs()/(dm_plus.rolling(14).mean()+dm_minus.rolling(14).mean()+1e-10)
    df["di_plus"]=100*dm_plus.rolling(14).mean()/(tr+1e-10)
    df["di_minus"]=100*dm_minus.rolling(14).mean()/(tr+1e-10)
    # Keltner
    df["kc_mid"]=ema(df["close"],20); df["kc_range"]=atr(df,10)
    df["kc_u"]=df["kc_mid"]+df["kc_range"]*1.5; df["kc_l"]=df["kc_mid"]-df["kc_range"]*1.5
    # Donchian
    df["dc_u20"]=df["high"].rolling(20).max(); df["dc_l20"]=df["low"].rolling(20).min(); df["dc_m20"]=(df["dc_u20"]+df["dc_l20"])/2
    # Parabolic SAR
    def psar(df, af=0.02, af_max=0.2):
        ps=df["close"].copy(); ep=df["low"].copy(); trend=1; af_v=af
        for i in range(2,len(df)):
            if trend==1:
                if df["low"].iloc[i]<ps.iloc[i-1]: trend=-1; ps.iloc[i]=ep.iloc[i-1]; ep.iloc[i]=df["high"].iloc[i]; af_v=af
                else:
                    ps.iloc[i]=ps.iloc[i-1]+af_v*(ep.iloc[i-1]-ps.iloc[i-1])
                    if df["high"].iloc[i]>ep.iloc[i-1]: ep.iloc[i]=df["high"].iloc[i]; af_v=min(af_v+af,af_max)
                    else: ep.iloc[i]=ep.iloc[i-1]
            else:
                if df["high"].iloc[i]>ps.iloc[i-1]: trend=1; ps.iloc[i]=ep.iloc[i-1]; ep.iloc[i]=df["low"].iloc[i]; af_v=af
                else:
                    ps.iloc[i]=ps.iloc[i-1]+af_v*(ep.iloc[i-1]-ps.iloc[i-1])
                    if df["low"].iloc[i]<ep.iloc[i-1]: ep.iloc[i]=df["low"].iloc[i]; af_v=min(af_v+af,af_max)
                    else: ep.iloc[i]=ep.iloc[i-1]
        return ps
    df["psar"]=psar(df)
    # Heiken Ashi
    df["ha_c"]=(df["open"]+df["high"]+df["low"]+df["close"])/4
    df["ha_o"]=(df["open"].shift(1)+df["close"].shift(1))/2; df["ha_o"].fillna(df["open"],inplace=True)
    df["ha_h"]=df[["high","ha_c","ha_o"]].max(1); df["ha_l"]=df[["low","ha_c","ha_o"]].min(1)
    # TSI
    m=df["close"].diff(); ms=m.ewm(span=25,adjust=False).mean(); mss=ms.ewm(span=13,adjust=False).mean()
    am=abs(m); ams=am.ewm(span=25,adjust=False).mean(); amss=ams.ewm(span=13,adjust=False).mean()
    df["tsi"]=mss/(amss+1e-10)*100
    # Stochastic
    k14=(df["close"]-df["ll14"])/(df["hh14"]-df["ll14"]+1e-10)*100; df["stoch_k"]=k14.rolling(3).mean(); df["stoch_d"]=df["stoch_k"].rolling(3).mean()
    # %R
    df["willr"]=(df["hh14"]-df["close"])/(df["hh14"]-df["ll14"]+1e-10)*-100
    # CCI
    tp=(df["high"]+df["low"]+df["close"])/3; df["cci"]=(tp-tp.rolling(20).mean())/(tp.rolling(20).std()+1e-10)/0.015
    # Features for ML
    df["roc5"]=df["close"].pct_change(5)*100; df["roc10"]=df["close"].pct_change(10)*100
    df["roc20"]=df["close"].pct_change(20)*100
    df["vol_ratio"]=df["tick_volume"]/(df["vma"]+1)
    df["body"]=abs(df["close"]-df["open"]); df["upper"]=df["high"]-df[["close","open"]].max(1); df["lower"]=df[["close","open"]].min(1)-df["low"]
    df["body_pct"]=df["body"]/(df["high"]-df["low"]+1e-10)
    df.dropna(inplace=True); return df


def run(df, m, signal_fn, lot=100, sl_m=2.0, mh=40, rp=0.05):
    m=float(m); pk=m; dd=0; tr=[]; trd=False; h=0; pn=None; ps=0; e=0; entries={}
    for i in range(5,len(df)-1):
        c=df["close"].iloc[i]; cn=df["close"].iloc[i+1]; a=df["a14"].iloc[i]; t=df.index[i]
        if m>pk: pk=m
        ddx=(pk-m)/pk*100; dd=max(dd,ddx)
        if ddx>30: trd=False; pn=None; continue
        sig=signal_fn(df,i)
        if not trd:
            if sig!=0:
                pn="L" if sig==1 else "S"; e=c; ps=m*lot/100; trd=True; h=0; et=t
        else:
            h+=1; pr=0; ex=False; sl=a*sl_m
            if pn=="L":
                if cn<=e-sl: pr=-ps*sl/e; ex=True; re="SL"
                elif sig==-1: pr=ps*(c-e)/e*2; ex=True; re="REV"
                elif h>mh: pr=ps*(c-e)/e*0.5; ex=True; re="MAXH"
                else: pr=ps*(cn-c)/c*rp; re="RUN"
            else:
                if cn>=e+sl: pr=-ps*sl/e; ex=True; re="SL"
                elif sig==1: pr=ps*(e-c)/e*2; ex=True; re="REV"
                elif h>mh: pr=ps*(e-c)/e*0.5; ex=True; re="MAXH"
                else: pr=ps*(c-cn)/c*rp; re="RUN"
            if ex:
                m+=pr; tr.append({"pr":round(pr),"h":h,"r":re,"s":pn,"t":str(t.date())})
                trd=False; pn=None
    roi=(m-MODAL)/MODAL*100
    w=sum(1 for x in tr if x["pr"]>0); l=sum(1 for x in tr if x["pr"]<0)
    pf=sum(x["pr"] for x in tr if x["pr"]>0)/abs(sum(x["pr"] for x in tr if x["pr"]<0)) if l else 999
    days=max((df.index[-1]-df.index[0]).days,1)
    return {"p":round(m-MODAL),"r":round(roi,2),"t":len(tr),"wr":round(w/max(len(tr),1)*100,1),
            "pf":round(pf,2),"dd":round(dd,1),"pb":round((m-MODAL)/days*30),"tr":tr[-10:]}


# ===== 6 POWER STRATEGIES =====

# D1: Donchian 20 Breakout (trend following, wide)
def sig_d1(df,i):
    c=df["close"].iloc[i]; dc_u=df["dc_u20"].iloc[i-1]; dc_l=df["dc_l20"].iloc[i-1]
    dc_m=df["dc_m20"].iloc[i-1]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]
    e50=df["e50"].iloc[i]; e200=df["e200"].iloc[i]; r=df["r14"].iloc[i]
    if c>dc_u and v>vm*1.3 and r>50: return 1
    if c<dc_l and v>vm*1.3 and r<50: return -1
    return 0

# D2: Triple EMA alignment (5>13>34)
def sig_d2(df,i):
    e5=df["e5"].iloc[i]; e13=df["e13"].iloc[i]; e34=df["e34"].iloc[i]
    e5_1=df["e5"].iloc[i-1]; e13_1=df["e13"].iloc[i-1]; e34_1=df["e34"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    adx=df["adx"].iloc[i]; c=df["close"].iloc[i]
    # Bullish alignment
    if e5>e13 and e13>e34 and e5_1<=e13_1 and r>40 and v>vm*1.2: return 1
    if e5<e13 and e13<e34 and e5_1>=e13_1 and r<60 and v>vm*1.2: return -1
    return 0

# D3: Heiken Ashi EMA cross (smoother)
def sig_d3(df,i):
    ha_c=df["ha_c"].iloc[i]; e5=df["e5"].iloc[i]; e13=df["e13"].iloc[i]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; ha_o=df["ha_o"].iloc[i]; c=df["close"].iloc[i]
    ha_bull=ha_c>ha_o; ha_bull1=df["ha_c"].iloc[i-1]>df["ha_o"].iloc[i-1]
    adx=df["adx"].iloc[i]
    if ha_bull and not ha_bull1 and ha_c>e13 and v>vm*1.3 and adx>20: return 1
    if not ha_bull and ha_bull1 and ha_c<e13 and v>vm*1.3 and adx>20: return -1
    return 0

# D4: Momentum Breakout (strongest candle + volume)
def sig_d4(df,i):
    c=df["close"].iloc[i]; o=df["open"].iloc[i]; h=df["high"].iloc[i]; l=df["low"].iloc[i]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; hh5=df["hh5"].iloc[i-1]; ll5=df["ll5"].iloc[i-1]
    e20=df["e20"].iloc[i]; r=df["r14"].iloc[i]; body=abs(c-o); rg=h-l
    body_pct=body/(rg+1e-10)
    mom=c-o; vol_r=v/(vm+1)
    # Strong bullish breakout candle
    if mom>0 and body_pct>0.7 and vol_r>1.8 and c>hh5 and c>e20 and r>55: return 1
    if mom<0 and body_pct>0.7 and vol_r>1.8 and c<ll5 and c<e20 and r<45: return -1
    return 0

# D5: Parabolic SAR trend follow
def sig_d5(df,i):
    ps=df["psar"].iloc[i]; ps1=df["psar"].iloc[i-1]; c=df["close"].iloc[i]; c1=df["close"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; e20=df["e20"].iloc[i]; e50=df["e50"].iloc[i]; adx=df["adx"].iloc[i]
    # PSAR flip bullish
    if c>ps and c1<=ps1 and c>e20 and v>vm*1.2: return 1
    if c<ps and c1>=ps1 and c<e20 and v>vm*1.2: return -1
    return 0

# D6: CCI + Stochastic combo
def sig_d6(df,i):
    cci=df["cci"].iloc[i]; cci1=df["cci"].iloc[i-1]
    sk=df["stoch_k"].iloc[i]; sd=df["stoch_d"].iloc[i]; sk1=df["stoch_k"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; e20=df["e20"].iloc[i]; r=df["r14"].iloc[i]
    # CCI oversold bounce + stochastic cross up
    if cci<-100 and cci>cci1 and sk>sk1 and sk>20 and r>30 and v>vm*1.2: return 1
    if cci>100 and cci<cci1 and sk<sk1 and sk<80 and r<70 and v>vm*1.2: return -1
    return 0


if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,1500)
mt5.shutdown()
h4=pd.DataFrame(rh); h4["time"]=pd.to_datetime(h4["time"],unit="s"); h4.set_index("time",inplace=True); h4=prep(h4)
h4_4=h4.iloc[-480:]

strategies = [
    (h4_4, sig_d1, "D1 Donchian20", 100, 2.5, 50, 0.08),
    (h4_4, sig_d2, "D2 Triple EMA5/13/34", 100, 1.5, 30, 0.08),
    (h4_4, sig_d3, "D3 Heiken Ashi EMA", 100, 2.0, 40, 0.08),
    (h4_4, sig_d4, "D4 MomBreakout (candle+vol)", 100, 1.5, 20, 0.10),
    (h4_4, sig_d5, "D5 Parabolic SAR", 100, 2.0, 40, 0.08),
    (h4_4, sig_d6, "D6 CCI+Stochastic", 100, 1.2, 20, 0.08),
]

print(f"{'='*105}")
print(f"  6 POWER STRATEGIES — XAUUSDm H4 — Modal Rp{MODAL:,}")
print(f"{'='*105}")
print(f"{'Strategi':<25} {'4bln':>14} {'DD':>6} {'Full':>14} {'DD':>6} {'WR':>6} {'Trade':>6}")

for df, fn, name, lot, sl, mh, rp in strategies:
    r4=run(h4_4,MODAL,fn,lot,sl,mh,rp)
    rf=run(h4,MODAL,fn,lot,sl,mh,rp)
    pm4="+" if r4["p"]>0 else ""; pmf="+" if rf["p"]>0 else ""
    print(f"  {name:<23} Rp{r4['p']:>9,} ({pm4}{r4['r']:>5.1f}%) DD {r4['dd']:>4}% "
          f"Rp{rf['p']:>9,} ({pmf}{rf['r']:>5.1f}%) DD {rf['dd']:>4}% WR {rf['wr']:>4}% {rf['t']:>3}tr")

# Grid search top 3
print(f"\n{'='*105}")
print(f"  GRID SEARCH — OPTIMASI PARAM (lot=100,150,200,250 | sl | max_hold)")
print(f"{'='*105}")

all_res=[]
for df, fn, name, lot, sl, mh, rp in strategies:
    for lt,sm,mh2,rpp in product([100,150,200,250,300],[1.2,1.5,2.0,2.5],[30,40,50],[0.05,0.08,0.1]):
        r4=run(h4_4,MODAL,fn,lt,sm,mh2,rpp)
        rf=run(h4,MODAL,fn,lt,sm,mh2,rpp)
        sc=r4["p"]*0.6+rf["p"]*0.4
        if r4["dd"]<15 and rf["dd"]<15 and r4["t"]>=2:
            all_res.append({"n":name,"r4":r4,"rf":rf,"p":f"{lt}/{sm}/{mh2}/{rpp}","s":sc})

all_res.sort(key=lambda x: x["s"], reverse=True)
seen={}
for r in all_res:
    if r["n"] not in seen:
        seen[r["n"]]=True
        pm4="+" if r["r4"]["p"]>0 else ""; pmf="+" if r["rf"]["p"]>0 else ""
        print(f"  {r['n']:<25} {r['p']:<18} 4bln: Rp{r['r4']['p']:>9,} ({pm4}{r['r4']['r']:>5.1f}%) DD {r['r4']['dd']:>3}% "
              f"Full: Rp{r['rf']['p']:>9,} ({pmf}{r['rf']['r']:>5.1f}%) DD {r['rf']['dd']:>3}% WR {r['rf']['wr']:>4}%")

# Compare with B
print(f"\n{'='*105}")
print(f"  PERBANDINGAN: Strategy B vs POWER STRATEGIES")
print(f"{'='*105}")

def sig_b(df,i):
    e10=df["e10"].iloc[i]; e30=df["e30"].iloc[i]; e10_1=df["e10"].iloc[i-1]; e30_1=df["e30"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
    if cu and v>=vm*1.2 and r>=20: return 1
    if cd and v>=vm*1.2 and r<=80: return -1
    return 0

# B at 100%
rb4=run(h4_4,MODAL,sig_b,100,2.0,40,0.05)
rbf=run(h4,MODAL,sig_b,100,2.0,40,0.05)
# B at 350%
rb4_350=run(h4_4,MODAL,sig_b,350,2.0,40,0.05)
rbf_350=run(h4,MODAL,sig_b,350,2.0,40,0.05)

pmb="+" if rb4["p"]>0 else ""; pmbf="+" if rbf["p"]>0 else ""
print(f"  B (100% lot):  4bln: Rp{rb4['p']:>9,} ({pmb}{rb4['r']:>5.1f}%) DD {rb4['dd']:>3}% /bln Rp{rb4['pb']:,}"
      f" | Full: Rp{rbf['p']:>9,} ({pmbf}{rbf['r']:>5.1f}%) DD {rbf['dd']:>3}% WR {rbf['wr']}%/{rbf['t']}tr")
pmb="+" if rb4_350["p"]>0 else ""; pmbf="+" if rbf_350["p"]>0 else ""
print(f"  B (350% lot):  4bln: Rp{rb4_350['p']:>9,} ({pmb}{rb4_350['r']:>5.1f}%) DD {rb4_350['dd']:>3}% /bln Rp{rb4_350['pb']:,}"
      f" | Full: Rp{rbf_350['p']:>9,} ({pmbf}{rbf_350['r']:>5.1f}%) DD {rbf_350['dd']:>3}% WR {rbf_350['wr']}%/{rbf_350['t']}tr")

# Show all grid results sorted globally (top 10)
print(f"\n{'='*105}")
print(f"  TOP 10 GLOBAL — semua strategi + parameter")
print(f"{'='*105}")
top10=sorted(all_res,key=lambda x: x["s"],reverse=True)[:10]
for i,r in enumerate(top10):
    pm4="+" if r["r4"]["p"]>0 else ""; pmf="+" if r["rf"]["p"]>0 else ""
    print(f"  #{i+1} {r['n']:<23} {r['p']:<18} 4bln: Rp{r['r4']['p']:>9,} ({pm4}{r['r4']['r']:>5.1f}%) DD {r['r4']['dd']:>3}% "
          f"Full: Rp{r['rf']['p']:>9,} ({pmf}{r['rf']['r']:>5.1f}%) DD {r['rf']['dd']:>3}% WR {r['rf']['wr']:>4}%")

# Best per strategi
print(f"\n{'='*105}")
print(f"  BEST SCORE — per strategi")
print(f"{'='*105}")
for name in sorted(set(r["n"] for r in all_res)):
    best=max((r for r in all_res if r["n"]==name), key=lambda x: x["s"])
    pm4="+" if best["r4"]["p"]>0 else ""; pmf="+" if best["rf"]["p"]>0 else ""
    print(f"  {name:<25} {best['p']:<18} 4bln: Rp{best['r4']['p']:>10,} ({pm4}{best['r4']['r']:>5.1f}%) DD {best['r4']['dd']:>3}% "
          f"/bln Rp{best['r4']['pb']:,} | Full: Rp{best['rf']['p']:>10,} ({pmf}{best['rf']['r']:>5.1f}%) DD {best['rf']['dd']:>3}% WR {best['rf']['wr']:>4}% /bln Rp{best['rf']['pb']:,}")

# Save best C8 from previous run too
print(f"\n{'='*105}")
print(f"  REFERENCE: Strategy B vs any strategy that beats it")
print(f"{'='*105}")
for r in top10:
    if r["r4"]["p"]>rb4_350["p"]:
        pm4="+" if r["r4"]["p"]>0 else ""
        print(f"  ** {r['n']} {r['p']} BEATS B! 4bln: Rp{r['r4']['p']:,} vs B Rp{rb4_350['p']:,}")
    elif r["rf"]["p"]>rbf_350["p"]:
        pmf="+" if r["rf"]["p"]>0 else ""
        print(f"  ** {r['n']} {r['p']} BEATS B (full)! Full: Rp{r['rf']['p']:,} vs B Rp{rbf_350['p']:,}")
