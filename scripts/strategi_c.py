import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np
from itertools import product
import json

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
    df["hh5"]=df["high"].rolling(5).max(); df["ll5"]=df["low"].rolling(5).min()
    df["hh10"]=df["high"].rolling(10).max(); df["ll10"]=df["low"].rolling(10).min()
    df["hh20"]=df["high"].rolling(20).max(); df["ll20"]=df["low"].rolling(20).min()
    # Bollinger
    df["bbm"]=sma(df["close"],20); df["bbstd"]=df["close"].rolling(20).std()
    df["bbu"]=df["bbm"]+df["bbstd"]*2; df["bbl"]=df["bbm"]-df["bbstd"]*2
    df["bbw"]=(df["bbu"]-df["bbl"])/df["bbm"]
    df["bbw_ma"]=df["bbw"].rolling(20).mean()
    # MACD
    df["macd"]=ema(df["close"],12)-ema(df["close"],26)
    df["macds"]=ema(df["macd"],9); df["macdh"]=df["macd"]-df["macds"]
    # ADX
    tr=atr(df,14); h=df["high"]; l=df["low"]; c=df["close"]
    dm_plus=(h-h.shift(1)).where((h-h.shift(1))>(l.shift(1)-l),0).clip(lower=0)
    dm_minus=(l.shift(1)-l).where((l.shift(1)-l)>(h-h.shift(1)),0).clip(lower=0)
    df["adx"]=100*(dm_plus.rolling(14).mean()-dm_minus.rolling(14).mean()).abs()/(dm_plus.rolling(14).mean()+dm_minus.rolling(14).mean())
    df["di_plus"]=100*dm_plus.rolling(14).mean()/tr
    df["di_minus"]=100*dm_minus.rolling(14).mean()/tr
    # Keltner
    df["kc_mid"]=ema(df["close"],20); df["kc_range"]=atr(df,10)
    df["kc_u"]=df["kc_mid"]+df["kc_range"]*1.5; df["kc_l"]=df["kc_mid"]-df["kc_range"]*1.5
    df.dropna(inplace=True); return df


def run(df, m, signal_fn, lot=100, sl_m=2.0, mh=40, rp=0.05):
    m=float(m); pk=m; dd=0; tr=[]; trd=False; h=0; pn=None; ps=0; e=0
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
    roi=(m-MODAL)/MODAL*100; w=sum(1 for x in tr if x["pr"]>0); l=sum(1 for x in tr if x["pr"]<0)
    pf=sum(x["pr"] for x in tr if x["pr"]>0)/abs(sum(x["pr"] for x in tr if x["pr"]<0)) if l else 999
    days=max((df.index[-1]-df.index[0]).days,1)
    return {"p":round(m-MODAL),"r":round(roi,2),"t":len(tr),"wr":round(w/max(len(tr),1)*100,1),
            "pf":round(pf,2),"dd":round(dd,1),"pb":round((m-MODAL)/days*30),"tr":tr[-10:]}


# ========== 8 STRATEGIES ==========

# C1: MACD Histogram Turn + EMA50 filter
def sig_c1(df,i):
    c=df["close"].iloc[i]; mh=df["macdh"].iloc[i]; mh1=df["macdh"].iloc[i-1]
    e50=df["e50"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    if mh>0 and mh1<=0 and c>e50 and r>40 and v>vm*1.2: return 1
    if mh<0 and mh1>=0 and c<e50 and r<60 and v>vm*1.2: return -1
    return 0

# C2: Bollinger squeeze + breakout
def sig_c2(df,i):
    c=df["close"].iloc[i]; bbu=df["bbu"].iloc[i]; bbl=df["bbl"].iloc[i]
    e20=df["e20"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    bbw=(bbu-bbl)/df["bbm"].iloc[i]
    squeeze=bbw<bbw.rolling(20).mean()
    if c>bbu and sqeeze and r>55 and v>vm*1.5: return 1  # LOL wrong var name
    if c<bbl and sqeeze and r<45 and v>vm*1.5: return -1
    return 0

# C2 Fixed: Breakout with Bollinger
def sig_c2b(df,i):
    c=df["close"].iloc[i]; bbu=df["bbu"].iloc[i]; bbl=df["bbl"].iloc[i]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    sq=df["bbw"].iloc[i]<df["bbw_ma"].iloc[i]
    if c>bbu and sq and r>55 and v>vm*1.5: return 1
    if c<bbl and sq and r<45 and v>vm*1.5: return -1
    return 0

# C3: ADX strong trend + DI cross
def sig_c3(df,i):
    a=df["adx"].iloc[i]; dp=df["di_plus"].iloc[i]; dm=df["di_minus"].iloc[i]
    dp1=df["di_plus"].iloc[i-1]; dm1=df["di_minus"].iloc[i-1]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]
    if a>25 and dp>dm and dp1<=dm1 and v>vm*1.2: return 1
    if a>25 and dm>dp and dm1>=dp1 and v>vm*1.2: return -1
    return 0

# C4: Multi-timeframe (H4 EMA cross + check D1 trend)
def sig_c4(df,i):
    e10=df["e10"].iloc[i]; e30=df["e30"].iloc[i]; e10_1=df["e10"].iloc[i-1]; e30_1=df["e30"].iloc[i-1]
    e100=df["e100"].iloc[i]; r=df["r14"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]
    cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
    if cu and r>30 and v>vm*1.2 and e10>e100: return 1
    if cd and r<70 and v>vm*1.2 and e10<e100: return -1
    return 0

# C5: RSI divergence (hidden)
def sig_c5(df,i):
    c=df["close"].iloc[i]; r=df["r14"].iloc[i]; ll10=df["ll10"].iloc[i]; hh10=df["hh10"].iloc[i]
    r_10=df["r14"].iloc[i-10]; c_10=df["close"].iloc[i-10]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]
    e20=df["e20"].iloc[i]; e50=df["e50"].iloc[i]
    # hidden bullish: price higher low, RSI higher low
    if c>c_10 and r>r_10 and c>e20 and c>e50 and v>vm*1.3: return 1
    if c<c_10 and r<r_10 and c<e20 and c<e50 and v>vm*1.3: return -1
    return 0

