import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.state_manager import StateManager
from src.audit.system_audit import SystemAudit
from src.audit.risk_audit import RiskAudit
from src.audit.backtest_audit import BacktestAudit
from src.context_builder import ContextBuilder
from src.decision_parser import DecisionParser
from src.override_handler import OverrideHandler
from datetime import datetime, timezone
import json

state = StateManager("data/test_backtest_flow.db")

state.upsert_metric("portfolio_drawdown", 3.2)
state.upsert_metric("rolling_sharpe_7d", 0.45)
state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
state.upsert_strategy("adaptive", "ACTIVE")
state.upsert_strategy("trend_re", "ACTIVE")
state.log_backtest("trend_re", "FAILED", {"profit": -1200, "trades": 8, "reason": "max_drawdown_exceeded", "max_dd": 22.5})

system_audit = SystemAudit(state)
risk_audit = RiskAudit(state)
backtest_audit = BacktestAudit(state)
context_builder = ContextBuilder(state, risk_audit, system_audit, backtest_audit)
parser = DecisionParser("data/test_bt_errors.log")
handler = OverrideHandler(state, "data/test_bt_decisions.log")

print("=== SYSTEM AUDIT ===")
sa = system_audit.run_all()
print(f'  VPS: {sa["vps_health"]["status"]}')
print(f'  MT5: {sa["mt5_connectivity"]["status"]}')
print(f'  HB:   {sa["heartbeat_status"]["status"]}')

print("\n=== RISK AUDIT ===")
ra = risk_audit.run_all()
print(f'  Drawdown: {ra["drawdown"]["value"]}% [{ra["drawdown"]["level"]}]')
print(f'  Sharpe:   {ra["sharpe"]["value"]} [{ra["sharpe"]["level"]}]')
print(f'  Strategies: {json.dumps(ra["strategies"], indent=4)}')

print("\n=== BACKTEST AUDIT ===")
ba = backtest_audit.run_all()
print(f'  Result: {ba["status"]} [{ba["level"]}]')
print(f'  Reason: {ba["details"].get("reason", "N/A")}')
print(f'  Max DD: {ba["details"].get("max_dd", "N/A")}%')

print("\n=== CONTEXT BUILDER (AI Input) ===")
ctx = context_builder.build()
for k, v in ctx.items():
    print(f'  {k}: {v}')

print("\n=== SIMULATED AI: backtest FAILED -> pause trend_re ===")
sim = '{"action": "pause_strategy", "target": "trend_re", "value": null, "reason": "Backtest FAILED for trend_re: max_drawdown 22.5% exceeded limit"}'
print(f'  Input: {sim}')
dec = parser.parse(sim)
print(f'  Parsed: {json.dumps(dec, indent=2)}')
res = handler.execute(dec)
print(f'  Result: {res["status"]} -- {res["message"]}')

print("\n=== SIMULATED AI: normal scenario (alert_only) ===")
sim2 = '{"action": "alert_only", "target": null, "value": null, "reason": "All systems normal, drawdown 3.2% within range"}'
dec2 = parser.parse(sim2)
res2 = handler.execute(dec2)
print(f'  Action: {res2["action"]} -- {res2["message"]}')

print("\n=== FINAL STRATEGY STATUS ===")
print(f'  {json.dumps(state.get_strategies(), indent=2)}')

print("\n=== AUDIT LOG ===")
import sqlite3
conn = sqlite3.connect("data/test_backtest_flow.db")
conn.row_factory = sqlite3.Row
for row in conn.execute("SELECT audit_type, status, details FROM audit_log ORDER BY id"):
    print(f'  [{row[0]}] {row[1]} | {row[2][:80]}')
conn.close()

print("\n=== ALL BACKTEST TESTS PASSED ===")
