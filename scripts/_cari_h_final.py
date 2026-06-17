import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"; MODAL = 12_000_000; SPREAD = 280; PV = 0.01

def mt5(bars, tf, n4=False, n1=False):
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(): return None,None,None
        mt5.symbol_select(SYMBOL,True)
        r = mt5.copy_rates_from_pos(SYMBOL,tf,0,bars)
        r4 = mt5.copy_rates_from_pos(SYMBOL,16385,0,bars//4) if n4 else None
        r1 = mt5.copy_rates_from_pos(SYMBOL,16385,0,bars) if n1 else None
        mt5.shutdown()
        if r is None or len(r)<200: return None,None,None
        d = pd.DataFrame(r); d["time"]=pd.to_datetime(d["time"],unit="s"); d.set_index("time",inplace=True)
        d4=None; d1=None
        if r4 is not None: d4=pd.DataFrame(r4); d4["time"]=pd.to_datetime(d4["time"],unit="s"); d4.set_index("time",inplace=True)
        if r1 is not None: d1=pd.DataFrame(r1); d1["time"]=pd.to_datetime(d1["time"],unit="s"); d1.set_index("time",inplace=True)
        return d,d4,d1
    except: return None,None,None

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff();g=d.where(d>0,0).rolling(p).mean();l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))

def prep(df, d4):
    for p in [5,8,9,13,21,50,200]: df[f"ema{p}"]=ema(df["close"],p)
    df["atr"]=atr(df,14); df["rsi"]=rsi(df["close"],14); df["vol_ma"]=sma(df["tick_volume"],20)
    m=df["close"].rolling(20).mean(); s=df["close"].rolling(20).std()
    df["bbw"]=(m+2*s-(m-2*s))/m; df["bbw_ma"]=sma(df["bbw"],20)
    df["squeeze"]=df["bbw"]<df["bbw_ma"]; df["hour_utc"]=df.index.hour
    if d4 is not None and len(d4)>50:
        d4["ema9"]=ema(d4["close"],9); d4["ema21"]=ema(d4["close"],21)
        d4["h4_trend"]=np.where(d4["ema9"]>d4["ema21"],"UP","DOWN"); d4.dropna(inplace=True)
        df["h4_trend"]=d4["h4_trend"].resample("1h").ffill().reindex(df.index,method="ffill")
    else: df["h4_trend"]="NEUTRAL"
    df.dropna(inplace=True); return df

def conf(row):
    s=0; bull=row["ema9"]>row["ema21"]; h4=row.get("h4_trend","NEUTRAL")
    if (bull and h4=="UP") or (not bull and h4=="DOWN"): s+=2
    if row.get("squeeze",False): s+=1
    if row.get("tick_volume",0)>row.get("vol_ma",1)*1.2: s+=1
    if bull and row.get("rsi",50)>75: s+=1
    if not bull and row.get("rsi",50)<25: s+=1
    if 7<=row.get("hour_utc",0)<14: s+=1
    c=row.get("close",0)
    if (bull and c>row.get("ema200",0)) or (not bull and c<row.get("ema200",0)): s+=1
    return s

def conf_ema5(row):
    s=0; bull=row["ema5"]>row["ema13"]; h4=row.get("h4_trend","NEUTRAL")
    if (bull and h4=="UP") or (not bull and h4=="DOWN"): s+=2
    if row.get("squeeze",False): s+=1
    if row.get("tick_volume",0)>row.get("vol_ma",1)*1.2: s+=1
    if bull and row.get("rsi",50)>75: s+=1
    if not bull and row.get("rsi",50)<25: s+=1
    if 7<=row.get("hour_utc",0)<14: s+=1
    c=row.get("close",0)
    if (bull and c>row.get("ema200",0)) or (not bull and c<row.get("ema200",0)): s+=1
    return s