# C6: Keltner Channel breakout
def sig_c6(df,i):
    c=df["close"].iloc[i]; ku=df["kc_u"].iloc[i]; kl=df["kc_l"].iloc[i]; km=df["kc_mid"].iloc[i]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    hh5=df["hh5"].iloc[i]; ll5=df["ll5"].iloc[i]
    if c>ku and c==hh5 and r>55 and v>vm*1.5: return 1
    if c<kl and c==ll5 and r<45 and v>vm*1.5: return -1
    return 0

# C7: Pullback to EMA50 (mid-term trend)
def sig_c7(df,i):
    c=df["close"].iloc[i]; e50=df["e50"].iloc[i]; e200=df["e200"].iloc[i]
    a=df["a14"].iloc[i]; r=df["r14"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]
    uptrend=e50>e200
    if uptrend and c<=e50+a*0.3 and c>=e50-a and r<45 and v>vm*1.2: return 1
    if not uptrend and c>=e50-a*0.3 and c<=e50+a and r>55 and v>vm*1.2: return -1
    return 0

# C8: EMA9/21 cross + ADX filter
def sig_c8(df,i):
    e9=df["e9"].iloc[i]; e21=df["e21"].iloc[i]; e9_1=df["e9"].iloc[i-1]; e21_1=df["e21"].iloc[i-1]
    adx=df["adx"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    cu=e9_1<=e21_1 and e9>e21; cd=e9_1>=e21_1 and e9<e21
    if cu and adx>20 and r>40 and v>vm*1.2: return 1
    if cd and adx>20 and r<60 and v>vm*1.2: return -1
    return 0


if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

# Load data D1 + H4
rf=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_D1,0,800)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,1500)
mt5.shutdown()

d1=pd.DataFrame(rf); d1["time"]=pd.to_datetime(d1["time"],unit="s"); d1.set_index("time",inplace=True); d1=prep(d1)
h4=pd.DataFrame(rh); h4["time"]=pd.to_datetime(h4["time"],unit="s"); h4.set_index("time",inplace=True); h4=prep(h4)

d4=d1.iloc[-120:]; h4_4=h4.iloc[-480:]

strategies = [
    (h4_4, sig_c1, "C1 MACD Histogram", 100, 1.5, 30, 0.08),
    (h4_4, sig_c2b,"C2 BB Breakout", 100, 1.5, 20, 0.1),
    (h4_4, sig_c3, "C3 ADX+DI Cross", 100, 2.0, 40, 0.08),
    (h4_4, sig_c4, "C4 Multi-TF (D1+H4)", 100, 2.0, 40, 0.08),
    (h4_4, sig_c5, "C5 RSI Divergence", 100, 1.5, 20, 0.1),
    (h4_4, sig_c6, "C6 Keltner Breakout", 100, 1.5, 15, 0.1),
    (h4_4, sig_c7, "C7 Pullback EMA50", 100, 2.5, 60, 0.08),
    (h4_4, sig_c8, "C8 EMA9/21+ADX", 100, 1.5, 25, 0.08),
]

print(f"{'='*95}")
print(f"  STRATEGI C — 8 STRATEGIES, Backtest 4 bulan + Full H4")
print(f"  Modal Rp{MODAL:,} | Lot 100% | XAUUSDm H4")
print(f"{'='*95}")

