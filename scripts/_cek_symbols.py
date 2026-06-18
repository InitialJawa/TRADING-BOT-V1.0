import MetaTrader5 as mt5
import sys

if not mt5.initialize():
    print("GAGAL init MT5. Buka MT5 manual dulu!")
    sys.exit(1)

a = mt5.account_info()
print(f"Account: {a.login} | {a.server} | Balance: {a.balance} {a.currency}")

# Cari semua simbol yang available
symbols = mt5.symbols_get()
print(f"\nTotal simbol tersedia: {len(symbols)}")

# Filter simbol yang umum untuk trading (forex, indeks, komoditas, crypto)
targets = []
for s in symbols:
    name = s.name
    # Skip yang aneh-aneh
    if any(x in name for x in ["SWAP", "CRUD", "NGAS", "Copper", "Aluminium", "Palladium", "Platinum", "Wheat", "Corn", "Sugar", "Soybean", "Cotton", "Coffee", "Cocoa", "LiveCow", "LeanHog", "Brent", "WTIOil", "VIX"]):
        continue
    # Ambil forex major, indeks, komoditas utama, crypto
    if any(x in name for x in ["EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "XAU", "XAG", "US30", "US100", "US500", "GER40", "UK100", "JPN225", "AUS200", "BTC", "ETH"]):
        if name.endswith("m") or name in ["US30Cash", "US100Cash", "US500Cash", "GER40Cash", "UK100Cash", "JPN225Cash", "AUS200Cash", "BTCUSD", "ETHUSD"]:
            targets.append(name)

# Prioritaskan yang paling menarik
prioritas = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCADm", "NZDUSDm", "USDCHFm",
             "EURJPYm", "GBPJPYm", "EURGBPm",
             "XAUUSDm", "XAGUSDm",
             "US30Cash", "US100Cash", "US500Cash", "GER40Cash", "UK100Cash", "JPN225Cash", "AUS200Cash",
             "BTCUSD", "ETHUSD"]

print(f"\n{'SYMBOL':<16} {'SPREAD':<8} {'POINT':<8} {'TRADE_MODE':<12} {'MIN_LOT':<8} {'MAX_LOT':<8} {'LEVERAGE':<10}")
print("="*80)

for sym in prioritas:
    if sym not in targets:
        continue
    info = mt5.symbol_info(sym)
    if info is None:
        continue
    spread = info.spread
    point = info.point
    trade_mode = ["ALLOWED" if info.trade_mode == 0 else "CLOSED_ONLY" if info.trade_mode == 2 else "DISABLED"][0]
    min_lot = info.volume_min
    max_lot = info.volume_max
    leverage = info.leverage if hasattr(info, 'leverage') else '-'
    print(f"{sym:<16} {spread:<8} {point:<8.6f} {trade_mode:<12} {min_lot:<8.4f} {max_lot:<8.2f} {leverage:<10}")

# Juga cek spread real-time (tanya tick)
print("\n\nSpread REAL-TIME (dari tick terakhir):")
print(f"{'SYMBOL':<16} {'BID':<10} {'ASK':<10} {'SPREAD_PTS':<12} {'SPREAD_USD':<12}")
print("="*60)
for sym in prioritas[:10]:
    if sym not in targets:
        continue
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        continue
    spread_pts = (tick.ask - tick.bid) / (mt5.symbol_info(sym).point if mt5.symbol_info(sym) else 1)
    spread_usd = (tick.ask - tick.bid) * 100000 if "JPY" not in sym else (tick.ask - tick.bid) * 1000
    print(f"{sym:<16} {tick.bid:<10.5f} {tick.ask:<10.5f} {spread_pts:<12.0f} {spread_usd:<12.2f}")

mt5.shutdown()
