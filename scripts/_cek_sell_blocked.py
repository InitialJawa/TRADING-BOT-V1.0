import MetaTrader5 as mt5; import pandas as pd; import numpy as np
if not mt5.initialize():
    print("MT5 fail"); exit()
mt5.symbol_select("XAUUSDm", True)
rates = mt5.copy_rates_from_pos("XAUUSDm", mt5.TIMEFRAME_M15, 0, 12000)
mt5.shutdown()
if rates is None: exit()
df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df.set_index("time", inplace=True)

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))
df["ema5"]=ema(df["close"],5)
df["ema13"]=ema(df["close"],13)
df["ema200"]=ema(df["close"],200)
df["rsi"]=rsi(df["close"],14)
df["vol_ma"]=sma(df["tick_volume"],15)
df.dropna(inplace=True)

# 1. RSI terlalu rendah block
b1 = df[(df["ema5"]<df["ema13"]) & (df["tick_volume"]>df["vol_ma"]*0.7) & (df["rsi"]<15)]
print(f"SELL diblokir RSI<15: {len(b1)} bar")
print("5 contoh TERAKHIR:")
for idx in b1.index[-5:]:
    r = b1.loc[idx]
    print(f"  {idx} | Close={r['close']:.2f} | RSI={r['rsi']:.1f} | Vol={r['tick_volume']:.0f}/{r['vol_ma']:.0f} | EMA5={r['ema5']:.2f} EMA13={r['ema13']:.2f}")

# 2. Volume kurang block
b2 = df[(df["ema5"]<df["ema13"]) & (df["rsi"]>=15) & (df["rsi"]<=70) & (df["tick_volume"]<=df["vol_ma"]*0.7)]
print(f"\nSELL diblokir VOLUME kurang: {len(b2)} bar")
print("5 contoh TERAKHIR:")
for idx in b2.index[-5:]:
    r = b2.loc[idx]
    vpct = r["tick_volume"] / r["vol_ma"] * 100
    print(f"  {idx} | Close={r['close']:.2f} | RSI={r['rsi']:.1f} | Vol={r['tick_volume']:.0f}/{r['vol_ma']:.0f} ({vpct:.0f}%)")

# 3. Cek: berapa bar dengan EMA5<EMA13 + volume OK + RSI > 70 (sell diblokir RSI terlalu tinggi)
b3 = df[(df["ema5"]<df["ema13"]) & (df["tick_volume"]>df["vol_ma"]*0.7) & (df["rsi"]>70)]
print(f"\nSELL diblokir RSI>70: {len(b3)} bar (RSI masih tinggi meskipun EMA turun)")
if len(b3) > 0:
    for idx in b3.index[-3:]:
        r = b3.loc[idx]
        print(f"  {idx} | Close={r['close']:.2f} | RSI={r['rsi']:.1f} | Vol={r['tick_volume']:.0f}/{r['vol_ma']:.0f}")

# 4. Timing issue: berapa bar sinyal muncul di bar yg beda dgn candle besar?
print(f"\n=== TIMING CHECK ===")
print(f"Rata-rata hold: 3 bar (44 menit) untuk F")
print(f"Maksudnya: signal di close bar, entry di close bar yang sama")
print(f"Kalo candle besar turun 0.5%+, entry di close masih di harga bagus")
print(f"TAPI kalo candle besar dengan body besar + wick panjang,")
print(f"entry di close bisa ketinggalan atau kepotong SL next bar")
