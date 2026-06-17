import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np
from itertools import product

MODAL = 12_000_000; SYMBOL = "XAUUSDm"
PCT = 100_000  # fee per trade

def sma(s,p): return s.rolling(p).mean()
def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()

def prep(df):
    for p in [5,7,10,12,13,15,20,26,30,50]: df[f"ema{p}"] = ema(df["close"],p)
    df["atr14"]=atr(df,14); df["atr7"]=atr(df,7)
    df["rsi14"]=100-(100/(1+df["close"].diff().where(lambda x:x>0,0).rolling(14).mean()/(-df["close"].diff().where(lambda x:x<0,0).rolling(14).mean())))
    df["vol_ma"]=df["tick_volume"].rolling(10).mean()
    df.dropna(inplace=True); return df

def run(df, modal, params, silent=True):
    m=float(modal); entry=0; peak=m; dd_max=0; trades=[]; in_trade=False; held=0; pos=None
    ef, ex, sl_m, mh, rsi_min, vol_f = (params.get(k) for k in ["ema_fast","ema_slow","sl_atr","max_hold","rsi_min","vol_factor"])

    for i in range(5,len(df)-1):
        c=df["close"].iloc[i]; cn=df["close"].iloc[i+1]; a=df["atr14"].iloc[i]
        if m>peak: peak=m
        dd=(peak-m)/peak*100; dd_max=max(dd_max,dd)
        if dd>30: in_trade=False; pos=None; continue

        emaF=df[f"ema{ef}"].iloc[i]; emaS=df[f"ema{es}"].iloc[i]
        eF1=df[f"ema{ef}"].iloc[i-1]; eS1=df[f"ema{es}"].iloc[i-1]
        r=df["rsi14"].iloc[i]; v=df["tick_volume"].iloc[i]; vm=df["vol_ma"].iloc[i]

        cross_up = eF1<=eS1 and emaF>emaS
        cross_dn = eF1>=eS1 and emaF<emaS
        high_vol = v >= vm * vol_f

        if not in_trade:
            if cross_up and high_vol and r >= rsi_min:
                pos="LONG"; entry=c; m-=PCT; in_trade=True; held=0
            elif cross_dn and high_vol and r <= 100-rsi_min:
                pos="SHORT"; entry=c; m-=PCT; in_trade=True; held=0
        else:
            held+=1; profit=0; exit_now=False
            if pos=="LONG":
                if cn<=entry-a*sl_m: profit=-(a*sl_m/entry)*m; exit_now=True
                elif cross_dn: profit=(c-entry)/entry*m; exit_now=True
                elif held>mh: profit=(c-entry)/entry*m*0.5; exit_now=True
                else: profit=(cn-c)/c*m*0.08
            else:
                if cn>=entry+a*sl_m: profit=-(a*sl_m/entry)*m; exit_now=True
                elif cross_up: profit=(entry-c)/entry*m; exit_now=True
                elif held>mh: profit=(entry-c)/entry*m*0.5; exit_now=True
                else: profit=(c-cn)/c*m*0.08
            if exit_now:
                m+=profit; trades.append({"profit":profit}); in_trade=False; pos=None

    roi=(m-modal)/modal*100; win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/abs(sum(t["profit"] for t in loss)) if loss else 999
    return {"profit":round(m-modal),"roi":round(roi,2),"trades":len(trades),"wr":round(len(win)/max(len(trades),1)*100,1),
            "pf":round(pf,2),"dd":round(dd_max,1),"modal_akhir":round(m)}


if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)

# Fetch H4 data
rh = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H4, 0, 1500)
mt5.shutdown()
dh = pd.DataFrame(rh); dh["time"]=pd.to_datetime(dh["time"],unit="s"); dh.set_index("time",inplace=True)
dh = prep(dh)
d4 = dh.iloc[-480:]   # 4 bulan H4
print(f"H4 4bln: {d4.index[0].date()} — {d4.index[-1].date()} ({len(d4)} bars)")

# Grid search
grid = list(product([5,7,10,12],[15,20,26,30],[1.5,2.0,2.5],[30,40,50],[30,40,50],[1.0,1.2,1.5]))
results = []
for ef, es, sl, mh, rsi_min, vf in grid:
    if ef >= es: continue
    r = run(d4, MODAL, {"ema_fast":ef,"ema_slow":es,"sl_atr":sl,"max_hold":mh,"rsi_min":rsi_min,"vol_factor":vf})
    results.append({**r, "params":f"{ef}/{es}/{sl}/{mh}/{rsi_min}/{vf}"})

results.sort(key=lambda x: x["profit"], reverse=True)

print(f"\n{'='*95}")
print(f"  TOP 10 BEST PARAMS — H4 EMA CROSS")
print(f"{'='*95}")
print(f"  {'#':<3} {'Params F/S/SL/MH/RSI/V':<28} {'Profit':<13} {'ROI':<8} {'WR':<7} {'PF':<7} {'DD':<6} {'Trades':<7}")
print(f"  {'-'*76}")
for i, r in enumerate(results[:10], 1):
    pm = "+" if r["profit"] > 0 else ""
    print(f"  {i:<3} {r['params']:<28} Rp{r['profit']:<10,} ({pm}{r['roi']:>6.2f}%) "
          f"{r['wr']:>4}%  {r['pf']:<5} {r['dd']:<4}%  {r['trades']}")

# Best params: full period test
best = results[0]
print(f"\n{'='*95}")
print(f"  BEST PARAMS: {best['params']}")
print(f"  4 bulan: Rp{best['profit']:,} | ROI {best['roi']}% | WR {best['wr']}% | PF {best['pf']} | DD {best['dd']}%")

# Test on full H4 data
print(f"\n{'='*95}")
print(f"  VALIDASI FULL DATA H4")
print(f"{'='*95}")
ef1, es1, sl1, mh1, rsi1, vf1 = [float(x) if '.' in x else int(x) for x in best["params"].split("/")]
r_full = run(dh, MODAL, {"ema_fast":int(ef1),"ema_slow":int(es1),"sl_atr":sl1,"max_hold":int(mh1),"rsi_min":int(rsi1),"vol_factor":vf1}, silent=False)
print(f"  Full {len(dh)} bars: Rp{r_full['profit']:,} | ROI {r_full['roi']}% | WR {r_full['wr']}% | PF {r_full['pf']} | DD {r_full['dd']}% | {r_full['trades']} trades")
print(f"  Modal: Rp{MODAL:,} -> Rp{r_full['modal_akhir']:,}")
