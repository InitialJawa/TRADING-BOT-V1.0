# strategies/ — Strategy Implementation Modules

## Purpose
Reusable strategy logic: technical indicators, stage analysis, confidence scoring, and backtesting engine shared across the project.

## Ownership
- `shared/indicators.py` — EMA, SMA, ATR, RSI, MACD, BB calculations
- `shared/stage_analysis.py` — Stage analysis (accumulation/trend/distribution), confidence scoring, backtesting engine, metrics calculation
- `xauusd/` — per-strategy implementations for XAUUSD (strategy_d_h1 through strategy_h_h1)

## Local Contracts
- Indicator functions are pure; no MT5 dependency in shared code
- Stage analysis returns: stage, confidence, trend direction, entry signals
- Backtest engine in `stage_analysis.py` works with OHLCV dataframes

## Verification
`python -c "from strategies.shared.indicators import *; print('OK')"`
