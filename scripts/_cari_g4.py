# G Final: skip jelek, gandain bagus
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
def macd(s,f=5,sl=13,sg=5):
    e1=ema(s,f); e2=ema(s,sl); m=e1-e2; return m, ema(m,sg)
def bb(df,p=20,std=2):
    m=df["close"].rolling(p).mean(); s=df["close"].rolling(p).std()
    return m+std*s, m, m-std*s

def prep(df, dh1):
    df["ema5"]=ema(df["close"],5); df["ema13"]=ema(df["close"],13)
    df["atr"]=atr(df,10); df["rsi"]=rsi(df["close"],14)
    df["macd"],df["macd_sig"]=macd(df["close"],5,13,5)
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

def backtest(df, label, skip_conf0=False, double_d5=False, double_d6=False):
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None; frac_now=1.0
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
        if skip_conf0 and conf==0: sig="HOLD"
        frac=1.0
        if double_d5 and conf>=5: frac=2.0
        if double_d6 and conf>=6: frac=2.5

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False
                cost=5000*frac; modal-=cost
                spread=(SPREAD_PTS*POINT_VAL/entry_price)*(modal)*frac; modal-=spread
                modal_at_entry=modal; frac_now=frac; in_trade=True
        else:
            bars=i-entry_idx; exit=False; profit=0.0
            if posisi=="BUY":
                if c<=sl_price: profit=(sl_price-entry_price)/entry_price*modal_at_entry*frac_now; exit=True
                elif c>=tp_price: profit=(c-entry_price)/entry_price*modal_at_entry*frac_now; exit=True
                elif ef<em: profit=(c-entry_price)/entry_price*modal_at_entry*frac_now; exit=True
                elif bars>=20: profit=(c-entry_price)/entry_price*modal_at_entry*frac_now; exit=True
                else:
                    td=a*0.3
                    if not trail and (c-entry_price)>=td: trail=True; sl_price=entry_price+td*0.3
                    if trail: sl_price=max(sl_price,c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*modal_at_entry*frac_now*0.12
            else:
                if c>=sl_price: profit=(entry_price-sl_price)/entry_price*modal_at_entry*frac_now; exit=True
                elif c<=tp_price: profit=(entry_price-c)/entry_price*modal_at_entry*frac_now; exit=True
                elif ef>em: profit=(entry_price-c)/entry_price*modal_at_entry*frac_now; exit=True
                elif bars>=20: profit=(entry_price-c)/entry_price*modal_at_entry*frac_now; exit=True
                else:
                    td=a*0.3
                    if not trail and (entry_price-c)>=td: trail=True; sl_price=entry_price-td*0.3
                    if trail: sl_price=min(sl_price,c+td*0.5)
                    profit=(df["close"].iloc[i-1]-c)/df["close"].iloc[i-1]*modal_at_entry*frac_now*0.12
            if exit:
                modal+=profit; day_pnl+=profit
                trades.append({"profit":round(profit),"conf":conf,"frac":frac_now})
                in_trade=False; posisi=None

    if cur_day: daily_pnl[cur_day]=day_pnl
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100
    avg_daily=np.mean(list(daily_pnl.values())) if daily_pnl else 0
    return {"label":label,"profit":round(modal-MODAL),"roi":round(roi,1),"dd":round(dd_max,1),
            "trades":len(trades),"wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),
            "avg_day":round(avg_daily,0)}

print("="*100)
print("  STRATEGI G FINAL — Skip Jelek, Gandain Bagus")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*100)

data = fetch()
if data[0] is None: print("Error"); exit()
df, dh1 = data; df = prep(df, dh1)
print(f"  Bars: {len(df)}\n")

tests = [
    ("F baseline (no filter)", False, False, False),
    ("G: skip conf=0", True, False, False),
    ("G: skip conf=0 + double conf>=5", True, True, False),
    ("G: skip conf=0 + double conf>=6 (2.5x)", True, False, True),
    ("G: double conf>=5 only (no skip)", False, True, False),
    ("G: skip conf 0-1 + double conf>=5", True, True, False),  # will need skip_conf01 param
]

for label, skip0, d5, d6 in tests:
    if "skip conf 0-1" in label:
        # Need to modify logic for this case - handle separately
        continue
    r=backtest(df, label, skip_conf0=skip0, double_d5=d5, double_d6=d6)
    pm="+" if r["profit"]>0 else ""
    print(f"  {label:<50}")
    print(f"    Rp{r['avg_day']:>8,}/hari | Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) "
          f"DD {r['dd']:>4}% {r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5}")
    print()

# Test skip conf 0-1 separately
r2=backtest(df, "G: skip conf 0-1 + double conf>=5", skip_conf0=False, double_d5=True, double_d6=False)
# Manual adjust: in the backtest, set skip_conf0 means skip conf==0 but not conf==1
# Need separate test
print("  (skip conf 0-1 needs separate run below)")
