import MetaTrader5 as mt5
import os, time, subprocess

path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
data_path = r"C:\Users\Bedil Gaib\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"

print("1. Starting MT5 terminal...")
proc = subprocess.Popen([path])
print(f"   PID: {proc.pid}")
time.sleep(30)

print("2. Attempting connection...")
for attempt in range(5):
    print(f"   Attempt {attempt+1}...")
    try:
        if mt5.initialize(path=path, timeout=30):
            a = mt5.account_info()
            if a and a.login > 0:
                print(f"   >>> SUCCESS! Account: {a.login}, Balance: {a.balance}")
                print(f"   >>> Server: {a.server}")
                mt5.shutdown()
                # Try getting data
                print("3. Fetching XAUUSD H1 data...")
                if mt5.initialize(path=path, timeout=30):
                    rates = mt5.copy_rates_from_pos("XAUUSDm", mt5.TIMEFRAME_H1, 0, 100)
                    if rates is not None:
                        print(f"   Got {len(rates)} bars!")
                    else:
                        print(f"   No data: {mt5.last_error()}")
                    mt5.shutdown()
                exit(0)
            else:
                print(f"   Connected, no account: {a}")
        else:
            err = mt5.last_error()
            print(f"   Failed: {err}")
    except Exception as e:
        print(f"   Error: {e}")
    finally:
        mt5.shutdown()
    time.sleep(5)

print("FAILED: Could not connect")
