from datetime import datetime, timezone


DRAWDOWN_WARNING = 5.0
DRAWDOWN_CRITICAL = 10.0
SHARPE_WARNING = 0.3
SHARPE_CRITICAL = 0.1


class RiskAudit:
    def __init__(self, state_manager):
        self.state = state_manager

    def run_all(self) -> dict:
        dd = self._check_drawdown()
        sharpe = self._check_sharpe()
        strategies = self._check_strategies()
        result = {
            "drawdown": dd,
            "sharpe": sharpe,
            "strategies": strategies,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        status = "OK"
        if dd["level"] == "CRITICAL" or sharpe["level"] == "CRITICAL":
            status = "CRITICAL"
        elif dd["level"] == "WARNING" or sharpe["level"] == "WARNING":
            status = "WARNING"
        self.state.log_audit("risk", status, result)
        return result

    def _check_drawdown(self) -> dict:
        dd = self.state.get_metric("portfolio_drawdown")
        if dd is None:
            return {"value": None, "level": "UNKNOWN", "message": "No drawdown data"}

        level = "OK"
        message = f"Drawdown {dd:.1f}% within normal range"
        if dd >= DRAWDOWN_CRITICAL:
            level = "CRITICAL"
            message = f"CRITICAL: Drawdown {dd:.1f}% exceeded {DRAWDOWN_CRITICAL}% threshold"
            self.state.log_error("risk", message, severity="CRITICAL")
        elif dd >= DRAWDOWN_WARNING:
            level = "WARNING"
            message = f"WARNING: Drawdown {dd:.1f}% approaching {DRAWDOWN_CRITICAL}% limit"

        return {"value": dd, "level": level, "message": message}

    def _check_sharpe(self) -> dict:
        sharpe = self.state.get_metric("rolling_sharpe_7d")
        if sharpe is None:
            return {"value": None, "level": "UNKNOWN", "message": "No Sharpe data"}

        level = "OK"
        message = f"Sharpe {sharpe:.2f} within acceptable range"
        if sharpe <= SHARPE_CRITICAL:
            level = "CRITICAL"
            message = f"CRITICAL: Sharpe {sharpe:.2f} below {SHARPE_CRITICAL} threshold"
            self.state.log_error("risk", message, severity="CRITICAL")
        elif sharpe <= SHARPE_WARNING:
            level = "WARNING"
            message = f"WARNING: Sharpe {sharpe:.2f} approaching {SHARPE_CRITICAL} floor"

        return {"value": sharpe, "level": level, "message": message}

    def _check_strategies(self) -> dict:
        strategies = self.state.get_strategies()
        paused = [k for k, v in strategies.items() if v != "ACTIVE"]
        return {
            "total": len(strategies),
            "active": len(strategies) - len(paused),
            "paused": paused,
            "details": strategies
        }
