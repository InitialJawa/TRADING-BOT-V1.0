import subprocess
import platform
import socket
from datetime import datetime, timezone


class SystemAudit:
    def __init__(self, state_manager):
        self.state = state_manager

    def run_all(self) -> dict:
        result = {
            "vps_health": self._check_vps_health(),
            "mt5_connectivity": self._check_mt5(),
            "heartbeat_status": self._check_heartbeat(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.state.log_audit("system", result["vps_health"]["status"], result)
        return result

    def _check_vps_health(self) -> dict:
        try:
            load = psutil_get_load() if has_psutil() else {"cpu": 0, "memory": 0, "disk": 0}
            status = "OK"
            if load.get("cpu", 0) > 90:
                status = "WARNING"
            if load.get("memory", 0) > 90:
                status = "WARNING"
            return {"status": status, "cpu_pct": load.get("cpu", 0), "memory_pct": load.get("memory", 0), "disk_pct": load.get("disk", 0)}
        except Exception as e:
            self.state.log_error("system_audit", f"VPS health check failed: {e}")
            return {"status": "ERROR", "error": str(e)}

    def _check_mt5(self) -> dict:
        try:
            import socket
            host = "127.0.0.1"
            port = 15555
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            connected = result == 0
            if not connected:
                self.state.log_error("mt5", "MT5 connection failed")
            return {"connected": connected, "status": "OK" if connected else "DISCONNECTED"}
        except Exception as e:
            self.state.log_error("mt5", f"MT5 check error: {e}")
            return {"connected": False, "status": "ERROR", "error": str(e)}

    def _check_heartbeat(self) -> dict:
        last = self.state.get_metric("last_heartbeat")
        if last is None:
            return {"status": "UNKNOWN"}
        try:
            last_time = datetime.fromisoformat(last)
            delta = (datetime.now(timezone.utc) - last_time).total_seconds()
            if delta > 3600:
                self.state.log_error("heartbeat", f"Heartbeat stale: {delta:.0f}s ago", severity="WARNING")
                return {"status": "STALE", "age_seconds": delta}
            return {"status": "OK", "age_seconds": delta}
        except Exception:
            return {"status": "UNKNOWN"}


def has_psutil():
    try:
        import psutil
        return True
    except ImportError:
        return False


def psutil_get_load() -> dict:
    import psutil
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent
    }
