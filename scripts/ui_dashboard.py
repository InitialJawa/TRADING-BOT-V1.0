import sys, os, json, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from strategies.shared.stage_analysis import prep_stage, detect_stage, signal_stage_enhanced, confidence_score

BOT_SCRIPT = os.path.join(os.path.dirname(__file__), "live_bot_4_ticker.py")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "live_bot.log")
os.makedirs(LOG_DIR, exist_ok=True)

bot_process = None
bot_running = False

TICKERS = [
    {"n":"XAGUSDm","t":"H1",
     "p":{"ema_fast":9,"ema_medium":21,"ema_trend":50,"ema_major":200,"rsi_period":14,"atr_period":14,
          "atr_sl_mult":1.2,"atr_trail_mult":0.8,"trail_sl_mul":1.5,"volume_ma_period":20,"volume_mult":0.8,
          "running_pct":0.1,"stage_slope_threshold":0.0004,"lot_pct":100,"fee":0,
          "conf_sizing":[(0,2,1.0),(3,4,1.5),(5,7,2.0)],
          "confidence_factors":{"h4":2,"session":1,"volume":1,"rsi":1,"squeeze":1,"ema200":1}}},
    {"n":"XAUUSDm","t":"H1",
     "p":{"ema_fast":9,"ema_medium":21,"ema_trend":50,"ema_major":200,"rsi_period":14,"atr_period":14,
          "atr_sl_mult":1.5,"atr_trail_mult":0.8,"trail_sl_mul":1.5,"volume_ma_period":20,"volume_mult":0.8,
          "running_pct":0.1,"stage_slope_threshold":0.0004,"lot_pct":100,"fee":0,
          "conf_sizing":[(0,2,1.0),(3,4,1.5),(5,7,2.0)],
          "confidence_factors":{"h4":2,"session":1,"volume":1,"rsi":1,"squeeze":1,"ema200":1}}},
    {"n":"JP225m","t":"H1",
     "p":{"ema_fast":9,"ema_medium":21,"ema_trend":50,"ema_major":200,"rsi_period":14,"atr_period":14,
          "atr_sl_mult":1.0,"atr_trail_mult":0.8,"trail_sl_mul":1.5,"volume_ma_period":20,"volume_mult":0.8,
          "running_pct":0.1,"stage_slope_threshold":0.0005,"lot_pct":100,"fee":0,
          "conf_sizing":[(0,2,1.0),(3,4,1.5),(5,7,2.0)],
          "confidence_factors":{"h4":2,"session":1,"volume":1,"rsi":1,"squeeze":1,"ema200":1}}},
]

STAGE_LABEL = {1:"ACCUM",2:"TREND+",3:"DISTR",4:"TREND-"}

