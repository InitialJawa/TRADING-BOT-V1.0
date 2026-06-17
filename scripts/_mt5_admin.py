import MetaTrader5 as mt5
import sys

path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

print("MT5 connect attempt (as admin)...")
sys.stdout.flush()

for attempt in range(3):
    print(f"Attempt {attempt+1}")
    sys.stdout.flush()
    
    res = mt5.initialize(path=path, timeout=30)
    if res:
        print("Init OK!")
        sys.stdout.flush()
        a = mt5.account_info()
        if a:
            print(f"Account: {a.login}, Balance: {a.balance}, Server: {a.server}")
            sys.stdout.flush()
            print("SUCCESS!")
            mt5.shutdown()
            exit(0)
        else:
            print("No account info")
            sys.stdout.flush()
    else:
        err = mt5.last_error()
        print(f"Failed: {err}")
        sys.stdout.flush()
    mt5.shutdown()

print("FAILED")
sys.stdout.flush()