results = []
for df, fn, name, lot, sl, mh, rp in strategies:
    r4=run(h4_4, MODAL, fn, lot, sl, mh, rp)
    rf=run(h4, MODAL, fn, lot, sl, mh, rp)
    results.append({"name":name,"r4":r4,"rf":rf})
    pm4="+" if r4["p"]>0 else ""; pmf="+" if rf["p"]>0 else ""
    print(f"  {name:<22} 4bln: Rp{r4['p']:>9,} ({pm4}{r4['r']:>6.2f}%) DD {r4['dd']:>4}% | "
          f"Full: Rp{rf['p']:>9,} ({pmf}{rf['r']:>6.2f}%) DD {rf['dd']:>4}% WR {rf['wr']}%/{rf['t']}tr")

# Grid search for TOP 3
print(f"\n{'='*95}")
print(f"  GRID SEARCH — TOP 5 STRATEGIES (parameter optimization)")
print(f"{'='*95}")

top_n = sorted(results, key=lambda x: x["r4"]["p"]*0.6+x["rf"]["p"]*0.4, reverse=True)[:5]
all_results = []
for t in top_n:
    fn = [s[1] for s in strategies if s[0] is h4_4 and s[2]==t["name"]]
    if not fn: continue
    fn=fn[0]
    for lot, sl, mh, rp in product([100,150,200,250],[1.2,1.5,2.0],[20,30,40],[0.05,0.08,0.1]):
        r4=run(h4_4,MODAL,fn,lot,sl,mh,rp)
        rf=run(h4,MODAL,fn,lot,sl,mh,rp)
        score=r4["p"]*0.6+rf["p"]*0.4
        if r4["dd"]<15 and rf["dd"]<15:
            all_results.append({"n":t["name"],"r4":r4,"rf":rf,"p":f"{lot}/{sl}/{mh}/{rp}","s":score})

all_results.sort(key=lambda x: x["s"], reverse=True)
seen={}
for r in all_results:
    if r["n"] not in seen:
        seen[r["n"]]=True
        pm4="+" if r["r4"]["p"]>0 else ""; pmf="+" if r["rf"]["p"]>0 else ""
        print(f"  {r['n']:<22} Params: {r['p']:<15} | 4bln: Rp{r['r4']['p']:>9,} ({pm4}{r['r4']['r']:>6.2f}%) DD {r['r4']['dd']:>4}% "
              f"| Full: Rp{r['rf']['p']:>9,} ({pmf}{r['rf']['r']:>6.2f}%) DD {r['rf']['dd']:>4}% WR {r['rf']['wr']}%")

# Compare with Strategy B
print(f"\n{'='*95}")
print(f"  PERBANDINGAN dengan STRATEGY B")
print(f"{'='*95}")
# Strategy B reference at 100% lot
def sig_b(df,i):
    e10=df["e10"].iloc[i]; e30=df["e30"].iloc[i]; e10_1=df["e10"].iloc[i-1]; e30_1=df["e30"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vma"].iloc[i]; r=df["r14"].iloc[i]
    cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
    if cu and v>=vm*1.2 and r>=20: return 1
    if cd and v>=vm*1.2 and r<=80: return -1
    return 0

rb4=run(h4_4,MODAL,sig_b,100,2.0,40,0.05)
rbf=run(h4,MODAL,sig_b,100,2.0,40,0.05)
pmb="+" if rb4["p"]>0 else ""; pmbf="+" if rbf["p"]>0 else ""
print(f"  B H4 EMA10/30 Cross {'':<14} 4bln: Rp{rb4['p']:>9,} ({pmb}{rb4['r']:>6.2f}%) DD {rb4['dd']:>4}% | "
      f"Full: Rp{rbf['p']:>9,} ({pmbf}{rbf['r']:>6.2f}%) DD {rbf['dd']:>4}% WR {rbf['wr']}%/{rbf['t']}tr")

# Best C
if all_results:
    best=all_results[0]
    print(f"\n  {'='*50}")
    print(f"  BEST C: {best['n']} params={best['p']}")
    pm4="+" if best['r4']['p']>0 else ""; pmf="+" if best['rf']['p']>0 else ""
    print(f"  4bln: Rp{best['r4']['p']:,} ({pm4}{best['r4']['r']}%) /bln Rp{best['r4']['pb']:,} DD {best['r4']['dd']}% WR {best['r4']['wr']}%")
    print(f"  Full: Rp{best['rf']['p']:,} ({pmf}{best['rf']['r']}%) /bln Rp{best['rf']['pb']:,} DD {best['rf']['dd']}% WR {best['rf']['wr']}%")

    print(f"\n  VS Strategy B (lot 100%):")
    print(f"  4bln: Rp{rb4['p']:,} /bln Rp{rb4['pb']:,} DD {rb4['dd']}%")
    ratio = best['r4']['p'] / rb4['p'] if rb4['p'] != 0 else 0
    print(f"  Ratio: {ratio:.2f}x dari Strategy B")
print(f"{'='*95}")
