import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np

MODAL=12_000_000; SYMBOL="XAUUSDm"; PCT=10_000

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()

def prep(df):
    for p in [5,10,12,13,15,20,26,30]: df[f"ema{p}"]=ema(df["close"],p)
    df["atr14"]=atr(df,14)
    r=df["close"].diff(); g=r.where(r>0,0).rolling(14).mean(); l=(-r.where(r<0,0)).rolling(14).mean()
    df["rsi14"]=100-(100/(1+g/l))
    df["vol_ma"]=df["tick_volume"].rolling(10).mean()
    df.dropna(inplace=True); return df

def run(df, modal, fn, name, sl_atr=2.0, max_hold=40, running_pct=0.08):
    m=float(modal); entry=0; peak=m; dd_max=0; trades=[]; in_trade=False; held=0; pos=None
    for i in range(5,len(df)-1):
        c=df["close"].iloc[i]; cn=df["close"].iloc[i+1]; a=df["atr14"].iloc[i]
        if m>peak: peak=m
        dd=(peak-m)/peak*100; dd_max=max(dd_max,dd)
        if dd>30: in_trade=False; pos=None; continue
        sig=fn(df,i)
        if not in_trade:
            if sig=="BUY": pos="LONG"; entry=c; m-=PCT; in_trade=True; held=0
            elif sig=="SELL": pos="SHORT"; entry=c; m-=PCT; in_trade=True; held=0
        else:
            held+=1; profit=0; exit=False
            if pos=="LONG":
                if cn<=entry-a*sl_atr: profit=-(a*sl_atr/entry)*m; exit=True
                elif sig=="SELL": profit=(c-entry)/entry*m; exit=True
                elif held>max_hold: profit=(c-entry)/entry*m*0.5; exit=True
                else: profit=(cn-c)/c*m*running_pct
            else:
                if cn>=entry+a*sl_atr: profit=-(a*sl_atr/entry)*m; exit=True
                elif sig=="BUY": profit=(entry-c)/entry*m; exit=True
                elif held>max_hold: profit=(entry-c)/entry*m*0.5; exit=True
                else: profit=(c-cn)/c*m*running_pct
            if exit:
                m+=profit; trades.append({"tgl":df.index[i],"side":pos,"held":held,"profit":round(profit)})
                in_trade=False; pos=None
    roi=(m-modal)/modal*100
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/abs(sum(t["profit"] for t in loss)) if loss else 999
    days=max((df.index[-1]-df.index[0]).days,1)
    return {"name":name,"profit":round(m-modal),"roi":round(roi,2),"trades":len(trades),
            "wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),"dd":round(dd_max,1),
            "per_bln":round((m-modal)/days*30),"tlist":trades}

# Strategy A: Pullback SMA30 LONG only
def sig_a(df,i):
    c=df["close"].iloc[i]; s30=df["ema30"].iloc[i]; s100=df["ema26"].iloc[i]
    r=df["rsi14"].iloc[i]; a=df["atr14"].iloc[i]; e20=df["ema20"].iloc[i]
    if s30>s100 and c<=s30+a*0.5 and c>=s30-a*2 and r<45 and c>e20*0.97: return "BUY"
    return "HOLD"

