import numpy as np
import pandas as pd

def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def sma(s, p):
    return s.rolling(p).mean()

def atr(df, p=14):
    tr = np.maximum(df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    return tr.rolling(p).mean()

def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def macd(s, f=12, sl=26, sg=9):
    e1 = ema(s, f)
    e2 = ema(s, sl)
    m = e1 - e2
    return m, ema(m, sg)

def bb(df, p=20, std=2):
    m = df["close"].rolling(p).mean()
    s = df["close"].rolling(p).std()
    return m + std * s, m, m - std * s
