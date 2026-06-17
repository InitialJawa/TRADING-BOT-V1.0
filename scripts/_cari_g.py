# Eksplorasi Strategi G — kombinasi Session + Multi-TF + Squeeze + E+F Hybrid
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd; import numpy as np; from datetime import datetime

SYMBOL = "XAUUSDm"; MODAL = 12_000_000
SPREAD_PTS = 25; POINT_VAL = 0.01

def fetch(bars=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize(): return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    rates_h1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, bars//4)
    mt5.shutdown()
    if rates is None: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    if rates_h1 is not None:
        dh1 = pd.DataFrame(rates_h1)
        dh1["time"] = pd.to_datetime(dh1["time"], unit="s")
        dh1.set_index("time", inplace=True)
    else: dh1 = None
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

def prep_m15(df, h1_df=None):
    df["ema5"]=ema(df["close"],5); df["ema13"]=ema(df["close"],13)
    df["ema50"]=ema(df["close"],50); df["ema200"]=ema(df["close"],200)
    df["atr"]=atr(df,10); df["rsi"]=rsi(df["close"],14)
    df["macd"],df["macd_sig"]=macd(df["close"],5,13,5)
    df["vol_ma"]=sma(df["tick_volume"],15)
    df["bbu"],df["bbm"],df["bbl"]=bb(df,20,2)
    df["bbw"]=(df["bbu"]-df["bbl"])/df["bbm"]
    df["bbw_ma"]=sma(df["bbw"],20)
    df["squeeze"]=df["bbw"]<df["bbw_ma"]
    df.dropna(inplace=True)

    # H1 trend (forward-filled ke M15)
    if h1_df is not None:
        h1_df["ema9"]=ema(h1_df["close"],9); h1_df["ema21"]=ema(h1_df["close"],21)
        h1_df["h1_trend"]=np.where(h1_df["ema9"]>h1_df["ema21"], "UP", "DOWN")
        h1_trend = h1_df["h1_trend"].resample("15min").ffill()
        df["h1_trend"] = h1_trend.reindex(df.index, method="ffill")
    else:
        df["h1_trend"] = "NEUTRAL"

    # Session filter (UTC hours)
    df["hour_utc"] = df.index.hour
    df["session_london"] = df["hour_utc"].between(7, 14)
    df["session_ny"] = df["hour_utc"].between(12, 19)
    df["session_overlap"] = df["hour_utc"].between(12, 14)

    return df

def backtest(df, label, use_session=False, use_h1trend=False, use_squeeze=False,
             use_agreement=False, rsi_smin=5, rsi_smax=70, rsi_lmin=30, rsi_lmax=95):
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None
    entry_price=0.0; entry_idx=0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; cur_day=None; day_pnl=0.0

    for i in range(50, len(df)):
        row=df.iloc[i]; c=row["close"]; a=row["atr"]
        ef=row["ema5"]; em=row["ema13"]
        day=df.index[i].date()
        if cur_day is None: cur_day=day
        if day!=cur_day: daily_pnl[cur_day]=day_pnl; cur_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>25: in_trade=False; posisi=None; continue

        # Filters
        if use_session and not row["session_london"]:
            # Skip non-London hours
            sig="HOLD"
        else:
            # === Signal F (base) ===
            ema_bull=row["ema5"]>row["ema13"]
            vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
            sig_f="HOLD"
            if ema_bull and rsi_lmin<=row["rsi"]<=rsi_lmax and vol_ok: sig_f="BUY"
            ema_bear=row["ema5"]<row["ema13"]
            if ema_bear and rsi_smin<=row["rsi"]<=rsi_smax and vol_ok: sig_f="SELL"

            # === Signal E (with MACD) ===
            sig_e="HOLD"
            if ema_bull and row["rsi"]>=35 and row["rsi"]<=82 and row["macd"]>row["macd_sig"] and vol_ok: sig_e="BUY"
            if ema_bear and row["rsi"]>=18 and row["rsi"]<=65 and row["macd"]<row["macd_sig"] and vol_ok: sig_e="SELL"

            # === Agreement filter ===
            if use_agreement:
                if sig_f=="BUY" and sig_e=="BUY": sig="BUY"
                elif sig_f=="SELL" and sig_e=="SELL": sig="SELL"
                else: sig="HOLD"
            else: sig=sig_f

            # === H1 Trend filter ===
            if use_h1trend and sig!="HOLD":
                h1_dir=row["h1_trend"]
                if sig=="BUY" and h1_dir!="UP": sig="HOLD"
                elif sig=="SELL" and h1_dir!="DOWN": sig="HOLD"

            # === Squeeze filter ===
            if use_squeeze and sig!="HOLD" and not row["squeeze"]:
                sig="HOLD"

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
                    if trail: sl_price=max(sl_price, c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*modal*0.12
            else:
                if c>=sl_price: profit=(entry_price-sl_price)/entry_price*modal; exit=True
                elif c<=tp_price: profit=(entry_price-c)/entry_price*modal; exit=True
                elif ef>em: profit=(entry_price-c)/entry_price*modal; exit=True
                elif bars>=20: profit=(entry_price-c)/entry_price*modal; exit=True
                else:
                    td=a*0.3
                    if not trail and (entry_price-c)>=td: trail=True; sl_price=entry_price-td*0.3
                    if trail: sl_price=min(sl_price, c+td*0.5)
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
            "avg_day":round(avg_daily,0),"modal":round(modal)}

print("="*100)
print("  EKSPLORASI STRATEGI G — Kombinasi Session + Multi-TF + Squeeze + Hybrid")
print(f"  Modal Rp{MODAL:,} | Spread 25 pts | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*100)

data = fetch()
if data[0] is None: print("Error"); exit()
df, dh1 = data
df = prep_m15(df, dh1)
t0, t1 = df.index[0].date(), df.index[-1].date()
print(f"  Periode: {t0} — {t1} ({len(df)} bars)")
print()

combos = [
    # (label, session, h1trend, squeeze, agreement)
    ("F baseline (RSI 5-70/30-95)", False, False, False, False),
    ("G1: +Session London (07-14UTC)", True, False, False, False),
    ("G2: +Session + H1 Trend", True, True, False, False),
    ("G3: +Session + H1 + Squeeze", True, True, True, False),
    ("G4: +Session + H1 + Agreement (E+F)", True, True, False, True),
    ("G5: +Session + H1 + Squeeze + Agreement", True, True, True, True),
]

for label, sess, h1t, sqz, agree in combos:
    r = backtest(df, label, use_session=sess, use_h1trend=h1t,
                 use_squeeze=sqz, use_agreement=agree)
    pm="+" if r["profit"]>0 else ""
    print(f"  {label:<50}")
    print(f"    Profit: Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) DD {r['dd']:>4}% "
          f"{r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5} Rp{r['avg_day']:>8,}/hari")
    print()

print("="*100)
print("  RANKING:")
results = [backtest(df, l, s, h, sq, a) for l,s,h,sq,a in combos]
for i, r in enumerate(sorted(results, key=lambda x: x["avg_day"], reverse=True), 1):
    print(f"  #{i:<2} {r['label']:<50} Rp{r['avg_day']:>8,}/hari | "
          f"Rp{r['profit']:>10,} | DD {r['dd']}% | {r['trades']}tr | PF {r['pf']}")