# Strategy B: H4 EMA10/30 Cross
def sig_b(df,i):
    e10=df["ema10"].iloc[i]; e30=df["ema30"].iloc[i]; e10_1=df["ema10"].iloc[i-1]; e30_1=df["ema30"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vol_ma"].iloc[i]; r=df["rsi14"].iloc[i]
    if e10_1<=e30_1 and e10>e30 and v>vm*1.2 and r>=30: return "BUY"
    if e10_1>=e30_1 and e10<e30 and v>vm*1.2 and r<=70: return "SELL"
    return "HOLD"

# Strategy C: H4 EMA12/26 Cross (faster)
def sig_c(df,i):
    e12=df["ema12"].iloc[i]; e26=df["ema26"].iloc[i]; e12_1=df["ema12"].iloc[i-1]; e26_1=df["ema26"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vol_ma"].iloc[i]; r=df["rsi14"].iloc[i]
    if e12_1<=e26_1 and e12>e26 and r>=30: return "BUY"
    if e12_1>=e26_1 and e12<e26 and r<=70: return "SELL"
    return "HOLD"

# Strategy D: H4 EMA5/13 Cross (fastest)
def sig_d(df,i):
    e5=df["ema5"].iloc[i]; e13=df["ema13"].iloc[i]; e5_1=df["ema5"].iloc[i-1]; e13_1=df["ema13"].iloc[i-1]
    v=df["tick_volume"].iloc[i]; vm=df["vol_ma"].iloc[i]
    if e5_1<=e13_1 and e5>e13 and v>vm*1.5: return "BUY"
    if e5_1>=e13_1 and e5<e13 and v>vm*1.5: return "SELL"
    return "HOLD"

# Strategy E: H4 Pullback SMA30 (long only)
def sig_e(df,i):
    c=df["close"].iloc[i]; s30=df["ema30"].iloc[i]; s100=df["ema26"].iloc[i]
    r=df["rsi14"].iloc[i]; a=df["atr14"].iloc[i]; e20=df["ema20"].iloc[i]
    if s30>s100 and c<=s30+a*0.3 and c>=s30-a*1.5 and r<50 and c>e20*0.97: return "BUY"
    return "HOLD"

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

rf = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, 800)
rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, 1500)
mt5.shutdown()

d1=pd.DataFrame(rf); d1["time"]=pd.to_datetime(d1["time"],unit="s"); d1.set_index("time",inplace=True); d1=prep(d1)
h4=pd.DataFrame(rh); h4["time"]=pd.to_datetime(h4["time"],unit="s"); h4.set_index("time",inplace=True); h4=prep(h4)

d1_4=d1.iloc[-120:]
h4_4=h4.iloc[-480:]

print(f"{'='*70}")
print(f"  PERBANDINGAN AKHIR — Fee Rp{PCT:,}/trade")
print(f"  Modal Rp{MODAL:,} | XAUUSDm")
print(f"{'='*70}")

tests = [
    (d1_4, sig_a, "A D1 Pullback SMA30", 2.5, 90, 0.15),
    (h4_4, sig_b, "B H4 EMA10/30 Cross", 2.0, 40, 0.08),
    (h4_4, sig_c, "C H4 EMA12/26 Cross", 2.0, 30, 0.08),
    (h4_4, sig_d, "D H4 EMA5/13 Cross", 1.5, 15, 0.08),
    (h4_4, sig_e, "E H4 Pullback SMA30", 2.0, 60, 0.12),
]

results = []
for df, fn, name, sl, mh, rp in tests:
    r = run(df, MODAL, fn, name, sl_atr=sl, max_hold=mh, running_pct=rp)
    results.append(r)
    pm="+" if r["profit"]>0 else ""
    print(f"  {r['name']:<25} Rp{r['profit']:>10,} ({pm}{r['roi']:>6.2f}%)  "
          f"WR: {r['wr']:>4}%  PF: {r['pf']:<5}  DD: {r['dd']:<4}%  /bln: Rp{r['per_bln']:>8,}  | {r['trades']} trades")

print(f"\n{'='*70}")
print(f"  VALIDASI FULL DATA")
print(f"{'='*70}")
for df, fn, name, sl, mh, rp in tests:
    r = run(df if len(df)>500 else d1, MODAL, fn, name, sl_atr=sl, max_hold=mh, running_pct=rp)
    pm="+" if r["profit"]>0 else ""
    print(f"  {r['name']:<28} Rp{r['profit']:>10,} ({pm}{r['roi']:>6.2f}%)  "
          f"WR: {r['wr']:>4}%  PF: {r['pf']:<5}  DD: {r['dd']:<4}%  | {r['trades']} trades")
