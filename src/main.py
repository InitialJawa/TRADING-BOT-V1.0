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
from src.provider.ollama_fallback import OllamaFallback
from src.provider.gemini_cli import GeminiCLI
from src.agent_ipc import init_chat, add_message, build_debate_context, is_finished, increment_round, get_conversation_summary
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

    ACTION_PRIORITY = {"pause_strategy": 3, "reduce_lot": 2, "alert_only": 1}
    MAX_DEBATE_ROUNDS = 2

    # === Provider fallback chain ===
    ollama = OllamaFallback()
    gemini_cli = GeminiCLI()
    provider_used = {"ai1": "opencode_cli", "ai2": "opencode_cli"}

    def _is_rate_limit(raw: str) -> bool:
        indicators = ["429", "rate limit", "too many requests", "quota", "limit reached", "resource exhausted", "model overloaded"]
        lower = raw.lower()
        return any(i in lower for i in indicators)

    def _query_with_fallback(prompt: str, ctx: str, ai_label: str) -> str:
        nonlocal provider_used
        raw = opencode_query(prompt, ctx)
        if raw and not _is_rate_limit(raw):
            provider_used[ai_label] = "opencode_cli"
            return raw

        print(f"[CYCLE] Opencode rate limit for {ai_label}, falling back to Ollama...")
        ollama_raw = ollama.query(f"{prompt}\n\nContext: {ctx}")
        if ollama_raw:
            provider_used[ai_label] = "ollama"
            return ollama_raw

        print(f"[CYCLE] Ollama unavailable for {ai_label}, falling back to Gemini CLI...")
        gemini_raw = gemini_cli.query(f"{prompt}\n\nContext: {ctx}")
        if gemini_raw:
            provider_used[ai_label] = "gemini_cli"
            return gemini_raw

        print(f"[CYCLE] All providers failed for {ai_label}, returning alert_only")
        return json.dumps({"action": "alert_only", "reason": f"All AI providers unavailable for {ai_label}"})

    def agent_prompt(agent_name, role_desc, rules):
        return f"""You are {agent_name} — {role_desc}

=== RULES ===
{rules}

=== COMMUNICATION ===
You share a chat file with AI-2. Read the debate log, then respond.

Write your message in this EXACT format:
MSG_TO_AI2: <your argument for AI-2 to read>

After your message, output your decision as JSON:
FINAL_ACTION: {{"action":"<action>", "target":"<symbol>", "value":<number>, "reason":"<reason>"}}

Allowed actions: alert_only, reduce_lot, pause_strategy
FORBIDDEN: buy, sell, close, increase_lot, increase_leverage
"""

    def query_ai1(ctx_str, round_num):
        prompt = agent_prompt("AI-1 (Risk Manager)", "conservative — prioritaskan safety, minimalisir drawdown, jaga modal", "alert_only if normal, reduce_lot if DD>10% or lot>300, pause_strategy if Sharpe<0.1")
        full = f"{prompt}\n\nContext: {ctx_str}\n\nDebate round #{round_num}. Berikan argumen dan keputusanmu."
        raw = _query_with_fallback(full, "", "ai1")
        msg = extract_message(raw)
        if msg:
            add_message("AI-1", "AI-2", msg, round_num)
        return raw

    def query_ai2(ctx_str, round_num):
        prompt = agent_prompt("AI-2 (Strategy Advisor)", "optimis — fokus pada performa strategi, peluang market, jangan pause kecuali darurat", "alert_only if normal, reduce_lot only if DD>15%, pause_strategy only if Sharpe<0.05 OR backtest failed")
        chat_log = get_conversation_summary()
        full = f"{prompt}\n\nContext: {ctx_str}\n\nDebate Log:\n{chat_log}\n\nDebate round #{round_num}. Baca argumen AI-1, berikan counter-argumen dan keputusanmu."
        raw = _query_with_fallback(full, "", "ai2")
        msg = extract_message(raw)
        if msg:
            add_message("AI-2", "AI-1", msg, round_num)
        return raw

    def extract_message(raw):
        for line in raw.split("\n"):
            if line.startswith("MSG_TO_AI2:"):
                return line[len("MSG_TO_AI2:"):].strip()
        return ""

    def extract_final_action(raw):
        for line in raw.split("\n"):
            if line.startswith("FINAL_ACTION:"):
                return parse_json_response(line[len("FINAL_ACTION:"):].strip())
        return parse_json_response(raw)

    init_chat(MAX_DEBATE_ROUNDS)

    print("[CYCLE] ===== DEBATE ROUND 1 =====")
    print("[CYCLE] Querying AI-1 (Risk Manager)...")
    raw_1 = query_ai1(ctx_json, 1)
    print(f"[CYCLE] AI-1 raw: {raw_1[:300]}...")

    print("[CYCLE] Running AI-2 (Strategy Advisor) — membaca argumen AI-1...")
    raw_2 = query_ai2(ctx_json, 1)
    print(f"[CYCLE] AI-2 raw: {raw_2[:300]}...")

    if MAX_DEBATE_ROUNDS >= 2:
        increment_round()
        print(f"[CYCLE] ===== DEBATE ROUND 2 =====")
        print("[CYCLE] AI-1 menanggapi AI-2...")
        raw_1 = query_ai1(ctx_json, 2)
        print(f"[CYCLE] AI-1 rebuttal: {raw_1[:300]}...")

        print("[CYCLE] AI-2 menanggapi AI-1...")
        raw_2 = query_ai2(ctx_json, 2)
        print(f"[CYCLE] AI-2 rebuttal: {raw_2[:300]}...")

    print("[CYCLE] ===== DEBATE SELESAI =====")
    d1 = extract_final_action(raw_1) or {"action": "alert_only", "reason": "AI-1 failed to produce valid action"}
    d2 = extract_final_action(raw_2) or {"action": "alert_only", "reason": "AI-2 failed to produce valid action"}

    p1 = ACTION_PRIORITY.get(d1["action"], 0)
    p2 = ACTION_PRIORITY.get(d2["action"], 0)
    decision = d1 if p1 >= p2 else d2
    decision["_debate_log"] = get_conversation_summary()
    decision["_d1_raw"] = d1["action"]
    decision["_d2_raw"] = d2["action"]

    print(f"[CYCLE] Final: AI-1={d1['action']} vs AI-2={d2['action']} → picked {decision['action']}")

    print(f"[CYCLE] Executing decision: {json.dumps(decision, indent=2)}")
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
        "providers": provider_used,
        "consensus": decision.get("_consensus", "unknown"),
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
