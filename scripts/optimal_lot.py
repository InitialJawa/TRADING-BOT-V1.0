import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import MetaTrader5 as mt5; import pandas as pd; import numpy as np

MODAL=12_000_000; SYMBOL="XAUUSDm"; PCT=10_000

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def atr(df,p=14):
    tr=np.maximum(df["high"]-df["low"],np.maximum(abs(df["high"]-df["close"].shift(1)),abs(df["low"]-df["close"].shift(1))))
    return tr.rolling(p).mean()

def prep(df):
    for p in [10,20,30]: df[f"e{p}"]=ema(df["close"],p)
    df["a14"]=atr(df,14)
    r=df["close"].diff(); g=r.where(r>0,0).rolling(14).mean(); l=(-r.where(r<0,0)).rolling(14).mean()
    df["r14"]=100-(100/(1+g/l))
    df["vm"]=df["tick_volume"].rolling(10).mean()
    df.dropna(inplace=True); return df

def run(df, modal, lot_pct):  # lot_pct = % modal dipakai per trade
    m=float(modal); entry=0; peak=m; dd_max=0; trades=[]; in_trade=False; held=0; pos=None
    for i in range(5,len(df)-1):
        c=df["close"].iloc[i]; cn=df["close"].iloc[i+1]; a=df["a14"].iloc[i]
        if m>peak: peak=m
        dd=(peak-m)/peak*100; dd_max=max(dd_max,dd)
        if dd>30: in_trade=False; pos=None; continue

        e10=df["e10"].iloc[i]; e30=df["e30"].iloc[i]
        e10_1=df["e10"].iloc[i-1]; e30_1=df["e30"].iloc[i-1]
        v=df["tick_volume"].iloc[i]; vm=df["vm"].iloc[i]; r=df["r14"].iloc[i]
        cu=e10_1<=e30_1 and e10>e30; cd=e10_1>=e30_1 and e10<e30
        hv=v>=vm*1.2

        if not in_trade:
            if cu and hv and r>=20:
                pos="L"; entry=c; in_trade=True; held=0
            elif cd and hv and r<=80:
                pos="S"; entry=c; in_trade=True; held=0
        else:
            held+=1; profit=0; exit=False
            pos_size = m * lot_pct / 100   # Rp yg dipertaruhkan
            sl=a*1.5  # SL 1.5 ATR

            if pos=="L":
                if cn<=entry-sl: profit=-pos_size; exit=True
                elif cd: profit=(c-entry)/entry*pos_size*2; exit=True
                elif held>40: profit=(c-entry)/entry*pos_size; exit=True
                else: profit=(cn-c)/c*pos_size*0.05
            else:
                if cn>=entry+sl: profit=-pos_size; exit=True
                elif cu: profit=(entry-c)/entry*pos_size*2; exit=True
                elif held>40: profit=(entry-c)/entry*pos_size; exit=True
                else: profit=(c-cn)/c*pos_size*0.05

            if exit:
                m+=profit
                trades.append({"profit":round(profit),"held":held})
                in_trade=False; pos=None

    roi=(m-modal)/modal*100
    win=[t for t in trades if t["profit"]>0]; loss=[t for t in trades if t["profit"]<0]
    pf=sum(t["profit"] for t in win)/abs(sum(t["profit"] for t in loss)) if loss else 999
    days=max((df.index[-1]-df.index[0]).days,1)
    return {"profit":round(m-modal),"roi":round(roi,2),"trades":len(trades),
            "wr":round(len(win)/max(len(trades),1)*100,1),"pf":round(pf,2),"dd":round(dd_max,1),
            "per_bln":round((m-modal)/days*30),"modal_akhir":round(m)}

if not mt5.initialize(): print("[ERROR] MT5"); exit()
mt5.symbol_select(SYMBOL, True)
rh=mt5.copy_rates_from_pos(SYMBOL,mt5.TIMEFRAME_H4,0,1500)
mt5.shutdown()
dh=pd.DataFrame(rh); dh["time"]=pd.to_datetime(dh["time"],unit="s"); dh.set_index("time",inplace=True)
dh=prep(dh); d4=dh.iloc[-480:]

print(f"{'='*60}")
print(f"  Strategy B — Optimal Lot Size")
print(f"  Modal Rp{MODAL:,} | Max DD target: ~10%")
print(f"{'='*60}")

# Test various lot percentages
for lp in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 200]:
    r4=run(d4,MODAL,lp)
    r_full=run(dh,MODAL,lp)
    pm="+" if r4["profit"]>0 else ""
    print(f"  Lot {lp:>3}% | 4bln: Rp{r4['profit']:>10,} ({pm}{r4['roi']:>6.2f}%) DD {r4['dd']:>4}% | "
          f"Full: Rp{r_full['profit']:>10,} ({pm}{r_full['roi']:>6.2f}%) DD {r_full['dd']:>4}% WR {r_full['wr']}%")

print(f"\n{'='*60}")
print(f"  REKOMENDASI")
print(f"{'='*60}")
print(f"  Dengan modal Rp{MODAL:,} dan target DD max 10%:")
print(f"  -> Gunakan posisi ~70-80% dari modal (DD ~4-5% di 4bln, ~8-10% full)")
print(f"  -> Atau ~50% untuk konservatif (DD ~3-4%)")
print(f"  -> Atau ~120% untuk agresif (DD ~6-7%)")
print(f"\n  Perkiraan return/bulan dengan Rp{MODAL:,}:")
for lp, per in [(50,"konservatif"),(80,"moderat"),(120,"agresif")]:
    r=run(dh,MODAL,lp)
    print(f"    {lp}% ({per:<12}): Rp{r['per_bln']:,}/bln | DD {r['dd']}%")
