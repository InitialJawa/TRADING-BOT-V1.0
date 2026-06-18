import MetaTrader5 as mt5

if not mt5.initialize():
    print("GAGAL"); exit(1)

# Cek semua simbol forex (dengan dan tanpa 'm')
symbols = mt5.symbols_get()

# Kelompokkan: forex major non-m vs m
non_m = []
m_suffix = []
for s in symbols:
    name = s.name
    if name in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
                 "EURJPY", "GBPJPY", "EURGBP", "US30", "US100", "US500", "GER40", "UK100", "JPN225"]:
        non_m.append(name)
    if name in ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCADm", "NZDUSDm", "USDCHFm",
                 "EURJPYm", "GBPJPYm", "EURGBPm", "XAUUSDm", "XAGUSDm", "US30m", "US500m"]:
        m_suffix.append(name)

print("=== SIMBOL NON-m (reguler) ===")
for sym in non_m:
    info = mt5.symbol_info(sym)
    if info:
        print(f"  {sym:<12} spread={info.spread} trade_mode={info.trade_mode}")
    else:
        print(f"  {sym:<12} -> TIDAK ADA")

print("\n=== SIMBOL m (mini) ===")
for sym in m_suffix:
    info = mt5.symbol_info(sym)
    if info:
        print(f"  {sym:<12} spread={info.spread} trade_mode={info.trade_mode}")
    else:
        print(f"  {sym:<12} -> TIDAK ADA")

# Cek jumlah data history yang tersedia
print("\n\n=== DATA HISTORY ===")
test_symbols = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "US30m",
                "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "US30Cash", "US30"]

for sym in test_symbols:
    info = mt5.symbol_info(sym)
    if not info:
        continue
    # Cek M15
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 10000)
    if rates is not None and len(rates) > 0:
        from datetime import datetime
        t0 = datetime.utcfromtimestamp(rates[0]['time']).date()
        t1 = datetime.utcfromtimestamp(rates[-1]['time']).date()
        days = (t1 - t0).days
        print(f"  {sym:<12} M15: {len(rates):>5} bars ({t0} sd {t1}, {days} hr)")
    else:
        print(f"  {sym:<12} M15: NO DATA")

    # Cek H1
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 5000)
    if rates is not None and len(rates) > 0:
        t0 = datetime.utcfromtimestamp(rates[0]['time']).date()
        t1 = datetime.utcfromtimestamp(rates[-1]['time']).date()
        days = (t1 - t0).days
        print(f"  {sym:<12} H1:  {len(rates):>5} bars ({t0} sd {t1}, {days} hr)")
    else:
        print(f"  {sym:<12} H1: NO DATA")

mt5.shutdown()
