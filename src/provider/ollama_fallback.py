import json
import os
import requests
from datetime import datetime, timezone


OLLAMA_SYSTEM_PROMPT = "You are AI Risk & Operations Manager. Return ONLY valid JSON. No explanation."


class OllamaFallback:
    def __init__(self, model: str = "qwen3:14b", endpoint: str = "http://localhost:11434/api/generate",
                 timeout: int = 120, error_log: str = "data/ai_errors.log"):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.error_log = error_log
        os.makedirs(os.path.dirname(error_log), exist_ok=True)

    def query(self, prompt: str) -> str | None:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": OLLAMA_SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9
            }
        }
        try:
            resp = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout
            )
            if resp.status_code != 200:
                self._log_error(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            output = data.get("response", "").strip()
            if not output:
                self._log_error("Ollama returned empty response")
                return None
            return output
        except requests.ConnectionError:
            self._log_error("Ollama connection refused. Is Ollama running?")
            return None
        except requests.Timeout:
            self._log_error(f"Ollama timed out after {self.timeout}s")
            return None
        except Exception as e:
            self._log_error(f"Ollama unexpected error: {e}")
            return None

    def is_available(self) -> bool:
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _log_error(self, message: str):
        with open(self.error_log, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] [ollama] {message}\n")
