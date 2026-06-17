import subprocess
import json
import os
from datetime import datetime, timezone


class GeminiCLI:
    def __init__(self, command: str = "gemini", timeout: int = 60, error_log: str = "data/ai_errors.log"):
        self.command = command
        self.timeout = timeout
        self.error_log = error_log
        os.makedirs(os.path.dirname(error_log), exist_ok=True)

    def query(self, prompt: str) -> str | None:
        try:
            result = subprocess.run(
                [self.command],
                input=prompt.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout
            )
            if result.returncode != 0:
                err = result.stderr.decode("utf-8", errors="replace")[:500]
                self._log_error(f"Gemini CLI error (code {result.returncode}): {err}")
                return None
            output = result.stdout.decode("utf-8", errors="replace").strip()
            if not output:
                self._log_error("Gemini CLI returned empty output")
                return None
            return output
        except FileNotFoundError:
            self._log_error("Gemini CLI not found. Is it installed?")
            return None
        except subprocess.TimeoutExpired:
            self._log_error(f"Gemini CLI timed out after {self.timeout}s")
            return None
        except Exception as e:
            self._log_error(f"Gemini CLI unexpected error: {e}")
            return None

    def is_available(self) -> bool:
        try:
            result = subprocess.run([self.command, "--version"], capture_output=True, timeout=10)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        except Exception:
            return False

    def _log_error(self, message: str):
        with open(self.error_log, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] [gemini_cli] {message}\n")
