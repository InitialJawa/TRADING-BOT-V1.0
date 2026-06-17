import MetaTrader5 as mt5
import time
import sys

path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Wait a bit for terminal to be ready
print(f"Terminal PID: {5556}")  # known from earlier check
print("Waiting 10s for terminal to sync...")
sys.stdout.flush()
time.sleep(10)

print("1. init with path...")
sys.stdout.flush()
if mt5.initialize(path=path, timeout=30):
    print("   Init OK!")
    sys.stdout.flush()
    a = mt5.account_info()
    if a:
        print(f"   Account: {a.login}, Server: {a.server}, Balance: {a.balance}")
        sys.stdout.flush()
    else:
        print("   No account info")
        sys.stdout.flush()
    ti = mt5.terminal_info()
    if ti:
        print(f"   Terminal: {ti.name}, DataPath: {ti.data_path}")
        sys.stdout.flush()
    mt5.shutdown()
    print("SUCCESS!")
    sys.stdout.flush()
    exit(0)
else:
    err = mt5.last_error()
    print(f"   Init failed: {err}")
    sys.stdout.flush()
    mt5.shutdown()

print("2. init with login...")
sys.stdout.flush()
if mt5.initialize(path=path, login=413889745, password="jatenggayeng", timeout=30):
    print("   Init OK!")
    sys.stdout.flush()
else:
    print(f"   Failed: {mt5.last_error()}")
    sys.stdout.flush()
    mt5.shutdown()

print("3. init without path...")
sys.stdout.flush()
if mt5.initialize(timeout=30):
    print("   Init OK!")
    sys.stdout.flush()
    a = mt5.account_info()
    if a:
        print(f"   Account: {a.login}")
    mt5.shutdown()
    exit(0)
else:
    print(f"   Failed: {mt5.last_error()}")
    sys.stdout.flush()
    mt5.shutdown()

print("\nFAILED all attempts")
