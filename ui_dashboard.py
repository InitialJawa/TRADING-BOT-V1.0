import sys, os, json, time, threading, glob, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime
import MetaTrader5 as mt5

BASE_DIR = os.path.dirname(__file__)
BOT_SCRIPT = os.path.join(BASE_DIR, "scripts", "live_bot_4_ticker.py")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "live_bot.log")
os.makedirs(LOG_DIR, exist_ok=True)

bot_process = None
bot_running = False
positions_cache = []
account_cache = {}
last_refresh = None

TICKERS = ["XAGUSDm", "ETHUSDm", "BTCUSDTm", "JP225m"]
STRAT_LABEL = {"XAGUSDm":"D","ETHUSDm":"D","BTCUSDTm":"D","JP225m":"G"}

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def fetch_positions():
    global positions_cache, account_cache, last_refresh
    try:
        if not mt5.initialize():
            account_cache = {"error": "MT5 not connected"}
            return
        a = mt5.account_info()
        if a:
            account_cache = {"balance": a.balance, "equity": a.equity, "profit": a.profit}
        pos = mt5.positions_get()
        positions_cache = []
        if pos:
            for p in pos:
                held = (datetime.now() - datetime.fromtimestamp(p.time)).total_seconds() / 3600
                positions_cache.append({
                    "symbol": p.symbol, "type": "BUY" if p.type==0 else "SELL",
                    "volume": p.volume, "entry": p.price_open,
                    "sl": p.sl, "tp": p.tp, "profit": p.profit,
                    "held": held, "ticket": p.ticket
                })
        mt5.shutdown()
        last_refresh = datetime.now()
    except Exception as e:
        account_cache = {"error": str(e)}

def draw_border(text=""):
    w = 90
    if text:
        print(f"┌{'─'*(w-2)}┐")
        print(f"│ {text:<{w-3}}│")
        print(f"├{'─'*(w-2)}┤")
    else:
        print(f"┌{'─'*(w-2)}┐")

def draw_line():
    print(f"├{'─'*88}┤")

def draw_end():
    print(f"└{'─'*88}┘")

def draw():
    clear()
    w = 90
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"┌{'─'*88}┐")
    print(f"│{'':^88}│")
    print(f"│{'🤖 TRADING BOT — 4 TICKER UNGGULAN':^88}│")
    print(f"│{f'🕐 {now}':^88}│")
    print(f"│{'':^88}│")
    print(f"├{'─'*88}┤")
    
    # Account
    ac = account_cache
    if "error" in ac:
        print(f"│ ⚠️  {ac['error']:<83}│")
    else:
        bal = ac.get("balance", 0)
        eq = ac.get("equity", 0)
        pf = ac.get("profit", 0)
        pf_s = f"+Rp{pf:,.0f}" if pf >= 0 else f"Rp{pf:,.0f}"
        print(f"│ Balance: Rp{bal:>12,.0f}  │  Equity: Rp{eq:>12,.0f}  │  Floating: {pf_s:>15}  │")
    
    print(f"├{'─'*88}┤")
    
    # Positions
    print(f"│ {'Ticker':<10} {'Type':<5} {'Lots':<6} {'Entry':>10} {'SL':>10} {'TP':>10} {'Profit':>12} {'Held':>7} {'Strat':<6} │")
    print(f"├{'─'*88}┤")
    
    if not positions_cache:
        print(f"│ {'':^88}│")
        print(f"│ {'📭 TIDAK ADA POSISI TERBUKA':^88}│")
        print(f"│ {'':^88}│")
    else:
        for p in positions_cache:
            pf = p["profit"]
            pf_s = f"+Rp{pf:,.0f}" if pf >= 0 else f"Rp{pf:,.0f}"
            held_s = f"{p['held']:.1f}h" if p['held'] < 24 else f"{p['held']/24:.1f}d"
            strat = STRAT_LABEL.get(p["symbol"], "?")
            print(f"│ {p['symbol']:<10} {p['type']:<5} {p['volume']:<6.2f} {p['entry']:>10.2f} {p['sl']:>10.2f} {p['tp']:>10.2f} {pf_s:>12} {held_s:>7} {strat:<6} │")
    
    print(f"├{'─'*88}┤")
    total_pf = sum(p["profit"] for p in positions_cache)
    total_s = f"+Rp{total_pf:,.0f}" if total_pf >= 0 else f"Rp{total_pf:,.0f}"
    print(f"│ {'TOTAL':<10} {'':<5} {'':<6} {'':>10} {'':>10} {'':>10} {total_s:>12} {'':>7} {'':<6} │")
    
    if last_refresh:
        print(f"│ {'':<10} {'':<5} {'':<6} {'':>10} {'':>10} {'':>10} {'':>12} {'':>7} {'':<6} │")
        print(f"│ Last refresh: {last_refresh.strftime('%H:%M:%S')} {'':>59} │")
    
    print(f"├{'─'*88}┤")
    
    # Bot status
    bot_status = "🟢 RUNNING" if bot_running else "🔴 STOPPED"
    print(f"│ BOT: {bot_status:<82}│")
    print(f"├{'─'*88}┤")
    
    # Menu
    print(f"│ {'MENU':^88}│")
    print(f"├{'─'*88}┤")
    print(f"│  {'[1] Start Bot':<25} {'[2] Stop Bot':<25} {'[3] Refresh now':<25} │")
    print(f"│  {'[4] View Log':<25} {'[5] Close All':<25} {'[6] Open Manual':<25} │")
    print(f"│  {'[Q] Quit':<25} {'':<25} {'':<25} │")
    print(f"└{'─'*88}┘")
    print(f"\n  Pilih menu: ", end="", flush=True)

