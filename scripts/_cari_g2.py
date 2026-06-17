# Lanjutan: coba kombinasi tanpa session filter
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
    if dh1 is not None:
        dh1["ema9"]=ema(dh1["close"],9); dh1["ema21"]=ema(dh1["close"],21)
        dh1["h1_trend"]=np.where(dh1["ema9"]>dh1["ema21"],"UP","DOWN")
        df["h1_trend"]=dh1["h1_trend"].reindex(df.index,method="ffill")
    else:
        df["h1_trend"]="NEUTRAL"
    df.dropna(inplace=True); return df

def backtest(df, label, use_h1=False, use_squeeze=False, use_agree=False,
             use_session=False, session_start=7, session_end=15):
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None
    entry_price=0.0; entry_idx=0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; cur_day=None; day_pnl=0.0

    for i in range(50,len(df)):
        row=df.iloc[i]; c=row["close"]; a=row["atr"]
        ef=row["ema5"]; em=row["ema13"]
        day=df.index[i].date()
        if cur_day is None: cur_day=day
        if day!=cur_day: daily_pnl[cur_day]=day_pnl; cur_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>25: in_trade=False; posisi=None; continue

        # Session filter
        if use_session:
            h=df.index[i].hour
            if session_start<=session_end and not (session_start<=h<session_end):
                sig="HOLD"
                if in_trade: pass  # let open trade continue
                else: sig="HOLD"
            else:
                sig=signal_fn(row, use_h1, use_squeeze, use_agree)
        else:
            sig=signal_fn(row, use_h1, use_squeeze, use_agree)

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False; modal-=5000
                spread=(SPREAD_PTS*POINT_VAL/entry_price)*modal; modal-=spread
                in_trade=True
        else:
            bars=i-entry_idx; exit=False; profit=0.0
            if posisi=="BUY":
                if c<=sl_price: profit=(sl_price-entry_price)/entry_price*modal; exit=True
                elif c>=tp_price: profit=(c-entry_price)/entry_price*modal; exit=True
                elif ef<em: profit=(c-entry_price)/entry_price*modal; exit=True
                elif bars>=20: profit=(c-entry_price)/entry_price*modal; exit=True
                else:
                    td=a*0.3
                    if not trail and (c-entry_price)>=td: trail=True; sl_price=entry_price+td*0.3
                    if trail: sl_price=max(sl_price,c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*modal*0.12
            else:
                if c>=sl_price: profit=(entry_price-sl_price)/entry_price*modal; exit=True
                elif c<=tp_price: profit=(entry_price-c)/entry_price*modal; exit=True
                elif ef>em: profit=(entry_price-c)/entry_price*modal; exit=True
                elif bars>=20: profit=(entry_price-c)/entry_price*modal; exit=True
                else:
                    td=a*0.3
                    if not trail and (entry_price-c)>=td: trail=True; sl_price=entry_price-td*0.3
                    if trail: sl_price=min(sl_price,c+td*0.5)
                    profit=(df["close"].iloc[i-1]-c)/df["close"].iloc[i-1]*modal*0.12
            if exit:
                modal+=profit; day_pnl+=profit
                trades.append({"profit":round(profit)})
                in_trade=False; posisi=None
    if cur_day: daily_pnl[cur_day]=day_pnl
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100
    avg_daily=np.mean(list(daily_pnl.values())) if daily_pnl else 0
    return {"label":label,"profit":round(modal-MODAL),"roi":round(roi,1),"dd":round(dd_max,1),
            "trades":len(trades),"wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),
            "avg_day":round(avg_daily,0)}

def signal_fn(row, use_h1, use_squeeze, use_agree):
    ema_bull=row["ema5"]>row["ema13"]
    vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
    # F signal (wide RSI)
    f_buy=ema_bull and 30<=row["rsi"]<=95 and vol_ok
    f_sell=not ema_bull and 5<=row["rsi"]<=70 and vol_ok
    # E signal (with MACD)
    e_buy=ema_bull and 35<=row["rsi"]<=82 and row["macd"]>row["macd_sig"] and vol_ok
    e_sell=not ema_bull and 18<=row["rsi"]<=65 and row["macd"]<row["macd_sig"] and vol_ok

    sig_f="BUY" if f_buy else ("SELL" if f_sell else "HOLD")
    sig_e="BUY" if e_buy else ("SELL" if e_sell else "HOLD")

    if use_agree:
        if sig_f=="BUY" and sig_e=="BUY": sig="BUY"
        elif sig_f=="SELL" and sig_e=="SELL": sig="SELL"
        else: sig="HOLD"
    else:
        sig=sig_f

    # H1 trend filter
    if use_h1 and sig!="HOLD":
        if sig=="BUY" and row["h1_trend"]!="UP": sig="HOLD"
        elif sig=="SELL" and row["h1_trend"]!="DOWN": sig="HOLD"

    # Squeeze filter
    if use_squeeze and sig!="HOLD" and not row["squeeze"]:
        sig="HOLD"

    return sig

print("="*100)
print("  G VARIANT — tanpa session filter (kombinasi lain)")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*100)

data = fetch()
if data[0] is None: print("Error"); exit()
df, dh1 = data; df = prep(df, dh1)
print(f"  Bars: {len(df)}\n")

tests = [
    ("F baseline", False, False, False),
    ("G: H1 Trend only", True, False, False),
    ("G: Squeeze only", False, True, False),
    ("G: Agreement E+F only", False, False, True),
    ("G: H1 + Squeeze", True, True, False),
    ("G: H1 + Agreement", True, False, True),
    ("G: H1 + Squeeze + Agreement", True, True, True),
    ("G: Squeeze + Agreement", False, True, True),
]

for label, h1, sq, agree in tests:
    r = backtest(df, label, use_h1=h1, use_squeeze=sq, use_agree=agree)
    pm = "+" if r["profit"]>0 else ""
    print(f"  {label:<40} Rp{r['avg_day']:>8,}/hari | "
          f"Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) DD {r['dd']:>4}% "
          f"{r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5}")
print()

# Ranking
results=[backtest(df,l,h,sq,a) for l,h,sq,a in tests]
print("  RANKING:")
for i,r in enumerate(sorted(results,key=lambda x:x["avg_day"],reverse=True),1):
    print(f"  #{i:<2} {r['label']:<40} Rp{r['avg_day']:>8,}/hari DD {r['dd']}% {r['trades']}tr PF {r['pf']}")
