#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone

from src.state_manager import StateManager
from src.audit.system_audit import SystemAudit
from src.audit.risk_audit import RiskAudit
from src.audit.backtest_audit import BacktestAudit
from src.context_builder import ContextBuilder
from src.provider.opencode_cli import query as opencode_query, parse_json_response
from src.override_handler import OverrideHandler
from src.notification.telegram import TelegramNotifier


CONFIG_PATH = "config/settings.json"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[FATAL] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def run_cycle():
    config = load_config()
    cfg = config["ai_manager"]

    state = StateManager(cfg["paths"]["db"])

    system_audit = SystemAudit(state)
    risk_audit = RiskAudit(state)
    backtest_audit = BacktestAudit(state)

    context_builder = ContextBuilder(state, risk_audit, system_audit, backtest_audit)
    handler = OverrideHandler(state, cfg["paths"]["decision_log"])

    telegram = TelegramNotifier(
        bot_token=cfg["telegram"]["bot_token"],
        chat_id=cfg["telegram"]["chat_id"],
        error_log_path=cfg["paths"]["error_log"]
    )

    print("[CYCLE] Running audits...")
    sys_audit = system_audit.run_all()
    rsk_audit = risk_audit.run_all()
    bt_audit = backtest_audit.run_all()

    print("[CYCLE] Building context...")
    ctx = context_builder.build()

    ctx_json = json.dumps(ctx, separators=(",", ":"))

    print("[CYCLE] Querying AI via OpenCode CLI...")
    rules = "alert_only if normal, reduce_lot if DD>10% or lot>300, pause_strategy if Sharpe<0.1. FORBIDDEN: buy/sell/close/increase_lot"
    raw_output = opencode_query(rules, ctx_json)
    print(f"[CYCLE] Raw output: {raw_output[:200]}...")

    print("[CYCLE] Parsing decision...")
    decision = parse_json_response(raw_output)

    if decision.get("action") in ("error", "parse_error"):
        print(f"[CYCLE] Decision parsing failed: {decision.get('reason')}")
        telegram.send(f"<b>AI PARSE FAILED</b>\nOutput: {raw_output[:300]}")
        return {
            "status": "PARSE_FAILED",
            "raw": raw_output,
            "audits": {"system": sys_audit, "risk": rsk_audit, "backtest": bt_audit}
        }

    print(f"[CYCLE] Decision: {json.dumps(decision, indent=2)}")

    print("[CYCLE] Executing decision...")
    result = handler.execute(decision)

    if telegram.enabled:
        audit_has_issues = (
            sys_audit.get("vps_health", {}).get("status") != "OK" or
            sys_audit.get("mt5_connectivity", {}).get("connected") != True or
            rsk_audit.get("drawdown", {}).get("level") in ("WARNING", "CRITICAL") or
            bt_audit.get("level") in ("FAILED",)
        )
        if audit_has_issues or result["action"] != "alert_only":
            telegram.alert_decision({**decision, **result})
            if sys_audit.get("mt5_connectivity", {}).get("connected") != True:
                telegram.alert_mt5_disconnect()
            if rsk_audit.get("drawdown", {}).get("level") == "CRITICAL":
                dd = rsk_audit["drawdown"]["value"]
                telegram.alert_drawdown(dd, "CRITICAL")
            if bt_audit.get("level") == "FAILED":
                telegram.alert_backtest_failure(bt_audit.get("strategy", "unknown"))

    print(f"[CYCLE] Complete: {json.dumps(result, indent=2)}")
    return {
        "status": "COMPLETE",
        "provider": "opencode_cli",
        "decision": decision,
        "result": result,
        "audits": {"system": sys_audit, "risk": rsk_audit, "backtest": bt_audit}
    }


def main():
    print("=" * 50)
    print("AI Risk & Operations Manager")
    print(f"Start time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)
    try:
        result = run_cycle()
        print(f"\nFinal status: {result.get('status', 'UNKNOWN')}")
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted by user")
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
