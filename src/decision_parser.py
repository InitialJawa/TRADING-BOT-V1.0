import json
import re
import os
from datetime import datetime, timezone

ALLOWED_ACTIONS = {"alert_only", "reduce_lot", "pause_strategy"}
FORBIDDEN_PATTERNS = ["BUY", "SELL", "CLOSE_POSITION", "increase_lot", "increase_leverage"]


class DecisionParser:
    def __init__(self, error_log_path: str = "data/ai_errors.log"):
        self.error_log = error_log_path
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

    def parse(self, raw_output: str) -> dict | None:
        json_obj = self._extract_json(raw_output)
        if json_obj is None:
            self._log_error(f"Failed to parse JSON from output: {raw_output[:200]}")
            return None

        action = json_obj.get("action", "")
        if action not in ALLOWED_ACTIONS:
            self._log_error(f"Forbidden or unknown action: {action}")
            return None

        for pat in FORBIDDEN_PATTERNS:
            if pat.lower() in raw_output.lower():
                self._log_error(f"Output contains forbidden pattern '{pat}'")
                return None

        return {
            "action": action,
            "target": json_obj.get("target"),
            "value": json_obj.get("value"),
            "reason": json_obj.get("reason", ""),
        }

    def _extract_json(self, text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _log_error(self, message: str):
        with open(self.error_log, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")
