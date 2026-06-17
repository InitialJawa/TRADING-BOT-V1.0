# G Final — sweet spot optimization
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd; import numpy as np; from datetime import datetime

SYMBOL="XAUUSDm"; MODAL=12_000_000; SPREAD_PTS=25; POINT_VAL=0.01

def fetch(b=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize(): return None
    mt5.symbol_select(SYMBOL,True)
    r=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_M15,0,b)
    rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H1,0,b//4)
    mt5.shutdown()
    if r is None: return None
    df=pd.DataFrame(r); df["time"]=pd.to_datetime(df["time"],unit="s"); df.set_index("time",inplace=True)
    if rh is not None: dh1=pd.DataFrame(rh); dh1["time"]=pd.to_datetime(dh1["time"],unit="s"); dh1.set_index("time",inplace=True)
    else: dh1=None
    return df, dh1

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=10):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))
def bb(df,p=20,std=2):
    m=df["close"].rolling(p).mean(); s=df["close"].rolling(p).std()
    return m+std*s, m, m-std*s

def prep(df, dh1):
    df["ema5"]=ema(df["close"],5); df["ema13"]=ema(df["close"],13)
    df["atr"]=atr(df,10); df["rsi"]=rsi(df["close"],14)
    df["vol_ma"]=sma(df["tick_volume"],15)
    df["bbu"],df["bbm"],df["bbl"]=bb(df,20,2)
    df["bbw"]=(df["bbu"]-df["bbl"])/df["bbm"]
    df["bbw_ma"]=sma(df["bbw"],20)
    df["squeeze"]=df["bbw"]<df["bbw_ma"]
    df["hour_utc"]=df.index.hour
    if dh1 is not None:
        dh1["ema9"]=ema(dh1["close"],9); dh1["ema21"]=ema(dh1["close"],21)
        dh1["h1_trend"]=np.where(dh1["ema9"]>dh1["ema21"],"UP","DOWN")
        df["h1_trend"]=dh1["h1_trend"].reindex(df.index,method="ffill")
    else: df["h1_trend"]="NEUTRAL"
    df.dropna(inplace=True); return df

def confidence(row):
    s=0; bull=row["ema5"]>row["ema13"]
    if (bull and row["h1_trend"]=="UP") or (not bull and row["h1_trend"]=="DOWN"): s+=2
    if row["squeeze"]: s+=1
    if row["tick_volume"]>row["vol_ma"]*1.2: s+=1
    if bull and row["rsi"]>65: s+=1
    if not bull and row["rsi"]<35: s+=1
    if 7<=row["hour_utc"]<15: s+=1
    return s

