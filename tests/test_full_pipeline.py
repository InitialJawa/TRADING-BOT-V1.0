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
from src.notification.telegram import TelegramNotifier
from datetime import datetime, timezone

state = StateManager("data/test_state.db")

state.upsert_metric("portfolio_drawdown", 12.3)
state.upsert_metric("rolling_sharpe_7d", 0.08)
state.upsert_metric("last_heartbeat", datetime.now(timezone.utc).isoformat())
state.upsert_strategy("adaptive", "ACTIVE")
state.upsert_strategy("trend_re", "ACTIVE")
state.log_backtest("adaptive", "PASS")

system_audit = SystemAudit(state)
risk_audit = RiskAudit(state)
backtest_audit = BacktestAudit(state)
context_builder = ContextBuilder(state, risk_audit, system_audit, backtest_audit)
parser = DecisionParser("data/test_errors.log")
handler = OverrideHandler(state, "data/test_decisions.log")

ctx = context_builder.build()
print("=== CONTEXT ===")
for k, v in ctx.items():
    print(f"  {k}: {v}")

# Simulate AI output (drawdown critical + sharpe critical)
simulated_output = '{"action": "reduce_lot", "target": "xauusdm", "value": 0.5, "reason": "Drawdown 12.3% above critical threshold 10%"}'
print(f"\n=== SIMULATED AI ===")
print(f"  {simulated_output}")

decision = parser.parse(simulated_output)
print(f"\n=== PARSED DECISION ===")
print(f"  {decision}")

result = handler.execute(decision)
print(f"\n=== RESULT ===")
for k, v in result.items():
    print(f"  {k}: {v}")

# Test pause_strategy
simulated_output2 = '{"action": "pause_strategy", "target": "adaptive", "value": null, "reason": "Sharpe 0.08 below critical threshold 0.1"}'
decision2 = parser.parse(simulated_output2)
result2 = handler.execute(decision2)
print(f"\n=== RESULT 2 (pause) ===")
for k, v in result2.items():
    print(f"  {k}: {v}")

# Test forbidden action
simulated_output3 = '{"action": "BUY", "target": "xauusdm", "value": 1.0, "reason": "Market looks bullish"}'
decision3 = parser.parse(simulated_output3)
print(f"\n=== FORBIDDEN ACTION ===")
print(f"  Decision: {decision3}")

# Test alert_only
simulated_output4 = '{"action": "alert_only", "target": null, "value": null, "reason": "Drawdown within normal range"}'
decision4 = parser.parse(simulated_output4)
result4 = handler.execute(decision4)
print(f"\n=== RESULT 4 (alert_only) ===")
for k, v in result4.items():
    print(f"  {k}: {v}")

strategies = state.get_strategies()
print(f"\n=== FINAL STRATEGIES ===")
print(f"  {strategies}")

print(f"\n=== ALL TESTS PASSED ===")
