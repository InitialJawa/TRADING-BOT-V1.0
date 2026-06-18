import json
import os
from datetime import datetime, timezone

CHAT_FILE = "data/agent_chat.json"

def init_chat(max_rounds=3):
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CHAT_FILE):
        data = {"messages": [], "round": 0, "max_rounds": max_rounds}
        save_chat(data)
        return data
    return load_chat()

def load_chat():
    with open(CHAT_FILE) as f:
        return json.load(f)

def save_chat(data):
    with open(CHAT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_message(sender, receiver, content, round_num):
    data = load_chat()
    data["messages"].append({
        "id": len(data["messages"]) + 1,
        "from": sender,
        "to": receiver,
        "content": content,
        "round": round_num,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    data["round"] = round_num
    save_chat(data)

def get_pending_for(agent_name, since_round=0):
    data = load_chat()
    return [m for m in data["messages"] if m["to"] == agent_name and m["round"] >= since_round]

def get_last_message(to_agent=None):
    data = load_chat()
    msgs = data["messages"]
    if not msgs:
        return None
    if to_agent:
        for m in reversed(msgs):
            if m["to"] == to_agent:
                return m
        return None
    return msgs[-1]

def get_conversation_summary():
    data = load_chat()
    return "\n".join(
        f"[R{m['round']}] {m['from']} → {m['to']}: {m['content'][:200]}"
        for m in data["messages"]
    )

def is_finished():
    data = load_chat()
    return data["round"] >= data["max_rounds"]

def increment_round():
    data = load_chat()
    data["round"] += 1
    save_chat(data)
    return data["round"]

def build_debate_context(agent_name, system_context):
    chat_summary = get_conversation_summary()
    last = get_last_message(agent_name)
    return f"""{json.dumps(system_context)}

=== DEBATE LOG ===
{chat_summary if chat_summary else "No prior messages."}

=== YOUR ROLE ===
You are {agent_name}.
"""
