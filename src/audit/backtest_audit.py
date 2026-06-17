from datetime import datetime, timezone


class BacktestAudit:
    def __init__(self, state_manager):
        self.state = state_manager

    def run_all(self) -> dict:
        last = self.state.get_last_backtest()
        if last is None:
            return {"status": "UNKNOWN", "message": "No backtest results found"}

        result = {
            "status": last["result"],
            "strategy": last["strategy"],
            "details": last.get("details", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        level = "OK"
        message = f"Backtest {last['result']} for {last['strategy']}"
        if last["result"] != "PASS":
            level = "FAILED"
            message = f"FAILED: Backtest {last['result']} for {last['strategy']}"
            self.state.log_error("backtest", message, severity="CRITICAL")

        result["level"] = level
        result["message"] = message
        self.state.log_audit("backtest", level, result)
        return result
