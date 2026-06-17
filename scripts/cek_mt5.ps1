python -c @"
import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    print(f'MT5 initialize FAILED: {mt5.last_error()}')
    exit()

print(f'MT5 version: {mt5.version()}')
print(f'Account: {mt5.account_info().login}')
print(f'Balance: {mt5.account_info().balance}')
print(f'Server: {mt5.account_info().server}')

symbols = mt5.symbols_get()
xau = [s for s in symbols if 'XAU' in s.name]
print(f'\nGold symbols found: {[s.name for s in xau]}')

if xau:
    print(f'\n--- {xau[0].name} info ---')
    s = xau[0]
    print(f'  Spread: {s.spread}')
    print(f'  Digits: {s.digits}')
    print(f'  Trade mode: {s.trade_mode}')

rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_D1, 0, 50)
if rates is not None:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print(f'\n--- XAUUSD Daily (last 50 bars) ---')
    print(df[['time','open','high','low','close','tick_volume']].tail(10).to_string(index=False))

mt5.shutdown()
"@