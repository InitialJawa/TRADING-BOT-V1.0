import MetaTrader5 as mt5
import time
import sys

print("Attempting MT5 init with 60s timeout...")
sys.stdout.flush()

if mt5.initialize(timeout=60):
    print("Init SUCCESS!")
    sys.stdout.flush()
    
    ti = mt5.terminal_info()
    if ti:
        print(f"Terminal: {ti.name}, {ti.community_account}")
    sys.stdout.flush()
    
    a = mt5.account_info()
    if a:
        print(f"Account: {a.login}")
        print(f"Balance: {a.balance}")
        print(f"Server:  {a.server}")
        print(f"Name:    {a.name}")
    else:
        print("No account info - trying login...")
        sys.stdout.flush()
        if mt5.login(413889745, password="jatenggayeng"):
            a = mt5.account_info()
            print(f"After login - Account: {a.login}, Balance: {a.balance}")
        else:
            print(f"Login failed: {mt5.last_error()}")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"Init FAILED: {err}")
    mt5.shutdown()
    sys.exit(1)

print("DONE")