def backtest(df, label, sizing_map):
    """sizing_map: dict conf_level->fraction, e.g. {0:1,1:1,2:1,3:1,4:1,5:2,6:2}"""
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None
    entry_price=0.0; entry_idx=0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; cur_day=None; day_pnl=0.0; modal_at_entry=0.0

    for i in range(50,len(df)):
        row=df.iloc[i]; c=row["close"]; a=row["atr"]
        ef=row["ema5"]; em=row["ema13"]
        day=df.index[i].date()
        if cur_day is None: cur_day=day
        if day!=cur_day: daily_pnl[cur_day]=day_pnl; cur_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>25: in_trade=False; posisi=None; continue

        bull=ef>em; vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
        sig="HOLD"
        if bull and 30<=row["rsi"]<=95 and vol_ok: sig="BUY"
        if not bull and 5<=row["rsi"]<=70 and vol_ok: sig="SELL"

        conf=confidence(row)
        frac=sizing_map.get(conf, 0)
        if frac==0: sig="HOLD"

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False
                cost=5000*frac; modal-=cost
                spread=(SPREAD_PTS*POINT_VAL/entry_price)*(modal)*frac; modal-=spread
                modal_at_entry=modal; trade_frac=frac; in_trade=True
        else:
            bars=i-entry_idx; exit=False; profit=0.0
            if posisi=="BUY":
                if c<=sl_price: profit=(sl_price-entry_price)/entry_price*modal_at_entry*trade_frac; exit=True
                elif c>=tp_price: profit=(c-entry_price)/entry_price*modal_at_entry*trade_frac; exit=True
                elif ef<em: profit=(c-entry_price)/entry_price*modal_at_entry*trade_frac; exit=True
                elif bars>=20: profit=(c-entry_price)/entry_price*modal_at_entry*trade_frac; exit=True
                else:
                    td=a*0.3
                    if not trail and (c-entry_price)>=td: trail=True; sl_price=entry_price+td*0.3
                    if trail: sl_price=max(sl_price,c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*modal_at_entry*trade_frac*0.12
            else:
                if c>=sl_price: profit=(entry_price-sl_price)/entry_price*modal_at_entry*trade_frac; exit=True
                elif c<=tp_price: profit=(entry_price-c)/entry_price*modal_at_entry*trade_frac; exit=True
                elif ef>em: profit=(entry_price-c)/entry_price*modal_at_entry*trade_frac; exit=True
                elif bars>=20: profit=(entry_price-c)/entry_price*modal_at_entry*trade_frac; exit=True
                else:
                    td=a*0.3
                    if not trail and (entry_price-c)>=td: trail=True; sl_price=entry_price-td*0.3
                    if trail: sl_price=min(sl_price,c+td*0.5)
                    profit=(df["close"].iloc[i-1]-c)/df["close"].iloc[i-1]*modal_at_entry*trade_frac*0.12
            if exit:
                modal+=profit; day_pnl+=profit
                trades.append({"profit":round(profit),"conf":conf})
                in_trade=False; posisi=None

    if cur_day: daily_pnl[cur_day]=day_pnl
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100
    avg_daily=np.mean(list(daily_pnl.values())) if daily_pnl else 0
    noc=[str(k)+":"+str(v) for k,v in sorted(sizing_map.items())]
    return {"label":label+" | "+" ".join(noc),"profit":round(modal-MODAL),"roi":round(roi,1),
            "dd":round(dd_max,1),"trades":len(trades),
            "wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),"avg_day":round(avg_daily,0)}

print("="*120)
print("  STRATEGI G — SWEET SPOT OPTIMIZATION")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*120)

data = fetch()
if data[0] is None: print("Error"); exit()
df, dh1 = data; df = prep(df, dh1)
print(f"  Bars: {len(df)}\n")

# Berbagai konfigurasi sizing
configs = [
    ("F baseline", {0:1,1:1,2:1,3:1,4:1,5:1,6:1}),
    ("G v1: 2x conf>=5", {0:1,1:1,2:1,3:1,4:1,5:2,6:2}),
    ("G v2: 1.5x conf>=4, 2x>=5, 2.5x>=6", {0:1,1:1,2:1,3:1,4:1.5,5:2,6:2.5}),
    ("G v3: skip0, 1.5x conf>=4, 2x>=5", {0:0,1:1,2:1,3:1,4:1.5,5:2,6:2}),
    ("G v4: 1.5x conf>=4", {0:1,1:1,2:1,3:1,4:1.5,5:1.5,6:1.5}),
    ("G v5: 2x conf>=4", {0:1,1:1,2:1,3:1,4:2,5:2,6:2}),
    ("G v6: 3x conf>=5", {0:1,1:1,2:1,3:1,4:1,5:3,6:3}),
    ("G v7: skip0, 2x conf>=4", {0:0,1:1,2:1,3:1,4:2,5:2,6:2}),
    ("G v8: 2x conf>=5, skip 0", {0:0,1:1,2:1,3:1,4:1,5:2,6:2}),
    ("G v9: 1.5x conf>=3, 2x>=5", {0:1,1:1,2:1,3:1.5,4:1.5,5:2,6:2}),
    ("G v10: 2x conf>=5, skip 0-1", {0:0,1:0,2:1,3:1,4:1,5:2,6:2}),
]

results = []
for label, smap in configs:
    r = backtest(df, label, smap)
    results.append(r)
    pm = "+" if r["profit"]>0 else ""
    print(f"  {r['label']:<65}")
    print(f"    Rp{r['avg_day']:>8,}/hari | Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) "
          f"DD {r['dd']:>4}% {r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5}")
    print()

print("="*120)
print("  RANKING:")
for i,r in enumerate(sorted(results,key=lambda x:x["avg_day"],reverse=True),1):
    pm="+" if r["profit"]>0 else ""
    extra = ""
    # Best trade-off
    if r["dd"]<=5.0 and r["avg_day"]>700000:
        extra = " * BEST"
    print(f"  #{i:<2} Rp{r['avg_day']:>8,}/hari | {r['label'][:55]:<55} | DD {r['dd']:>4}% "
          f"{r['trades']:>4}tr PF {r['pf']:>5} WR {r['wr']:>4}%{extra}")
