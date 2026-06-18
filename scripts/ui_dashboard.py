import sys, os, json, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategies.shared.indicators import ema, sma, atr, rsi, macd

BOT_SCRIPT = os.path.join(os.path.dirname(__file__), "live_bot_4_ticker.py")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "live_bot.log")
os.makedirs(LOG_DIR, exist_ok=True)

bot_process = None
bot_running = False

TICKERS = [
    {"n":"XAGUSDm","s":"D","t":"H1","p":{"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,"rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":1.2,"atr_tp_mult":4.0,"atr_trail_mult":0.3,"volume_ma_period":20,"volume_mult":0.8,"max_hold_bars":30,"lot_pct":100,"running_pct":0.1,"no_ema200":False,"no_macd":False}},
    {"n":"ETHUSDm","s":"D","t":"H1","p":{"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,"rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":1.5,"atr_tp_mult":4.0,"atr_trail_mult":0.4,"volume_ma_period":20,"volume_mult":1.0,"max_hold_bars":24,"lot_pct":60,"running_pct":0.1,"no_ema200":False,"no_macd":False}},
    {"n":"BTCUSDTm","s":"D","t":"H1","p":{"mode":"trend","ema_fast":9,"ema_medium":21,"rsi_long_min":30,"rsi_long_max":80,"rsi_short_min":20,"rsi_short_max":70,"atr_period":14,"atr_sl_mult":2.0,"atr_tp_mult":3.5,"atr_trail_mult":0.4,"volume_ma_period":20,"volume_mult":1.0,"max_hold_bars":24,"lot_pct":50,"running_pct":0.1,"no_ema200":False,"no_macd":False}},
    {"n":"JP225m","s":"G","t":"M15","p":{"mode":"trend","ema_fast":5,"ema_medium":13,"rsi_long_min":30,"rsi_long_max":95,"rsi_short_min":5,"rsi_short_max":70,"atr_period":10,"atr_sl_mult":0.7,"atr_tp_mult":3.5,"atr_trail_mult":0.3,"volume_ma_period":15,"volume_mult":0.7,"max_hold_bars":20,"lot_pct":120,"running_pct":0.12,"no_ema200":True,"no_macd":True}},
]

def clr():
    os.system("cls" if os.name == "nt" else "clear")

def prep(df, p):
    ef, em = p["ema_fast"], p["ema_medium"]
    df[f"e{ef}"] = ema(df["close"], ef); df[f"e{em}"] = ema(df["close"], em)
    df["e50"] = ema(df["close"], p.get("ema_trend", 50))
    df["e200"] = ema(df["close"], p.get("ema_major", 200))
    df["a"] = atr(df, p.get("atr_period", 14))
    df["r"] = rsi(df["close"], p.get("rsi_period", 14))
    if not p.get("no_macd", False):
        df["m"], df["ms"] = macd(df["close"], 12, 26, 9)
    else:
        df["m"] = 0; df["ms"] = 0
    df["v"] = sma(df["tick_volume"], p.get("volume_ma_period", 20))
    df.dropna(inplace=True); return df

def sig(df, i, p):
    try:
        row=df.iloc[i]; c=float(row["close"])
        ef,em=f"e{p['ema_fast']}",f"e{p['ema_medium']}"
        eb=float(row[ef])>float(row[em]); es=float(row[ef])<float(row[em])
        a2=c>float(row["e200"]) if not p.get("no_ema200",False) else True
        rsiv=float(row["r"])
        rl=p.get("rsi_long_min",30)<=rsiv<=p.get("rsi_long_max",80)
        rs=p.get("rsi_short_min",20)<=rsiv<=p.get("rsi_short_max",80)
        mv,msv=float(row["m"]),float(row["ms"])
        mb=p.get("no_macd",False) or mv>msv
        ms2=p.get("no_macd",False) or mv<msv
        vo=float(row["tick_volume"])>float(row["v"])*p.get("volume_mult",1.0)
        if a2 and eb and rl and mb and vo: return "BUY"
        if (not a2) and es and rs and ms2 and vo: return "SELL"
        return "HOLD"
    except: return "N/A"

def whyno(df, i, p):
    try:
        row=df.iloc[i]; c=float(row["close"])
        ef,em=f"e{p['ema_fast']}",f"e{p['ema_medium']}"
        r=[]
        a2=c>float(row["e200"]) if not p.get("no_ema200",False) else True
        if not a2: r.append("<200")
        if not float(row[ef])>float(row[em]): r.append("ema")
        rsiv=float(row["r"])
        if not (p.get("rsi_long_min",30)<=rsiv<=p.get("rsi_long_max",80)): r.append("rsi")
        mv,msv=float(row["m"]),float(row["ms"])
        if not (p.get("no_macd",False) or mv>msv): r.append("macd")
        if not (float(row["tick_volume"])>float(row["v"])*p.get("volume_mult",1.0)): r.append("vol")
        return ",".join(r) if r else "ready"
    except: return "err"

def get_data():
    r={"pos":[],"sig":[],"hist":[],"ac":{}}
    try:
        if not mt5.initialize(): r["ac"]={"err":"MT5 down"}; return r
        a=mt5.account_info()
        if a: r["ac"]={"b":a.balance,"e":a.equity,"p":a.profit}
        pos=mt5.positions_get()
        for p in (pos or []):
            h=(datetime.now()-datetime.fromtimestamp(p.time)).total_seconds()/3600
            r["pos"].append({"s":p.symbol,"t":"B" if p.type==0 else "S","v":p.volume,"e":p.price_open,"sl":p.sl,"tp":p.tp,"pnl":p.profit,"h":h,"id":p.ticket})
        td=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        deals=mt5.history_deals_get(td,datetime.now())
        seen=set()
        for d in reversed(deals or []):
            if d.symbol not in seen:
                r["hist"].append({"s":d.symbol,"t":"B" if d.type==0 else "S","p":d.price,"pnl":d.profit,"tm":datetime.fromtimestamp(d.time).strftime("%H:%M")})
                seen.add(d.symbol)
            if len(r["hist"])>=8: break
        for tc in TICKERS:
            si={"s":tc["n"],"st":tc["s"],"tf":tc["t"],"sg":"N/A","tr":"?","rsi":0,"vp":"?","mac":"?","rs":"nd","hp":False}
            try:
                tf=mt5.TIMEFRAME_H1 if tc["t"]=="H1" else mt5.TIMEFRAME_M15
                rates=mt5.copy_rates_from_pos(tc["n"],tf,0,300)
                if rates is not None and len(rates)>100:
                    df=pd.DataFrame(rates); df["time"]=pd.to_datetime(df["time"],unit="s"); df.set_index("time",inplace=True)
                    df=prep(df,tc["p"])
                    if len(df)>5:
                        l=df.iloc[-1]; ef,em=f"e{tc['p']['ema_fast']}",f"e{tc['p']['ema_medium']}"
                        si["tr"]="U" if l[ef]>l[em] else "D"
                        si["rsi"]=float(round(l["r"],0)) if not pd.isna(l["r"]) else 0
                        si["mac"]="B" if float(l["m"])>float(l["ms"]) else "b"
                        si["vp"]="H" if float(l["tick_volume"])>float(l["v"]) else "L"
                        si["c"]=float(round(l["close"],2))
                        si["e1"]=float(round(l[ef],1)); si["e2"]=float(round(l[em],1))
                        s2=sig(df,-1,tc["p"]); si["sg"]=s2
                        si["rs"]=whyno(df,-1,tc["p"])
                        if s2!="HOLD":
                            sv=float(l["a"])*tc["p"]["atr_sl_mult"]; tv=float(l["a"])*tc["p"]["atr_tp_mult"]
                            si["sl"]=round(float(l["close"])-sv,2) if s2=="BUY" else round(float(l["close"])+sv,2)
                            si["tp"]=round(float(l["close"])+tv,2) if s2=="BUY" else round(float(l["close"])-tv,2)
            except Exception as et:
                si["rs"]=f"err:{str(et)[:40]}"
            for p in r["pos"]:
                if p["s"]==tc["n"]: si["hp"]=True; si["pt"]=p["t"]; si["pp"]=p["pnl"]; si["pe"]=p["e"]
            r["sig"].append(si)
        mt5.shutdown()
    except Exception as e: r["ac"]={"err":str(e)}
    return r

def draw():
    clr()
    d=get_data()
    ac=d["ac"]; pos=d["pos"]; sigs=d["sig"]; hist=d["hist"]
    
    now=datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Header
    print(f"\n  === TRADING BOT === {now}")
    b=e=pfl=0
    if "err" not in ac:
        b=ac.get("b",0); e=ac.get("e",0); pfl=ac.get("p",0)
        pf_f=f"+Rp{pfl:,.0f}" if pfl>=0 else f"Rp{pfl:,.0f}"
        print(f"  Balance: Rp{b:,.0f}  Equity: Rp{e:,.0f}  Float: {pf_f}")
    else:
        print(f"  [WARN] {ac['err']}")
    print()
    
    # Strategy status
    print(f"  {'Ticker':<10} {'S':<4} {'Status':<9} {'Trend':<5} {'RSI':<4} {'Signal':<7} {'Entry':>10} {'PnL':>12}")
    print(f"  {'-'*62}")
    for s in sigs:
        tf="--HOLD"; pnl_f="---"; entry="---"
        if s["hp"]:
            tf="*LIVE"
            pnl=s.get("pp",0)
            pnl_f=f"+Rp{pnl:,}" if pnl>=0 else f"Rp{pnl:,}"
            entry=s.get("pe","---")
        tr=s["tr"]
        tr_d="^U" if tr=="U" else "vD"
        rv=s.get("rsi",0)
        r_d=f"v{rv:.0f}" if rv<=30 else f"^{rv:.0f}" if rv>=70 else f"{rv:.0f}"
        sg=s["sg"]
        sg_d="BUY" if sg=="BUY" else "SELL" if sg=="SELL" else "---"
        print(f"  {s['s']:<10} {s['st']+s['tf']:<4} {tf:<9} {tr_d:<5} {r_d:<4} {sg_d:<7} {str(entry):>10} {pnl_f:>12}")
    
    # Market detail
    print(f"\n  Market:")
    for s in sigs:
        if s.get("c"):
            ema_s=f"{s.get('e1','?')}/{s.get('e2','?')}"
            sl=s.get("sl","---"); tp=s.get("tp","---")
            sl_s=f"{sl:.2f}" if isinstance(sl,float) else "---"
            tp_s=f"{tp:.2f}" if isinstance(tp,float) else "---"
            print(f"  {s['s']:<10} {s['c']:>9} {s['mac']:<4} {s['vp']:<4} SL:{sl_s:<9} TP:{tp_s:<9} {s['rs']}")
    
    # History
    if hist:
        print(f"\n  History:")
        for h in hist:
            pf_h=h["pnl"]
            pf_s=f"+Rp{pf_h:,}" if pf_h>=0 else f"Rp{pf_h:,}"
            rs="TP" if pf_h>0 else ("SL" if pf_h<0 else "---")
            print(f"  {h['s']:<10} {h['t']:<3} {h['p']:>10.2f} {pf_s:>12} {rs:<5} {h['tm']}")
    
    # Bot control
    bot_s="*RUNNING" if bot_running else "STOPPED"
    print(f"\n  Bot: {bot_s}")
    print(f"  [1]Start [2]Stop [3]Refresh [4]Log [5]CloseAll")
    print(f"  [6]BUY   [7]SELL [T]Select  [Q]Quit")
    print()
    i=input("  > ").strip().upper()
    return i

def start_bot():
    global bot_process,bot_running
    if bot_running: return
    bot_process=subprocess.Popen([sys.executable,BOT_SCRIPT],stdout=open(LOG_FILE,"a"),stderr=subprocess.STDOUT,cwd=os.path.dirname(os.path.dirname(__file__)))
    bot_running=True

def stop_bot():
    global bot_process,bot_running
    if not bot_running: return
    if bot_process: bot_process.terminate(); bot_process.wait(timeout=5)
    bot_running=False

def open_pos(sym,side):
    if not mt5.initialize(): return
    mt5.symbol_select(sym,True)
    s=mt5.symbol_info(sym); tick=mt5.symbol_info_tick(sym)
    price=tick.ask if side=="BUY" else tick.bid
    sl=price-s.point*500 if side=="BUY" else price+s.point*500
    tp=price+s.point*1500 if side=="BUY" else price-s.point*1500
    req={"action":mt5.TRADE_ACTION_DEAL,"symbol":sym,"volume":s.volume_min,"type":mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL,"price":price,"sl":sl,"tp":tp,"deviation":10,"magic":123456,"comment":"manual"}
    r=mt5.order_send(req); mt5.shutdown()
    print(f"  {'[OK]' if r.retcode==10009 else '[FAIL]'} {sym} {side}"); time.sleep(1)

def close_all():
    if not mt5.initialize(): return
    c=0
    for p in (mt5.positions_get() or []):
        ct=mt5.ORDER_TYPE_SELL if p.type==0 else mt5.ORDER_TYPE_BUY
        tk=mt5.symbol_info_tick(p.symbol); pr=tk.bid if p.type==0 else tk.ask
        req={"action":mt5.TRADE_ACTION_DEAL,"symbol":p.symbol,"volume":p.volume,"type":ct,"position":p.ticket,"price":pr,"deviation":10,"magic":p.magic,"comment":"close_all"}
        r=mt5.order_send(req)
        if r.retcode==10009: c+=1
    mt5.shutdown(); print(f"  [OK] Closed {c}"); time.sleep(1.5)

sel=0
while True:
    key=draw()
    if key=="1": start_bot()
    elif key=="2": stop_bot()
    elif key=="3": pass
    elif key=="4":
        clr(); print(f"\n  [LOG] {LOG_FILE[-30:]}")
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                for l in f.readlines()[-30:]: print(f"  {l.rstrip()}")
        input(); clr()
    elif key=="5": close_all()
    elif key=="6": open_pos(TICKERS[sel]["n"],"BUY")
    elif key=="7": open_pos(TICKERS[sel]["n"],"SELL")
    elif key=="T": sel=(sel+1)%4; print(f"  Selected: {TICKERS[sel]['n']}"); time.sleep(1)
    elif key=="Q":
        if bot_running: stop_bot()
        clr(); print("  Bye!"); break
