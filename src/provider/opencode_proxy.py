import json, requests, os, sys
from datetime import datetime

API_KEY = os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENCODE_API_KEY or OPENAI_API_KEY environment variable not set")
BASE_URL = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1/chat/completions")
MODEL = os.environ.get("OPENCODE_MODEL", "minimax-m2.5-free")

def query(system_prompt, user_context, timeout=30):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(BASE_URL, json=payload, headers=headers, timeout=timeout)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return text
    except Exception as e:
        return json.dumps({"error": str(e), "action": "alert_only", "reason": f"Opencode API error: {e}"})


# Test
if __name__ == "__main__":
    sys_prompt = "Kamu adalah AI Risk Manager. Balas HANYA dengan satu kata: OK"
    user_ctx = "test connection"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Testing OpenCode proxy API...")
    result = query(sys_prompt, user_ctx)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Response: {result}")
