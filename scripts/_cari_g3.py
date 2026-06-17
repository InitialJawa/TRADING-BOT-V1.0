# Strategi G v3: Confidence-scored sizing (corrected)
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
    """Score 0-6"""
    s=0; bull=row["ema5"]>row["ema13"]
    h1=row["h1_trend"]
    if (bull and h1=="UP") or (not bull and h1=="DOWN"): s+=2
    if row["squeeze"]: s+=1
    if row["tick_volume"]>row["vol_ma"]*1.2: s+=1
    if bull and row["rsi"]>65: s+=1
    if not bull and row["rsi"]<35: s+=1
    if 7<=row["hour_utc"]<15: s+=1
    return s

def sizing(score):
    """Return fraksi modal (0.0-1.5) berdasarkan confidence score"""
    # 0: 0.3, 1: 0.3, 2: 0.5, 3: 0.7, 4: 1.0, 5: 1.3, 6: 1.5
    return {0:0.3,1:0.3,2:0.5,3:0.7,4:1.0,5:1.3,6:1.5}.get(score,0.3)

def backtest(df, label, mode="fixed", min_conf=0):
    """mode: 'fixed' (fraksi=1.0 selalu), 'dynamic' (fraksi by score)"""
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None
    entry_price=0.0; entry_idx=0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; cur_day=None; day_pnl=0.0
    modal_at_entry=0.0

    for i in range(50,len(df)):
        row=df.iloc[i]; c=row["close"]; a=row["atr"]
        ef=row["ema5"]; em=row["ema13"]
        day=df.index[i].date()
        if cur_day is None: cur_day=day
        if day!=cur_day: daily_pnl[cur_day]=day_pnl; cur_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>25: in_trade=False; posisi=None; continue

        # F signal
        bull=ef>em; vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
        sig="HOLD"
        if bull and 30<=row["rsi"]<=95 and vol_ok: sig="BUY"
        if not bull and 5<=row["rsi"]<=70 and vol_ok: sig="SELL"

        # Confidence-based filter
        conf=confidence(row)
        if mode=="filter" and sig!="HOLD" and conf<min_conf: sig="HOLD"

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False
                # Fraksi modal untuk trade ini
                if mode=="dynamic":
                    frac=sizing(conf)
                else: frac=1.0
                # Biaya sebanding dengan fraksi
                cost_komisi=5000*frac
                cost_spread=(SPREAD_PTS*POINT_VAL/entry_price)*(modal-cost_komisi)*frac
                modal-=cost_komisi; modal-=cost_spread
                modal_at_entry=modal
                trade_frac=frac; in_trade=True
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
    return {"label":label,"profit":round(modal-MODAL),"roi":round(roi,1),"dd":round(dd_max,1),
            "trades":len(trades),"wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),
            "avg_day":round(avg_daily,0)}

print("="*100)
print("  STRATEGI G v3 — Confidence-Scored Dynamic Sizing (fix)")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*100)

data = fetch()
if data[0] is None: print("Error"); exit()
df, dh1 = data; df = prep(df, dh1)
print(f"  Bars: {len(df)}\n")

r_fixed = backtest(df, "F baseline (fraksi 1.0)", mode="fixed")
r_dyn = backtest(df, "G Dynamic (fraksi 0.3-1.5 by confidence)", mode="dynamic")

for r in [r_fixed, r_dyn]:
    pm="+" if r["profit"]>0 else ""
    print(f"  {r['label']:<55}")
    print(f"    Rp{r['avg_day']:>8,}/hari | Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) "
          f"DD {r['dd']:>4}% {r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5}")
    print()

# Filter mode
print("  --- Filter by min confidence ---")
for thresh in range(1,7):
    r=backtest(df, f"", mode="filter", min_conf=thresh)
    print(f"    min>={thresh}: Rp{r['avg_day']:>8,}/hari | Rp{r['profit']:>10,} "
          f"DD {r['dd']}% {r['trades']}tr WR {r['wr']}% PF {r['pf']}")

# Perbandingan distribusi confidence
conf_dist={i:0 for i in range(7)}
for i in range(50,len(df)):
    c=confidence(df.iloc[i])
    bull=df.iloc[i]["ema5"]>df.iloc[i]["ema13"]
    vol=df.iloc[i]["tick_volume"]>df.iloc[i]["vol_ma"]*0.7
    rsi=30<=df.iloc[i]["rsi"]<=95 if bull else 5<=df.iloc[i]["rsi"]<=70
    if rsi and vol: conf_dist[c]=conf_dist.get(c,0)+1

print("\n  Distribusi confidence (hanya bar dengan sinyal F):")
for i in range(7):
    print(f"    score={i}: {conf_dist[i]:>4} bar ({conf_dist[i]/sum(conf_dist.values())*100:.1f}%)")

# Summary confidence vs profit
print("\n  --- Performance by confidence level ---")
for conf_level in range(7):
    trades_at_conf=[t for t in (r_fixed.get("all_trades",[]) if hasattr(r_fixed,"get") else [])]
    # Simplified: just show distribution
    pct=conf_dist[conf_level]/sum(conf_dist.values())*100 if sum(conf_dist.values())>0 else 0
    print(f"    score {conf_level}: {pct:.1f}% of signals")
