# Test RSI variants on ORIGINAL F backtest engine
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd; import numpy as np; from datetime import datetime

SYMBOL = "XAUUSDm"; MODAL = 12_000_000; TARGET_HARIAN = 300_000
SPREAD_POINTS = 25; POINT_VALUE = 0.01

def try_mt5_data(bars=12000):
    import MetaTrader5 as mt5
    if not mt5.initialize(): return None
    mt5.symbol_select(SYMBOL, True)
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, bars)
    mt5.shutdown()
    if rates is None or len(rates) < 500: return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True); return df

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def atr(df,p=10):
    tr = np.maximum(df["high"]-df["low"],
        np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))
def macd(s,f=5,sl=13,sg=5):
    e1=ema(s,f); e2=ema(s,sl); m=e1-e2; return m, ema(m,sg)

def prep(df):
    p = {"ema_fast":5, "ema_medium":13, "ema_trend":50, "ema_major":200,
         "atr_period":10, "volume_ma_period":15}
    df["ema5"]=ema(df["close"],p["ema_fast"])
    df["ema13"]=ema(df["close"],p["ema_medium"])
    df["ema50"]=ema(df["close"],p["ema_trend"])
    df["ema200"]=ema(df["close"],p["ema_major"])
    df["atr"]=atr(df,p["atr_period"])
    df["rsi"]=rsi(df["close"],14)
    df["macd"],df["macd_sig"]=macd(df["close"],5,13,5)
    df["vol_ma"]=sma(df["tick_volume"],p["volume_ma_period"])
    df.dropna(inplace=True); return df

def backtest(df, params):
    p = params; modal = float(MODAL); peak = modal; dd_max = 0.0
    trades = []; in_trade = False; posisi = None
    entry_price = 0.0; entry_idx = 0; sl_price=0.0; tp_price=0.0; trail=False
    daily_pnl={}; current_day=None; day_pnl=0.0

    for i in range(50, len(df)):
        c=df["close"].iloc[i]; a=df["atr"].iloc[i]
        ef=df["ema5"].iloc[i]; em=df["ema13"].iloc[i]
        row=df.iloc[i]; day=df.index[i].date()
        if current_day is None: current_day=day
        if day!=current_day: daily_pnl[current_day]=day_pnl; current_day=day; day_pnl=0.0
        if modal>peak: peak=modal
        dd=(peak-modal)/peak*100; dd_max=max(dd_max,dd)
        if dd>25: in_trade=False; posisi=None; continue

        # Signal F logic
        ema_bull=row["ema5"]>row["ema13"]
        rsi_long=p["rsi_lmin"]<=row["rsi"]<=p["rsi_lmax"]
        macd_bull=row["macd"]>row["macd_sig"] or True
        vol_ok=row["tick_volume"]>row["vol_ma"]*0.7
        sig="HOLD"
        if ema_bull and rsi_long and macd_bull and vol_ok: sig="BUY"
        ema_bear=row["ema5"]<row["ema13"]
        rsi_short=p["rsi_smin"]<=row["rsi"]<=p["rsi_smax"]
        macd_bear=row["macd"]<row["macd_sig"] or True
        if ema_bear and rsi_short and macd_bear and vol_ok: sig="SELL"

        if not in_trade:
            if sig!="HOLD":
                posisi=sig; entry_price=c; entry_idx=i
                sl_price=c-a*0.5 if sig=="BUY" else c+a*0.5
                tp_price=c+a*2.2 if sig=="BUY" else c-a*2.2
                trail=False; modal-=5000
                spread_cost=(SPREAD_POINTS*POINT_VALUE/entry_price)*modal
                modal-=spread_cost; in_trade=True
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
                trades.append({"tgl":df.index[i],"posisi":posisi,"held":bars,"profit":round(profit),"modal":round(modal)})
                in_trade=False; posisi=None
    if current_day: daily_pnl[current_day]=day_pnl
    win=[t for t in trades if t["profit"]>0]
    loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/max(abs(sum(t["profit"] for t in loss)),1) if loss else 999
    roi=(modal-MODAL)/MODAL*100
    avg_daily=np.mean(list(daily_pnl.values())) if daily_pnl else 0
    return {"label":params["label"],"profit":round(modal-MODAL),"roi":round(roi,1),
            "dd":round(dd_max,1),"trades":len(trades),"win":len(win),
            "wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),
            "avg_day":round(avg_daily,0),"modal":round(modal)}

print("="*100)
print("  OPTIMASI RSI - ORIGINAL F ENGINE")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*100)

df = try_mt5_data()
if df is None: print("Error"); exit()
df = prep(df)

variants = [
    dict(label="Current: 15-70 / 30-85", rsi_smin=15, rsi_smax=70, rsi_lmin=30, rsi_lmax=85),
    dict(label="Opt: 10-70 / 30-90", rsi_smin=10, rsi_smax=70, rsi_lmin=30, rsi_lmax=90),
    dict(label="Opt: 5-70 / 30-95", rsi_smin=5, rsi_smax=70, rsi_lmin=30, rsi_lmax=95),
    dict(label="No RSI: 0-100 / 0-100", rsi_smin=0, rsi_smax=100, rsi_lmin=0, rsi_lmax=100),
]

results = []
for p in variants:
    r = backtest(df, p)
    results.append(r)
    pm="+" if r["profit"]>0 else ""
    print(f"  {p['label']:<35} Profit: Rp{r['profit']:>9,} ({pm}{r['roi']:>6.1f}%) DD {r['dd']:>4}% "
          f"{r['trades']:>4}tr WR {r['wr']:>4}% PF {r['pf']:>5} Rp{r['avg_day']:>8,}/hari")
print()
print("  RANKING:")
for i,r in enumerate(sorted(results,key=lambda x:x["avg_day"],reverse=True),1):
    print(f"  #{i:<2} {r['label']:<35} Rp{r['avg_day']:>8,}/hari | "
          f"Rp{r['profit']:>9,} | DD {r['dd']}% | {r['trades']} tr")
