import json
from datetime import datetime, timezone


class ContextBuilder:
    def __init__(self, state_manager, risk_audit, system_audit, backtest_audit):
        self.state = state_manager
        self.risk = risk_audit
        self.system = system_audit
        self.backtest = backtest_audit

    def build(self) -> dict:
        dd = self.state.get_metric("portfolio_drawdown") or 0.0
        sharpe = self.state.get_metric("rolling_sharpe_7d") or 0.0
        strategies = self.state.get_strategies()
        mt5 = self.system._check_mt5()
        hb = self.system._check_heartbeat()
        errors = self.state.get_recent_errors(5)
        bt = self.state.get_last_backtest()

        return {
            "portfolio_drawdown": round(dd, 2),
            "rolling_sharpe_7d": round(sharpe, 2),
            "strategy_status": strategies,
            "mt5_connection": mt5.get("connected", False),
            "heartbeat_status": hb.get("status", "UNKNOWN"),
            "recent_errors": [e["message"] for e in errors],
            "backtest_status": bt["result"] if bt else "UNKNOWN",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def build_prompt(self) -> str:
        ctx = self.build()
        return f"""You are AI Risk & Operations Manager for an MT5 trading system.

Analyze the current system state and return ONLY valid JSON (no markdown, no explanation).

System State:
{json.dumps(ctx, indent=2)}

Allowed actions:
- alert_only (no system changes needed)
- reduce_lot (reduce lot size on a symbol)
- pause_strategy (pause a specific strategy)

Rules:
- You MUST NOT suggest BUY, SELL, or CLOSE_POSITION
- You MUST NOT increase lot size or leverage
- You MUST NOT disable drawdown protection
- If everything is normal, return alert_only
- If drawdown > 10%, reduce_lot on affected symbols
- If Sharpe < 0.1 or backtest fails, pause_strategy
- If MT5 is disconnected or heartbeat stale, alert_only + escalate

Return format:
{{"action": "<action>", "target": "<symbol or strategy or null>", "value": <number or null>, "reason": "<brief reason>"}}"""