def start_bot():
    global bot_process, bot_running
    if bot_running:
        # Check if process is actually alive
        if bot_process and bot_process.poll() is None:
            print("\n  Bot already running!")
            time.sleep(1)
            return
        else:
            print("\n  Stale flag detected, resetting...")
            bot_running = False
            bot_process = None
    bot_process = subprocess.Popen(
        [sys.executable, BOT_SCRIPT],
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        cwd=BASE_DIR
    )
    bot_running = True
    print(f"\n  ✅ Bot started (PID: {bot_process.pid})")
    time.sleep(1.5)

def stop_bot():
    global bot_process, bot_running
    if not bot_running:
        print("\n  Bot not running!")
        time.sleep(1)
        return
    if bot_process:
        bot_process.terminate()
        bot_process.wait(timeout=5)
    bot_running = False
    print("\n  🛑 Bot stopped")
    time.sleep(1.5)

def close_all():
    if not mt5.initialize():
        print("\n  MT5 not connected")
        time.sleep(1)
        return
    pos = mt5.positions_get()
    if not pos:
        print("\n  No positions to close")
        mt5.shutdown()
        time.sleep(1)
        return
    closed = 0
    for p in pos:
        close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        price = tick.bid if p.type == 0 else tick.ask
        req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":p.symbol,"volume":p.volume,
               "type":close_type,"position":p.ticket,"price":price,
               "deviation":10,"magic":p.magic,"comment":"manual_close",
               "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req)
        if r.retcode == 10009:
            closed += 1
    mt5.shutdown()
    print(f"\n  ✅ Closed {closed} positions")
    time.sleep(1.5)
    fetch_positions()

def open_manual():
    print("\n\n  ── OPEN MANUAL POSITION ──")
    print("  Ticker:")
    for i, t in enumerate(TICKERS):
        print(f"    [{i+1}] {t}")
    t_idx = input("  Pilih [1-4]: ").strip()
    if not t_idx.isdigit() or int(t_idx) < 1 or int(t_idx) > 4:
        return
    sym = TICKERS[int(t_idx)-1]
    side = input("  [1] BUY  [2] SELL: ").strip()
    if side not in ("1","2"):
        return
    is_buy = side == "1"
    
    if not mt5.initialize():
        print("  MT5 not connected")
        time.sleep(1)
        return
    mt5.symbol_select(sym, True)
    s = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    vol = s.volume_min
    price = tick.ask if is_buy else tick.bid
    sl = price - s.point * 1000 if is_buy else price + s.point * 1000
    tp = price + s.point * 3000 if is_buy else price - s.point * 3000
    
    req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":sym,"volume":vol,
           "type":mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
           "price":price,"sl":sl,"tp":tp,"deviation":10,
           "magic":123456,"comment":"manual","type_time":mt5.ORDER_TIME_GTC,
           "type_filling":mt5.ORDER_FILLING_IOC}
    r = mt5.order_send(req)
    mt5.shutdown()
    if r.retcode == 10009:
        print(f"  ✅ {sym} {'BUY' if is_buy else 'SELL'} opened!")
    else:
        print(f"  ❌ Failed: {r.comment}")
    time.sleep(2)
    fetch_positions()

def view_log():
    clear()
    print(f"\n{'='*90}")
    print(f"  LAST 50 LINES — {LOG_FILE}")
    print(f"{'='*90}\n")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            lines = f.readlines()
            for line in lines[-50:]:
                print(line.rstrip())
    else:
        print("  (log file not yet created)")
    print(f"\n{'='*90}")
    input("\n  Press Enter to return...")
    clear()

fetch_positions()

while True:
    draw()
    key = input().strip().upper()
    
    if key == "1":
        start_bot()
    elif key == "2":
        stop_bot()
    elif key == "3":
        fetch_positions()
    elif key == "4":
        view_log()
    elif key == "5":
        close_all()
        fetch_positions()
    elif key == "6":
        open_manual()
    elif key == "Q":
        if bot_running:
            stop_bot()
        clear()
        print("👋 Bye!")
        break