def run(ef, em, rl, rs, sm, tm, trm, mh, rp, bm, frac_t, conf_f, name):
    df, d4, _ = mt5(3000, 16385, True, False)
    if df is None: print(f"  {name}: SKIP"); return None
    df = prep(df, d4)
    if df is None: print(f"  {name}: SKIP"); return None
    modal=float(MODAL); peak=modal; ddx=0; trades=[]; in_t=False; pos=None
    ep=0.0; ei=0; sl=0.0; tp=0.0; trl=False; dpnl={}; cd=None; dp=0.0; mae=0.0
    for i in range(100, len(df)):
        c=df["close"].iloc[i]; a=df["atr"].iloc[i]; ef_=df[ef].iloc[i]; em_=df[em].iloc[i]
        day=df.index[i].date()
        if cd is None: cd=day
        if day!=cd: dpnl[cd]=dp; cd=day; dp=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; ddx=max(ddx,dd)
        if dd>15: in_t=False; pos=None; continue
        row=df.iloc[i]
        bull=row[ef]>row[em]; sig="HOLD"
        if bull and rl[0]<=row["rsi"]<=rl[1] and row["tick_volume"]>row["vol_ma"]*0.8: sig="BUY"
        if not bull and rs[0]<=row["rsi"]<=rs[1] and row["tick_volume"]>row["vol_ma"]*0.8: sig="SELL"
        cf=conf_f(row); frac=1.0
        for lo,hi,f in frac_t(cf):
            if lo<=cf<=hi: frac=f; break
        tf_=frac*bm
        if not in_t:
            if sig!="HOLD":
                pos=sig; ep=c; ei=i
                sl=c-a*sm if sig=="BUY" else c+a*sm
                tp=c+a*tm if sig=="BUY" else c-a*tm
                trl=False; modal-=5000*tf_; sc=(SPREAD*PV/ep)*modal; modal-=sc*tf_
                mae=modal; in_t=True
        else:
            bars=i-ei; exit=False; profit=0.0
            if pos=="BUY":
                if c<=sl: profit=(sl-ep)/ep*mae*tf_; exit=True
                elif c>=tp: profit=(c-ep)/ep*mae*tf_; exit=True
                elif ef_<em_: profit=(c-ep)/ep*mae*tf_; exit=True
                elif bars>=mh: profit=(c-ep)/ep*mae*tf_; exit=True
                else:
                    td=a*trm
                    if not trl and (c-ep)>=td: trl=True; sl=ep+td*0.3
                    if trl: sl=max(sl,c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*mae*tf_*rp
            else:
                if c>=sl: profit=(ep-sl)/ep*mae*tf_; exit=True
                elif c<=tp: profit=(ep-c)/ep*mae*tf_; exit=True
                elif ef_>em_: profit=(ep-c)/ep*mae*tf_; exit=True
                elif bars>=mh: profit=(ep-c)/ep*mae*tf_; exit=True
                else:
                    td=a*trm
                    if not trl and (ep-c)>=td: trl=True; sl=ep-td*0.3
                    if trl: sl=min(sl,c+td*0.5)
                    profit=(df["close"].iloc[i-1]-c)/df["close"].iloc[i-1]*mae*tf_*rp
            if exit:
                modal+=profit; dp+=profit; trades.append({"tgl":df.index[i],"profit":profit})
                in_t=False; pos=None
    if cd: dpnl[cd]=dp
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100; ad=sum(dpnl.values())/len(dpnl) if dpnl else 0
    print(f"  {name:<18} ROI {roi:>6.1f}% DD {ddx:>4.1f}% Rp{ad:>8,.0f}/h {len(trades):>4}tr WR {len(win)/max(len(trades),1)*100:>4.0f}% PF {pf:>.2f}")
    return {"name":name,"roi":roi,"dd":ddx,"ad":ad,"tr":len(trades),"wr":len(win)/max(len(trades),1)*100,"pf":pf}

def main():
    print("="*70)
    print(f"  FINAL OPTIMASI H — spread {SPREAD} pts | {datetime.now():%Y-%m-%d %H:%M}")
    print("="*70)
    R=[]
    base=lambda c: [(0,2,1.0),(3,4,1.5),(5,7,2.0)]
    boost=lambda c: [(0,2,1.0),(3,4,1.8),(5,7,2.5)]
    
    R.append(run("ema9","ema21",(40,80),(20,60),1.5,3.0,0.5,24,0.05,1.0,base,conf,"H_BASELINE"))
    R.append(run("ema9","ema21",(40,80),(20,60),1.5,3.0,0.5,24,0.08,1.67,boost,conf,"H_BOOST500"))
    R.append(run("ema5","ema13",(40,80),(20,60),1.5,3.0,0.5,24,0.05,1.0,boost,conf_ema5,"H_E5_BOOST"))
    R.append(run("ema9","ema21",(45,75),(25,55),1.5,3.0,0.5,24,0.05,1.0,boost,conf,"H_RSI45_BOOST"))
    R.append(run("ema5","ema13",(42,78),(22,58),1.5,3.0,0.5,24,0.06,1.15,boost,conf_ema5,"H_CUSTOM1"))
    R.append(run("ema9","ema21",(40,80),(20,60),1.5,3.0,0.5,24,0.05,1.2,boost,conf,"H_BOOST120"))
    R.append(run("ema5","ema13",(40,80),(20,60),1.5,3.0,0.5,24,0.07,1.3,boost,conf_ema5,"H_E5_LOT130"))
    R = [r for r in R if r]
    R.sort(key=lambda x: x["ad"], reverse=True)
    
    print(f"\n{'='*70}")
    print(f"  RANGKUMAN FINAL")
    print(f"{'='*70}")
    print(f"  {'Nama':<18} {'ROI':>7} {'DD':>5} {'Rp/hari':>10} {'Tr':>4} {'WR':>4} {'PF':>5}")
    print(f"  {'-'*55}")
    for r in R:
        m=" ***" if r["ad"]>150000 else " **" if r["ad"]>100000 else " *"
        print(f"  {r['name']:<18} {r['roi']:>6.1f}% {r['dd']:>4.1f}% Rp{r['ad']:>8,.0f} {r['tr']:>4} {r['wr']:>3.0f}% {r['pf']:>.2f}{m}")

if __name__=="__main__":
    main()
