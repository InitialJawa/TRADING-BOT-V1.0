# config/ — Ticker & Strategy Configuration

## Purpose
Per-ticker JSON configuration files for all strategy variants (a–h), ticker metadata, and aggregated best configs.

## Ownership
- Root `settings.json` — base MT5 login credentials
- `tickers/` — per-ticker metadata (spread, point value, modal capital, target profit, timeframes)
- `best/` — aggregated best configs for live trading
- Per-ticker dirs (`AUDUSDm/`, `XAUUSD/`, etc.) — strategy_a.json through strategy_h.json

## Local Contracts
- Edit per-ticker JSON to change strategy parameters (EMAs, RSI, ATR, lot_pct, trailing stop, risk rules)
- `XAUUSD/settings.json` is special: contains AI Manager config block + extra strategy_h.json
- `best/best_4_configs.json` drives the live bot's strategy selection

## Verification
Validate JSON: `python -c "import json; json.load(open('config/settings.json'))"`
