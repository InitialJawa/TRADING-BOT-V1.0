import json
import os
from datetime import datetime, timezone


class OverrideHandler:
    def __init__(self, state_manager, decision_log_path: str = "data/decisions.log"):
        self.state = state_manager
        self.decision_log = decision_log_path
        os.makedirs(os.path.dirname(decision_log_path), exist_ok=True)

    def execute(self, decision: dict) -> dict:
        action = decision["action"]
        target = decision.get("target")
        value = decision.get("value")
        reason = decision.get("reason", "")

        result = {
            "action": action,
            "target": target,
            "value": value,
            "status": "EXECUTED",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if action == "alert_only":
            result["message"] = "Alert raised, no system changes"
            self.state.log_error("ai_manager", f"ALERT: {reason}", severity="INFO")

        elif action == "reduce_lot":
            if not target or value is None:
                result["status"] = "FAILED"
                result["message"] = "reduce_lot requires target and value"
            elif value <= 0:
                result["status"] = "REJECTED"
                result["message"] = "Lot reduction must be positive"
            else:
                current = self.state.get_metric(f"lot_{target}")
                new_lot = (current or 1.0) - value
                if new_lot < 0.01:
                    result["status"] = "REJECTED"
                    result["message"] = f"Resulting lot {new_lot:.2f} below minimum 0.01"
                else:
                    self.state.upsert_metric(f"lot_{target}", round(new_lot, 2))
                    result["message"] = f"Lot for {target} reduced by {value} to {new_lot:.2f}"

        elif action == "pause_strategy":
            if not target:
                result["status"] = "FAILED"
                result["message"] = "pause_strategy requires target strategy name"
            else:
                self.state.upsert_strategy(target, "PAUSED")
                result["message"] = f"Strategy {target} paused"

        self._log(result)
        self.state.log_decision(
            raw=json.dumps(decision),
            action=action,
            target=target,
            value=value,
            status=result["status"]
        )
        return result

    def _log(self, entry: dict):
        with open(self.decision_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
