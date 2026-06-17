# Backtest G real: spread asli MT5, 1 minggu + 1 bulan
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOL = "XAUUSDm"; MODAL = 12_000_000
POINT_VALUE = 0.01

CONF_SIZING = [(0,2,1.0),(3,4,1.5),(5,6,2.0)]

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=10):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))

def prep(df):
    df["ema5"]=ema(df["close"],5); df["ema13"]=ema(df["close"],13)
    df["atr"]=atr(df,10); df["rsi"]=rsi(df["close"],14)
    df["vol_ma"]=sma(df["tick_volume"],15)
    m=df["close"].rolling(20).mean(); s=df["close"].rolling(20).std()
    df["bbw"]=(m+2*s-(m-2*s))/m; df["bbw_ma"]=sma(df["bbw"],20)
    df["squeeze"]=df["bbw"]<df["bbw_ma"]
    df["hour_utc"]=df.index.hour
    # H1 dari resample
    dh1=df.resample("1h").agg({"close":"last"})
    dh1["ema9"]=ema(dh1["close"],9); dh1["ema21"]=ema(dh1["close"],21)
    dh1["h1_trend"]=np.where(dh1["ema9"]>dh1["ema21"],"UP","DOWN")
    df["h1_trend"]=dh1["h1_trend"].resample("15min").ffill().reindex(df.index,method="ffill")
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

def get_frac(c):
    for l,h,f in CONF_SIZING:
        if l<=c<=h: return f
    return 1.0

def backtest(df, label):
    modal=float(MODAL); peak=modal; dd_max=0.0
    trades=[]; in_trade=False; posisi=None
    entry_price=0.0; entry_idx=0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; cur_day=None; day_pnl=0.0; modal_at_entry=0.0
    spread_total=0.0; commission_total=0.0
    p={"sl":0.5,"tp":2.2,"max_hold":20,"running":0.12,"max_dd":25}

    for i in range(50,len(df)):
        row=df.iloc[i]; c=row["close"]; a=row["atr"]
        ef=row["ema5"]; em=row["ema13"]
        day=df.index[i].date()
        # Real spread dari data MT5 (points -> rupiah)
        real_spread_pts=row.get("spread", 260)  # fallback
        if cur_day is None: cur_day=day
        if day!=cur_day: daily_pnl[cur_day]=day_pnl; cur_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>p["max_dd"]: in_trade=False; posisi=None; continue

        sig="HOLD"
        bull=ef>em; vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
        if bull and 30<=row["rsi"]<=95 and vol_ok: sig="BUY"
        if not bull and 5<=row["rsi"]<=70 and vol_ok: sig="SELL"

        conf=confidence(row); frac=get_frac(conf)

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False
                comm=5000*frac; modal-=comm; commission_total+=comm
                # Real spread cost
                spread_rp=(real_spread_pts*POINT_VALUE/entry_price)*(modal)*frac
                modal-=spread_rp; spread_total+=spread_rp
                modal_at_entry=modal; trade_frac=frac; in_trade=True
        else:
            bars=i-entry_idx; exit=False; profit=0.0; base=modal_at_entry*trade_frac
            if posisi=="BUY":
                if c<=sl_price: profit=(sl_price-entry_price)/entry_price*base; exit=True
                elif c>=tp_price: profit=(c-entry_price)/entry_price*base; exit=True
                elif ef<em: profit=(c-entry_price)/entry_price*base; exit=True
                elif bars>=p["max_hold"]: profit=(c-entry_price)/entry_price*base; exit=True
                else:
                    td=a*0.3
                    if not trail and (c-entry_price)>=td: trail=True; sl_price=entry_price+td*0.3
                    if trail: sl_price=max(sl_price,c-td*0.5)
                    profit=(c-df["close"].iloc[i-1])/df["close"].iloc[i-1]*base*p["running"]
            else:
                if c>=sl_price: profit=(entry_price-sl_price)/entry_price*base; exit=True
                elif c<=tp_price: profit=(entry_price-c)/entry_price*base; exit=True
                elif ef>em: profit=(entry_price-c)/entry_price*base; exit=True
                elif bars>=p["max_hold"]: profit=(entry_price-c)/entry_price*base; exit=True
                else:
                    td=a*0.3
                    if not trail and (entry_price-c)>=td: trail=True; sl_price=entry_price-td*0.3
                    if trail: sl_price=min(sl_price,c+td*0.5)
                    profit=(df["close"].iloc[i-1]-c)/df["close"].iloc[i-1]*base*p["running"]
            if exit:
                modal+=profit; day_pnl+=profit
                trades.append({"tgl":df.index[i], "posisi":posisi, "profit":round(profit)})
                in_trade=False; posisi=None

    if cur_day: daily_pnl[cur_day]=day_pnl
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100; avg_daily=np.mean(list(daily_pnl.values())) if daily_pnl else 0
    return {"label":label,"profit":round(modal-MODAL),"roi":round(roi,1),"dd":round(dd_max,1),
            "trades":len(trades),"wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),
            "avg_day":round(avg_daily,0),"spread":round(spread_total),"comm":round(commission_total)}

print("="*90)
print(f"  STRATEGY G — REAL SPREAD BACKTEST")
now=datetime.now()
print(f"  {now.strftime('%Y-%m-%d %H:%M')}")
print("="*90)

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL,True)

for label, bars in [("1 MINGGU", 672), ("1 BULAN", 2880)]:
    rates=mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    if rates is None: print(f"No data for {label}"); continue
    df=pd.DataFrame(rates)
    df["time"]=pd.to_datetime(df["time"],unit="s")
    df.set_index("time",inplace=True)
    t0,t1=df.index[0].date(),df.index[-1].date()
    avg_spr=df["spread"].mean()
    print(f"\n  --- {label} ({t0} — {t1}, {len(df)} bars, spread avg {avg_spr:.0f} pts) ---")

    df=prep(df)
    r=backtest(df, label)
    pm="+" if r["profit"]>0 else ""
    print(f"  Profit: Rp{r['profit']:>10,} ({pm}{r['roi']:>6.1f}%) | DD {r['dd']}% | "
          f"{r['trades']:>3}tr WR {r['wr']}% PF {r['pf']} | Rp{r['avg_day']:>8,}/hari")
    print(f"  Biaya Spread: Rp{r['spread']:>9,} | Komisi: Rp{r['comm']:>9,} | Total: Rp{r['spread']+r['comm']:>9,}")

    # Comparison: with simulated 25pts spread
    print(f"  --- vs simulasi spread 25 pts ---")
    df2=df.copy()
    df2["spread"]=25
    df2=prep(df2)
    r2=backtest(df2, label)
    pm2="+" if r2["profit"]>0 else ""
    print(f"  25pts: Rp{r2['avg_day']:>8,}/hari | Spread: Rp{r2['spread']:>9,} | Profit: Rp{r2['profit']:>9,}")
    diff=r["avg_day"]-r2["avg_day"]
    print(f"  SELISIH (real lebih): Rp{diff:>8,}/hari ({'LEBIH JELEK' if diff<0 else 'LEBIH BAGUS'})")

mt5.shutdown()
print(f"\n{'='*90}")
print(f"  KESIMPULAN:")
print(f"  Spread real MT5: 260-396 pts (rata-rata ~276 pts)")
print(f"  Spread simulasi: 25 pts (asumsi awal)")
print(f"  Real spread ~11x lebih besar dari asumsi!")
print(f"{'='*90}")
