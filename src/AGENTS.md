# src/ — AI Risk & Operations Manager

## Purpose
Core application source for the AI-driven risk management and strategy oversight pipeline. Runs a cycle of audit → context → AI debate → decision → override → notification.

## Ownership
- `main.py` — cycle orchestrator, entry point
- `state_manager.py` — SQLite state (data/state.db) CRUD
- `context_builder.py` — assembles system state context for AI
- `decision_parser.py` — validates AI output, enforces safety whitelist
- `override_handler.py` — executes AI commands (reduce lot, pause, alert)
- `agent_ipc.py` — file-based 2-AI debate system

### Subdirectories
- `audit/` — SystemAudit, RiskAudit, BacktestAudit engines
- `provider/` — AI provider layer (OpenCode CLI, Gemini CLI, Ollama fallback, OpenCode proxy)
- `notification/` — Telegram alert sender
- `prompts/` — AI system prompt templates

## Local Contracts
- `main.py` runs the full cycle: run audits → build context → AI debate → parse → execute → notify
- DecisionParser rejects: BUY, SELL, CLOSE, leverage increase, stop loss/take profit modification
- Allowed actions: `alert_only`, `reduce_lot`, `pause_strategy`
- Primary AI provider is OpenCode CLI (Gemini), fallback is Ollama
- State DB location: `data/state.db`

## Verification
Run: `python -m src.main` (dry-run safe with config)

## Child DOX Index
- `audit/` — 3 audit modules for system/risk/backtest health
- `provider/` — multi-provider AI abstraction layer
- `notification/` — Telegram integration
- `prompts/` — AI system prompt for risk manager role
