import subprocess, json, os, sys, tempfile

MODEL = "google/gemini-2.5-flash"
TEMP_DIR = os.path.join(tempfile.gettempdir(), "oc_ai_mgr")
OPCODE_CMD = r"C:\Users\BedilGaib\AppData\Roaming\npm\opencode.cmd"

def query(system_prompt, user_context, timeout=30):
    prompt_one_line = f"Rules: {system_prompt} | Data: {user_context} | Reply ONLY JSON:"
    os.makedirs(TEMP_DIR, exist_ok=True)
    env = os.environ.copy()
    if "GEMINI_API_KEY" in env and "GOOGLE_GENERATIVE_AI_API_KEY" not in env:
        env["GOOGLE_GENERATIVE_AI_API_KEY"] = env["GEMINI_API_KEY"]
    try:
        result = subprocess.run(
            [OPCODE_CMD, "run", prompt_one_line, "-m", MODEL, "--pure"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=TEMP_DIR, env=env
        )
        out = result.stdout.strip()
        if not out:
            out = result.stderr.strip()
        return out
    except Exception as e:
        return json.dumps({"action": "alert_only", "reason": str(e)})


def parse_json_response(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        for i, l in enumerate(lines):
            if l.startswith("```"):
                raw = "\n".join(lines[i+1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
                break
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(raw[brace_start:brace_end+1])
            except:
                pass
        return {"action": "alert_only", "reason": f"Parse error: {raw[:200]}"}


if __name__ == "__main__":
    data = '{"strategy":"H4 EMA10/30 Cross","modal":12000000,"lot_pct":350,"dd_pct":0,"max_dd":9.9,"price":4332.9,"trend":"UP","signal":"HOLD"}'
    rules = "Allowed actions: reduce_lot, pause_strategy, alert_only. FORBIDDEN: buy/sell/close. If normal -> alert_only"
    result = query(rules, data)
    print(f"RESPONSE: {result.strip()}")
    parsed = parse_json_response(result)
    print(f"JSON: {json.dumps(parsed, indent=2)}")