def clr():
    os.system("cls" if os.name == "nt" else "clear")

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
            si={"s":tc["n"],"st":"I","tf":tc["t"],"sg":"N/A","tr":"?","rsi":0,"stage":0,"conf":0,"frac":1.0,"hp":False}
            try:
                rates=mt5.copy_rates_from_pos(tc["n"],mt5.TIMEFRAME_H1,0,500)
                if rates is not None and len(rates)>100:
                    df=pd.DataFrame(rates); df["time"]=pd.to_datetime(df["time"],unit="s"); df.set_index("time",inplace=True)
                    h4r=mt5.copy_rates_from_pos(tc["n"],mt5.TIMEFRAME_H4,0,125)
                    dh4=None
                    if h4r is not None and len(h4r)>50:
                        dh4=pd.DataFrame(h4r); dh4["time"]=pd.to_datetime(dh4["time"],unit="s"); dh4.set_index("time",inplace=True)
                    df=prep_stage(df,dh4,tc["p"])
                    if len(df)>5:
                        l=df.iloc[-1]
                        st=detect_stage(l,tc["p"].get("stage_slope_threshold",0.0004))
                        si["stage"]=st; si["tr"]="U" if l["ema9"]>l["ema21"] else "D"
                        si["rsi"]=float(round(l["rsi"],0)) if not pd.isna(l["rsi"]) else 0
                        si["c"]=float(round(l["close"],2))
                        si["e1"]=float(round(l["ema9"],1)); si["e2"]=float(round(l["ema21"],1))
                        s2=signal_stage_enhanced(df,-1,tc["p"]); si["sg"]=s2
                        conf=confidence_score(l,tc["p"].get("confidence_factors",None))
                        si["conf"]=conf
                        frac=1.0
                        for lo,hi,fv in tc["p"].get("conf_sizing",[(0,2,1.0),(3,4,1.5),(5,7,2.0)]):
                            if lo<=conf<=hi: frac=fv; break
                        si["frac"]=frac
                        if s2!="HOLD":
                            sv=float(l["atr"])*tc["p"]["atr_sl_mult"]
                            si["sl"]=round(float(l["close"])-sv,2) if s2=="BUY" else round(float(l["close"])+sv,2)
            except Exception as et:
                si["sg"]=f"err:{str(et)[:40]}"
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
    print(f"\n  === TRADING BOT — STRATEGY I (Stage Analysis) === {now}")
    b=e=pfl=0
    if "err" not in ac:
        b=ac.get("b",0); e=ac.get("e",0); pfl=ac.get("p",0)
        pf_f=f"+Rp{pfl:,.0f}" if pfl>=0 else f"Rp{pfl:,.0f}"
        print(f"  Balance: Rp{b:,.0f}  Equity: Rp{e:,.0f}  Float: {pf_f}")
    else:
        print(f"  [WARN] {ac['err']}")
    print()
    print(f"  {'Ticker':<10} {'Stage':<7} {'Trend':<5} {'Conf':<5} {'RSI':<4} {'Signal':<7} {'Entry':>10} {'PnL':>12}")
    print(f"  {'-'*62}")
    for s in sigs:
        tf="--HOLD"; pnl_f="---"; entry="---"
        if s["hp"]:
            tf="*LIVE"
            pnl=s.get("pp",0)
            pnl_f=f"+Rp{pnl:,}" if pnl>=0 else f"Rp{pnl:,}"
            entry=s.get("pe","---")
        tr=s["tr"]; tr_d="^U" if tr=="U" else "vD"
        st_l=STAGE_LABEL.get(s["stage"],"?")
        conf=s.get("conf",0); frac=s.get("frac",1.0)
        conf_s=f"{conf}x{frac:.1f}"
        rv=s.get("rsi",0)
        r_d=f"v{rv:.0f}" if rv<=30 else f"^{rv:.0f}" if rv>=70 else f"{rv:.0f}"
        sg=s["sg"]; sg_d="BUY" if sg=="BUY" else "SELL" if sg=="SELL" else "---"
        print(f"  {s['s']:<10} {st_l:<7} {tr_d:<5} {conf_s:<5} {r_d:<4} {sg_d:<7} {str(entry):>10} {pnl_f:>12}")
    print(f"\n  Market:")
    for s in sigs:
        if s.get("c"):
            ema_s=f"{s.get('e1','?')}/{s.get('e2','?')}"
            sl_s=f"{s.get('sl',0):.2f}" if isinstance(s.get('sl'),float) else "---"
            print(f"  {s['s']:<10} {s['c']:>9}  EMA:{ema_s:<14} SL:{sl_s}")
    if hist:
        print(f"\n  History:")
        for h in hist:
            pf_h=h["pnl"]
            pf_s=f"+Rp{pf_h:,}" if pf_h>=0 else f"Rp{pf_h:,}"
            rs="TP" if pf_h>0 else ("SL" if pf_h<0 else "---")
            print(f"  {h['s']:<10} {h['t']:<3} {h['p']:>10.2f} {pf_s:>12} {rs:<5} {h['tm']}")
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
    tp=0
    req={"action":mt5.TRADE_ACTION_DEAL,"symbol":sym,"volume":s.volume_min,"type":mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL,"price":price,"sl":sl,"tp":tp,"deviation":10,"magic":123456,"comment":"manual_I"}
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
