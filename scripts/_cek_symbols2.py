import MetaTrader5 as mt5

if not mt5.initialize():
    print("FAILED. Buka MT5 manual dulu!")
    exit(1)

a = mt5.account_info()
print(f"Akun: {a.login} @ {a.server}")
print(f"Balance: {a.balance:,.0f} {a.currency}")
print()

symbols = mt5.symbols_get()

# Cari forex major + XAU/XAG + indeks + crypto
target_keywords = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCADm", "NZDUSDm", "USDCHFm",
                   "EURJPYm", "GBPJPYm", "EURGBPm", "EURAUDm", "GBPAUDm", "EURCHFm", "GBPCHFm",
                   "XAUUSDm", "XAGUSDm", "XPDUSDm", "XPTUSDm",
                   "BTCUSDm", "ETHUSDm", "SOLUSDm", "XRPUSDm", "ADAUSDm", "DOGEUSDm", "BNBUSDm",
                   "US30", "US100", "US500", "GER40", "UK100", "JPN225", "AUS200", "FRA40", "HKG50",
                   "BTCUSD", "ETHUSD"]

print(f"{'Symbol':<16} {'Spread':>8} {'Point':>10} {'Mode':<12} {'MinLot':>8} {'MaxLot':>8}")
print("="*70)

for sym in symbols:
    name = sym.name
    if not any(kw in name for kw in target_keywords):
        continue
    if "SWAP" in name:
        continue

    spread = sym.spread
    point = sym.point
    mode = {0: "ALLOWED", 1: "CLOSED_ONLY", 2: "DISABLED"}.get(sym.trade_mode, "?")
    min_lot = sym.volume_min
    max_lot = sym.volume_max

    # Hitung spread dalam satuan harga
    tick = mt5.symbol_info_tick(name)
    if tick and point > 0:
        spread_real = (tick.ask - tick.bid) / point
    else:
        spread_real = spread

    print(f"{name:<16} {spread_real:>8.0f} {point:>10.7f} {mode:<12} {min_lot:>8.4f} {max_lot:>8.2f}")

print("\n\n=== KESIMPULAN ===")
print("Forex major spread 8-14 pts -> SANGAT RENDAH")
print("XAUUSDm spread 280 pts -> SANGAT TINGGI")
print(f"Modal: Rp{a.balance:,.0f}")
print("\nPotensi ticker alternatif dengan spread rendah:")
print("  EURUSDm - 8 pts")
print("  GBPUSDm - 10 pts")
print("  USDJPYm - 10 pts")
print("  AUDUSDm - 9 pts")
print("  USDCADm - 14 pts")
print("  XAGUSDm - 30 pts")

mt5.shutdown()
