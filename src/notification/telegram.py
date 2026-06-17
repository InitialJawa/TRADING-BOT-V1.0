import json
import os
import requests
from datetime import datetime, timezone


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = "", error_log_path: str = "data/ai_errors.log"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.error_log = error_log_path
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled:
            self._log_error("Telegram disabled: no bot_token or chat_id configured")
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                self._log_error(f"Telegram API error {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except requests.RequestException as e:
            self._log_error(f"Telegram request failed: {e}")
            return False

    def alert_drawdown(self, value: float, level: str):
        self.send(f"<b>DRAWDOWN {level}</b>\nValue: {value:.1f}%\nAction required.")

    def alert_mt5_disconnect(self):
        self.send("<b>MT5 DISCONNECTED</b>\nMT5 connection lost. Immediate attention needed.")

    def alert_backtest_failure(self, strategy: str):
        self.send(f"<b>BACKTEST FAILED</b>\nStrategy: {strategy}\nReview required.")

    def alert_heartbeat(self, status: str):
        self.send(f"<b>HEARTBEAT {status}</b>\nSystem heartbeat abnormal.")

    def alert_decision(self, decision: dict):
        msg = f"<b>AI Decision: {decision.get('action', 'UNKNOWN')}</b>\n"
        if decision.get("target"):
            msg += f"Target: {decision['target']}\n"
        if decision.get("value"):
            msg += f"Value: {decision['value']}\n"
        if decision.get("reason"):
            msg += f"Reason: {decision['reason']}\n"
        msg += f"Status: {decision.get('status', 'UNKNOWN')}"
        self.send(msg)

    def _log_error(self, message: str):
        with open(self.error_log, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")
